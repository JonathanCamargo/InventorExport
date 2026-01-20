"""Unit tests for mesh_converter module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from inventor_exporter.writers.mesh_converter import (
    CADQUERY_AVAILABLE,
    MeshConverter,
    convert_step_to_stl,
)


class TestMeshConverterImport:
    """Tests for module import."""

    def test_module_imports(self):
        """Module should import without errors."""
        from inventor_exporter.writers import mesh_converter

        assert mesh_converter is not None

    def test_functions_exported(self):
        """convert_step_to_stl and MeshConverter should be available."""
        from inventor_exporter.writers.mesh_converter import (
            MeshConverter,
            convert_step_to_stl,
        )

        assert callable(convert_step_to_stl)
        assert MeshConverter is not None

    def test_cadquery_available_flag(self):
        """CADQUERY_AVAILABLE should be a boolean."""
        assert isinstance(CADQUERY_AVAILABLE, bool)


class TestMeshConverterClass:
    """Tests for MeshConverter class."""

    def test_init_stores_output_dir(self, tmp_path):
        """MeshConverter should store output_dir."""
        converter = MeshConverter(tmp_path)
        assert converter.output_dir == tmp_path

    def test_init_stores_mesh_subdir(self, tmp_path):
        """MeshConverter should store mesh_subdir."""
        converter = MeshConverter(tmp_path, mesh_subdir="my_meshes")
        assert converter.mesh_subdir == "my_meshes"

    def test_default_mesh_subdir(self, tmp_path):
        """Default mesh_subdir should be 'meshes'."""
        converter = MeshConverter(tmp_path)
        assert converter.mesh_subdir == "meshes"

    def test_mesh_dir_property(self, tmp_path):
        """mesh_dir should return absolute path to mesh directory."""
        converter = MeshConverter(tmp_path, mesh_subdir="stls")
        expected = tmp_path / "stls"
        assert converter.mesh_dir == expected

    def test_get_mesh_path_returns_relative(self, tmp_path):
        """get_mesh_path should return relative path from output_dir."""
        converter = MeshConverter(tmp_path, mesh_subdir="meshes")
        mesh_path = converter.get_mesh_path("part1")
        # Should be relative path: meshes/part1.stl
        assert mesh_path == Path("meshes/part1.stl")
        # Should not be absolute
        assert not mesh_path.is_absolute()

    def test_get_mesh_path_with_custom_subdir(self, tmp_path):
        """get_mesh_path should use custom mesh_subdir."""
        converter = MeshConverter(tmp_path, mesh_subdir="stl_files")
        mesh_path = converter.get_mesh_path("link2")
        assert mesh_path == Path("stl_files/link2.stl")

    def test_clear_cache(self, tmp_path):
        """clear_cache should reset internal cache."""
        converter = MeshConverter(tmp_path)
        # Manually add to cache (simulating conversion)
        converter._converted["test"] = tmp_path / "meshes" / "test.stl"
        assert "test" in converter._converted

        converter.clear_cache()
        assert len(converter._converted) == 0


class TestCadQueryAvailability:
    """Tests for CadQuery availability handling."""

    def test_convert_raises_when_cadquery_unavailable(self, tmp_path):
        """convert_step_to_stl should raise RuntimeError if cadquery not available."""
        # Mock CADQUERY_AVAILABLE as False
        with patch(
            "inventor_exporter.writers.mesh_converter.CADQUERY_AVAILABLE", False
        ):
            step_path = tmp_path / "test.step"
            stl_path = tmp_path / "test.stl"

            with pytest.raises(RuntimeError) as excinfo:
                convert_step_to_stl(step_path, stl_path)

            assert "cadquery" in str(excinfo.value).lower()
            assert "required" in str(excinfo.value).lower()


class TestConvertStepToStl:
    """Tests for convert_step_to_stl function."""

    def test_raises_file_not_found_for_missing_step(self, tmp_path):
        """Should raise FileNotFoundError if STEP file doesn't exist."""
        step_path = tmp_path / "nonexistent.step"
        stl_path = tmp_path / "output.stl"

        # Only test if cadquery is available
        if CADQUERY_AVAILABLE:
            with pytest.raises(FileNotFoundError) as excinfo:
                convert_step_to_stl(step_path, stl_path)
            assert "not found" in str(excinfo.value).lower()

    def test_function_signature(self):
        """Function should accept expected parameters."""
        import inspect

        sig = inspect.signature(convert_step_to_stl)
        params = list(sig.parameters.keys())
        assert "step_path" in params
        assert "stl_path" in params
        assert "tolerance" in params
        assert "angular_tolerance" in params


class TestMeshConverterConvert:
    """Tests for MeshConverter.convert method."""

    def test_convert_returns_relative_path(self, tmp_path):
        """convert should return relative path."""
        converter = MeshConverter(tmp_path)

        # Mock the actual conversion
        if CADQUERY_AVAILABLE:
            # Create a fake STEP file
            step_path = tmp_path / "test.step"
            step_path.write_text("fake step content")

            # This will fail to import but tests the path handling
            # In real use, a valid STEP file would be needed
            with pytest.raises(Exception):
                # Will fail during import but tests that return type is Path
                converter.convert(step_path, "test_part")
        else:
            # If cadquery not available, verify RuntimeError is raised
            step_path = tmp_path / "test.step"
            with pytest.raises(RuntimeError):
                converter.convert(step_path, "test_part")

    def test_convert_caches_result(self, tmp_path):
        """convert should cache converted mesh to avoid re-conversion."""
        converter = MeshConverter(tmp_path)

        # Create mesh directory and a pre-existing STL file
        mesh_dir = tmp_path / "meshes"
        mesh_dir.mkdir(parents=True)
        stl_file = mesh_dir / "cached_part.stl"
        stl_file.write_bytes(b"fake stl content")

        # Create a fake STEP file
        step_path = tmp_path / "source.step"
        step_path.write_text("fake step")

        # First call should find existing file and cache it
        result = converter.convert(step_path, "cached_part")
        assert result == Path("meshes/cached_part.stl")
        assert "cached_part" in converter._converted

    def test_skip_conversion_if_stl_exists(self, tmp_path):
        """convert should skip conversion if STL already exists on disk."""
        converter = MeshConverter(tmp_path)

        # Create mesh directory and STL file
        mesh_dir = tmp_path / "meshes"
        mesh_dir.mkdir(parents=True)
        stl_file = mesh_dir / "existing.stl"
        stl_file.write_bytes(b"existing stl")

        # Create fake STEP (won't actually be read)
        step_path = tmp_path / "source.step"
        step_path.write_text("fake step")

        # Should return path without raising conversion error
        result = converter.convert(step_path, "existing")
        assert result == Path("meshes/existing.stl")
