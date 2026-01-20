"""Writers package - format writers for exporting AssemblyModel.

This package provides:
    - FormatWriter: Protocol defining the writer interface
    - WriterRegistry: Central registry for format lookup
    - get_writer(): Convenience function to get writer by name

Built-in writers are auto-registered when this package is imported.

Example:
    from inventor_exporter.writers import get_writer

    writer = get_writer("adams")
    writer.write(model, Path("output.cmd"))
"""

from inventor_exporter.writers.protocol import FormatWriter
from inventor_exporter.writers.registry import WriterRegistry

# Import built-in writers to trigger registration
from inventor_exporter.writers import adams  # noqa: F401
from inventor_exporter.writers import urdf  # noqa: F401


def get_writer(format_name: str) -> FormatWriter:
    """Get an instantiated writer by format name.

    Args:
        format_name: The format name (e.g., 'adams').

    Returns:
        Instantiated writer ready to use.

    Raises:
        KeyError: If format is not registered.
    """
    writer_cls = WriterRegistry.get_or_raise(format_name)
    return writer_cls()


__all__ = [
    "FormatWriter",
    "WriterRegistry",
    "get_writer",
]
