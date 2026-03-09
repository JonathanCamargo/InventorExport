"""SDF (Simulation Description Format) writer for Gazebo.

Generates SDF 1.8 XML files compatible with Gazebo simulator.

Coordinate conventions:
    - Position: meters (same as IR)
    - Rotation: RPY angles in radians
    - Mesh files: STL, referenced via URI elements

Structure:
    - Rigid groups: merged into single links with multiple visuals.
    - Constraint/joint metadata emitted as XML comments.
"""

import logging
from pathlib import Path

from lxml import etree

from inventor_exporter.core.rotation import EulerConvention, rotation_to_euler
from inventor_exporter.model import AssemblyModel, Body
from inventor_exporter.writers.mesh_converter import MeshConverter
from inventor_exporter.writers.registry import WriterRegistry

logger = logging.getLogger(__name__)


def _format_pose(position, rotation) -> str:
    rpy = rotation_to_euler(rotation, EulerConvention.URDF_RPY, degrees=False)
    return (
        f"{position[0]} {position[1]} {position[2]} "
        f"{rpy[0]} {rpy[1]} {rpy[2]}"
    )


@WriterRegistry.register("sdf")
class SDFWriter:
    """SDF format writer with rigid-group merging and constraint metadata."""

    format_name: str = "sdf"
    file_extension: str = ".sdf"

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        errors = model.validate()
        if errors:
            raise ValueError(
                "Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        output_dir = output_path.parent
        mesh_converter = MeshConverter(output_dir, mesh_subdir="meshes")
        self._convert_meshes(model, mesh_converter)

        root = self._build_sdf_tree(model, mesh_converter)

        tree = etree.ElementTree(root)
        tree.write(
            str(output_path),
            pretty_print=True,
            xml_declaration=True,
            encoding="utf-8",
        )
        logger.info("Wrote SDF file: %s", output_path)

    def _convert_meshes(
        self, model: AssemblyModel, converter: MeshConverter
    ) -> None:
        for body in model.bodies:
            if body.geometry_file and body.geometry_file.exists():
                try:
                    converter.convert(body.geometry_file, body.name)
                except Exception as e:
                    logger.warning("Failed to convert mesh for %s: %s", body.name, e)

    def _build_sdf_tree(
        self, model: AssemblyModel, mesh_converter: MeshConverter
    ) -> etree._Element:
        sdf = etree.Element("sdf", version="1.8")
        model_elem = etree.SubElement(sdf, "model", name=model.name)

        # Constraint / joint metadata
        if model.constraints:
            self._add_constraint_comments(model_elem, model)

        # Base link
        etree.SubElement(model_elem, "link", name="base_link")

        # Links and joints — rigid-group aware
        groups = model.rigid_groups()
        emitted: set[str] = set()
        link_names: list[tuple[str, Body]] = []

        for rep, members in groups.items():
            if len(members) == 1:
                body = model.get_body(members[0])
                if body is not None:
                    self._add_link(model_elem, body, mesh_converter)
                    link_names.append((body.name, body))
            else:
                name, primary = self._add_rigid_group_link(
                    model_elem, members, model, mesh_converter
                )
                if primary is not None:
                    link_names.append((name, primary))
            emitted.update(members)

        for body in model.bodies:
            if body.name not in emitted:
                self._add_link(model_elem, body, mesh_converter)
                link_names.append((body.name, body))

        # Fixed joints
        for lname, primary in link_names:
            self._add_joint(model_elem, lname)

        return sdf

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
            if c.axis is not None:
                parts.append(f"axis=({c.axis[0]:.3f},{c.axis[1]:.3f},{c.axis[2]:.3f})")
            if c.origin is not None:
                parts.append(
                    f"origin=({c.origin[0]:.4f},{c.origin[1]:.4f},{c.origin[2]:.4f})m"
                )
            if c.is_rigid:
                parts.append("[RIGID]")
            lines.append(", ".join(parts))
        lines.append("")
        parent.append(etree.Comment("\n".join(lines)))

    # ------------------------------------------------------------------
    # Single link
    # ------------------------------------------------------------------

    def _add_link(
        self,
        parent: etree._Element,
        body: Body,
        mesh_converter: MeshConverter,
    ) -> None:
        link = etree.SubElement(parent, "link", name=body.name)

        pose = etree.SubElement(link, "pose", relative_to="base_link")
        pose.text = _format_pose(body.transform.position, body.transform.rotation)

        if body.inertia is not None:
            self._add_inertial(link, body)

        if body.geometry_file is not None:
            mesh_path = mesh_converter.get_mesh_path(body.name)
            self._add_visual(link, mesh_path)
            self._add_collision(link, mesh_path)

    # ------------------------------------------------------------------
    # Rigid group link
    # ------------------------------------------------------------------

    def _add_rigid_group_link(
        self,
        parent: etree._Element,
        member_names: list[str],
        model: AssemblyModel,
        mesh_converter: MeshConverter,
    ) -> "tuple[str, Body | None]":
        primary = model.get_body(member_names[0])
        if primary is None:
            return member_names[0], None

        group_name = "_".join(member_names[:2]) + "_group"
        link = etree.SubElement(parent, "link", name=group_name)
        link.append(etree.Comment(f" Rigid group: {', '.join(member_names)} "))

        pose = etree.SubElement(link, "pose", relative_to="base_link")
        pose.text = _format_pose(
            primary.transform.position, primary.transform.rotation
        )

        # Simplified inertial
        total_mass = 0.0
        for bname in member_names:
            b = model.get_body(bname)
            if b is not None and b.inertia is not None:
                total_mass += b.inertia.mass

        if total_mass > 0:
            inertial = etree.SubElement(link, "inertial")
            mass_el = etree.SubElement(inertial, "mass")
            mass_el.text = f"{total_mass:.6g}"

        # Visual + collision per member
        for bname in member_names:
            b = model.get_body(bname)
            if b is None or b.geometry_file is None:
                continue

            mesh_path = mesh_converter.get_mesh_path(bname)
            rel = b.transform.relative_to(primary.transform)

            # Visual
            visual = etree.SubElement(link, "visual", name=f"{bname}_visual")
            vpose = etree.SubElement(visual, "pose")
            vpose.text = _format_pose(rel.position, rel.rotation)
            geom = etree.SubElement(visual, "geometry")
            mesh = etree.SubElement(geom, "mesh")
            uri = etree.SubElement(mesh, "uri")
            uri.text = str(mesh_path).replace("\\", "/")
            scale = etree.SubElement(mesh, "scale")
            scale.text = "0.001 0.001 0.001"

            # Collision
            collision = etree.SubElement(link, "collision", name=f"{bname}_collision")
            cpose = etree.SubElement(collision, "pose")
            cpose.text = _format_pose(rel.position, rel.rotation)
            geom = etree.SubElement(collision, "geometry")
            mesh = etree.SubElement(geom, "mesh")
            uri = etree.SubElement(mesh, "uri")
            uri.text = str(mesh_path).replace("\\", "/")
            scale = etree.SubElement(mesh, "scale")
            scale.text = "0.001 0.001 0.001"

        return group_name, primary

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_inertial(self, link: etree._Element, body: Body) -> None:
        inertia = body.inertia
        inertial = etree.SubElement(link, "inertial")

        mass_el = etree.SubElement(inertial, "mass")
        mass_el.text = str(inertia.mass)

        I = inertia.inertia_tensor
        inertia_elem = etree.SubElement(inertial, "inertia")
        for tag, val in [
            ("ixx", I[0, 0]), ("ixy", I[0, 1]), ("ixz", I[0, 2]),
            ("iyy", I[1, 1]), ("iyz", I[1, 2]), ("izz", I[2, 2]),
        ]:
            el = etree.SubElement(inertia_elem, tag)
            el.text = str(val)

    def _add_visual(
        self, link: etree._Element, mesh_path: Path
    ) -> None:
        visual = etree.SubElement(link, "visual", name="visual")
        geometry = etree.SubElement(visual, "geometry")
        mesh = etree.SubElement(geometry, "mesh")
        uri = etree.SubElement(mesh, "uri")
        uri.text = str(mesh_path).replace("\\", "/")
        scale = etree.SubElement(mesh, "scale")
        scale.text = "0.001 0.001 0.001"

    def _add_collision(
        self, link: etree._Element, mesh_path: Path
    ) -> None:
        collision = etree.SubElement(link, "collision", name="collision")
        geometry = etree.SubElement(collision, "geometry")
        mesh = etree.SubElement(geometry, "mesh")
        uri = etree.SubElement(mesh, "uri")
        uri.text = str(mesh_path).replace("\\", "/")
        scale = etree.SubElement(mesh, "scale")
        scale.text = "0.001 0.001 0.001"

    def _add_joint(self, parent: etree._Element, link_name: str) -> None:
        joint = etree.SubElement(
            parent, "joint", name=f"{link_name}_joint", type="fixed"
        )
        parent_link = etree.SubElement(joint, "parent")
        parent_link.text = "base_link"
        child_link = etree.SubElement(joint, "child")
        child_link.text = link_name
