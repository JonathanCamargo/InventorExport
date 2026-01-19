"""Extraction package - Inventor COM API data extraction.

This package provides functions to extract assembly data from Inventor
via the COM API. The extracted data populates the intermediate representation
(IR) defined in the model package.

Functions:
    traverse_assembly: Walk assembly hierarchy, return all leaf occurrences
    extract_transform: Convert Inventor Matrix to Transform dataclass
    extract_material: Extract material name and density from part
    extract_mass_properties: Extract mass, CoM, and inertia tensor from part

Classes:
    OccurrenceData: Data holder for a single leaf occurrence
"""

from inventor_exporter.extraction.assembly import (
    OccurrenceData,
    extract_transform,
    traverse_assembly,
)
from inventor_exporter.extraction.material import extract_material
from inventor_exporter.extraction.mass import extract_mass_properties

__all__ = [
    "traverse_assembly",
    "extract_transform",
    "OccurrenceData",
    "extract_material",
    "extract_mass_properties",
]
