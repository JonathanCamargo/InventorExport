---
phase: 04-inventor-extraction
plan: 04
subsystem: extraction
tags: [inventor, com, orchestrator, client, assembly-model]

# Dependency graph
requires:
  - phase: 04-inventor-extraction-01
    provides: traverse_assembly, extract_transform, OccurrenceData
  - phase: 04-inventor-extraction-02
    provides: export_unique_parts for STEP geometry
  - phase: 04-inventor-extraction-03
    provides: extract_material, extract_mass_properties

provides:
  - InventorClient class as single entry point for extraction
  - extract_assembly() returns complete AssemblyModel
  - Error handling for partial extraction on failures

affects:
  - 05-cli-integration (CLI will use InventorClient)
  - Phase 6 (format writers consume AssemblyModel from client)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Context manager composition for COM lifecycle
    - Dictionary deduplication for materials by name
    - Graceful degradation on extraction failures

key-files:
  created:
    - src/inventor_exporter/extraction/client.py
    - tests/test_extraction_client.py
  modified:
    - src/inventor_exporter/extraction/__init__.py

key-decisions:
  - "Material deduplication by name: Multiple occurrences may use same material"
  - "Partial extraction: Continue building model when individual parts fail"
  - "Validation logging: Log errors but return model anyway"
  - "Context manager composition: inventor_app() wraps active_assembly()"

patterns-established:
  - "Orchestrator pattern: Client composes extraction functions"
  - "Error isolation: Try/except around each extraction step"
  - "Progress logging: Log count/total during iteration"

# Metrics
duration: 7min
completed: 2026-01-19
---

# Phase 04 Plan 04: InventorClient Orchestrator Summary

**High-level extraction orchestrator combining assembly traversal, STEP export, material and mass extraction into complete AssemblyModel with graceful error handling**

## Performance

- **Duration:** 7 min
- **Started:** 2026-01-19T23:30:00Z
- **Completed:** 2026-01-19T23:37:00Z
- **Tasks:** 3
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- InventorClient class as single entry point for all extraction
- extract_assembly() orchestrates full pipeline from Inventor to AssemblyModel
- Material deduplication by name (multiple occurrences share materials)
- Graceful error handling - extraction continues when individual parts fail
- 8 integration tests with fully mocked COM (no Inventor dependency)
- Test count increased from 56 to 64

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement InventorClient orchestrator** - `c90cf5b` (feat)
2. **Task 2: Update package exports** - `70ba645` (chore)
3. **Task 3: Add integration tests** - `817829a` (test)

## Files Created/Modified

| File | Change |
|------|--------|
| `src/inventor_exporter/extraction/client.py` | Created - InventorClient class with extract_assembly() |
| `src/inventor_exporter/extraction/__init__.py` | Modified - Added InventorClient to exports |
| `tests/test_extraction_client.py` | Created - 8 integration tests |

## API Design

### InventorClient Usage

```python
from inventor_exporter.extraction import InventorClient
from pathlib import Path

client = InventorClient()
model = client.extract_assembly(output_dir=Path("./output"))

# Model is validated automatically
errors = model.validate()
if errors:
    print("Validation warnings:", errors)
```

### Extraction Pipeline

```
extract_assembly(output_dir)
    |
    +-- inventor_app() context manager
    |       |
    |       +-- active_assembly(app) context manager
    |               |
    |               +-- traverse_assembly(doc) -> [OccurrenceData]
    |               |
    |               +-- export_unique_parts(app, occs, dir) -> {path: Path}
    |               |
    |               +-- extract_material(doc) -> Material (for each unique)
    |               |
    |               +-- extract_mass_properties(def) -> Inertia (per occ)
    |               |
    |               +-- Build Body for each occurrence
    |               |
    |               +-- Build AssemblyModel with bodies + materials
    |               |
    |               +-- model.validate() -> log warnings
    |
    +-- Return AssemblyModel
```

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Material deduplication | By name string | Same material may appear on multiple parts |
| Error handling | Log and continue | Partial model better than no model |
| Validation timing | After assembly | All data available for cross-validation |
| Geometry reference | Path from geometry_map | definition_path is dedup key |

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Test Coverage

| Test | Description |
|------|-------------|
| test_extract_assembly_builds_complete_model | Full flow with 2 occurrences |
| test_extract_assembly_deduplicates_materials | 3 occs, 2 materials |
| test_handles_material_extraction_failure | Returns None |
| test_handles_mass_extraction_failure | Raises exception |
| test_handles_geometry_missing | Empty geometry map |
| test_validation_errors_logged | Invalid material ref |
| test_empty_assembly_returns_valid_model | Zero occurrences |
| test_init_does_not_connect | Lazy connection |

## Next Phase Readiness

**Phase 4 Extraction Complete:**
- 04-01: Assembly traversal
- 04-02: STEP geometry export
- 04-03: Material and mass extraction
- 04-04: InventorClient orchestrator (this plan)

**Ready for Phase 5 (CLI Integration):**
- InventorClient provides single import for CLI
- AssemblyModel ready for format writers
- 64 total tests passing
- All extraction functions tested with mocked COM

---
*Phase: 04-inventor-extraction*
*Completed: 2026-01-19*
