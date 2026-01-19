"""FormatWriter Protocol definition.

This module defines the interface for format writers using Python's
Protocol for structural subtyping. Writers only need to implement
the required methods - no explicit inheritance is needed.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from inventor_exporter.model import AssemblyModel


@runtime_checkable
class FormatWriter(Protocol):
    """Protocol defining the format writer interface.

    Any class implementing these methods/properties satisfies the protocol.
    No explicit inheritance needed (structural subtyping).

    Example implementation:
        class MyWriter:
            format_name = "myformat"
            file_extension = ".mf"

            def write(self, model: AssemblyModel, output_path: Path) -> None:
                # Generate output...
                output_path.write_text(content)

    Attributes:
        format_name: Unique identifier for this format (e.g., 'adams', 'urdf').
        file_extension: File extension including dot (e.g., '.cmd', '.urdf').
    """

    @property
    def format_name(self) -> str:
        """Unique identifier for this format.

        Used by WriterRegistry for lookup. Lowercase recommended.
        Examples: 'adams', 'urdf', 'mujoco'
        """
        ...

    @property
    def file_extension(self) -> str:
        """File extension including dot.

        Examples: '.cmd', '.urdf', '.xml'
        """
        ...

    def write(self, model: "AssemblyModel", output_path: Path) -> None:
        """Write the assembly model to the specified path.

        Implementations should:
        1. Validate the model (model.validate())
        2. Convert units as needed for the format
        3. Generate format-specific content
        4. Write to output_path

        Args:
            model: Validated AssemblyModel to export.
            output_path: Destination file path. Parent directory must exist.

        Raises:
            ValueError: If model validation fails.
            IOError: If file cannot be written.
        """
        ...
