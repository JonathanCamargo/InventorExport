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
        click.echo("Connecting to Inventor...")
        client = InventorClient()
        model = client.extract_assembly(output_dir=output_path.parent)

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
