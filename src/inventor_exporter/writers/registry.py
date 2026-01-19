"""WriterRegistry for format writer discovery and lookup.

This module provides a central registry for format writers with
decorator-based self-registration.
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Type

if TYPE_CHECKING:
    from inventor_exporter.writers.protocol import FormatWriter

logger = logging.getLogger(__name__)


class WriterRegistry:
    """Central registry for format writers.

    Provides registration and lookup of format writers by name.
    Writers register using the @WriterRegistry.register decorator.

    Thread Safety: The registry is populated at import time. After
    initial registration, it is read-only and thread-safe.

    Example:
        @WriterRegistry.register("myformat")
        class MyWriter:
            format_name = "myformat"
            file_extension = ".mf"
            def write(self, model, path): ...

        # Later:
        writer_cls = WriterRegistry.get("myformat")
        writer = writer_cls()
        writer.write(model, output_path)
    """

    _writers: Dict[str, Type["FormatWriter"]] = {}

    @classmethod
    def register(cls, format_name: str):
        """Decorator to register a writer class.

        Args:
            format_name: The name to register under (case-insensitive).

        Returns:
            Decorator function that registers the class.

        Example:
            @WriterRegistry.register("adams")
            class AdamsWriter:
                ...
        """

        def decorator(writer_class: Type["FormatWriter"]) -> Type["FormatWriter"]:
            key = format_name.lower()
            if key in cls._writers:
                logger.warning(f"Overwriting existing writer for format '{key}'")
            cls._writers[key] = writer_class
            logger.debug(f"Registered writer for format '{key}'")
            return writer_class

        return decorator

    @classmethod
    def get(cls, format_name: str) -> Optional[Type["FormatWriter"]]:
        """Get a writer class by format name.

        Args:
            format_name: The format name to look up (case-insensitive).

        Returns:
            The writer class, or None if not found.
        """
        return cls._writers.get(format_name.lower())

    @classmethod
    def list_formats(cls) -> List[str]:
        """List all registered format names.

        Returns:
            Sorted list of format names.
        """
        return sorted(cls._writers.keys())

    @classmethod
    def get_or_raise(cls, format_name: str) -> Type["FormatWriter"]:
        """Get a writer class, raising if not found.

        Args:
            format_name: The format name to look up.

        Returns:
            The writer class.

        Raises:
            KeyError: If format is not registered.
        """
        writer_cls = cls.get(format_name)
        if writer_cls is None:
            available = ", ".join(cls.list_formats()) or "(none)"
            raise KeyError(
                f"Unknown format '{format_name}'. Available formats: {available}"
            )
        return writer_cls
