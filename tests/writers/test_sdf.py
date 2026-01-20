"""Unit tests for SDF writer."""

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


class TestSDFWriterRegistration:
    """Tests for writer registration."""

    def test_sdf_writer_registered(self):
        """SDF writer should be registered."""
        assert "sdf" in WriterRegistry.list_formats()

    def test_sdf_writer_properties(self):
        """Writer should have correct format_name and file_extension."""
        writer = get_writer("sdf")
        assert writer.format_name == "sdf"
        assert writer.file_extension == ".sdf"


class TestSDFWriterOutput:
    """Tests for SDF file output."""

    def test_write_simple_assembly(self, simple_assembly, tmp_path):
        """Should write a valid .sdf file."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        assert output_path.exists()
        # Should be valid XML
        tree = etree.parse(str(output_path))
        assert tree.getroot() is not None

    def test_output_has_sdf_root(self, simple_assembly, tmp_path):
        """Output should have <sdf> as root element with version attribute."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        assert root.tag == "sdf"
        assert root.get("version") == "1.8"

    def test_output_has_model(self, simple_assembly, tmp_path):
        """Output should contain model element with name."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        model = root.find(".//model")
        assert model is not None
        assert model.get("name") == "TestAssembly"

    def test_output_has_base_link(self, simple_assembly, tmp_path):
        """Output should contain base_link element."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        base_links = root.findall(".//link[@name='base_link']")
        assert len(base_links) == 1

    def test_pose_element_format(self, simple_assembly, tmp_path):
        """Pose element should have 6 space-separated values."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        # Find pose element for link1
        link = root.find(".//link[@name='link1']")
        pose = link.find("pose")
        assert pose is not None
        values = pose.text.split()
        # Should have 6 values: x y z roll pitch yaw
        assert len(values) == 6


class TestSDFWriterConversions:
    """Tests for unit conversions and formatting."""

    def test_position_in_meters(self, simple_assembly, tmp_path):
        """Position values should be in meters (no conversion from IR)."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        link = root.find(".//link[@name='link1']")
        pose = link.find("pose")
        values = [float(v) for v in pose.text.split()]
        # Position should be [1.0, 2.0, 3.0] meters
        assert values[0] == pytest.approx(1.0)
        assert values[1] == pytest.approx(2.0)
        assert values[2] == pytest.approx(3.0)

    def test_rotation_as_rpy_radians(self, tmp_path):
        """Rotation should be RPY angles in radians."""
        # 90-degree rotation around Z axis
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
        transform = Transform(rotation=rotation)
        body = Body(name="rotated_part", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        link = root.find(".//link[@name='rotated_part']")
        pose = link.find("pose")
        values = [float(v) for v in pose.text.split()]
        # Rotation values are indices 3, 4, 5 (roll, pitch, yaw)
        rpy = values[3:6]
        # Should be in radians (90 deg = pi/2 rad)
        max_angle = max(abs(v) for v in rpy)
        assert max_angle == pytest.approx(np.pi / 2, abs=0.01)

    def test_inertia_values(self, assembly_with_inertia, tmp_path):
        """Inertia tensor values should be in kg*m^2 (no conversion from IR)."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        inertia_elem = root.find(".//inertia")
        assert inertia_elem is not None
        # Diagonal values should match
        ixx = float(inertia_elem.find("ixx").text)
        iyy = float(inertia_elem.find("iyy").text)
        izz = float(inertia_elem.find("izz").text)
        assert ixx == pytest.approx(0.1)
        assert iyy == pytest.approx(0.2)
        assert izz == pytest.approx(0.3)

    def test_mass_value(self, assembly_with_inertia, tmp_path):
        """Mass value should be correct."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(assembly_with_inertia, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        mass_elem = root.find(".//mass")
        assert mass_elem is not None
        assert float(mass_elem.text) == pytest.approx(10.0)


class TestSDFWriterValidation:
    """Tests for validation error handling."""

    def test_validation_error_raised(self, tmp_path):
        """Writer should raise ValueError for invalid model."""
        # Body references nonexistent material
        body = Body(name="part1", transform=Transform(), material_name="nonexistent")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        with pytest.raises(ValueError) as excinfo:
            writer.write(assembly, output_path)

        assert "validation failed" in str(excinfo.value).lower()


class TestSDFWriterGeometry:
    """Tests for geometry/mesh handling."""

    def test_body_without_geometry(self, simple_assembly, tmp_path):
        """Body without geometry_file should not have visual/collision elements."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

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
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        # Should have base_link + one link per body
        links = root.findall(".//link")
        assert len(links) == len(simple_assembly.bodies) + 1  # +1 for base_link


class TestSDFWriterJoints:
    """Tests for joint generation."""

    def test_joint_structure(self, simple_assembly, tmp_path):
        """Joint should have correct parent, child elements."""
        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"

        writer.write(simple_assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        joint = root.find(".//joint[@name='link1_joint']")
        assert joint is not None
        assert joint.get("type") == "fixed"

        parent = joint.find("parent")
        assert parent.text == "base_link"

        child = joint.find("child")
        assert child.text == "link1"

    def test_joints_for_all_bodies(self, tmp_path):
        """Each body should have a corresponding fixed joint."""
        body1 = Body(name="part1", transform=Transform())
        body2 = Body(name="part2", transform=Transform())
        assembly = AssemblyModel(name="Test", bodies=(body1, body2), materials=())

        writer = get_writer("sdf")
        output_path = tmp_path / "test.sdf"
        writer.write(assembly, output_path)

        tree = etree.parse(str(output_path))
        root = tree.getroot()
        joints = root.findall(".//joint[@type='fixed']")
        assert len(joints) == 2
