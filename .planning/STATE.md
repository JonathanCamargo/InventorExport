# Project State: Inventor Assembly Exporter

## Project Reference

**Core Value:** Adding a new export format should only require implementing a format-specific writer

**Current Focus:** Phase 4 In Progress - Inventor Extraction (Plan 3 of 5 complete)

## Current Position

**Phase:** 4 of 6 (Inventor Extraction)
**Plan:** 3 of 5 complete
**Status:** In progress
**Last activity:** 2026-01-19 - Completed 04-03-PLAN.md (material and mass extraction)

**Progress:** [#########.] 10/12 plans complete (Phases 1-3, 04-01 to 04-03)

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed | 3/6 |
| Plans Completed | 10 (01-01, 01-02, 01-03, 02-01, 02-02, 03-01, 03-02, 04-01, 04-02, 04-03) |
| Requirements Done | 18/34 (INFRA-01-06, MODEL-01-06, WRITER-01-06) |
| Tests | 56 passing |

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase |
|----------|-----------|-------|
| Python over VBA | Better abstractions, testing, maintainability | Project |
| Plugin architecture | Core goal - easy format addition | Project |
| ETL pattern | Clean separation of extraction, model, writers | Roadmap |
| ADAMS first | Validates IR against known-good VBA output | Roadmap |
| src-layout package structure | Standard Python packaging, cleaner imports | 01-01 |
| dictConfig for logging | More flexible than basicConfig, file-configurable | 01-01 |
| NamedTuple for Position | Immutable, lightweight, attribute and index access | 01-01 |
| Class methods on InventorUnits | Stateless operations, no instance needed | 01-01 |
| scipy.spatial.transform for rotation | Handles gimbal lock gracefully, all conventions supported | 01-02 |
| Scalar-first quaternion (w,x,y,z) | MuJoCo convention | 01-02 |
| No explicit CoInitialize in context manager | Main thread auto-initializes COM | 01-03 |
| Delete COM refs in finally block | Deterministic cleanup, prevents memory leaks | 01-03 |
| Frozen dataclasses for model | Immutability ensures data integrity through pipeline | 02-01 |
| Inertia tensor at CoM | Standard physics convention; at_point() for body origin | 02-01 |
| Body name sanitization | Replace colons/spaces with underscores for format compatibility | 02-02 |
| Tuple collections in AssemblyModel | list in frozen dataclass still mutable; tuple is truly immutable | 02-02 |
| validate() returns all errors | Better UX - fix all issues in one pass | 02-02 |
| material_name ref not Material obj | Avoids circular deps; AssemblyModel owns lookup | 02-02 |
| Protocol over ABC | Structural subtyping, no inheritance needed | 03-01 |
| Class-level WriterRegistry | Simple, import-time registration | 03-01 |
| f-strings over templates | ADAMS output is simple; Jinja2 overkill | 03-02 |
| AllLeafOccurrences over manual recursion | Simpler, handles transform accumulation automatically | 04-01 |
| OccurrenceData holds COM reference | Allows later extraction of mass/material from same doc | 04-01 |
| definition_path for deduplication | Multiple occurrences may reference same part definition | 04-01 |
| TranslatorAddIn for STEP export | Native Inventor method; supports AP203/AP214/AP242 | 04-02 |
| AP214 as default STEP protocol | Best balance of geometry and metadata support | 04-02 |
| Partial name matching for density | Handles locale variations (Density/Dichte) | 04-03 |
| Default density fallback | 7800 kg/m^3 (steel) when properties missing | 04-03 |
| Tuple unpacking for XYZMomentsOfInertia | pywin32 returns tuple, not ByRef like VBA | 04-03 |

### Technical Notes

- pywin32 for COM automation (verify Python 3.13 compatibility before use)
- lxml for XML generation (URDF, MuJoCo)
- click for CLI framework
- dataclasses for intermediate representation
- scipy.spatial.transform for rotation math
- pytest for testing (56 tests passing)

### Unit Conversion Constants

| Constant | Value | Usage |
|----------|-------|-------|
| CM_TO_M | 0.01 | Length: cm to meters |
| CM_TO_MM | 10.0 | Length: cm to millimeters |
| CM3_TO_M3 | 1,000,000 | Density: kg/cm^3 to kg/m^3 |
| CM2_TO_M2 | 0.0001 | Inertia: kg*cm^2 to kg*m^2 |

### Research Flags

| Phase | Research Level | Notes |
|-------|----------------|-------|
| Phase 1 | LOW | Standard patterns - COMPLETE |
| Phase 2 | LOW | Mathematical transforms - COMPLETE |
| Phase 3 | LOW | VBA provides reference - COMPLETE |
| Phase 4 | MEDIUM | Verify Inventor COM API details - IN PROGRESS |
| Phase 5 | LOW | Standard click patterns |
| Phase 6 | MEDIUM | Verify current format specs |

### Critical Pitfalls (from research)

1. **COM lifecycle** - Use context managers, explicit cleanup, gc.collect()
2. **Euler angles** - Format-specific rotation orders; use scipy or verified implementations
3. **Unit conversion** - Inventor uses cm internally; URDF/MuJoCo use meters; ADAMS uses mm
4. **Transform accumulation** - Matrix multiplication order matters for nested assemblies
5. **Inertia tensors** - Reference frame transformations with parallel axis theorem

### Open TODOs

- [ ] Verify pywin32 compatibility with Python 3.13
- [ ] Verify current URDF/MuJoCo format specifications (Phase 6)
- [ ] Determine ADAMS version targeting
- [ ] Golden file comparison with VBA output (deferred until test assembly available)

### Blockers

None currently.

## Session Continuity

### Last Session

**Date:** 2026-01-19
**Work Done:** Completed 04-03-PLAN.md (material and mass extraction)
- extract_material() reading from PhysicalPropertiesAsset
- extract_mass_properties() using XYZMomentsOfInertia()
- Locale-agnostic property searching
- 10 unit tests for property extraction
**Stopping Point:** Plan 04-03 complete; ready for 04-04 (full pipeline)

### Commits This Session

| Hash | Description |
|------|-------------|
| 2707129 | feat(04-03): implement material extraction from Inventor parts |
| af7c649 | feat(04-03): implement mass property extraction from Inventor parts |
| 135cef2 | test(04-03): add unit tests for material and mass extraction |
| f9b7694 | chore(04-03): export material and mass extraction from package |

### Next Session

**Resume At:** Plan 04-04 (full extraction pipeline) or 04-05 (integration tests)
**Context Needed:** None additional
**First Action:** `/gsd:execute-phase` for 04-04

---

*State initialized: 2026-01-19*
*Last updated: 2026-01-19 after 04-03 completion*
