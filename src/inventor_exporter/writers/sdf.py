"""SDF (Simulation Description Format) writer for Gazebo.

Generates SDF 1.8 XML files compatible with Gazebo simulator.
SDF is the native format for Gazebo and extends URDF capabilities.

Coordinate conventions:
    - Position: meters (same as IR, no conversion needed)
    - Rotation: RPY angles in radians (roll-pitch-yaw, same as URDF)
    - Mesh files: STL, referenced via URI elements

Output structure:
    1. SDF root element with version="1.8"
    2. Model element containing all links and joints
    3. Virtual base_link at world origin
    4. Physical links with pose, inertial, visual, collision
    5. Fixed joints connecting each link to base_link

Key differences from URDF:
    - Root element is <sdf version="1.8"> containing <model>
    - Pose uses single <pose> element with 6 space-separated values
    - Inertia elements are nested separately, not as attributes
    - Mesh uses <uri> child element instead of filename attribute
    - Visual/collision have name attribute
"""

import logging
from pathlib import Path

from lxml import etree

from inventor_exporter.core.rotation import EulerConvention, rotation_to_euler
from inventor_exporter.model import AssemblyModel, Body
from inventor_exporter.writers.mesh_converter import MeshConverter
from inventor_exporter.writers.registry import WriterRegistry

logger = logging.getLogger(__name__)


@WriterRegistry.register("sdf")
class SDFWriter:
    """SDF format writer for Gazebo simulation.

    Generates SDF 1.8 XML files with proper model structure,
    mesh references, and inertial properties.

    Attributes:
        format_name: "sdf"
        file_extension: ".sdf"
    """

    format_name: str = "sdf"
    file_extension: str = ".sdf"

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write assembly model to SDF file.

        Creates:
            - {output_path}: SDF XML file
            - {output_path.parent}/meshes/: Directory with STL mesh files

        Args:
            model: AssemblyModel to export.
            output_path: Destination .sdf file path.

        Raises:
            ValueError: If model validation fails.
        """
        errors = model.validate()
        if errors:
            raise ValueError(
                "Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Set up mesh converter for STEP -> STL conversion
        output_dir = output_path.parent
        mesh_converter = MeshConverter(output_dir, mesh_subdir="meshes")

        # Convert meshes for bodies with geometry
        self._convert_meshes(model, mesh_converter)

        # Build XML tree
        root = self._build_sdf_tree(model, mesh_converter)

        # Write with pretty printing
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
        """Convert STEP geometry files to STL meshes.

        Args:
            model: AssemblyModel containing bodies with geometry.
            converter: MeshConverter instance for conversion.
        """
        for body in model.bodies:
            if body.geometry_file and body.geometry_file.exists():
                try:
                    converter.convert(body.geometry_file, body.name)
                    logger.debug("Converted mesh for %s", body.name)
                except Exception as e:
                    logger.warning(
                        "Failed to convert mesh for %s: %s", body.name, e
                    )

    def _build_sdf_tree(
        self, model: AssemblyModel, mesh_converter: MeshConverter
    ) -> etree._Element:
        """Build complete SDF XML tree.

        Args:
            model: AssemblyModel to convert.
            mesh_converter: MeshConverter for mesh path lookup.

        Returns:
            Root <sdf> element.
        """
        # Root SDF element with version
        sdf = etree.Element("sdf", version="1.8")

        # Model element
        model_elem = etree.SubElement(sdf, "model", name=model.name)

        # Virtual base_link at world origin (no geometry)
        etree.SubElement(model_elem, "link", name="base_link")

        # Add each body as a link with fixed joint
        for body in model.bodies:
            self._add_link(model_elem, body, mesh_converter)
            self._add_joint(model_elem, body)

        return sdf

    def _add_link(
        self,
        parent: etree._Element,
        body: Body,
        mesh_converter: MeshConverter,
    ) -> None:
        """Add link element for a body.

        Args:
            parent: Parent model element.
            body: Body to add.
            mesh_converter: MeshConverter for mesh paths.
        """
        link = etree.SubElement(parent, "link", name=body.name)

        # Pose relative to base_link: x y z roll pitch yaw
        pose_str = self._format_pose(body)
        pose = etree.SubElement(link, "pose", relative_to="base_link")
        pose.text = pose_str

        # Inertial element (if inertia present)
        if body.inertia is not None:
            self._add_inertial(link, body)

        # Visual element (if geometry present)
        if body.geometry_file is not None:
            mesh_path = mesh_converter.get_mesh_path(body.name)
            self._add_visual(link, body.name, mesh_path)
            self._add_collision(link, body.name, mesh_path)

    def _format_pose(self, body: Body) -> str:
        """Format pose as SDF pose string.

        Args:
            body: Body with transform.

        Returns:
            String with "x y z roll pitch yaw" (meters, radians).
        """
        pos = body.transform.position
        rpy = rotation_to_euler(
            body.transform.rotation, EulerConvention.URDF_RPY, degrees=False
        )
        return f"{pos[0]} {pos[1]} {pos[2]} {rpy[0]} {rpy[1]} {rpy[2]}"

    def _add_inertial(self, link: etree._Element, body: Body) -> None:
        """Add inertial element to link.

        Args:
            link: Parent link element.
            body: Body with inertia data.
        """
        inertia = body.inertia
        inertial = etree.SubElement(link, "inertial")

        # Mass
        mass = etree.SubElement(inertial, "mass")
        mass.text = str(inertia.mass)

        # Inertia tensor (at CoM, in body frame)
        I = inertia.inertia_tensor
        inertia_elem = etree.SubElement(inertial, "inertia")

        ixx = etree.SubElement(inertia_elem, "ixx")
        ixx.text = str(I[0, 0])
        ixy = etree.SubElement(inertia_elem, "ixy")
        ixy.text = str(I[0, 1])
        ixz = etree.SubElement(inertia_elem, "ixz")
        ixz.text = str(I[0, 2])
        iyy = etree.SubElement(inertia_elem, "iyy")
        iyy.text = str(I[1, 1])
        iyz = etree.SubElement(inertia_elem, "iyz")
        iyz.text = str(I[1, 2])
        izz = etree.SubElement(inertia_elem, "izz")
        izz.text = str(I[2, 2])

    def _add_visual(
        self, link: etree._Element, name: str, mesh_path: Path
    ) -> None:
        """Add visual element to link.

        Args:
            link: Parent link element.
            name: Visual name (same as link name).
            mesh_path: Relative path to mesh file.
        """
        visual = etree.SubElement(link, "visual", name="visual")
        geometry = etree.SubElement(visual, "geometry")
        mesh = etree.SubElement(geometry, "mesh")
        uri = etree.SubElement(mesh, "uri")
        # Use forward slashes for URI path (cross-platform)
        uri.text = str(mesh_path).replace("\\", "/")

    def _add_collision(
        self, link: etree._Element, name: str, mesh_path: Path
    ) -> None:
        """Add collision element to link.

        Collision geometry matches visual geometry per CONTEXT.md.

        Args:
            link: Parent link element.
            name: Collision name (same as link name).
            mesh_path: Relative path to mesh file.
        """
        collision = etree.SubElement(link, "collision", name="collision")
        geometry = etree.SubElement(collision, "geometry")
        mesh = etree.SubElement(geometry, "mesh")
        uri = etree.SubElement(mesh, "uri")
        # Use forward slashes for URI path (cross-platform)
        uri.text = str(mesh_path).replace("\\", "/")

    def _add_joint(self, parent: etree._Element, body: Body) -> None:
        """Add fixed joint connecting link to base_link.

        Args:
            parent: Parent model element.
            body: Body being connected.
        """
        joint = etree.SubElement(
            parent, "joint", name=f"{body.name}_joint", type="fixed"
        )

        parent_link = etree.SubElement(joint, "parent")
        parent_link.text = "base_link"

        child_link = etree.SubElement(joint, "child")
        child_link.text = body.name
