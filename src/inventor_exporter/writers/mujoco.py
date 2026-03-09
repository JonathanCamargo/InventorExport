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

        # Disable contacts by default (adjacent bodies share joint boundaries)
        default = etree.SubElement(mujoco, "default")
        etree.SubElement(default, "geom", contype="0", conaffinity="0")

        # Assets
        asset = etree.SubElement(mujoco, "asset")
        self._add_mesh_assets(asset, mesh_names)
        self._add_material_assets(asset, model.materials)

        # Constraint / joint metadata as comments
        if model.constraints:
            self._add_constraint_comments(mujoco, model)

        # Build kinematic tree with loop detection
        ktree = classify_joints(
            [b.name for b in model.bodies],
            model.constraints,
            ground=model.ground_body,
        )
        groups = model.rigid_groups()

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
            self._add_equality_constraints(mujoco, ktree, model)

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

        # Recurse into children
        for child_name in ktree.children_of.get(body.name, []):
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
    ) -> None:
        """Add <equality> section for loop-closing cut joints.

        Revolute cut joints use two <connect> constraints offset along
        the axis to create a hinge outside the kinematic tree.
        Other types use a single <connect> (ball joint approximation).
        """
        equality = etree.SubElement(mujoco, "equality")
        equality.append(etree.Comment(
            " Loop-closing constraints for closed kinematic chains "
        ))

        for i, cj in enumerate(ktree.cut_joints):
            body1 = cj.occurrence_one.replace(":", "_").replace(" ", "_")
            body2 = cj.occurrence_two.replace(":", "_").replace(" ", "_")
            joint_name = cj.name.replace(":", "_") if cj.name else f"loop_{i}"

            # Verify both bodies exist
            b1 = model.get_body(body1)
            b2 = model.get_body(body2)
            if b1 is None or b2 is None:
                logger.warning(
                    "Cut joint '%s': body not found (%s or %s), skipping",
                    joint_name, body1, body2,
                )
                continue

            if cj.origin is None:
                logger.warning(
                    "Cut joint '%s': no origin, using weld constraint",
                    joint_name,
                )
                etree.SubElement(
                    equality, "weld",
                    name=joint_name,
                    body1=body1,
                    body2=body2,
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
