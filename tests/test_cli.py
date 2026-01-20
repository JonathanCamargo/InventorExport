"""Tests for CLI module.

Tests verify all CLI requirements (CLI-01 through CLI-05) are met:
- CLI-01: User can run from command line
- CLI-02: Format validation
- CLI-03: Output path handling
- CLI-04: Error messages
- CLI-05: List formats
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path

from inventor_exporter.cli import main
from inventor_exporter.core.com import InventorNotRunningError, NotAssemblyError


@pytest.fixture
def runner():
    """Create CliRunner for testing."""
    return CliRunner()


class TestListFormats:
    """Tests for --list-formats flag (CLI-05)."""

    def test_list_formats_shows_available_formats(self, runner):
        """--list-formats shows registered formats and exits."""
        result = runner.invoke(main, ['--list-formats'])

        assert result.exit_code == 0
        assert 'Available formats:' in result.output
        assert 'adams' in result.output.lower()

    def test_list_formats_exits_without_requiring_other_options(self, runner):
        """--list-formats works without --format or --output."""
        result = runner.invoke(main, ['--list-formats'])

        assert result.exit_code == 0
        # Should NOT show "Missing option" errors
        assert 'Missing option' not in result.output


class TestRequiredOptions:
    """Tests for required options validation."""

    def test_missing_format_shows_error(self, runner):
        """Missing --format shows usage error."""
        result = runner.invoke(main, ['--output', 'test.cmd'])

        assert result.exit_code == 2  # UsageError
        assert 'Missing option' in result.output or 'format' in result.output.lower()

    def test_missing_output_shows_error(self, runner):
        """Missing --output shows usage error."""
        result = runner.invoke(main, ['--format', 'adams'])

        assert result.exit_code == 2  # UsageError
        assert 'Missing option' in result.output or 'output' in result.output.lower()

    def test_missing_all_options_shows_error(self, runner):
        """Missing all options shows usage error."""
        result = runner.invoke(main, [])

        assert result.exit_code == 2


class TestFormatValidation:
    """Tests for format option validation (CLI-02)."""

    def test_invalid_format_shows_valid_choices(self, runner):
        """Invalid format shows error with available choices."""
        result = runner.invoke(main, ['--format', 'invalid', '--output', 'test.txt'])

        assert result.exit_code == 2
        # Click Choice shows available options in error
        assert 'adams' in result.output.lower()

    def test_format_is_case_insensitive(self, runner):
        """Format option is case-insensitive."""
        # This test verifies Click's case_sensitive=False works
        # We mock the actual export to avoid needing Inventor
        with patch('inventor_exporter.cli.InventorClient') as mock_client:
            mock_model = MagicMock()
            mock_client.return_value.extract_assembly.return_value = mock_model

            with patch('inventor_exporter.cli.get_writer') as mock_get_writer:
                mock_writer = MagicMock()
                mock_get_writer.return_value = mock_writer

                result = runner.invoke(main, ['--format', 'ADAMS', '--output', 'test.cmd'])

                # Should not fail format validation
                assert result.exit_code == 0 or 'Invalid value' not in result.output


class TestVersionOption:
    """Tests for --version flag."""

    def test_version_shows_version_number(self, runner):
        """--version shows version and exits."""
        result = runner.invoke(main, ['--version'])

        assert result.exit_code == 0
        assert '0.1.0' in result.output


class TestInventorErrors:
    """Tests for Inventor connection error handling (CLI-04)."""

    def test_inventor_not_running_shows_clear_error(self, runner):
        """Shows clear error when Inventor is not running."""
        with patch('inventor_exporter.cli.InventorClient') as mock_client:
            mock_client.return_value.extract_assembly.side_effect = InventorNotRunningError()

            result = runner.invoke(main, ['--format', 'adams', '--output', 'test.cmd'])

            assert result.exit_code == 1
            assert 'Inventor is not running' in result.output

    def test_not_assembly_shows_clear_error(self, runner):
        """Shows clear error when no assembly is open."""
        with patch('inventor_exporter.cli.InventorClient') as mock_client:
            mock_client.return_value.extract_assembly.side_effect = NotAssemblyError()

            result = runner.invoke(main, ['--format', 'adams', '--output', 'test.cmd'])

            assert result.exit_code == 1
            assert 'assembly' in result.output.lower()


class TestSuccessfulExport:
    """Tests for successful export path (CLI-01, CLI-03)."""

    def test_successful_export_prints_output_path(self, runner, tmp_path):
        """Successful export prints confirmation with output path."""
        output_file = tmp_path / "model.cmd"

        with patch('inventor_exporter.cli.InventorClient') as mock_client:
            mock_model = MagicMock()
            mock_model.name = "TestAssembly"
            mock_client.return_value.extract_assembly.return_value = mock_model

            with patch('inventor_exporter.cli.get_writer') as mock_get_writer:
                mock_writer = MagicMock()
                mock_get_writer.return_value = mock_writer

                result = runner.invoke(main, [
                    '--format', 'adams',
                    '--output', str(output_file)
                ])

                assert result.exit_code == 0
                assert 'Exported to' in result.output
                mock_client.return_value.extract_assembly.assert_called_once()
                mock_writer.write.assert_called_once()

    def test_creates_output_directory_if_needed(self, runner, tmp_path):
        """Creates parent directory for output file if it doesn't exist."""
        output_file = tmp_path / "subdir" / "model.cmd"

        with patch('inventor_exporter.cli.InventorClient') as mock_client:
            mock_model = MagicMock()
            mock_client.return_value.extract_assembly.return_value = mock_model

            with patch('inventor_exporter.cli.get_writer') as mock_get_writer:
                mock_writer = MagicMock()
                mock_get_writer.return_value = mock_writer

                result = runner.invoke(main, [
                    '--format', 'adams',
                    '--output', str(output_file)
                ])

                assert result.exit_code == 0
                # Directory should have been created
                assert output_file.parent.exists()


class TestHelpOutput:
    """Tests for help text."""

    def test_help_shows_description(self, runner):
        """--help shows command description."""
        result = runner.invoke(main, ['--help'])

        assert result.exit_code == 0
        assert 'Export' in result.output
        assert 'Inventor' in result.output

    def test_help_shows_all_options(self, runner):
        """--help shows all options."""
        result = runner.invoke(main, ['--help'])

        assert '--format' in result.output
        assert '--output' in result.output
        assert '--list-formats' in result.output
        assert '--version' in result.output
        assert '--help' in result.output
