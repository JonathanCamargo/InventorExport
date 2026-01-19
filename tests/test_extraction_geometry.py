"""Unit tests for STEP geometry export.

Tests use mocked COM objects to verify correct TranslatorAddIn usage
without requiring Inventor to be installed or running.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from inventor_exporter.extraction.geometry import (
    STEP_TRANSLATOR_GUID,
    AP203,
    AP214,
    AP242,
    export_step,
    export_unique_parts,
    _sanitize_filename,
)


class TestStepTranslatorConstants:
    """Test STEP translator constants."""

    def test_step_translator_guid(self):
        """STEP_TRANSLATOR_GUID should match official Inventor GUID."""
        assert STEP_TRANSLATOR_GUID == "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"

    def test_protocol_constants(self):
        """Protocol constants should match Inventor API values."""
        assert AP203 == 2  # Configuration Controlled Design
        assert AP214 == 3  # Automotive Design
        assert AP242 == 5  # Managed model based 3D engineering


class TestSanitizeFilename:
    """Test filename sanitization."""

    def test_sanitizes_colons(self):
        """Colons should be replaced with underscores."""
        assert _sanitize_filename("Part:1") == "Part_1"

    def test_sanitizes_spaces(self):
        """Spaces should be replaced with underscores."""
        assert _sanitize_filename("Part Name") == "Part_Name"

    def test_sanitizes_multiple_special_chars(self):
        """Multiple special characters should become single underscore."""
        assert _sanitize_filename("Part:1 Assembly") == "Part_1_Assembly"

    def test_sanitizes_windows_invalid_chars(self):
        """Windows invalid filename chars should be replaced."""
        assert _sanitize_filename('Part<>:"/\\|?*') == "Part"

    def test_removes_consecutive_underscores(self):
        """Consecutive underscores should collapse to one."""
        assert _sanitize_filename("Part::1") == "Part_1"

    def test_strips_leading_trailing_underscores(self):
        """Leading/trailing underscores should be stripped."""
        assert _sanitize_filename(":Part:") == "Part"

    def test_returns_default_for_empty(self):
        """Empty result should return 'part' as default."""
        assert _sanitize_filename(":::") == "part"

    def test_handles_normal_name(self):
        """Normal names should pass through unchanged."""
        assert _sanitize_filename("ValidPartName123") == "ValidPartName123"


class TestExportStep:
    """Test export_step function."""

    @pytest.fixture
    def mock_app(self):
        """Create mock Inventor Application."""
        app = MagicMock()
        translator = MagicMock()
        app.ApplicationAddIns.ItemById.return_value = translator
        app.TransientObjects.CreateTranslationContext.return_value = MagicMock()
        app.TransientObjects.CreateNameValueMap.return_value = MagicMock()
        app.TransientObjects.CreateDataMedium.return_value = MagicMock()
        return app

    @pytest.fixture
    def mock_document(self):
        """Create mock document."""
        return MagicMock()

    @patch('inventor_exporter.extraction.geometry.win32com.client.CastTo')
    def test_export_step_calls_translator(self, mock_castto, mock_app, mock_document, tmp_path):
        """export_step should get translator by GUID and call SaveCopyAs."""
        mock_translator = MagicMock()
        mock_translator.HasSaveCopyAsOptions.return_value = True
        mock_castto.return_value = mock_translator

        output_path = tmp_path / "test.stp"
        result = export_step(mock_app, mock_document, output_path)

        # Should get translator by GUID
        mock_app.ApplicationAddIns.ItemById.assert_called_once_with(
            STEP_TRANSLATOR_GUID
        )

        # Should cast to TranslatorAddIn interface
        mock_castto.assert_called_once()
        args, kwargs = mock_castto.call_args
        assert args[1] == "TranslatorAddIn"

        # Should call SaveCopyAs
        mock_translator.SaveCopyAs.assert_called_once()

        # Should return True on success
        assert result is True

    @patch('inventor_exporter.extraction.geometry.win32com.client.CastTo')
    def test_export_step_sets_ap214_by_default(self, mock_castto, mock_app, mock_document, tmp_path):
        """export_step should set AP214 protocol by default."""
        mock_translator = MagicMock()
        mock_translator.HasSaveCopyAsOptions.return_value = True
        mock_castto.return_value = mock_translator

        options = MagicMock()
        mock_app.TransientObjects.CreateNameValueMap.return_value = options

        output_path = tmp_path / "test.stp"
        export_step(mock_app, mock_document, output_path)

        # Should set ApplicationProtocolType to AP214 (3)
        assert options.Value.__setitem__.called
        call_args = options.Value.__setitem__.call_args
        assert call_args[0] == ("ApplicationProtocolType", AP214)

    @patch('inventor_exporter.extraction.geometry.win32com.client.CastTo')
    def test_export_step_sets_custom_protocol(self, mock_castto, mock_app, mock_document, tmp_path):
        """export_step should use custom protocol when specified."""
        mock_translator = MagicMock()
        mock_translator.HasSaveCopyAsOptions.return_value = True
        mock_castto.return_value = mock_translator

        options = MagicMock()
        mock_app.TransientObjects.CreateNameValueMap.return_value = options

        output_path = tmp_path / "test.stp"
        export_step(mock_app, mock_document, output_path, protocol=AP242)

        # Should set ApplicationProtocolType to AP242 (5)
        assert options.Value.__setitem__.called
        call_args = options.Value.__setitem__.call_args
        assert call_args[0] == ("ApplicationProtocolType", AP242)

    @patch('inventor_exporter.extraction.geometry.win32com.client.CastTo')
    def test_export_step_sets_output_path(self, mock_castto, mock_app, mock_document, tmp_path):
        """export_step should set output filename in data medium."""
        mock_translator = MagicMock()
        mock_translator.HasSaveCopyAsOptions.return_value = True
        mock_castto.return_value = mock_translator

        data_medium = MagicMock()
        mock_app.TransientObjects.CreateDataMedium.return_value = data_medium

        output_path = tmp_path / "test.stp"
        export_step(mock_app, mock_document, output_path)

        # Should set FileName on data medium
        assert data_medium.FileName == str(output_path)

    @patch('inventor_exporter.extraction.geometry.win32com.client.CastTo')
    def test_export_step_handles_error(self, mock_castto, mock_app, mock_document, tmp_path):
        """export_step should return False and log on error."""
        mock_castto.side_effect = Exception("COM error")

        output_path = tmp_path / "test.stp"
        result = export_step(mock_app, mock_document, output_path)

        assert result is False


def _make_mock_occurrence(definition_path: str, part_name: str):
    """Create a mock occurrence with proper attribute access.

    Note: MagicMock(name=...) sets the mock's repr name, not a .name attribute.
    We need to configure the mock or set the attribute after creation.
    """
    mock = MagicMock()
    mock.definition_path = definition_path
    mock.part_document = MagicMock()
    mock.name = part_name  # Set as attribute, not constructor arg
    return mock


class TestExportUniqueParts:
    """Test export_unique_parts function."""

    @pytest.fixture
    def mock_app(self):
        """Create mock Inventor Application."""
        app = MagicMock()
        return app

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_deduplicates_by_definition_path(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should export once per unique definition_path."""
        # Create 3 occurrences, 2 with same definition_path
        occurrences = [
            _make_mock_occurrence("C:\\parts\\part1.ipt", "Part1:1"),
            _make_mock_occurrence("C:\\parts\\part1.ipt", "Part1:2"),  # Duplicate
            _make_mock_occurrence("C:\\parts\\part2.ipt", "Part2:1"),  # Different
        ]

        mock_export.return_value = True

        result = export_unique_parts(mock_app, occurrences, tmp_path)

        # Should only call export_step twice (not 3 times)
        assert mock_export.call_count == 2

        # Should return 2 entries
        assert len(result) == 2
        assert "C:\\parts\\part1.ipt" in result
        assert "C:\\parts\\part2.ipt" in result

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_sanitizes_filename(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should use sanitized filename."""
        occurrences = [
            _make_mock_occurrence("C:\\parts\\part.ipt", "Part:1 Assembly"),
        ]

        mock_export.return_value = True

        result = export_unique_parts(mock_app, occurrences, tmp_path)

        # Should call export_step with sanitized filename
        call_args = mock_export.call_args
        output_path = call_args[0][2]  # Third positional arg
        assert ":" not in output_path.name
        assert " " not in output_path.name
        assert output_path.name == "Part_1_Assembly.stp"

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_handles_dict_occurrences(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should work with dict-like occurrences."""
        occurrences = [
            {
                'definition_path': "C:\\parts\\part1.ipt",
                'part_document': MagicMock(),
                'name': "Part1"
            },
        ]

        mock_export.return_value = True

        result = export_unique_parts(mock_app, occurrences, tmp_path)

        assert mock_export.call_count == 1
        assert len(result) == 1

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_creates_output_directory(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should create output directory if needed."""
        nested_dir = tmp_path / "nested" / "output"
        occurrences = [
            _make_mock_occurrence("C:\\parts\\part.ipt", "Part"),
        ]

        mock_export.return_value = True

        export_unique_parts(mock_app, occurrences, nested_dir)

        assert nested_dir.exists()

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_handles_export_failure(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should not include failed exports in result."""
        occurrences = [
            _make_mock_occurrence("C:\\parts\\part1.ipt", "Part1"),
            _make_mock_occurrence("C:\\parts\\part2.ipt", "Part2"),
        ]

        # First succeeds, second fails
        mock_export.side_effect = [True, False]

        result = export_unique_parts(mock_app, occurrences, tmp_path)

        # Only successful export should be in result
        assert len(result) == 1
        assert "C:\\parts\\part1.ipt" in result
        assert "C:\\parts\\part2.ipt" not in result

    @patch('inventor_exporter.extraction.geometry.export_step')
    def test_handles_filename_collision(self, mock_export, mock_app, tmp_path):
        """export_unique_parts should handle filename collisions."""
        # Two different parts that would sanitize to same filename
        occurrences = [
            _make_mock_occurrence("C:\\parts\\part1.ipt", "Part:1"),
            _make_mock_occurrence("C:\\parts\\part2.ipt", "Part 1"),  # Sanitizes to same
        ]

        mock_export.return_value = True

        result = export_unique_parts(mock_app, occurrences, tmp_path)

        # Both should be exported with different names
        assert len(result) == 2
        paths = list(result.values())
        assert paths[0] != paths[1]  # Different output paths
