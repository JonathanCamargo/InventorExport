"""Assembly traversal and transform extraction from Inventor.

Uses AllLeafOccurrences for flat traversal - this property returns all leaf
parts at any nesting level with transformations already in assembly (world)
coordinates. No manual transform accumulation needed.

Key features:
- AllLeafOccurrences handles nested subassemblies automatically
- Transformation property includes all parent transforms
- Units are converted from Inventor cm to meters
"""

from dataclasses import dataclass
from typing import Any, List
import logging

import numpy as np

from inventor_exporter.core.rotation import extract_rotation_matrix
from inventor_exporter.core.units import InventorUnits
from inventor_exporter.model import Transform

logger = logging.getLogger(__name__)


@dataclass
class OccurrenceData:
    """Data extracted from a leaf occurrence in the assembly.

    Attributes:
        name: Occurrence name (unique within assembly)
        transformation: 6-DOF pose in world (assembly) frame
        definition_path: Full file path to the part document (for deduplication)
        part_document: COM reference to the part document (for material/mass extraction)
    """

    name: str
    transformation: Transform
    definition_path: str
    part_document: Any  # COM reference - Any since type varies at runtime


def extract_transform(occurrence) -> Transform:
    """Extract Transform from a ComponentOccurrence.

    The Transformation property of a leaf occurrence obtained via
    AllLeafOccurrences already includes all parent transformations.
    No manual accumulation needed.

    Args:
        occurrence: Inventor ComponentOccurrence COM object

    Returns:
        Transform dataclass with position (meters) and rotation matrix

    Note:
        Inventor Matrix.Cell(row, col) uses 1-based indexing.
        Translation is in column 4: Cell(1,4), Cell(2,4), Cell(3,4).
        Rotation is in upper-left 3x3: Cell(1..3, 1..3).
        Units are always cm regardless of document settings.
    """
    matrix = occurrence.Transformation

    # Dump full 4x4 matrix for debugging transform issues
    if logger.isEnabledFor(logging.DEBUG):
        name = getattr(occurrence, 'Name', '?')
        logger.debug(f"Transform matrix for {name}:")
        for r in range(1, 5):
            row = [matrix.Cell(r, c) for c in range(1, 5)]
            logger.debug(f"  Row {r}: [{row[0]:12.6f} {row[1]:12.6f} {row[2]:12.6f} {row[3]:12.6f}]")

    # Extract translation from column 4 (1-indexed)
    # Inventor internal units are cm
    x_cm = matrix.Cell(1, 4)
    y_cm = matrix.Cell(2, 4)
    z_cm = matrix.Cell(3, 4)

    # Convert to meters for IR
    position = np.array([
        InventorUnits.length_to_meters(x_cm),
        InventorUnits.length_to_meters(y_cm),
        InventorUnits.length_to_meters(z_cm),
    ])

    # Extract 3x3 rotation from upper-left portion
    rotation = extract_rotation_matrix(matrix)

    return Transform(position=position, rotation=rotation)


def traverse_assembly_recursive(asm_doc) -> List[OccurrenceData]:
    """Traverse assembly recursively to find ALL leaf parts.

    Unlike AllLeafOccurrences, this manually walks into each subassembly
    via SubOccurrences, which is more reliable for deeply nested assemblies.

    Args:
        asm_doc: Inventor AssemblyDocument COM object

    Returns:
        List of OccurrenceData for each leaf part found at any depth.
    """
    asm_def = asm_doc.ComponentDefinition
    occurrences = asm_def.Occurrences

    logger.info(
        "Starting recursive traversal (%d top-level occurrences)",
        occurrences.Count,
    )

    results: List[OccurrenceData] = []
    _recurse_occurrences(occurrences, results, depth=0)

    logger.info("Recursive traversal found %d leaf parts", len(results))
    return results


# Inventor document-type constants
_PART_DOC_TYPE = 12290       # kPartDocumentObject
_ASSEMBLY_DOC_TYPE = 12291   # kAssemblyDocumentObject


def _recurse_occurrences(occurrences, results: List[OccurrenceData], depth: int):
    """Walk an Occurrences or SubOccurrences collection."""
    try:
        count = occurrences.Count
    except Exception:
        return

    for i in range(1, count + 1):
        occ = None
        try:
            occ = occurrences.Item(i)

            # Skip suppressed occurrences
            try:
                if occ.Suppressed:
                    logger.debug("%sSkipping suppressed: %s", "  " * depth, occ.Name)
                    continue
            except Exception:
                pass

            occ_name = occ.Name

            try:
                doc_type = occ.DefinitionDocumentType
            except Exception:
                doc_type = _PART_DOC_TYPE  # assume leaf if unknown

            if doc_type == _PART_DOC_TYPE:
                # Leaf part
                try:
                    transform = extract_transform(occ)
                    definition_path = occ.Definition.Document.FullFileName
                    part_document = occ.Definition.Document

                    results.append(OccurrenceData(
                        name=occ_name,
                        transformation=transform,
                        definition_path=definition_path,
                        part_document=part_document,
                    ))
                    logger.debug("%sPart: %s", "  " * depth, occ_name)
                except Exception as e:
                    logger.warning(
                        "Failed to extract data for part %s: %s", occ_name, e
                    )

            elif doc_type == _ASSEMBLY_DOC_TYPE:
                # Subassembly - recurse
                logger.debug("%sSubassembly: %s", "  " * depth, occ_name)
                try:
                    sub_occs = occ.SubOccurrences
                    _recurse_occurrences(sub_occs, results, depth + 1)
                except Exception as e:
                    logger.warning(
                        "Failed to traverse subassembly %s: %s", occ_name, e
                    )
            else:
                logger.debug(
                    "%sSkipping %s (doc type %d)", "  " * depth, occ_name, doc_type
                )

        except Exception as e:
            logger.warning("Failed to process occurrence %d at depth %d: %s", i, depth, e)
        finally:
            if occ is not None:
                del occ


def traverse_assembly(asm_doc) -> List[OccurrenceData]:
    """Traverse assembly and extract data for all leaf occurrences.

    Uses AllLeafOccurrences to get all parts at any nesting level with
    their transformations already in assembly (world) coordinates.

    Args:
        asm_doc: Inventor AssemblyDocument COM object

    Returns:
        List of OccurrenceData for each leaf part in the assembly

    Note:
        COM references are deleted after processing each occurrence
        to prevent memory leaks during large assembly traversal.
    """
    asm_def = asm_doc.ComponentDefinition
    leaf_occs = asm_def.Occurrences.AllLeafOccurrences

    logger.info(f"Found {leaf_occs.Count} leaf occurrences")

    results: List[OccurrenceData] = []

    for i in range(1, leaf_occs.Count + 1):  # COM collections are 1-indexed
        occ = None
        try:
            occ = leaf_occs.Item(i)

            # Extract transform
            transform = extract_transform(occ)

            # Get definition document path (for deduplication)
            definition_path = occ.Definition.Document.FullFileName

            # Get part document reference (for material/mass extraction)
            part_document = occ.Definition.Document

            occurrence_data = OccurrenceData(
                name=occ.Name,
                transformation=transform,
                definition_path=definition_path,
                part_document=part_document,
            )
            results.append(occurrence_data)

            logger.debug(f"Processed {i}/{leaf_occs.Count}: {occ.Name}")

        finally:
            # Release COM reference to prevent memory leaks
            if occ is not None:
                del occ

    return results
