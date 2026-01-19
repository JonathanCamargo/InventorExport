"""Unit tests for assembly traversal and transform extraction.

Since we cannot run Inventor in tests, COM objects are mocked.
"""

from unittest.mock import MagicMock, PropertyMock

import numpy as np
import pytest

from inventor_exporter.extraction import (
    OccurrenceData,
    extract_transform,
    traverse_assembly,
)
from inventor_exporter.model import Transform


def mock_inventor_matrix(translation_cm, rotation_3x3=None):
    """Create a mock Inventor Matrix COM object.

    Args:
        translation_cm: Tuple of (x, y, z) translation in centimeters
        rotation_3x3: 3x3 numpy array for rotation, or None for identity

    Returns:
        MagicMock with Cell(row, col) method returning appropriate values
    """
    if rotation_3x3 is None:
        rotation_3x3 = np.eye(3)

    def cell(row, col):
        # Inventor Matrix.Cell() uses 1-based indexing
        # Rotation is in upper-left 3x3
        if row <= 3 and col <= 3:
            return rotation_3x3[row - 1, col - 1]
        # Translation is in row 4, columns 1-3
        if row == 4 and col <= 3:
            return translation_cm[col - 1]
        # Cell(4,4) is 1 for homogeneous coordinates
        if row == 4 and col == 4:
            return 1.0
        # Column 4, rows 1-3 are 0
        return 0.0

    matrix = MagicMock()
    matrix.Cell = MagicMock(side_effect=cell)
    return matrix


def mock_occurrence(name, translation_cm, rotation_3x3=None, doc_path="C:\\parts\\part.ipt"):
    """Create a mock ComponentOccurrence COM object.

    Args:
        name: Occurrence name
        translation_cm: Tuple of (x, y, z) translation in centimeters
        rotation_3x3: 3x3 numpy array for rotation, or None for identity
        doc_path: Full file path to the part document

    Returns:
        MagicMock occurrence with Transformation, Definition, Name properties
    """
    matrix = mock_inventor_matrix(translation_cm, rotation_3x3)

    occ = MagicMock()
    occ.Name = name
    occ.Transformation = matrix

    # Mock the definition and document hierarchy
    occ.Definition.Document.FullFileName = doc_path
    occ.Definition.Document = MagicMock()
    occ.Definition.Document.FullFileName = doc_path

    return occ


class TestExtractTransform:
    """Tests for extract_transform function."""

    def test_extract_transform_identity(self):
        """Identity matrix should produce zero position and identity rotation."""
        occ = mock_occurrence("part1", (0, 0, 0))

        result = extract_transform(occ)

        assert isinstance(result, Transform)
        np.testing.assert_array_almost_equal(result.position, [0, 0, 0])
        np.testing.assert_array_almost_equal(result.rotation, np.eye(3))

    def test_extract_transform_with_translation(self):
        """Translation in cm should be converted to meters."""
        # 100, 200, 300 cm = 1.0, 2.0, 3.0 meters
        occ = mock_occurrence("part1", (100, 200, 300))

        result = extract_transform(occ)

        np.testing.assert_array_almost_equal(result.position, [1.0, 2.0, 3.0])
        np.testing.assert_array_almost_equal(result.rotation, np.eye(3))

    def test_extract_transform_with_negative_translation(self):
        """Negative translations should be handled correctly."""
        # -50, 0, 150 cm = -0.5, 0, 1.5 meters
        occ = mock_occurrence("part1", (-50, 0, 150))

        result = extract_transform(occ)

        np.testing.assert_array_almost_equal(result.position, [-0.5, 0, 1.5])

    def test_extract_transform_with_90deg_z_rotation(self):
        """90-degree rotation about Z axis should be extracted correctly."""
        # 90 degrees about Z: [0, -1, 0], [1, 0, 0], [0, 0, 1]
        rotation_z90 = np.array([
            [0, -1, 0],
            [1, 0, 0],
            [0, 0, 1],
        ], dtype=float)

        occ = mock_occurrence("part1", (0, 0, 0), rotation_z90)

        result = extract_transform(occ)

        np.testing.assert_array_almost_equal(result.position, [0, 0, 0])
        np.testing.assert_array_almost_equal(result.rotation, rotation_z90)

    def test_extract_transform_combined(self):
        """Combined translation and rotation should both be extracted."""
        rotation_x90 = np.array([
            [1, 0, 0],
            [0, 0, -1],
            [0, 1, 0],
        ], dtype=float)

        occ = mock_occurrence("part1", (50, 100, 25), rotation_x90)

        result = extract_transform(occ)

        # 50, 100, 25 cm = 0.5, 1.0, 0.25 meters
        np.testing.assert_array_almost_equal(result.position, [0.5, 1.0, 0.25])
        np.testing.assert_array_almost_equal(result.rotation, rotation_x90)


class TestTraverseAssembly:
    """Tests for traverse_assembly function."""

    def test_traverse_assembly_empty(self):
        """Empty assembly should return empty list."""
        asm_doc = MagicMock()
        asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences.Count = 0

        result = traverse_assembly(asm_doc)

        assert result == []

    def test_traverse_assembly_single_part(self):
        """Single part assembly should return one OccurrenceData."""
        occ = mock_occurrence("part1", (100, 0, 0), doc_path="C:\\parts\\part1.ipt")

        # Mock the collection
        leaf_occs = MagicMock()
        leaf_occs.Count = 1
        leaf_occs.Item = MagicMock(return_value=occ)

        asm_doc = MagicMock()
        asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences = leaf_occs

        result = traverse_assembly(asm_doc)

        assert len(result) == 1
        assert isinstance(result[0], OccurrenceData)
        assert result[0].name == "part1"
        assert result[0].definition_path == "C:\\parts\\part1.ipt"
        np.testing.assert_array_almost_equal(result[0].transformation.position, [1.0, 0, 0])

    def test_traverse_assembly_multiple_parts(self):
        """Multiple parts should all be returned."""
        occs = [
            mock_occurrence("link1", (0, 0, 0), doc_path="C:\\parts\\link1.ipt"),
            mock_occurrence("link2", (100, 0, 0), doc_path="C:\\parts\\link2.ipt"),
            mock_occurrence("link3", (200, 0, 0), doc_path="C:\\parts\\link3.ipt"),
        ]

        # Mock the collection with proper Item() behavior
        leaf_occs = MagicMock()
        leaf_occs.Count = 3
        leaf_occs.Item = MagicMock(side_effect=lambda i: occs[i - 1])  # 1-indexed

        asm_doc = MagicMock()
        asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences = leaf_occs

        result = traverse_assembly(asm_doc)

        assert len(result) == 3
        assert result[0].name == "link1"
        assert result[1].name == "link2"
        assert result[2].name == "link3"

        # Verify positions
        np.testing.assert_array_almost_equal(result[0].transformation.position, [0, 0, 0])
        np.testing.assert_array_almost_equal(result[1].transformation.position, [1.0, 0, 0])
        np.testing.assert_array_almost_equal(result[2].transformation.position, [2.0, 0, 0])

    def test_traverse_assembly_preserves_document_reference(self):
        """Part document COM reference should be preserved for later use."""
        doc_mock = MagicMock()
        doc_mock.FullFileName = "C:\\parts\\special.ipt"

        occ = MagicMock()
        occ.Name = "special_part"
        occ.Transformation = mock_inventor_matrix((0, 0, 0))
        occ.Definition.Document = doc_mock
        occ.Definition.Document.FullFileName = "C:\\parts\\special.ipt"

        leaf_occs = MagicMock()
        leaf_occs.Count = 1
        leaf_occs.Item = MagicMock(return_value=occ)

        asm_doc = MagicMock()
        asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences = leaf_occs

        result = traverse_assembly(asm_doc)

        # The part_document should be the same mock object
        assert result[0].part_document is doc_mock


class TestOccurrenceData:
    """Tests for OccurrenceData dataclass."""

    def test_occurrence_data_creation(self):
        """OccurrenceData should store all fields correctly."""
        transform = Transform(position=np.array([1.0, 2.0, 3.0]))
        doc_mock = MagicMock()

        data = OccurrenceData(
            name="test_part",
            transformation=transform,
            definition_path="C:\\parts\\test.ipt",
            part_document=doc_mock,
        )

        assert data.name == "test_part"
        assert data.transformation is transform
        assert data.definition_path == "C:\\parts\\test.ipt"
        assert data.part_document is doc_mock
