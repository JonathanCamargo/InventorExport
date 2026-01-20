"""Unit tests for URDF writer."""

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
    """Create a body with inertia data."""
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
def assembly_with_inertia(body_with_inertia, simple_material):
    """Create an assembly with a body that has inertia."""
    return AssemblyModel(
        name="InertiaAssembly",
        bodies=(body_with_inertia,),
        materials=(simple_material,),
    )


class TestURDFWriterRegistration:
    """Tests for writer registration."""

    def test_urdf_writer_registered(self):
        """URDF writer should be registered."""
        assert "urdf" in WriterRegistry.list_formats()

    def test_urdf_writer_properties(self):
        """Writer should have correct format_name and file_extension."""
        writer = get_writer("urdf")
        assert writer.format_name == "urdf"
        assert writer.file_extension == ".urdf"


class TestURDFWriterOutput:
    """Tests for URDF file output."""

    def test_write_simple_assembly(self, simple_assembly, tmp_path):
        """Should write a valid .urdf file."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        assert output_path.exists()
        # Should be valid XML
        tree = etree.parse(str(output_path))
        assert tree.getroot() is not None

    def test_output_has_robot_root(self, simple_assembly, tmp_path):
        """Output should have <robot> as root element with name attribute."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        assert root.tag == "robot"
        assert root.get("name") == "TestAssembly"

    def test_output_has_base_link(self, simple_assembly, tmp_path):
        """Output should contain base_link element."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        base_links = root.findall(".//link[@name='base_link']")
        assert len(base_links) == 1

    def test_output_has_fixed_joints(self, simple_assembly, tmp_path):
        """Output should contain fixed joint elements."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        joints = root.findall(".//joint[@type='fixed']")
        # Should have one fixed joint per body
        assert len(joints) == len(simple_assembly.bodies)

    def test_materials_defined_at_robot_level(self, simple_assembly, tmp_path):
        """Materials should be defined at robot level, not inside links."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        # Materials should be direct children of robot
        materials = root.findall("material")
        assert len(materials) == len(simple_assembly.materials)
        for mat in materials:
            assert mat.find("color") is not None


class TestURDFWriterConversions:
    """Tests for unit conversions and formatting."""

    def test_position_in_meters(self, simple_assembly, tmp_path):
        """Position values should be in meters (no conversion from IR)."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        # Find the joint origin (contains position)
        joint = root.find(".//joint[@name='link1_joint']")
        origin = joint.find("origin")
        xyz = origin.get("xyz")
        # Position should be [1.0, 2.0, 3.0] meters
        values = [float(v) for v in xyz.split()]
        assert values == pytest.approx([1.0, 2.0, 3.0])

    def test_rotation_as_rpy_radians(self, tmp_path):
        """Rotation should be RPY angles in radians."""
        # 90-degree rotation around Z axis
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
        transform = Transform(rotation=rotation)
        body = Body(name="rotated_part", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        joint = root.find(".//joint[@name='rotated_part_joint']")
        origin = joint.find("origin")
        rpy = origin.get("rpy")
        values = [float(v) for v in rpy.split()]
        # Should be in radians (90 deg = pi/2 rad)
        # For intrinsic ZYX (URDF RPY), Z rotation appears as first angle
        # At least one value should be approximately pi/2
        max_angle = max(abs(v) for v in values)
        assert max_angle == pytest.approx(np.pi / 2, abs=0.01)

    def test_inertia_values(self, assembly_with_inertia, tmp_path):
        """Inertia tensor values should be in kg*m^2 (no conversion from IR)."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        inertia_elem = root.find(".//inertia")
        assert inertia_elem is not None
        # Diagonal values should match
        assert float(inertia_elem.get("ixx")) == pytest.approx(0.1)
        assert float(inertia_elem.get("iyy")) == pytest.approx(0.2)
        assert float(inertia_elem.get("izz")) == pytest.approx(0.3)

    def test_mass_value(self, assembly_with_inertia, tmp_path):
        """Mass value should be correct."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        mass_elem = root.find(".//mass")
        assert mass_elem is not None
        assert float(mass_elem.get("value")) == pytest.approx(10.0)


class TestURDFWriterValidation:
    """Tests for validation error handling."""

    def test_validation_error_raised(self, tmp_path):
        """Writer should raise ValueError for invalid model."""
        # Body references nonexistent material
        body = Body(name="part1", transform=Transform(), material_name="nonexistent")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        with pytest.raises(ValueError) as excinfo:
            writer.write(assembly, output_path)

        assert "validation failed" in str(excinfo.value).lower()


class TestURDFWriterGeometry:
    """Tests for geometry/mesh handling."""

    def test_body_without_geometry(self, simple_assembly, tmp_path):
        """Body without geometry_file should not have visual/collision elements."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        link = root.find(".//link[@name='link1']")
        assert link is not None
        # No visual or collision without geometry
        assert link.find("visual") is None
        assert link.find("collision") is None

    def test_link_elements_created(self, simple_assembly, tmp_path):
        """Each body should create a link element."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        # Should have base_link + one link per body
        links = root.findall(".//link")
        assert len(links) == len(simple_assembly.bodies) + 1  # +1 for base_link


class TestURDFWriterJoints:
    """Tests for joint generation."""

    def test_joint_structure(self, simple_assembly, tmp_path):
        """Joint should have correct parent, child, and origin."""
        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        joint = root.find(".//joint[@name='link1_joint']")
        assert joint is not None
        assert joint.get("type") == "fixed"

        parent = joint.find("parent")
        assert parent.get("link") == "base_link"

        child = joint.find("child")
        assert child.get("link") == "link1"

        origin = joint.find("origin")
        assert origin is not None
        assert origin.get("xyz") is not None
        assert origin.get("rpy") is not None


class TestURDFWriterMaterials:
    """Tests for material handling."""

    def test_steel_material_color(self, tmp_path):
        """Steel material should get gray color."""
        material = Material(name="steel_alloy", density=7800.0)
        body = Body(name="part1", transform=Transform(), material_name="steel_alloy")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=(material,))

        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        material_elem = root.find(".//material[@name='steel_alloy']")
        color = material_elem.find("color")
        rgba = color.get("rgba")
        # Steel should be gray (0.7 0.7 0.7)
        values = [float(v) for v in rgba.split()]
        assert values[0] == pytest.approx(0.7)  # R
        assert values[1] == pytest.approx(0.7)  # G
        assert values[2] == pytest.approx(0.7)  # B
        assert values[3] == pytest.approx(1.0)  # A

    def test_aluminum_material_color(self, tmp_path):
        """Aluminum material should get light blue-gray color."""
        material = Material(name="aluminum", density=2700.0)
        body = Body(name="part1", transform=Transform(), material_name="aluminum")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=(material,))

        writer = get_writer("urdf")
        output_path = tmp_path / "test.urdf"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        material_elem = root.find(".//material[@name='aluminum']")
        color = material_elem.find("color")
        rgba = color.get("rgba")
        # Aluminum should be light blue-gray (0.8 0.8 0.85)
        values = [float(v) for v in rgba.split()]
        assert values[0] == pytest.approx(0.8)  # R
        assert values[2] == pytest.approx(0.85)  # B
