# Phase 5: CLI Integration - Research

**Researched:** 2026-01-20
**Domain:** Click CLI framework, command-line interface design, pyproject.toml entry points
**Confidence:** HIGH

## Summary

This phase integrates the existing InventorClient extraction and WriterRegistry/get_writer() infrastructure into a user-facing command-line interface using Click 8.x. The existing codebase already provides all the core functionality - the CLI's job is to wire up user input to these APIs and provide clear error messages.

The architecture is straightforward: a single command entry point that accepts `--format`, `--output`, and `--list-formats` options. Click's built-in Choice type integrates naturally with the WriterRegistry.list_formats() method to validate format selection. The main complexity lies in translating Python exceptions (InventorNotRunningError, NotAssemblyError, KeyError from registry) into user-friendly error messages with appropriate exit codes.

**Primary recommendation:** Create a single cli.py module with one `@click.command()` decorated function that orchestrates InventorClient.extract_assembly() and get_writer().write() with proper Click exception handling for clear error messages.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| click | >=8.1 | CLI framework | Official Click documentation recommends it; decorative API, automatic help generation, built-in testing support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| click.testing.CliRunner | (included) | CLI test runner | Testing all CLI commands without spawning processes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| click | argparse | argparse is stdlib but more verbose; Click's decorator API is more maintainable |
| click | typer | Typer builds on Click with type hints; adds dependency for marginal benefit here |

**Installation:**
```bash
pip install "click>=8.1"
```

**pyproject.toml addition:**
```toml
dependencies = [
    "pywin32>=306",
    "scipy>=1.11",
    "numpy>=1.24",
    "click>=8.1",
]

[project.scripts]
inventorexport = "inventor_exporter.cli:main"
```

## Architecture Patterns

### Recommended Project Structure
```
src/inventor_exporter/
    cli.py          # Single module containing main() and click command
    __main__.py     # Enables `python -m inventor_exporter`
```

### Pattern 1: Single Command with Options
**What:** One `@click.command()` decorated function with `@click.option()` decorators for flags
**When to use:** Simple CLIs without subcommand hierarchy (this project)
**Example:**
```python
# Source: Click Documentation 8.3.x - Options
import click

@click.command()
@click.option('--format', '-f',
              type=click.Choice(['adams', 'urdf', 'mujoco'], case_sensitive=False),
              required=True,
              help='Output format')
@click.option('--output', '-o',
              type=click.Path(dir_okay=False, writable=True),
              required=True,
              help='Output file path')
@click.option('--list-formats', is_flag=True, is_eager=True,
              expose_value=False, callback=list_formats_callback,
              help='List available output formats and exit')
@click.version_option(version='0.1.0')
def main(format: str, output: str):
    """Export Autodesk Inventor assemblies to simulation formats."""
    pass
```

### Pattern 2: Eager Flag with Callback for --list-formats
**What:** Use `is_eager=True` and a callback to handle flags that print and exit
**When to use:** Options like --version, --list-formats that don't require other params
**Example:**
```python
# Source: Click Documentation 8.3.x - Advanced Patterns
def list_formats_callback(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    from inventor_exporter.writers import WriterRegistry
    formats = WriterRegistry.list_formats()
    click.echo("Available formats:")
    for fmt in formats:
        click.echo(f"  {fmt}")
    ctx.exit()

@click.option('--list-formats', is_flag=True, is_eager=True,
              expose_value=False, callback=list_formats_callback,
              help='List available formats and exit')
```

### Pattern 3: Exception-to-ClickException Translation
**What:** Catch domain exceptions and re-raise as click.ClickException for user-friendly errors
**When to use:** Translating library exceptions to CLI error messages
**Example:**
```python
# Source: Click Documentation 8.3.x - Exception Handling
from inventor_exporter.core.com import InventorNotRunningError, NotAssemblyError

try:
    model = client.extract_assembly(output_dir)
except InventorNotRunningError:
    raise click.ClickException(
        "Inventor is not running. Please start Inventor and open an assembly."
    )
except NotAssemblyError:
    raise click.ClickException(
        "No assembly document is open. Please open an assembly in Inventor."
    )
```

### Pattern 4: __main__.py for python -m Support
**What:** Enable running package as `python -m inventor_exporter`
**When to use:** All CLI packages should support this
**Example:**
```python
# src/inventor_exporter/__main__.py
from inventor_exporter.cli import main

if __name__ == "__main__":
    main()
```

### Anti-Patterns to Avoid
- **Don't put business logic in CLI module:** CLI should only orchestrate; keep export logic in extraction/writers
- **Don't catch all exceptions:** Let unexpected errors bubble up with full traceback for debugging
- **Don't use click.echo() for logging:** Use the existing logging module; click.echo() is for user output
- **Don't hardcode format list:** Use WriterRegistry.list_formats() for dynamic discovery

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Argument parsing | Custom sys.argv parsing | click decorators | Click handles edge cases (quoted strings, =, etc.) |
| Format validation | if/elif checking | click.Choice | Automatic error messages with valid options |
| Help generation | Manually written --help | Click auto-help | Stays in sync with actual options |
| File path validation | os.path.exists checks | click.Path | Cross-platform, handles permissions |
| Exit codes | sys.exit(1) everywhere | click.ClickException | Consistent exit code 1, formatted output |
| Version option | Custom --version handling | @click.version_option() | Standard implementation |

**Key insight:** Click provides all the CLI infrastructure; your code should only contain domain logic and exception translation.

## Common Pitfalls

### Pitfall 1: Dynamic Choice from Registry at Import Time
**What goes wrong:** `click.Choice(WriterRegistry.list_formats())` is evaluated at module import time, before writers are registered
**Why it happens:** Decorators are evaluated when module is imported, not when command runs
**How to avoid:** Either ensure writers are imported before CLI module, or use callback validation instead of Choice
**Warning signs:** Empty format list or KeyError for valid formats

**Solution pattern:**
```python
# In cli.py - ensure writers are registered first
from inventor_exporter.writers import WriterRegistry  # This imports adams, etc.

# Now Choice will have the formats
@click.option('--format', type=click.Choice(WriterRegistry.list_formats(), case_sensitive=False))
```

### Pitfall 2: Missing Exit on Eager Flags
**What goes wrong:** --list-formats prints formats but then continues to require --format and --output
**Why it happens:** Callback doesn't call ctx.exit()
**How to avoid:** Always call ctx.exit() after handling eager flags
**Warning signs:** "Missing required option" error after --list-formats output

### Pitfall 3: Forgetting resilient_parsing Check
**What goes wrong:** --list-formats causes errors during shell completion
**Why it happens:** Shell completion parses args without executing; callback runs anyway
**How to avoid:** Check `if not value or ctx.resilient_parsing: return` at callback start
**Warning signs:** Tab completion errors or hangs

### Pitfall 4: Exit Code Confusion
**What goes wrong:** All errors return exit code 1, making automation difficult
**Why it happens:** Using generic exceptions instead of specific Click exception types
**How to avoid:** Use ClickException (exit 1) for user errors, let unexpected errors propagate (exit 1 but with traceback)
**Warning signs:** Scripts can't distinguish error types

### Pitfall 5: Blocking on Missing Inventor Without Clear Message
**What goes wrong:** Generic COM error instead of clear "Inventor not running" message
**Why it happens:** Not catching InventorNotRunningError specifically
**How to avoid:** Explicitly catch and translate InventorNotRunningError
**Warning signs:** Cryptic "pywintypes.com_error" in output

## Code Examples

Verified patterns from official sources:

### Complete CLI Module Structure
```python
# src/inventor_exporter/cli.py
# Source: Click Documentation 8.3.x
"""Command-line interface for inventor-exporter."""

import click
from pathlib import Path

from inventor_exporter import __version__
from inventor_exporter.core.com import InventorNotRunningError, NotAssemblyError
from inventor_exporter.extraction import InventorClient
from inventor_exporter.writers import WriterRegistry, get_writer


def list_formats_callback(ctx, param, value):
    """Callback for --list-formats flag."""
    if not value or ctx.resilient_parsing:
        return
    formats = WriterRegistry.list_formats()
    if formats:
        click.echo("Available formats:")
        for fmt in formats:
            click.echo(f"  {fmt}")
    else:
        click.echo("No formats registered.")
    ctx.exit()


@click.command()
@click.option(
    '--format', '-f',
    type=click.Choice(WriterRegistry.list_formats(), case_sensitive=False),
    required=True,
    help='Output format (e.g., adams, urdf, mujoco).'
)
@click.option(
    '--output', '-o',
    type=click.Path(dir_okay=False),
    required=True,
    help='Output file path.'
)
@click.option(
    '--list-formats',
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=list_formats_callback,
    help='List available output formats and exit.'
)
@click.version_option(version=__version__)
def main(format: str, output: str):
    """Export Autodesk Inventor assembly to simulation format.

    Connects to a running Inventor instance and exports the active
    assembly document to the specified format.

    Example:

        inventorexport --format adams --output model.cmd
    """
    output_path = Path(output)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Extract assembly from Inventor
        client = InventorClient()
        model = client.extract_assembly(output_dir=output_path.parent)

        # Get writer and export
        writer = get_writer(format)
        writer.write(model, output_path)

        click.echo(f"Exported to {output_path}")

    except InventorNotRunningError:
        raise click.ClickException(
            "Inventor is not running. Please start Inventor and open an assembly."
        )
    except NotAssemblyError:
        raise click.ClickException(
            "No assembly document is open in Inventor. Please open an assembly."
        )
    except KeyError as e:
        # From WriterRegistry.get_or_raise - shouldn't happen with Choice validation
        raise click.ClickException(str(e))
    except Exception as e:
        # Log unexpected errors but re-raise for traceback
        raise click.ClickException(f"Export failed: {e}")


if __name__ == '__main__':
    main()
```

### __main__.py for Module Execution
```python
# src/inventor_exporter/__main__.py
# Source: Python Packaging User Guide
"""Enable running as python -m inventor_exporter."""

from inventor_exporter.cli import main

if __name__ == "__main__":
    main()
```

### Testing with CliRunner
```python
# tests/test_cli.py
# Source: Click Documentation 8.3.x - Testing
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from inventor_exporter.cli import main


@pytest.fixture
def runner():
    return CliRunner()


def test_list_formats(runner):
    """--list-formats shows available formats and exits."""
    result = runner.invoke(main, ['--list-formats'])
    assert result.exit_code == 0
    assert 'adams' in result.output.lower()


def test_missing_required_options(runner):
    """Missing --format or --output shows usage error."""
    result = runner.invoke(main, [])
    assert result.exit_code == 2  # UsageError
    assert 'Missing option' in result.output


def test_invalid_format(runner):
    """Invalid format shows available choices."""
    result = runner.invoke(main, ['--format', 'invalid', '--output', 'out.txt'])
    assert result.exit_code == 2
    assert 'invalid' in result.output.lower()
    assert 'adams' in result.output.lower()  # Shows valid choices


def test_inventor_not_running(runner):
    """Shows clear error when Inventor not running."""
    with patch('inventor_exporter.cli.InventorClient') as mock_client:
        from inventor_exporter.core.com import InventorNotRunningError
        mock_client.return_value.extract_assembly.side_effect = InventorNotRunningError()

        result = runner.invoke(main, ['--format', 'adams', '--output', 'out.cmd'])

        assert result.exit_code == 1
        assert 'Inventor is not running' in result.output


def test_version(runner):
    """--version shows version and exits."""
    result = runner.invoke(main, ['--version'])
    assert result.exit_code == 0
    assert '0.1.0' in result.output
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| setup.py entry_points | pyproject.toml [project.scripts] | 2021 (PEP 621) | Cleaner configuration |
| argparse stdlib | Click framework | N/A (preference) | More maintainable CLI code |
| Manual --help text | Click auto-generated help | N/A | Help always matches actual options |

**Deprecated/outdated:**
- setup.py console_scripts: Still works but pyproject.toml is preferred
- Click 7.x: Click 8.x has better type hints and Choice handling

## Open Questions

Things that couldn't be fully resolved:

1. **Geometry output directory separate from format output**
   - What we know: InventorClient.extract_assembly() requires output_dir for STEP files
   - What's unclear: Should STEP files go in same directory as format output, or separate?
   - Recommendation: Use output path's parent directory for STEP files (keeps related files together)

2. **Verbose/quiet output modes**
   - What we know: Click supports --verbose flags easily
   - What's unclear: Is verbose output needed for Phase 5 scope?
   - Recommendation: Defer to later phase; current logging infrastructure can be wired up if needed

## Sources

### Primary (HIGH confidence)
- [Click Documentation 8.3.x - Entry Points](https://click.palletsprojects.com/en/stable/entry-points/) - pyproject.toml setup, cli function structure
- [Click Documentation 8.3.x - Options](https://click.palletsprojects.com/en/stable/options/) - Option decorators, Choice, Path types
- [Click Documentation 8.3.x - Exception Handling](https://click.palletsprojects.com/en/stable/exceptions/) - ClickException, exit codes
- [Click Documentation 8.3.x - Testing](https://click.palletsprojects.com/en/stable/testing/) - CliRunner, Result object
- [Click Documentation 8.3.x - Advanced Patterns](https://click.palletsprojects.com/en/stable/advanced/) - Eager parameters, callbacks

### Secondary (MEDIUM confidence)
- [Python Packaging User Guide - Command Line Tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) - pyproject.toml scripts section
- [Real Python - Click CLI Apps](https://realpython.com/python-click/) - Best practices, module structure

### Tertiary (LOW confidence)
- [GitHub pallets/click #928](https://github.com/pallets/click/issues/928) - Dynamic Choice discussion (workarounds, not official feature)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Click is well-documented and stable; pyproject.toml scripts is PEP 621 standard
- Architecture: HIGH - Single command pattern is directly from Click docs; existing codebase architecture is clear
- Pitfalls: HIGH - Based on Click documentation and common issues from GitHub discussions

**Research date:** 2026-01-20
**Valid until:** 90 days (Click 8.x is stable; patterns unlikely to change)
