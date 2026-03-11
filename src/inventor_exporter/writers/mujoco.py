"""MuJoCo MJCF format writer.

Generates .xml files compatible with MuJoCo 3.x physics engine.
MJCF (MuJoCo XML Format) is the native format for MuJoCo simulation.

Coordinate conventions:
    - Position: meters (same as IR, no conversion needed)
    - Rotation: quaternion (w, x, y, z) - scalar first (MuJoCo convention)
    - Inertia: kg*m^2 (same as IR, no conversion needed)
    - Mass: kg (same as IR, no conversion needed)

Key MJCF structure:
    - Rigid groups: parts connected by rigid joints are merged into a single
      <body> with multiple <geom> elements.
    - Kinematic tree: built via BFS spanning tree; closed loops handled with
      <equality> constraints (connect / weld).
    - Meshes: Referenced by name via <asset> definitions.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from lxml import etree

from inventor_exporter.core.rotation import rotation_to_quaternion
from inventor_exporter.model import AssemblyModel, Body, Material
from inventor_exporter.model.constraint import ConstraintInfo
from inventor_exporter.model.kinematic_tree import (
    KINEMATIC_JOINT_TYPES,
    KinematicTree,
    classify_joints,
    get_joint_origin_in_child_frame,
)
from inventor_exporter.model.transform import Transform
from inventor_exporter.writers.mesh_converter import MeshConverter
from inventor_exporter.writers.registry import WriterRegistry

logger = logging.getLogger(__name__)

# Tolerance for considering off-diagonal inertia terms as zero
INERTIA_ZERO_TOLERANCE = 1e-10

# Inventor joint type -> MuJoCo joint type
_MUJOCO_JOINT_TYPE = {
    "rotational_joint": "hinge",
    "slider_joint": "slide",
    "ball_joint": "ball",
    "cylindrical_joint": "hinge",
    "planar_joint": "slide",
}

# Small offset along axis for two-connect hinge constraints (meters)
_HINGE_OFFSET = 0.01


def _format_pos(position) -> str:
    """Format a position array as space-separated string."""
    return f"{position[0]} {position[1]} {position[2]}"


def _format_quat(rotation) -> str:
    """Format a rotation matrix as MuJoCo quaternion string (w x y z)."""
    q = rotation_to_quaternion(rotation, scalar_first=True)
    return f"{q[0]} {q[1]} {q[2]} {q[3]}"


@WriterRegistry.register("mujoco")
class MuJoCoWriter:
    """MuJoCo MJCF format writer.

    Generates .xml files for MuJoCo physics simulation.  Rigid groups
    (parts connected by rigid joints) are merged into single bodies.
    Closed kinematic loops are handled via <equality> constraints.

    Attributes:
        format_name: "mujoco"
        file_extension: ".xml"
    """

    format_name: str = "mujoco"
    file_extension: str = ".xml"

    def __init__(self, mesh_subdir: str = "meshes"):
        self._mesh_subdir = mesh_subdir

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        errors = model.validate()
        if errors:
            raise ValueError(
                "Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        output_dir = output_path.parent
        converter = MeshConverter(output_dir, mesh_subdir=self._mesh_subdir)

        mesh_names = self._convert_meshes(model, converter)
        root = self._build_mujoco_tree(model, mesh_names)

        tree = etree.ElementTree(root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )
        logger.info("Wrote MuJoCo MJCF to %s", output_path)

    # ------------------------------------------------------------------
    # Mesh conversion
    # ------------------------------------------------------------------

    def _convert_meshes(
        self, model: AssemblyModel, converter: MeshConverter
    ) -> dict[str, str]:
        mesh_names: dict[str, str] = {}
        for body in model.bodies:
            if body.geometry_file is not None:
                mesh_name = f"{body.name}_mesh"
                try:
                    converter.convert(body.geometry_file, mesh_name)
                    mesh_names[body.name] = mesh_name
                except Exception as e:
                    logger.warning("Failed to convert mesh for %s: %s", body.name, e)
        return mesh_names

    # ------------------------------------------------------------------
    # XML tree
    # ------------------------------------------------------------------

    def _build_mujoco_tree(
        self, model: AssemblyModel, mesh_names: dict[str, str]
    ) -> etree._Element:
        mujoco = etree.Element("mujoco", model=model.name)

        etree.SubElement(mujoco, "compiler", meshdir=self._mesh_subdir)

        etree.SubElement(
            mujoco, "option",
            gravity="0 0 -9.81", integrator="implicitfast",
        )

        # Scale joint defaults to mechanism mass — light mechanisms need
        # low damping (velocity-dependent force overwhelms tiny inertias)
        # and higher friction (constant drag prevents velocity runaway).
        damping, frictionloss = self._compute_joint_defaults(model)

        default = etree.SubElement(mujoco, "default")
        etree.SubElement(default, "geom", contype="0", conaffinity="0")
        etree.SubElement(
            default, "joint", damping=damping, frictionloss=frictionloss,
        )

        # Assets
        asset = etree.SubElement(mujoco, "asset")
        self._add_mesh_assets(asset, mesh_names)
        self._add_material_assets(asset, model.materials)

        # Constraint / joint metadata as comments
        if model.constraints:
            self._add_constraint_comments(mujoco, model)

        # Build kinematic tree with loop detection (rigid-group-aware)
        groups = model.rigid_groups()
        ktree = classify_joints(
            [b.name for b in model.bodies],
            model.constraints,
            ground=model.ground_body,
            rigid_groups=groups,
        )

        worldbody = etree.SubElement(mujoco, "worldbody")
        emitted: set[str] = set()

        # Add root bodies (not a child in any joint) and recurse
        for body in model.bodies:
            if body.name in emitted or body.name in ktree.parent_of:
                continue
            self._add_body_recursive(
                worldbody, body, None, None, False,
                model, mesh_names, ktree, groups, emitted,
            )

        # Equality constraints for closed-loop cut joints
        if ktree.cut_joints:
            self._add_equality_constraints(mujoco, ktree, model, groups)

        return mujoco

    # ------------------------------------------------------------------
    # Constraint comments
    # ------------------------------------------------------------------

    def _add_constraint_comments(
        self, parent: etree._Element, model: AssemblyModel
    ) -> None:
        lines = [" Assembly constraints and joints:"]
        for c in model.constraints:
            parts = [f"  {c.type}: {c.occurrence_one} <-> {c.occurrence_two}"]
            if c.name:
                parts.append(f"name={c.name}")
            if c.offset is not None:
                parts.append(f"offset={c.offset:.4f}m")
            if c.angle is not None:
                parts.append(f"angle={c.angle:.4f}rad")
            if c.axis is not None:
                parts.append(f"axis=({c.axis[0]:.3f},{c.axis[1]:.3f},{c.axis[2]:.3f})")
            if c.origin is not None:
                parts.append(
                    f"origin=({c.origin[0]:.4f},{c.origin[1]:.4f},{c.origin[2]:.4f})m"
                )
            if c.limits is not None:
                parts.append(f"limits=({c.limits[0]:.4f},{c.limits[1]:.4f})")
            if c.is_rigid:
                parts.append("[RIGID]")
            lines.append(", ".join(parts))
        lines.append("")
        parent.append(etree.Comment("\n".join(lines)))

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    def _add_mesh_assets(
        self, asset: etree._Element, mesh_names: dict[str, str]
    ) -> None:
        mm_to_m = "0.001 0.001 0.001"
        for body_name, mesh_name in mesh_names.items():
            etree.SubElement(
                asset, "mesh",
                name=mesh_name, file=f"{mesh_name}.stl", scale=mm_to_m,
            )

    def _add_material_assets(
        self, asset: etree._Element, materials: tuple[Material, ...]
    ) -> None:
        for material in materials:
            etree.SubElement(
                asset, "material", name=material.name, rgba="0.7 0.7 0.7 1",
            )

    # ------------------------------------------------------------------
    # Recursive body builder
    # ------------------------------------------------------------------

    def _add_body_recursive(
        self,
        parent_elem: etree._Element,
        body: Body,
        parent_body: Optional[Body],
        joint_info: Optional[ConstraintInfo],
        is_flipped: bool,
        model: AssemblyModel,
        mesh_names: dict[str, str],
        ktree: KinematicTree,
        groups: dict[str, list[str]],
        emitted: set[str],
    ) -> None:
        """Add a body and recursively nest its children."""
        if body.name in emitted:
            return

        # Compute transform: relative to parent if nested, else world
        if parent_body is not None:
            rel = body.transform.relative_to(parent_body.transform)
            pos_str = _format_pos(rel.position)
            quat_str = _format_quat(rel.rotation)
        else:
            pos_str = _format_pos(body.transform.position)
            quat_str = _format_quat(body.transform.rotation)

        # Resolve joint origin for flipped joints
        origin_override = None
        if joint_info is not None and is_flipped and parent_body is not None:
            origin_override = get_joint_origin_in_child_frame(
                joint_info,
                body.name,
                flipped=True,
                child_rotation=body.transform.rotation,
                parent_rotation=parent_body.transform.rotation,
                child_position=body.transform.position,
                parent_position=parent_body.transform.position,
            )

        # Check for rigid group membership
        group_members = None
        for _rep, members in groups.items():
            if body.name in members and len(members) > 1:
                group_members = members
                break

        if group_members:
            body_elem = self._make_rigid_group(
                parent_elem, group_members, model, mesh_names,
                pos_str, quat_str, joint_info, body.transform,
                origin_override=origin_override,
            )
            emitted.update(group_members)
        else:
            body_elem = etree.SubElement(
                parent_elem, "body",
                name=body.name, pos=pos_str, quat=quat_str,
            )
            if joint_info is not None:
                self._add_joint_elem(
                    body_elem, joint_info, body.transform,
                    origin_override=origin_override,
                )
            if body.inertia is not None:
                self._add_inertial(body_elem, body)
            mesh_name = mesh_names.get(body.name)
            if mesh_name is not None:
                attribs: dict[str, str] = {"type": "mesh", "mesh": mesh_name}
                if body.material_name is not None:
                    attribs["material"] = body.material_name
                etree.SubElement(body_elem, "geom", **attribs)
            emitted.add(body.name)

        # Recurse into children.
        # For rigid groups, the spanning tree keys children under the
        # group representative, so check all group members for children.
        child_lookup_names = [body.name]
        if group_members:
            child_lookup_names = list(group_members)
        for lookup_name in child_lookup_names:
            for child_name in ktree.children_of.get(lookup_name, []):
                if child_name in emitted:
                    continue
                child_body = model.get_body(child_name)
                if child_body is not None:
                    child_flipped = child_name in ktree.flipped
                    self._add_body_recursive(
                        body_elem, child_body, body,
                        ktree.joint_for.get(child_name),
                        child_flipped,
                        model, mesh_names, ktree, groups, emitted,
                    )

    # ------------------------------------------------------------------
    # Joint element
    # ------------------------------------------------------------------

    def _add_joint_elem(
        self,
        body_elem: etree._Element,
        constraint: ConstraintInfo,
        body_transform: Optional[Transform] = None,
        origin_override: Optional[tuple[float, float, float]] = None,
    ) -> None:
        """Add a MuJoCo <joint> element from constraint info.

        Joint axis and origin are transformed from world frame into the
        child body's local frame so that MuJoCo interprets them correctly.
        """
        mj_type = _MUJOCO_JOINT_TYPE.get(constraint.type, "hinge")
        attribs: dict[str, str] = {
            "name": constraint.name.replace(":", "_"),
            "type": mj_type,
        }
        if body_transform is not None:
            R_inv = body_transform.rotation.T

            if constraint.axis is not None:
                axis_world = np.array(constraint.axis)
                axis_local = R_inv @ axis_world
                attribs["axis"] = _format_pos(axis_local)
                logger.debug(
                    "Joint %s axis: world=(%s) -> local=(%s)",
                    constraint.name,
                    _format_pos(axis_world),
                    _format_pos(axis_local),
                )
            elif mj_type == "hinge":
                # No axis extracted — default to world-Z transformed to body-local.
                # This is correct for planar mechanisms (most common case).
                axis_local = R_inv @ np.array([0.0, 0.0, 1.0])
                attribs["axis"] = _format_pos(axis_local)
                logger.info(
                    "Joint %s: no axis extracted, defaulting to world-Z -> local=(%s)",
                    constraint.name,
                    _format_pos(axis_local),
                )

            origin = origin_override if origin_override is not None else constraint.origin
            if origin is not None:
                # Origin is in the child body's local (part) frame — use directly.
                attribs["pos"] = (
                    f"{origin[0]} {origin[1]} {origin[2]}"
                )
        else:
            if constraint.axis is not None:
                attribs["axis"] = (
                    f"{constraint.axis[0]} {constraint.axis[1]} {constraint.axis[2]}"
                )
        if constraint.limits is not None:
            attribs["limited"] = "true"
            attribs["range"] = f"{constraint.limits[0]} {constraint.limits[1]}"
        etree.SubElement(body_elem, "joint", **attribs)

    # ------------------------------------------------------------------
    # Equality constraints (closed-loop cut joints)
    # ------------------------------------------------------------------

    def _add_equality_constraints(
        self,
        mujoco: etree._Element,
        ktree: KinematicTree,
        model: AssemblyModel,
        groups: dict[str, list[str]],
    ) -> None:
        """Add <equality> section for loop-closing cut joints.

        Revolute cut joints use two <connect> constraints offset along
        the axis to create a hinge outside the kinematic tree.
        Other types use a single <connect> (ball joint approximation).

        Body names are resolved through rigid groups: if a body was
        merged into a rigid group, the group's XML element name is used.
        """
        # Build body name -> MuJoCo XML body name mapping for rigid groups
        body_to_xml: dict[str, str] = {}
        for rep, members in groups.items():
            if len(members) > 1:
                xml_name = "_".join(members[:2]) + "_group"
                for m in members:
                    body_to_xml[m] = xml_name
            else:
                body_to_xml[rep] = rep

        def resolve_body(name: str) -> str:
            return body_to_xml.get(name, name)

        equality = etree.SubElement(mujoco, "equality")
        equality.append(etree.Comment(
            " Loop-closing constraints for closed kinematic chains "
        ))

        for i, cj in enumerate(ktree.cut_joints):
            body1_raw = cj.occurrence_one.replace(":", "_").replace(" ", "_")
            body2_raw = cj.occurrence_two.replace(":", "_").replace(" ", "_")
            joint_name = cj.name.replace(":", "_") if cj.name else f"loop_{i}"

            # Resolve through rigid groups for MuJoCo XML body references
            body1 = resolve_body(body1_raw)
            body2 = resolve_body(body2_raw)

            if body1 == body2:
                logger.debug(
                    "Cut joint '%s': both bodies in same rigid group, skipping",
                    joint_name,
                )
                continue

            # Get the actual Body objects (use raw name, not group name)
            b1 = model.get_body(body1_raw)
            b2 = model.get_body(body2_raw)
            if b1 is None or b2 is None:
                logger.warning(
                    "Cut joint '%s': body not found (%s or %s), skipping",
                    joint_name, body1_raw, body2_raw,
                )
                continue

            if cj.origin is None:
                # For mate/flush loop closures: add virtual coupler bodies.
                # MuJoCo connect pins anchor (in body1) to body2's ORIGIN.
                # Since neither body's origin is at the coupler, we add
                # lightweight virtual bodies at the estimated coupler point
                # on each arm, then connect those (like the end_effector
                # pattern in standard MuJoCo 5-bar models).
                self._add_virtual_coupler_connect(
                    mujoco, equality, joint_name,
                    b1, b2, body1, body2, ktree,
                )
                continue

            # Anchor in body1's frame (origin is from OccurrenceOne's frame)
            anchor = cj.origin
            anchor_str = f"{anchor[0]} {anchor[1]} {anchor[2]}"

            if cj.type == "rotational_joint" and cj.axis is not None:
                # Two connect constraints = hinge outside kinematic tree
                axis_world = np.array(cj.axis)
                axis_local = b1.transform.rotation.T @ axis_world
                norm = np.linalg.norm(axis_local)
                if norm > 1e-12:
                    axis_local = axis_local / norm

                anchor2 = (
                    anchor[0] + _HINGE_OFFSET * axis_local[0],
                    anchor[1] + _HINGE_OFFSET * axis_local[1],
                    anchor[2] + _HINGE_OFFSET * axis_local[2],
                )
                anchor2_str = f"{anchor2[0]} {anchor2[1]} {anchor2[2]}"

                etree.SubElement(
                    equality, "connect",
                    name=f"{joint_name}_a",
                    body1=body1, body2=body2,
                    anchor=anchor_str,
                )
                etree.SubElement(
                    equality, "connect",
                    name=f"{joint_name}_b",
                    body1=body1, body2=body2,
                    anchor=anchor2_str,
                )
            else:
                # Single connect (ball joint approximation)
                etree.SubElement(
                    equality, "connect",
                    name=joint_name,
                    body1=body1, body2=body2,
                    anchor=anchor_str,
                )

    # ------------------------------------------------------------------
    # Virtual coupler bodies for loop closure
    # ------------------------------------------------------------------

    def _add_virtual_coupler_connect(
        self,
        mujoco: etree._Element,
        equality: etree._Element,
        joint_name: str,
        b1: Body, b2: Body,
        body1_xml: str, body2_xml: str,
        ktree: KinematicTree,
    ) -> None:
        """Add virtual coupler bodies and connect constraint for a mate loop.

        Estimates the coupler point (where both arms meet) using
        ``2*CoM - pivot`` on one arm, then places lightweight virtual
        bodies at that point on each arm.  The connect constraint between
        the virtual bodies uses ``anchor="0 0 0"`` — the standard MuJoCo
        pattern for closed kinematic chains (cf. end_effector in 5-bar
        examples).
        """
        # Estimate coupler in b2's local frame: reflect pivot through CoM
        coupler_in_b2 = self._estimate_coupler_local(b2, ktree)
        if coupler_in_b2 is None:
            # Fallback: try b1 instead
            coupler_in_b1 = self._estimate_coupler_local(b1, ktree)
            if coupler_in_b1 is None:
                logger.warning(
                    "Cut joint '%s': cannot estimate coupler — "
                    "using connect at body origins, adjust manually",
                    joint_name,
                )
                etree.SubElement(
                    equality, "connect", name=joint_name,
                    body1=body1_xml, body2=body2_xml, anchor="0 0 0",
                )
                return
            # Compute b2's coupler from b1's world position
            coupler_world = (b1.transform.rotation @ np.array(coupler_in_b1)
                             + b1.transform.position)
            coupler_in_b2 = tuple(
                b2.transform.rotation.T @ (coupler_world - b2.transform.position)
            )
        else:
            # Compute b1's coupler from b2's world position
            coupler_world = (b2.transform.rotation @ np.array(coupler_in_b2)
                             + b2.transform.position)
            coupler_in_b1 = tuple(
                b1.transform.rotation.T @ (coupler_world - b1.transform.position)
            )

        logger.info(
            "Loop '%s': coupler_in_%s=%s, coupler_in_%s=%s",
            joint_name, body1_xml, coupler_in_b1, body2_xml, coupler_in_b2,
        )

        # Find the body elements in the XML tree and add virtual children
        b1_elem = mujoco.find(f".//body[@name='{body1_xml}']")
        b2_elem = mujoco.find(f".//body[@name='{body2_xml}']")
        if b1_elem is None or b2_elem is None:
            logger.warning("Could not find body elements for virtual couplers")
            etree.SubElement(
                equality, "connect", name=joint_name,
                body1=body1_xml, body2=body2_xml, anchor="0 0 0",
            )
            return

        coupler_a = f"{joint_name}_coupler_a"
        coupler_b = f"{joint_name}_coupler_b"

        vc1 = etree.SubElement(
            b1_elem, "body", name=coupler_a,
            pos=_format_pos(coupler_in_b1),
        )
        etree.SubElement(
            vc1, "inertial", pos="0 0 0", mass="0.0001",
            diaginertia="1e-9 1e-9 1e-9",
        )

        vc2 = etree.SubElement(
            b2_elem, "body", name=coupler_b,
            pos=_format_pos(coupler_in_b2),
        )
        etree.SubElement(
            vc2, "inertial", pos="0 0 0", mass="0.0001",
            diaginertia="1e-9 1e-9 1e-9",
        )

        etree.SubElement(
            equality, "connect", name=joint_name,
            body1=coupler_a, body2=coupler_b, anchor="0 0 0",
        )

    @staticmethod
    def _estimate_coupler_local(
        body: Body, ktree: KinematicTree,
    ) -> "tuple[float, float, float] | None":
        """Estimate the coupler end of an arm in its local frame.

        Uses ``2*CoM - pivot`` — reflects the pivot (joint) through the
        center of mass to approximate the far end of the arm.
        """
        joint_info = ktree.joint_for.get(body.name)
        if joint_info is None or body.inertia is None:
            return None

        is_flipped = body.name in ktree.flipped

        # Get pivot in the body's LOCAL frame (not the parent's frame)
        pivot = None
        if is_flipped:
            # Flipped: occurrence_one is parent, occurrence_two is child (this body).
            # origin_two is in OccurrenceTwo's frame = this body's frame.
            if joint_info.origin_two is not None:
                pivot = np.array(joint_info.origin_two)
            # IMPORTANT: do NOT fall back to joint_info.origin here — it's
            # in the parent's frame, which would produce a wrong estimate.
        else:
            # Normal: occurrence_one is child (this body).
            # origin is in OccurrenceOne's frame = this body's frame.
            if joint_info.origin is not None:
                pivot = np.array(joint_info.origin)

        if pivot is None:
            logger.warning(
                "Cannot estimate coupler for '%s': no origin in body's local frame",
                body.name,
            )
            return None

        com = np.array(body.inertia.center_of_mass)
        coupler = 2.0 * com - pivot
        return tuple(coupler)

    # ------------------------------------------------------------------
    # Rigid group (multiple parts merged into one body)
    # ------------------------------------------------------------------

    def _make_rigid_group(
        self,
        parent_elem: etree._Element,
        member_names: list[str],
        model: AssemblyModel,
        mesh_names: dict[str, str],
        pos_str: str,
        quat_str: str,
        joint_info: Optional[ConstraintInfo],
        body_transform: Optional[Transform] = None,
        origin_override: Optional[tuple[float, float, float]] = None,
    ) -> etree._Element:
        """Create a merged body element for a rigid group. Returns the element."""
        primary = model.get_body(member_names[0])
        group_name = "_".join(member_names[:2]) + "_group"

        body_elem = etree.SubElement(
            parent_elem, "body",
            name=group_name, pos=pos_str, quat=quat_str,
        )
        body_elem.append(
            etree.Comment(f" Rigid group: {', '.join(member_names)} ")
        )

        if joint_info is not None:
            self._add_joint_elem(
                body_elem, joint_info, body_transform,
                origin_override=origin_override,
            )

        # Combined mass (simplified: sum of masses, primary CoM)
        total_mass = 0.0
        for bname in member_names:
            b = model.get_body(bname)
            if b is not None and b.inertia is not None:
                total_mass += b.inertia.mass

        if total_mass > 0 and primary is not None and primary.inertia is not None:
            com = primary.inertia.center_of_mass
            etree.SubElement(
                body_elem, "inertial",
                pos=_format_pos(com), mass=str(total_mass),
            )

        # Geoms — each member with pose relative to primary
        for bname in member_names:
            b = model.get_body(bname)
            if b is None:
                continue
            mname = mesh_names.get(bname)
            if mname is None:
                continue
            attribs: dict[str, str] = {"type": "mesh", "mesh": mname}
            if b.material_name is not None:
                attribs["material"] = b.material_name
            if primary is not None and bname != primary.name:
                rel = b.transform.relative_to(primary.transform)
                attribs["pos"] = _format_pos(rel.position)
                attribs["quat"] = _format_quat(rel.rotation)
            etree.SubElement(body_elem, "geom", **attribs)

        return body_elem

    # ------------------------------------------------------------------
    # Joint default scaling
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_joint_defaults(model: AssemblyModel) -> tuple[str, str]:
        """Compute damping and frictionloss scaled to mechanism mass.

        Reference point: at m_char=0.1 kg, damping=0.005, frictionloss=0.005.
        Damping scales linearly with mass (velocity-dependent force must not
        overwhelm small inertias).  Friction loss scales inversely with
        mass^0.7 (constant drag prevents velocity runaway on light parts).
        """
        _M_REF = 0.1  # reference mass (kg)
        _DAMP_REF = 0.005
        _FRIC_REF = 0.005

        masses = [
            b.inertia.mass
            for b in model.bodies
            if b.inertia is not None and b.inertia.mass > 0
        ]
        if not masses:
            return str(_DAMP_REF), str(_FRIC_REF)

        masses.sort()
        m_char = masses[len(masses) // 2]  # median

        damping = _DAMP_REF * (m_char / _M_REF)
        damping = max(1e-5, min(damping, 0.1))

        frictionloss = _FRIC_REF * (_M_REF / m_char) ** 0.7
        frictionloss = max(0.001, min(frictionloss, 1.0))

        logger.info(
            "Joint defaults: m_char=%.4f kg -> damping=%.6f, frictionloss=%.6f",
            m_char, damping, frictionloss,
        )
        return f"{damping:.6g}", f"{frictionloss:.6g}"

    # ------------------------------------------------------------------
    # Inertial
    # ------------------------------------------------------------------

    def _add_inertial(self, body_elem: etree._Element, body: Body) -> None:
        inertia = body.inertia
        if inertia is None:
            return

        com = inertia.center_of_mass
        pos_str = _format_pos(com)

        inertial_attribs: dict[str, str] = {
            "pos": pos_str,
            "mass": str(inertia.mass),
        }

        I = inertia.inertia_tensor
        ixy, ixz, iyz = I[0, 1], I[0, 2], I[1, 2]

        if (
            abs(ixy) < INERTIA_ZERO_TOLERANCE
            and abs(ixz) < INERTIA_ZERO_TOLERANCE
            and abs(iyz) < INERTIA_ZERO_TOLERANCE
        ):
            ixx, iyy, izz = I[0, 0], I[1, 1], I[2, 2]
            inertial_attribs["diaginertia"] = f"{ixx} {iyy} {izz}"
        else:
            ixx, iyy, izz = I[0, 0], I[1, 1], I[2, 2]
            inertial_attribs["fullinertia"] = f"{ixx} {iyy} {izz} {ixy} {ixz} {iyz}"

        etree.SubElement(body_elem, "inertial", **inertial_attribs)
