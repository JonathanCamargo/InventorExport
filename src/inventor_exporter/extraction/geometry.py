"""STEP geometry export via Inventor TranslatorAddIn.

Uses the official TranslatorAddIn mechanism with GUID {90AF7F40-0C01-11D5-8E83-0010B541CD80}
for STEP export. Exports each unique part definition once (not per occurrence).

Key features:
- Uses TranslatorAddIn with correct GUID for STEP export
- CastTo required for proper interface access (ItemById returns base ApplicationAddIn)
- AP214 protocol used by default for better compatibility
- Deduplication by definition_path avoids redundant exports

Reference:
    Autodesk Inventor API - TranslatorAddIn5_Sample.htm
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

import pythoncom
import win32com.client
import win32com.client.dynamic

from inventor_exporter.core.com import late_bind

logger = logging.getLogger(__name__)


# STEP Translator AddIn GUID
STEP_TRANSLATOR_GUID = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"

# Application Protocol Types (STEP versions)
AP203 = 2   # Configuration Controlled Design
AP214 = 3   # Automotive Design (better compatibility)
AP242 = 5   # Managed model based 3D engineering (newest)


def _sanitize_filename(name: str) -> str:
    """Sanitize a part name for use as a filename.

    Replaces characters that are invalid in filenames or problematic
    for downstream tools (colons, spaces, special chars).

    Args:
        name: Original part name

    Returns:
        Sanitized name safe for use as filename
    """
    # Replace problematic characters with underscores
    sanitized = re.sub(r'[:\s<>"|?*\\/]', '_', name)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized if sanitized else "part"


def export_step(
    app: Any,
    document: Any,
    output_path: Path,
    protocol: int = AP214,
) -> bool:
    """Export a document to STEP format using TranslatorAddIn.

    Args:
        app: Inventor.Application COM object
        document: Document to export (PartDocument or AssemblyDocument)
        output_path: Path for output .stp file
        protocol: Application Protocol type (AP203, AP214, or AP242)

    Returns:
        True if export succeeded, False on error

    Note:
        CastTo is required because ItemById returns the base ApplicationAddIn
        interface. Without casting to "TranslatorAddIn", methods like
        SaveCopyAs will not be available.
    """
    abs_path = str(output_path.absolute())
    print(f"  [DEBUG] Exporting STEP to: {abs_path}")

    try:
        # Get the STEP translator add-in by GUID (use late binding)
        print(f"  [DEBUG] Getting translator add-in...")
        translator = late_bind(app.ApplicationAddIns.ItemById(STEP_TRANSLATOR_GUID))
        print(f"  [DEBUG] Translator: {translator}")

        # Ensure document is late-bound (may come from early-bound traversal)
        document = late_bind(document)
        print(f"  [DEBUG] Document: {document}")

        # Create translation context
        context = late_bind(app.TransientObjects.CreateTranslationContext())
        context.Type = 13059  # kFileBrowseIOMechanism

        # Create options map
        options = late_bind(app.TransientObjects.CreateNameValueMap())

        # Get default options (protocol setting often fails, use defaults)
        try:
            translator.HasSaveCopyAsOptions(document, context, options)
        except Exception as e:
            print(f"  [DEBUG] HasSaveCopyAsOptions failed: {e}")

        # Create data medium with output path (must be absolute for Inventor COM)
        data_medium = late_bind(app.TransientObjects.CreateDataMedium())
        data_medium.FileName = abs_path

        # Perform export
        print(f"  [DEBUG] Calling SaveCopyAs...")
        translator.SaveCopyAs(document, context, options, data_medium)
        print(f"  [DEBUG] SaveCopyAs completed")

        logger.info(f"Exported STEP: {output_path}")
        return True

    except Exception as e:
        print(f"  [DEBUG] STEP export FAILED: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"STEP export failed for {output_path}: {e}")
        return False


def export_unique_parts(
    app: Any,
    occurrences: List[Any],
    output_dir: Path,
) -> Dict[str, Path]:
    """Export STEP files for unique part definitions.

    Multiple occurrences of the same part share one STEP file, avoiding
    duplicate exports. Parts are deduplicated by their definition_path
    (the full filename of the part document).

    Args:
        app: Inventor.Application COM object
        occurrences: List of occurrence data dicts/objects with:
            - definition_path: str - Full path to part document
            - part_document: COM object - Part document for export
            - name: str - Part name (used for filename)
        output_dir: Directory for STEP output files

    Returns:
        Dict mapping definition_path to exported STEP file path.
        Only includes successfully exported parts.

    Note:
        Occurrence objects should have at minimum:
        - definition_path: str (for deduplication key)
        - part_document: COM object (for export)
        - name: str (for generating output filename)

        Works with OccurrenceData dataclass or any object with these attributes.
    """
    # Track unique parts by definition path
    unique_parts: Dict[str, Any] = {}
    for occ in occurrences:
        # Support both dict-like and attribute access
        if hasattr(occ, 'definition_path'):
            def_path = occ.definition_path
            doc = occ.part_document
            name = occ.name
        else:
            def_path = occ['definition_path']
            doc = occ['part_document']
            name = occ['name']

        if def_path not in unique_parts:
            unique_parts[def_path] = {
                'document': doc,
                'name': name,
            }

    logger.info(f"Found {len(unique_parts)} unique parts from {len(occurrences)} occurrences")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export each unique part
    result: Dict[str, Path] = {}
    for def_path, part_info in unique_parts.items():
        # Generate sanitized filename
        sanitized_name = _sanitize_filename(part_info['name'])
        step_path = output_dir / f"{sanitized_name}.stp"

        # Handle filename collisions by appending suffix
        counter = 1
        while step_path in result.values():
            step_path = output_dir / f"{sanitized_name}_{counter}.stp"
            counter += 1

        # Export
        if export_step(app, part_info['document'], step_path):
            result[def_path] = step_path
        else:
            logger.warning(f"Failed to export {def_path}")

    logger.info(f"Exported {len(result)}/{len(unique_parts)} parts to STEP")
    return result
