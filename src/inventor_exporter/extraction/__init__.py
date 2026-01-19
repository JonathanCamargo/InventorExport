"""Extraction package - Inventor COM API data extraction.

This package provides functions to extract assembly data from Inventor
via the COM API. The extracted data populates the intermediate representation
(IR) defined in the model package.

Functions:
    traverse_assembly: Walk assembly hierarchy, return all leaf occurrences
    extract_transform: Convert Inventor Matrix to Transform dataclass
    export_step: Export document to STEP format via TranslatorAddIn
    export_unique_parts: Export STEP for unique parts (deduplicated)

Classes:
    OccurrenceData: Data holder for a single leaf occurrence

Constants:
    STEP_TRANSLATOR_GUID: GUID for STEP TranslatorAddIn
    AP203, AP214, AP242: Application Protocol types for STEP export
"""

from inventor_exporter.extraction.assembly import (
    OccurrenceData,
    extract_transform,
    traverse_assembly,
)
from inventor_exporter.extraction.geometry import (
    AP203,
    AP214,
    AP242,
    STEP_TRANSLATOR_GUID,
    export_step,
    export_unique_parts,
)

__all__ = [
    "traverse_assembly",
    "extract_transform",
    "OccurrenceData",
    "STEP_TRANSLATOR_GUID",
    "AP203",
    "AP214",
    "AP242",
    "export_step",
    "export_unique_parts",
]
