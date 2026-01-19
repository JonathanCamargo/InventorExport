"""COM connection management for Autodesk Inventor.

This module provides context managers for connecting to Inventor and accessing
assembly documents with proper lifecycle management.

Python's garbage collector doesn't deterministically release COM objects,
leading to memory leaks and stale references. Context managers ensure COM
objects are released even on exceptions, preventing "object disconnected"
errors and memory growth.

Example:
    from inventor_exporter.core.com import inventor_app, active_assembly

    with inventor_app() as app:
        print(f"Connected to Inventor {app.SoftwareVersion.DisplayVersion}")
        with active_assembly(app) as doc:
            print(f"Assembly: {doc.DisplayName}")
            print(f"Parts: {doc.ComponentDefinition.Occurrences.Count}")
"""

import logging
from contextlib import contextmanager
from typing import Any, Generator

import pythoncom
import win32com.client


class InventorNotRunningError(Exception):
    """Raised when Inventor is not running.

    This error indicates that GetActiveObject could not find a running
    instance of Inventor. Start Inventor before running the exporter.
    """

    pass


class NotAssemblyError(Exception):
    """Raised when active document is not an assembly.

    This error indicates either:
    - No document is open in Inventor
    - The active document is a part or drawing, not an assembly

    Open an assembly document before running the exporter.
    """

    pass


@contextmanager
def inventor_app() -> Generator[Any, None, None]:
    """Context manager for Inventor application connection.

    Connects to a running Inventor instance and ensures proper cleanup
    of the COM reference when the context exits (normally or via exception).

    Yields:
        Inventor.Application COM object

    Raises:
        InventorNotRunningError: If Inventor is not running

    Example:
        with inventor_app() as app:
            doc = app.ActiveDocument
            print(doc.DisplayName)
    """
    logger = logging.getLogger(__name__)
    app = None
    try:
        logger.debug("Connecting to Inventor...")
        app = win32com.client.GetActiveObject("Inventor.Application")
        logger.debug(f"Connected to Inventor {app.SoftwareVersion.DisplayVersion}")
        yield app
    except pythoncom.com_error as e:
        # MK_E_UNAVAILABLE: The object is not running
        if e.hresult == -2147221021:
            raise InventorNotRunningError(
                "Inventor is not running. Please start Inventor and open an assembly."
            ) from e
        raise
    finally:
        if app is not None:
            logger.debug("Releasing Inventor connection")
            del app


@contextmanager
def active_assembly(app: Any) -> Generator[Any, None, None]:
    """Context manager for active assembly document.

    Retrieves the currently active document from Inventor and verifies
    it is an assembly document. Ensures proper cleanup of the COM
    reference when the context exits.

    Document type constants (from Inventor API):
        - kPartDocumentObject = 12290
        - kAssemblyDocumentObject = 12291
        - kDrawingDocumentObject = 12292

    Args:
        app: Inventor.Application COM object (from inventor_app context)

    Yields:
        AssemblyDocument COM object

    Raises:
        NotAssemblyError: If no document is open or it's not an assembly

    Example:
        with inventor_app() as app:
            with active_assembly(app) as doc:
                print(f"Parts: {doc.ComponentDefinition.Occurrences.Count}")
    """
    doc = app.ActiveDocument
    if doc is None:
        raise NotAssemblyError("No document is open in Inventor")

    # kAssemblyDocumentObject = 12291
    if doc.DocumentType != 12291:
        raise NotAssemblyError(
            f"Active document is not an assembly (type={doc.DocumentType})"
        )

    try:
        yield doc
    finally:
        del doc
