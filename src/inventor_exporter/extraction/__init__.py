"""Extraction package - Inventor data extraction.

This package provides functions and classes for extracting assembly data
from Autodesk Inventor via COM automation.

Classes:
    InventorClient: High-level orchestrator for complete assembly extraction.
    OccurrenceData: Data holder for a single leaf occurrence.

Functions:
    traverse_assembly: Walk assembly hierarchy, collect leaf occurrences.
    extract_transform: Get Transform from occurrence.
    export_step: Export single document to STEP format.
    export_unique_parts: Export STEP for unique part definitions.
    extract_material: Get Material from part document.
    extract_mass_properties: Get Inertia from part definition.

Constants:
    STEP_TRANSLATOR_GUID: GUID for STEP TranslatorAddIn.
    AP203, AP214, AP242: Application Protocol types for STEP export.
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
from inventor_exporter.extraction.mass import extract_mass_properties
from inventor_exporter.extraction.material import extract_material
from inventor_exporter.extraction.client import InventorClient

__all__ = [
    "InventorClient",
    "traverse_assembly",
    "extract_transform",
    "OccurrenceData",
    "export_step",
    "export_unique_parts",
    "STEP_TRANSLATOR_GUID",
    "AP203",
    "AP214",
    "AP242",
    "extract_material",
    "extract_mass_properties",
]
