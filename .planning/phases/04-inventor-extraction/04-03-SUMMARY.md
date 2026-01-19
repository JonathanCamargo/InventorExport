---
phase: 04-inventor-extraction
plan: 03
subsystem: extraction
tags: [material, mass, inertia, unit-conversion, COM]

dependency-graph:
  requires:
    - 02-01 (Material and Inertia dataclasses)
    - 01-01 (InventorUnits for length conversion)
  provides:
    - extract_material() for reading material density from parts
    - extract_mass_properties() for reading mass, CoM, inertia tensor
  affects:
    - 04-04 (will use material/mass in full extraction pipeline)
    - Phase 5 (CLI will invoke these functions)

tech-stack:
  added: []
  patterns:
    - Locale-agnostic property searching
    - COM collection iteration (1-indexed)
    - Unit conversion at extraction boundary

files:
  key-files:
    created:
      - src/inventor_exporter/extraction/material.py
      - src/inventor_exporter/extraction/mass.py
      - tests/test_extraction_properties.py
    modified:
      - src/inventor_exporter/extraction/__init__.py

decisions:
  - key: partial-name-matching
    choice: Use partial string matching for property names
    reason: Handles locale variations (Density/Dichte)
  - key: default-density-fallback
    choice: Return Material with 7800 kg/m^3 when density missing
    reason: Steel is common default; ensures Material is always valid
  - key: tensor-about-origin
    choice: Document that inertia is about coordinate origin, not CoM
    reason: Matches Inventor's XYZMomentsOfInertia behavior; use at_point() if needed

metrics:
  duration: ~5 minutes
  completed: 2026-01-19
---

# Phase 04 Plan 03: Material and Mass Extraction Summary

**One-liner:** Material density and full inertia tensor extraction from Inventor with automatic locale handling and unit conversion to SI.

## What Was Built

### Material Extraction (`extraction/material.py`)

```python
def extract_material(part_doc) -> Optional[Material]:
    """Extract material from ActiveMaterial.PhysicalPropertiesAsset."""
```

- Reads `ActiveMaterial.DisplayName` for material name
- Searches `PhysicalPropertiesAsset` for density property
- Handles locale variations: "Density" (EN), "Dichte" (DE)
- Converts kg/cm^3 to kg/m^3 (CM3_TO_M3 = 1,000,000)
- Graceful fallback to 7800 kg/m^3 when data missing

### Mass Property Extraction (`extraction/mass.py`)

```python
def extract_mass_properties(part_definition) -> Inertia:
    """Extract mass, center of mass, and inertia tensor."""
```

- Reads `MassProperties.Mass` (already in kg)
- Reads `MassProperties.CenterOfMass` (converts cm to m)
- Calls `XYZMomentsOfInertia()` for full 6-component tensor
- Constructs symmetric 3x3 matrix with off-diagonal terms
- Converts kg*cm^2 to kg*m^2 (CM2_TO_M2 = 0.0001)

### Unit Tests (`tests/test_extraction_properties.py`)

10 tests covering:
- Material extraction with density conversion
- German locale property name handling
- Missing material/property fallback behavior
- Mass/CoM extraction with unit conversion
- Inertia tensor symmetry verification
- Negative products of inertia handling

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Density fallback | 7800 kg/m^3 | Common steel value; ensures valid Material |
| Property search | Partial name match | Handles all locale variations |
| Tensor layout | Standard [Ixx,Ixy,Ixz;...] | Matches numpy convention |
| pywin32 handling | Tuple unpacking | XYZMomentsOfInertia returns tuple, not ByRef |

## Key Unit Conversions

| Property | Inventor Units | Output Units | Factor |
|----------|---------------|--------------|--------|
| Density | kg/cm^3 | kg/m^3 | x 1,000,000 |
| Center of mass | cm | m | x 0.01 |
| Inertia | kg*cm^2 | kg*m^2 | x 0.0001 |

## Files Changed

| File | Change |
|------|--------|
| `src/inventor_exporter/extraction/material.py` | Created - extract_material() |
| `src/inventor_exporter/extraction/mass.py` | Created - extract_mass_properties() |
| `src/inventor_exporter/extraction/__init__.py` | Updated - export new functions |
| `tests/test_extraction_properties.py` | Created - 10 unit tests |

## Commits

| Hash | Message |
|------|---------|
| 2707129 | feat(04-03): implement material extraction from Inventor parts |
| af7c649 | feat(04-03): implement mass property extraction from Inventor parts |
| 135cef2 | test(04-03): add unit tests for material and mass extraction |
| f9b7694 | chore(04-03): export material and mass extraction from package |

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

**Blockers:** None

**Dependencies satisfied for 04-04:**
- Assembly traversal (04-01)
- Geometry export (04-02)
- Material extraction (04-03) - this plan
- All extraction functions exported from package

**Integration notes:**
- `extract_material(occ.part_document)` can be called on OccurrenceData
- `extract_mass_properties(occ.part_document.ComponentDefinition)` for inertia
- Both return model dataclasses directly for IR population
