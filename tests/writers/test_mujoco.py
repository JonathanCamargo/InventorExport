"""Unit tests for MuJoCo MJCF writer."""

from pathlib import Path

import numpy as np
import pytest
from lxml import etree

from inventor_exporter.model import (
    AssemblyModel,
    Body,
    Inertia,
    Material,
    Transform,
)
from inventor_exporter.writers import WriterRegistry, get_writer


@pytest.fixture
def simple_material():
    """Create a simple steel material."""
    return Material(name="steel", density=7800.0)


@pytest.fixture
def simple_transform():
    """Create a transform with position [1.0, 2.0, 3.0] meters."""
    return Transform(position=np.array([1.0, 2.0, 3.0]))


@pytest.fixture
def simple_body(simple_transform, simple_material):
    """Create a body with transform and material reference."""
    return Body(
        name="link1",
        transform=simple_transform,
        material_name=simple_material.name,
    )


@pytest.fixture
def simple_assembly(simple_body, simple_material):
    """Create a simple assembly with one body and one material."""
    return AssemblyModel(
        name="TestAssembly",
        bodies=(simple_body,),
        materials=(simple_material,),
    )


@pytest.fixture
def body_with_inertia(simple_transform, simple_material):
    """Create a body with diagonal inertia data."""
    inertia = Inertia(
        mass=10.0,
        inertia_tensor=np.diag([0.1, 0.2, 0.3]),
        center_of_mass=np.array([0.01, 0.02, 0.03]),
    )
    return Body(
        name="link_with_inertia",
        transform=simple_transform,
        material_name=simple_material.name,
        inertia=inertia,
    )


@pytest.fixture
def body_with_full_inertia(simple_transform, simple_material):
    """Create a body with non-diagonal inertia tensor."""
    # Inertia tensor with off-diagonal terms
    inertia_tensor = np.array([
        [0.1, 0.01, 0.02],
        [0.01, 0.2, 0.03],
        [0.02, 0.03, 0.3],
    ])
    inertia = Inertia(
        mass=10.0,
        inertia_tensor=inertia_tensor,
        center_of_mass=np.array([0.0, 0.0, 0.0]),
    )
    return Body(
        name="link_full_inertia",
        transform=simple_transform,
        material_name=simple_material.name,
        inertia=inertia,
    )


@pytest.fixture
def assembly_with_inertia(body_with_inertia, simple_material):
    """Create an assembly with a body that has diagonal inertia."""
    return AssemblyModel(
        name="InertiaAssembly",
        bodies=(body_with_inertia,),
        materials=(simple_material,),
    )


@pytest.fixture
def assembly_with_full_inertia(body_with_full_inertia, simple_material):
    """Create an assembly with a body that has full inertia tensor."""
    return AssemblyModel(
        name="FullInertiaAssembly",
        bodies=(body_with_full_inertia,),
        materials=(simple_material,),
    )


class TestMuJoCoWriterRegistration:
    """Tests for writer registration."""

    def test_mujoco_writer_registered(self):
        """MuJoCo writer should be registered."""
        assert "mujoco" in WriterRegistry.list_formats()

    def test_mujoco_writer_properties(self):
        """Writer should have correct format_name and file_extension."""
        writer = get_writer("mujoco")
        assert writer.format_name == "mujoco"
        assert writer.file_extension == ".xml"


class TestMuJoCoWriterOutput:
    """Tests for MuJoCo file output."""

    def test_write_simple_assembly(self, simple_assembly, tmp_path):
        """Should write a valid .xml file."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        assert output_path.exists()
        # Should be valid XML
        tree = etree.parse(str(output_path))
        assert tree.getroot() is not None

    def test_output_has_mujoco_root(self, simple_assembly, tmp_path):
        """Output should have <mujoco> as root element with model attribute."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        assert root.tag == "mujoco"
        assert root.get("model") == "TestAssembly"

    def test_output_has_asset_section(self, simple_assembly, tmp_path):
        """Output should contain asset element."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        asset = root.find(".//asset")
        assert asset is not None

    def test_output_has_worldbody(self, simple_assembly, tmp_path):
        """Output should contain worldbody element."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        worldbody = root.find(".//worldbody")
        assert worldbody is not None

    def test_compiler_meshdir(self, simple_assembly, tmp_path):
        """Output should contain compiler element with meshdir."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        compiler = root.find(".//compiler")
        assert compiler is not None
        assert compiler.get("meshdir") == "meshes"


class TestMuJoCoWriterConversions:
    """Tests for unit conversions and formatting."""

    def test_position_in_meters(self, simple_assembly, tmp_path):
        """Position values should be in meters (no conversion from IR)."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        body = root.find(".//body[@name='link1']")
        pos = body.get("pos")
        values = [float(v) for v in pos.split()]
        # Position should be [1.0, 2.0, 3.0] meters
        assert values == pytest.approx([1.0, 2.0, 3.0])

    def test_rotation_as_quaternion(self, simple_assembly, tmp_path):
        """Rotation should be quaternion with 4 values."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        body = root.find(".//body[@name='link1']")
        quat = body.get("quat")
        values = [float(v) for v in quat.split()]
        # Should have 4 values
        assert len(values) == 4

    def test_quaternion_format_scalar_first(self, tmp_path):
        """Quaternion should be in w x y z order (scalar first)."""
        # Identity rotation should be [1, 0, 0, 0]
        transform = Transform()  # Identity rotation
        body = Body(name="identity_part", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        body_elem = root.find(".//body[@name='identity_part']")
        quat = body_elem.get("quat")
        values = [float(v) for v in quat.split()]
        # Identity quaternion: w=1, x=0, y=0, z=0 (scalar first)
        assert values[0] == pytest.approx(1.0)  # w
        assert values[1] == pytest.approx(0.0)  # x
        assert values[2] == pytest.approx(0.0)  # y
        assert values[3] == pytest.approx(0.0)  # z

    def test_quaternion_non_identity(self, tmp_path):
        """Non-identity rotation should produce non-trivial quaternion."""
        # 90-degree rotation around Z axis
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
        transform = Transform(rotation=rotation)
        body = Body(name="rotated_part", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        body_elem = root.find(".//body[@name='rotated_part']")
        quat = body_elem.get("quat")
        values = [float(v) for v in quat.split()]
        # Quaternion should be normalized (length 1)
        norm = np.sqrt(sum(v**2 for v in values))
        assert norm == pytest.approx(1.0)


class TestMuJoCoWriterInertia:
    """Tests for inertia handling."""

    def test_diaginertia_for_diagonal_tensor(self, assembly_with_inertia, tmp_path):
        """Diagonal inertia tensor should use diaginertia attribute."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        inertial = root.find(".//inertial")
        assert inertial is not None
        # Should use diaginertia, not fullinertia
        assert inertial.get("diaginertia") is not None
        assert inertial.get("fullinertia") is None

        values = [float(v) for v in inertial.get("diaginertia").split()]
        assert values == pytest.approx([0.1, 0.2, 0.3])

    def test_fullinertia_for_full_tensor(self, assembly_with_full_inertia, tmp_path):
        """Non-diagonal inertia tensor should use fullinertia attribute."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(assembly_with_full_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        inertial = root.find(".//inertial")
        assert inertial is not None
        # Should use fullinertia, not diaginertia
        assert inertial.get("fullinertia") is not None
        assert inertial.get("diaginertia") is None

        values = [float(v) for v in inertial.get("fullinertia").split()]
        # MuJoCo order: ixx iyy izz ixy ixz iyz
        assert len(values) == 6

    def test_mass_value(self, assembly_with_inertia, tmp_path):
        """Mass value should be correct."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        inertial = root.find(".//inertial")
        assert inertial is not None
        assert float(inertial.get("mass")) == pytest.approx(10.0)


class TestMuJoCoWriterValidation:
    """Tests for validation error handling."""

    def test_validation_error_raised(self, tmp_path):
        """Writer should raise ValueError for invalid model."""
        # Body references nonexistent material
        body = Body(name="part1", transform=Transform(), material_name="nonexistent")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        with pytest.raises(ValueError) as excinfo:
            writer.write(assembly, output_path)

        assert "validation failed" in str(excinfo.value).lower()


class TestMuJoCoWriterGeometry:
    """Tests for geometry/mesh handling."""

    def test_body_without_geometry(self, simple_assembly, tmp_path):
        """Body without geometry_file should not have geom element."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        body = root.find(".//body[@name='link1']")
        assert body is not None
        # No geom without geometry
        assert body.find("geom") is None

    def test_body_elements_in_worldbody(self, simple_assembly, tmp_path):
        """Body elements should be direct children of worldbody."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        worldbody = root.find(".//worldbody")
        bodies = worldbody.findall("body")
        assert len(bodies) == len(simple_assembly.bodies)


class TestMuJoCoWriterMaterials:
    """Tests for material handling in asset section."""

    def test_materials_in_asset(self, simple_assembly, tmp_path):
        """Materials should be defined in asset section."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        asset = root.find(".//asset")
        materials = asset.findall("material")
        assert len(materials) == len(simple_assembly.materials)

    def test_material_has_rgba(self, simple_assembly, tmp_path):
        """Material element should have rgba attribute."""
        writer = get_writer("mujoco")
        output_path = tmp_path / "test.xml"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        material = root.find(".//asset/material[@name='steel']")
        assert material is not None
        rgba = material.get("rgba")
        assert rgba is not None
        values = [float(v) for v in rgba.split()]
        assert len(values) == 4  # r, g, b, a
