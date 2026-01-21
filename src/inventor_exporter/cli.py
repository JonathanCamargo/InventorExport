"""Command-line interface for inventor-exporter."""

import logging
import click
from pathlib import Path

from inventor_exporter import __version__
from inventor_exporter.core.com import InventorNotRunningError, NotAssemblyError
from inventor_exporter.extraction import InventorClient
from inventor_exporter.writers import WriterRegistry, get_writer


def setup_logging(verbose: bool):
    """Configure logging for CLI output."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(message)s',
    )


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
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed extraction progress.'
)
@click.version_option(version=__version__)
def main(format: str, output: str, verbose: bool):
    """Export Autodesk Inventor assembly to simulation format.

    Connects to a running Inventor instance and exports the active
    assembly document to the specified format.

    Example:

        inventorexport --format adams --output model.cmd
    """
    setup_logging(verbose)
    output_path = Path(output)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Extract assembly from Inventor
        click.echo("Connecting to Inventor...")
        client = InventorClient()
        click.echo("Extracting assembly...")
        model = client.extract_assembly(output_dir=output_path.parent)

        # Show extraction summary
        click.echo(f"  Found {len(model.bodies)} bodies, {len(model.materials)} materials")
        geometry_count = sum(1 for b in model.bodies if b.geometry_file is not None)
        click.echo(f"  Exported {geometry_count} STEP files")

        # Get writer and export
        click.echo(f"Writing {format} format...")
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


if __name__ == '__main__':
    main()
