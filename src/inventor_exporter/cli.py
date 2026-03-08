"""Command-line interface for inventor-exporter."""

import logging
import click
from pathlib import Path

from inventor_exporter import __version__
from inventor_exporter.core.com import InventorNotRunningError, NotAssemblyError
from inventor_exporter.extraction import InventorClient
from inventor_exporter.importing import import_stl_folder
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

        # Show geometry files
        geometry_files = [b.geometry_file for b in model.bodies if b.geometry_file is not None]
        missing_geometry = [b.name for b in model.bodies if b.geometry_file is None]

        if geometry_files:
            click.echo(f"  Exported {len(set(geometry_files))} STEP files to {output_path.parent.absolute()}")
            if verbose:
                for gf in sorted(set(geometry_files)):
                    click.echo(f"    - {gf.name}")
        else:
            click.echo("  No STEP files exported (geometry export failed)")

        if verbose and missing_geometry:
            click.echo(f"  Bodies without geometry: {', '.join(missing_geometry)}")

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


@click.command()
@click.argument(
    'input_dir',
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
)
@click.option(
    '--output', '-o',
    type=click.Path(file_okay=False),
    default=None,
    help='Output directory for IPT files. Defaults to input directory.'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Show detailed conversion progress.'
)
@click.version_option(version=__version__)
def import_cmd(input_dir: str, output: str | None, verbose: bool):
    """Import STL files from a folder and convert to Inventor IPT.

    Opens each STL file in Inventor, converts the mesh to a base feature,
    deletes the original mesh, and saves as .ipt with the same name.

    Example:

        inventorimport ./stl_files --output ./ipt_files
    """
    setup_logging(verbose)
    input_path = Path(input_dir)
    output_path = Path(output) if output else None

    try:
        click.echo(f"Scanning {input_path} for STL files...")
        created = import_stl_folder(input_path, output_path)

        if created:
            click.echo(f"Converted {len(created)} STL files to IPT:")
            for ipt in created:
                click.echo(f"  {ipt.name}")
        else:
            click.echo("No STL files found.")

    except InventorNotRunningError:
        raise click.ClickException(
            "Inventor is not running. Please start Inventor."
        )


if __name__ == '__main__':
    main()
