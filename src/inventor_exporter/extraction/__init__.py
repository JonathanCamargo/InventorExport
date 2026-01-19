"""Extraction package - Inventor COM API data extraction.

This package provides functions to extract assembly data from Inventor
via the COM API. The extracted data populates the intermediate representation
(IR) defined in the model package.

Functions:
    traverse_assembly: Walk assembly hierarchy, return all leaf occurrences
    extract_transform: Convert Inventor Matrix to Transform dataclass

Classes:
    OccurrenceData: Data holder for a single leaf occurrence
"""

from inventor_exporter.extraction.assembly import (
    traverse_assembly,
    extract_transform,
    OccurrenceData,
)

__all__ = [
    "traverse_assembly",
    "extract_transform",
    "OccurrenceData",
]
