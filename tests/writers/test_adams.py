"""Unit tests for ADAMS writer."""

from pathlib import Path

import numpy as np
import pytest

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


class TestAdamsWriterRegistration:
    """Tests for writer registration."""

    def test_adams_writer_registered(self):
        """ADAMS writer should be registered."""
        assert "adams" in WriterRegistry.list_formats()

    def test_adams_writer_properties(self):
        """Writer should have correct format_name and file_extension."""
        writer = get_writer("adams")
        assert writer.format_name == "adams"
        assert writer.file_extension == ".cmd"


class TestAdamsWriterOutput:
    """Tests for ADAMS file output."""

    def test_write_simple_assembly(self, simple_assembly, tmp_path):
        """Should write a valid .cmd file."""
        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"

        writer.write(simple_assembly, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "material create" in content
        assert "part create rigid_body" in content

    def test_output_contains_header(self, simple_assembly, tmp_path):
        """Output should contain header comments."""
        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"

        writer.write(simple_assembly, output_path)

        content = output_path.read_text()
        assert "! ADAMS View command file" in content
        assert "! Assembly:" in content

    def test_output_sections_ordered(self, simple_assembly, tmp_path):
        """Materials should appear before rigid bodies."""
        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"

        writer.write(simple_assembly, output_path)

        content = output_path.read_text()
        mat_pos = content.find("! === Materials ===")
        body_pos = content.find("! === Rigid Bodies ===")
        geom_pos = content.find("! === Geometry ===")

        assert mat_pos < body_pos < geom_pos


class TestAdamsWriterConversions:
    """Tests for unit conversions."""

    def test_material_density_conversion(self, tmp_path):
        """Density should convert from kg/m^3 to kg/mm^3."""
        # 7800 kg/m^3 -> 7.8e-6 kg/mm^3
        material = Material(name="steel", density=7800.0)
        body = Body(name="part1", transform=Transform(), material_name="steel")
        assembly = AssemblyModel(
            name="Test",
            bodies=(body,),
            materials=(material,),
        )

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        # Should contain 7.8e-06 (7800 * 1e-9)
        assert "7.800000000000000e-06" in content

    def test_position_conversion(self, tmp_path):
        """Position should convert from meters to millimeters."""
        # [1.0, 2.0, 3.0] m -> [1000.0, 2000.0, 3000.0] mm
        transform = Transform(position=np.array([1.0, 2.0, 3.0]))
        body = Body(name="part1", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        assert "1000.000000" in content
        assert "2000.000000" in content
        assert "3000.000000" in content

    def test_rotation_format(self, tmp_path):
        """Rotation should be ZXZ Euler angles with 'd' suffix."""
        # 90-degree Z rotation
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
        transform = Transform(rotation=rotation)
        body = Body(name="part1", transform=transform)
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        # Should contain 'd' suffix for degrees
        assert "d," in content or "d\n" in content

    def test_inertia_conversion(self, tmp_path):
        """Inertia tensor should convert from kg*m^2 to kg*mm^2."""
        # diag([1.0, 2.0, 3.0]) kg*m^2 -> diag([1e6, 2e6, 3e6]) kg*mm^2
        inertia = Inertia(
            mass=10.0,
            inertia_tensor=np.diag([1.0, 2.0, 3.0]),
        )
        material = Material(name="steel", density=7800.0)
        transform = Transform()
        body = Body(
            name="part1",
            transform=transform,
            material_name="steel",
            inertia=inertia,
        )
        assembly = AssemblyModel(
            name="Test",
            bodies=(body,),
            materials=(material,),
        )

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        # ixx = 1.0 * 1e6 = 1.0e+06
        assert "ixx = 1.000000e+06" in content
        # iyy = 2.0 * 1e6 = 2.0e+06
        assert "iyy = 2.000000e+06" in content
        # izz = 3.0 * 1e6 = 3.0e+06
        assert "izz = 3.000000e+06" in content


class TestAdamsWriterValidation:
    """Tests for validation error handling."""

    def test_validation_error_raised(self, tmp_path):
        """Writer should raise ValueError for invalid model."""
        # Body references nonexistent material
        body = Body(name="part1", transform=Transform(), material_name="nonexistent")
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"

        with pytest.raises(ValueError) as excinfo:
            writer.write(assembly, output_path)

        assert "validation failed" in str(excinfo.value).lower()


class TestAdamsWriterGeometry:
    """Tests for geometry section generation."""

    def test_geometry_section(self, tmp_path):
        """Should generate geometry import for bodies with geometry_file."""
        transform = Transform()
        body = Body(
            name="part1",
            transform=transform,
            geometry_file=Path("parts/part1.stp"),
        )
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        assert "file geometry read" in content
        assert "type_of_geometry = stp" in content
        assert "part1.stp" in content

    def test_no_geometry_for_body_without_file(self, tmp_path):
        """Should not generate geometry for bodies without geometry_file."""
        body = Body(name="part1", transform=Transform())
        assembly = AssemblyModel(name="Test", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        # Should have geometry section header but no file geometry read after it
        geom_section = content.split("! === Geometry ===")[1]
        assert "file geometry read" not in geom_section


class TestAdamsWriterModelName:
    """Tests for model name handling."""

    def test_model_name_sanitization(self, tmp_path):
        """Model name should have spaces and dashes replaced."""
        body = Body(name="part1", transform=Transform())
        assembly = AssemblyModel(name="My Assembly-Name", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        assert "model_My_Assembly_Name" in content

    def test_model_name_prefix(self, tmp_path):
        """Model name should be prefixed with 'model_' if not already."""
        body = Body(name="part1", transform=Transform())
        assembly = AssemblyModel(name="Robot", bodies=(body,), materials=())

        writer = get_writer("adams")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        assert "model_Robot" in content

    def test_model_name_override(self, tmp_path):
        """Model name override should be used when provided."""
        body = Body(name="part1", transform=Transform())
        assembly = AssemblyModel(name="Robot", bodies=(body,), materials=())

        from inventor_exporter.writers.adams import AdamsWriter

        writer = AdamsWriter(model_name="custom_model")
        output_path = tmp_path / "test.cmd"
        writer.write(assembly, output_path)

        content = output_path.read_text()
        assert "custom_model" in content
        assert "model_Robot" not in content
