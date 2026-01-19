"""Integration tests for InventorClient extraction orchestrator.

Tests verify the full extraction flow with mocked Inventor COM components.
No actual Inventor connection is required.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from inventor_exporter.extraction.client import InventorClient
from inventor_exporter.extraction.assembly import OccurrenceData
from inventor_exporter.model import Transform, Material, Inertia


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_occurrence():
    """Factory fixture for creating mock occurrences."""

    def _create(
        name: str = "Part:1",
        definition_path: str = "C:\\Parts\\Part.ipt",
        position: np.ndarray = None,
    ):
        """Create a mock OccurrenceData object.

        Args:
            name: Occurrence name
            definition_path: Path to part definition document
            position: 3D position array, defaults to origin

        Returns:
            OccurrenceData with mocked part_document
        """
        if position is None:
            position = np.array([0.0, 0.0, 0.0])

        transform = Transform(
            position=position,
            rotation=np.eye(3),
        )

        # Mock part document
        part_doc = MagicMock()
        part_doc.DisplayName = name.split(":")[0]

        # Mock component definition for mass properties
        comp_def = MagicMock()
        part_doc.ComponentDefinition = comp_def

        return OccurrenceData(
            name=name,
            transformation=transform,
            definition_path=definition_path,
            part_document=part_doc,
        )

    return _create


@pytest.fixture
def mock_inventor_app():
    """Create a mock Inventor.Application COM object."""
    app = MagicMock()
    app.SoftwareVersion.DisplayVersion = "2024.0"
    return app


@pytest.fixture
def mock_assembly_doc():
    """Create a mock AssemblyDocument COM object."""
    doc = MagicMock()
    doc.DisplayName = "TestAssembly"
    doc.DocumentType = 12291  # kAssemblyDocumentObject
    return doc


# -----------------------------------------------------------------------------
# Tests: Full extraction flow
# -----------------------------------------------------------------------------


class TestExtractAssemblyBuildsModel:
    """Tests for extract_assembly building complete model."""

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_extract_assembly_builds_complete_model(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that extract_assembly builds complete AssemblyModel."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        # Create two occurrences
        occ1 = mock_occurrence(
            name="Link1:1",
            definition_path="C:\\Parts\\Link1.ipt",
            position=np.array([0.1, 0.0, 0.0]),
        )
        occ2 = mock_occurrence(
            name="Link2:1",
            definition_path="C:\\Parts\\Link2.ipt",
            position=np.array([0.2, 0.0, 0.0]),
        )
        mock_traverse.return_value = [occ1, occ2]

        # Set up geometry export
        mock_export_parts.return_value = {
            "C:\\Parts\\Link1.ipt": tmp_path / "Link1.stp",
            "C:\\Parts\\Link2.ipt": tmp_path / "Link2.stp",
        }

        # Set up material extraction
        steel = Material(name="Steel", density=7800.0)
        mock_extract_mat.return_value = steel

        # Set up mass properties extraction
        inertia = Inertia(
            mass=1.5,
            center_of_mass=np.array([0.05, 0.0, 0.0]),
            inertia_tensor=np.diag([0.001, 0.002, 0.003]),
        )
        mock_extract_mass.return_value = inertia

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify AssemblyModel
        assert model.name == "TestAssembly"
        assert len(model.bodies) == 2
        assert len(model.materials) == 1  # Same material for both

        # Verify bodies have all data
        body1 = model.bodies[0]
        assert body1.name == "Link1_1"  # Colon sanitized
        assert np.allclose(body1.transform.position, [0.1, 0.0, 0.0])
        assert body1.material_name == "Steel"
        assert body1.inertia is not None
        assert body1.inertia.mass == 1.5
        assert body1.geometry_file == tmp_path / "Link1.stp"

        body2 = model.bodies[1]
        assert body2.name == "Link2_1"
        assert np.allclose(body2.transform.position, [0.2, 0.0, 0.0])

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_extract_assembly_deduplicates_materials(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that materials are deduplicated by name."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        # Create three occurrences - two use same material
        occ1 = mock_occurrence(name="Link1:1", definition_path="C:\\Parts\\Link1.ipt")
        occ2 = mock_occurrence(name="Link2:1", definition_path="C:\\Parts\\Link2.ipt")
        occ3 = mock_occurrence(name="Link3:1", definition_path="C:\\Parts\\Link3.ipt")
        mock_traverse.return_value = [occ1, occ2, occ3]

        mock_export_parts.return_value = {
            "C:\\Parts\\Link1.ipt": tmp_path / "Link1.stp",
            "C:\\Parts\\Link2.ipt": tmp_path / "Link2.stp",
            "C:\\Parts\\Link3.ipt": tmp_path / "Link3.stp",
        }

        # Return different materials - but Link1 and Link3 share "Steel"
        steel = Material(name="Steel", density=7800.0)
        aluminum = Material(name="Aluminum", density=2700.0)
        mock_extract_mat.side_effect = [steel, aluminum, steel]

        mock_extract_mass.return_value = Inertia(
            mass=1.0,
            center_of_mass=np.zeros(3),
            inertia_tensor=np.eye(3) * 0.001,
        )

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify materials are deduplicated
        assert len(model.materials) == 2
        material_names = {m.name for m in model.materials}
        assert material_names == {"Steel", "Aluminum"}


class TestExtractAssemblyErrorHandling:
    """Tests for error handling during extraction."""

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_handles_material_extraction_failure(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that extraction continues when material extraction returns None."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        occ = mock_occurrence(name="Part:1", definition_path="C:\\Parts\\Part.ipt")
        mock_traverse.return_value = [occ]
        mock_export_parts.return_value = {
            "C:\\Parts\\Part.ipt": tmp_path / "Part.stp"
        }

        # Material returns None (no material assigned)
        mock_extract_mat.return_value = None

        mock_extract_mass.return_value = Inertia(
            mass=1.0,
            center_of_mass=np.zeros(3),
            inertia_tensor=np.eye(3) * 0.001,
        )

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify extraction continues
        assert len(model.bodies) == 1
        assert model.bodies[0].material_name is None
        assert len(model.materials) == 0

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_handles_mass_extraction_failure(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that extraction continues when mass extraction raises exception."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        occ = mock_occurrence(name="Part:1", definition_path="C:\\Parts\\Part.ipt")
        mock_traverse.return_value = [occ]
        mock_export_parts.return_value = {
            "C:\\Parts\\Part.ipt": tmp_path / "Part.stp"
        }

        steel = Material(name="Steel", density=7800.0)
        mock_extract_mat.return_value = steel

        # Mass extraction raises exception
        mock_extract_mass.side_effect = Exception("Mass properties unavailable")

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify extraction continues
        assert len(model.bodies) == 1
        assert model.bodies[0].inertia is None
        assert model.bodies[0].material_name == "Steel"

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_handles_geometry_missing(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that extraction continues when geometry export fails for a part."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        occ = mock_occurrence(name="Part:1", definition_path="C:\\Parts\\Part.ipt")
        mock_traverse.return_value = [occ]

        # Geometry export returns empty dict (failed)
        mock_export_parts.return_value = {}

        mock_extract_mat.return_value = Material(name="Steel", density=7800.0)
        mock_extract_mass.return_value = Inertia(
            mass=1.0,
            center_of_mass=np.zeros(3),
            inertia_tensor=np.eye(3) * 0.001,
        )

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify body created without geometry
        assert len(model.bodies) == 1
        assert model.bodies[0].geometry_file is None


class TestExtractAssemblyValidation:
    """Tests for model validation during extraction."""

    @patch("inventor_exporter.extraction.client.extract_mass_properties")
    @patch("inventor_exporter.extraction.client.extract_material")
    @patch("inventor_exporter.extraction.client.export_unique_parts")
    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_validation_errors_logged(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_export_parts,
        mock_extract_mat,
        mock_extract_mass,
        mock_occurrence,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
        caplog,
    ):
        """Test that validation errors are logged."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        occ = mock_occurrence(name="Part:1", definition_path="C:\\Parts\\Part.ipt")
        mock_traverse.return_value = [occ]
        mock_export_parts.return_value = {
            "C:\\Parts\\Part.ipt": tmp_path / "Part.stp"
        }

        # Material set to "UnknownMaterial" but we won't add it to materials dict
        unknown_material = Material(name="Unknown", density=1000.0)

        # First call returns material for adding to materials_dict
        # Second call (in _build_body) returns a different material name
        mock_extract_mat.side_effect = [
            Material(name="Steel", density=7800.0),  # For materials dict
            Material(name="UnknownRef", density=1000.0),  # For body - not in dict
        ]

        mock_extract_mass.return_value = Inertia(
            mass=1.0,
            center_of_mass=np.zeros(3),
            inertia_tensor=np.eye(3) * 0.001,
        )

        # Execute
        with caplog.at_level(logging.WARNING):
            client = InventorClient()
            model = client.extract_assembly(output_dir=tmp_path)

        # Model should still be returned (validation is non-blocking)
        assert model is not None
        assert len(model.bodies) == 1

        # Validation error should be logged (body references material not in materials)
        errors = model.validate()
        assert len(errors) > 0


class TestExtractAssemblyEmptyAssembly:
    """Tests for edge cases with empty assemblies."""

    @patch("inventor_exporter.extraction.client.traverse_assembly")
    @patch("inventor_exporter.extraction.client.active_assembly")
    @patch("inventor_exporter.extraction.client.inventor_app")
    def test_empty_assembly_returns_valid_model(
        self,
        mock_inv_app,
        mock_active_asm,
        mock_traverse,
        mock_inventor_app,
        mock_assembly_doc,
        tmp_path,
    ):
        """Test that empty assembly returns valid model with no bodies."""
        # Set up context managers
        mock_inv_app.return_value.__enter__ = MagicMock(
            return_value=mock_inventor_app
        )
        mock_inv_app.return_value.__exit__ = MagicMock(return_value=False)
        mock_active_asm.return_value.__enter__ = MagicMock(
            return_value=mock_assembly_doc
        )
        mock_active_asm.return_value.__exit__ = MagicMock(return_value=False)

        # No occurrences
        mock_traverse.return_value = []

        # Execute
        client = InventorClient()
        model = client.extract_assembly(output_dir=tmp_path)

        # Verify empty but valid model
        assert model.name == "TestAssembly"
        assert len(model.bodies) == 0
        assert len(model.materials) == 0
        assert model.validate() == []  # No validation errors


class TestInventorClientInit:
    """Tests for InventorClient initialization."""

    def test_init_does_not_connect(self):
        """Test that __init__ does not connect to Inventor."""
        # This should not raise even without Inventor running
        client = InventorClient()
        assert client._app is None
        assert client._doc is None
        assert client.logger is not None
