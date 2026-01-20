"""MuJoCo MJCF format writer.

Generates .xml files compatible with MuJoCo 3.x physics engine.
MJCF (MuJoCo XML Format) is the native format for MuJoCo simulation.

Coordinate conventions:
    - Position: meters (same as IR, no conversion needed)
    - Rotation: quaternion (w, x, y, z) - scalar first (MuJoCo convention)
    - Inertia: kg*m^2 (same as IR, no conversion needed)
    - Mass: kg (same as IR, no conversion needed)

Key MJCF structure differences from URDF/SDF:
    - worldbody: Base frame is implicit (no explicit base_link needed)
    - Assets: Meshes and materials defined separately in <asset> section,
      referenced by name in <geom> elements
    - Meshes: Referenced by name via asset definitions, not by path
    - Compiler: <compiler meshdir="meshes"/> sets mesh search path
    - Inertia: Can use diaginertia (diagonal only) or fullinertia (all 6 terms)

Example output structure:
    <mujoco model="assembly">
      <compiler meshdir="meshes"/>
      <asset>
        <mesh name="part1_mesh" file="part1.stl"/>
        <material name="steel" rgba="0.7 0.7 0.7 1"/>
      </asset>
      <worldbody>
        <body name="part1" pos="1.0 2.0 3.0" quat="1 0 0 0">
          <inertial pos="0 0 0" mass="1.0" diaginertia="0.1 0.1 0.1"/>
          <geom type="mesh" mesh="part1_mesh" material="steel"/>
        </body>
      </worldbody>
    </mujoco>
"""

import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from inventor_exporter.core.rotation import rotation_to_quaternion
from inventor_exporter.model import AssemblyModel, Body, Material
from inventor_exporter.writers.mesh_converter import MeshConverter
from inventor_exporter.writers.registry import WriterRegistry

logger = logging.getLogger(__name__)

# Tolerance for considering off-diagonal inertia terms as zero
INERTIA_ZERO_TOLERANCE = 1e-10


@WriterRegistry.register("mujoco")
class MuJoCoWriter:
    """MuJoCo MJCF format writer.

    Generates .xml files for MuJoCo physics simulation. Bodies are placed
    directly under worldbody (flat structure, no tree hierarchy needed
    for rigid assemblies).

    Attributes:
        format_name: "mujoco"
        file_extension: ".xml"
    """

    format_name: str = "mujoco"
    file_extension: str = ".xml"

    def __init__(self, mesh_subdir: str = "meshes"):
        """Initialize MuJoCo writer.

        Args:
            mesh_subdir: Subdirectory name for mesh files. Default "meshes".
        """
        self._mesh_subdir = mesh_subdir

    def write(self, model: AssemblyModel, output_path: Path) -> None:
        """Write assembly model to MuJoCo MJCF XML file.

        Args:
            model: AssemblyModel to export.
            output_path: Destination .xml file path.

        Raises:
            ValueError: If model validation fails.
        """
        errors = model.validate()
        if errors:
            raise ValueError(
                "Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Set up mesh converter for STEP to STL conversion
        output_dir = output_path.parent
        converter = MeshConverter(output_dir, mesh_subdir=self._mesh_subdir)

        # Convert meshes (STEP -> STL) for bodies with geometry
        mesh_names = self._convert_meshes(model, converter)

        # Build XML tree
        root = self._build_mujoco_tree(model, mesh_names)

        # Write to file with pretty printing
        tree = etree.ElementTree(root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(
            str(output_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

        logger.info("Wrote MuJoCo MJCF to %s", output_path)

    def _convert_meshes(
        self, model: AssemblyModel, converter: MeshConverter
    ) -> dict[str, str]:
        """Convert STEP files to STL for bodies with geometry.

        Args:
            model: AssemblyModel containing bodies.
            converter: MeshConverter instance for STEP->STL conversion.

        Returns:
            Dict mapping body.name to mesh asset name (without extension).
        """
        mesh_names: dict[str, str] = {}

        for body in model.bodies:
            if body.geometry_file is not None:
                mesh_name = f"{body.name}_mesh"
                try:
                    converter.convert(body.geometry_file, mesh_name)
                    mesh_names[body.name] = mesh_name
                    logger.debug("Converted mesh for body %s", body.name)
                except Exception as e:
                    logger.warning(
                        "Failed to convert mesh for body %s: %s", body.name, e
                    )

        return mesh_names

    def _build_mujoco_tree(
        self, model: AssemblyModel, mesh_names: dict[str, str]
    ) -> etree._Element:
        """Build the MJCF XML tree.

        Args:
            model: AssemblyModel to convert.
            mesh_names: Dict mapping body.name to mesh asset name.

        Returns:
            Root <mujoco> element.
        """
        # Root mujoco element
        mujoco = etree.Element("mujoco", model=model.name)

        # Compiler settings - set mesh search directory
        etree.SubElement(mujoco, "compiler", meshdir=self._mesh_subdir)

        # Asset section
        asset = etree.SubElement(mujoco, "asset")
        self._add_mesh_assets(asset, mesh_names)
        self._add_material_assets(asset, model.materials)

        # Worldbody section
        worldbody = etree.SubElement(mujoco, "worldbody")
        for body in model.bodies:
            mesh_name = mesh_names.get(body.name)
            self._add_body(worldbody, body, mesh_name)

        return mujoco

    def _add_mesh_assets(
        self, asset: etree._Element, mesh_names: dict[str, str]
    ) -> None:
        """Add mesh asset definitions.

        Args:
            asset: Parent <asset> element.
            mesh_names: Dict mapping body.name to mesh asset name.
        """
        for body_name, mesh_name in mesh_names.items():
            etree.SubElement(
                asset,
                "mesh",
                name=mesh_name,
                file=f"{mesh_name}.stl",
            )

    def _add_material_assets(
        self, asset: etree._Element, materials: tuple[Material, ...]
    ) -> None:
        """Add material asset definitions.

        Args:
            asset: Parent <asset> element.
            materials: Tuple of materials to add.
        """
        for material in materials:
            # Default gray color for materials
            # MuJoCo rgba format: "r g b a" with values 0-1
            etree.SubElement(
                asset,
                "material",
                name=material.name,
                rgba="0.7 0.7 0.7 1",
            )

    def _add_body(
        self,
        worldbody: etree._Element,
        body: Body,
        mesh_name: Optional[str],
    ) -> None:
        """Add a body element to worldbody.

        Args:
            worldbody: Parent <worldbody> element.
            body: Body to add.
            mesh_name: Mesh asset name, or None if no geometry.
        """
        # Format position (meters, space-separated)
        pos = body.transform.position
        pos_str = f"{pos[0]} {pos[1]} {pos[2]}"

        # Format quaternion (w, x, y, z) scalar-first
        quat = rotation_to_quaternion(body.transform.rotation, scalar_first=True)
        quat_str = f"{quat[0]} {quat[1]} {quat[2]} {quat[3]}"

        # Create body element
        body_elem = etree.SubElement(
            worldbody,
            "body",
            name=body.name,
            pos=pos_str,
            quat=quat_str,
        )

        # Add inertial element if inertia data present
        if body.inertia is not None:
            self._add_inertial(body_elem, body)

        # Add geom element if mesh available
        if mesh_name is not None:
            geom_attribs = {
                "type": "mesh",
                "mesh": mesh_name,
            }
            if body.material_name is not None:
                geom_attribs["material"] = body.material_name
            etree.SubElement(body_elem, "geom", **geom_attribs)

    def _add_inertial(self, body_elem: etree._Element, body: Body) -> None:
        """Add inertial element to body.

        Args:
            body_elem: Parent <body> element.
            body: Body with inertia data.
        """
        inertia = body.inertia
        if inertia is None:
            return

        # Inertial position (center of mass relative to body frame)
        com = inertia.center_of_mass
        pos_str = f"{com[0]} {com[1]} {com[2]}"

        # Build inertial attributes
        inertial_attribs = {
            "pos": pos_str,
            "mass": str(inertia.mass),
        }

        # Check if off-diagonal terms are zero (within tolerance)
        I = inertia.inertia_tensor
        ixy = I[0, 1]
        ixz = I[0, 2]
        iyz = I[1, 2]

        if (
            abs(ixy) < INERTIA_ZERO_TOLERANCE
            and abs(ixz) < INERTIA_ZERO_TOLERANCE
            and abs(iyz) < INERTIA_ZERO_TOLERANCE
        ):
            # Use diaginertia (diagonal only)
            ixx, iyy, izz = I[0, 0], I[1, 1], I[2, 2]
            inertial_attribs["diaginertia"] = f"{ixx} {iyy} {izz}"
        else:
            # Use fullinertia (all 6 components)
            # MuJoCo order: ixx iyy izz ixy ixz iyz
            ixx, iyy, izz = I[0, 0], I[1, 1], I[2, 2]
            inertial_attribs["fullinertia"] = f"{ixx} {iyy} {izz} {ixy} {ixz} {iyz}"

        etree.SubElement(body_elem, "inertial", **inertial_attribs)
