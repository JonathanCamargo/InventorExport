---
phase: 06-additional-writers
plan: 01
subsystem: writers
tags: [mesh, step, stl, cadquery, lxml]
dependency-graph:
  requires: [03-01]
  provides: [mesh-conversion-infrastructure]
  affects: [06-02, 06-03, 06-04]
tech-stack:
  added: [lxml, cadquery]
  patterns: [lazy-import, caching]
key-files:
  created:
    - src/inventor_exporter/writers/mesh_converter.py
  modified:
    - pyproject.toml
decisions:
  - Binary STL over ASCII (smaller files)
  - CadQuery over PythonOCC (pip installable)
  - Caching by mesh name
metrics:
  duration: 5 minutes
  completed: 2026-01-20
---

# Phase 6 Plan 1: Mesh Conversion Infrastructure Summary

**One-liner:** CadQuery-based STEP to binary STL converter with caching and graceful fallback for missing dependency.

## What Was Built

### 1. Dependencies Added (pyproject.toml)

Added two new dependencies:
- `lxml>=4.9` - XML generation and schema validation for URDF/SDF/MuJoCo writers
- `cadquery>=2.2` - STEP to STL mesh conversion using OpenCASCADE backend

### 2. Mesh Converter Module (mesh_converter.py)

Created `src/inventor_exporter/writers/mesh_converter.py` with:

**`convert_step_to_stl()` function:**
- Converts single STEP file to binary STL
- Configurable mesh quality via `tolerance` and `angular_tolerance`
- Clear error messages for missing files or import failures

**`MeshConverter` class:**
- Batch conversion with path management
- Creates `meshes/` subdirectory automatically
- Caches converted meshes by name (avoids redundant work)
- Returns relative paths suitable for XML file references
- `convert(step_path, mesh_name)` - converts and returns relative path
- `get_mesh_path(mesh_name)` - returns path for XML reference

**Graceful dependency handling:**
- `CADQUERY_AVAILABLE` flag set at import time
- Clear error message if cadquery not installed when conversion attempted
- Module still imports successfully without cadquery (for testing)

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 475e472 | chore | add lxml and cadquery dependencies |
| c486929 | feat | add STEP to STL mesh converter module |

## Key Code Snippets

### Graceful CadQuery Import

```python
try:
    import cadquery as cq
    CADQUERY_AVAILABLE = True
except ImportError:
    CADQUERY_AVAILABLE = False
```

### MeshConverter Usage Pattern

```python
from inventor_exporter.writers.mesh_converter import MeshConverter

converter = MeshConverter(Path("output"), mesh_subdir="meshes")
rel_path = converter.convert(Path("parts/bracket.step"), "bracket")
# Returns Path("meshes/bracket.stl") - relative path for XML reference
```

## Verification Results

1. **Dependencies install:** `pip install -e .[dev]` succeeded
   - lxml 6.0.2 installed
   - cadquery 2.6.1 installed (with cadquery-ocp backend)

2. **Module imports:** Verified with:
   ```bash
   python -c "from inventor_exporter.writers.mesh_converter import MeshConverter, convert_step_to_stl, CADQUERY_AVAILABLE"
   ```
   - All symbols exported correctly
   - CADQUERY_AVAILABLE = True

3. **Tests pass:** All 78 existing tests pass (no regressions)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Binary STL (not ASCII) | 5-10x smaller file sizes per RESEARCH.md |
| CadQuery over PythonOCC | pip installable, cleaner API, RESEARCH.md recommendation |
| Caching by mesh name | Avoid redundant conversions when same part appears multiple times |
| Lazy import error | Module usable for testing even without cadquery |
| Default tolerance 0.1 | Reasonable balance of quality vs file size |

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

This plan provides mesh conversion infrastructure required by:
- **06-02**: URDF writer (uses `<mesh filename="meshes/part.stl"/>`)
- **06-03**: SDF writer (uses `<uri>meshes/part.stl</uri>`)
- **06-04**: MuJoCo writer (uses `<mesh file="part.stl"/>` in assets)

All downstream plans can now import and use `MeshConverter` for geometry export.
