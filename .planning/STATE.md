# Project State: Inventor Assembly Exporter

## Project Reference

**Core Value:** Adding a new export format should only require implementing a format-specific writer

**Current Focus:** Phase 5 Complete - CLI Integration (1 plan done)

## Current Position

**Phase:** 5 of 6 (CLI Integration)
**Plan:** 1 of 1 complete
**Status:** Phase complete
**Last activity:** 2026-01-20 - Completed 05-01-PLAN.md (CLI entry point)

**Progress:** [############] 12/12 plans complete (Phases 1-5 complete)

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed | 5/6 |
| Plans Completed | 12 (01-01, 01-02, 01-03, 02-01, 02-02, 03-01, 03-02, 04-01, 04-02, 04-03, 04-04, 05-01) |
| Requirements Done | 26/34 (INFRA-01-06, MODEL-01-06, WRITER-01-06, EXTRACT-01-07, CLI-01) |
| Tests | 64 passing |

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
| Material deduplication by name | Same material may appear on multiple parts | 04-04 |
| Partial extraction on failure | Log and continue - partial model better than no model | 04-04 |
| Click over argparse | Cleaner decorators, better help formatting | 05-01 |
| is_eager=True for --list-formats | Runs before required option validation | 05-01 |
| ClickException for errors | Clean user-facing messages, no tracebacks | 05-01 |

### Technical Notes

- pywin32 for COM automation (verify Python 3.13 compatibility before use)
- lxml for XML generation (URDF, MuJoCo)
- click for CLI framework
- dataclasses for intermediate representation
- scipy.spatial.transform for rotation math
- pytest for testing (64 tests passing)

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
| Phase 4 | MEDIUM | Inventor COM API - COMPLETE |
| Phase 5 | LOW | Standard click patterns - COMPLETE |
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

**Date:** 2026-01-20
**Work Done:** Completed 05-01-PLAN.md (CLI entry point)
- Click-based CLI with --format, --output, --list-formats, --version
- inventorexport console script entry point
- python -m inventor_exporter module execution
- User-friendly error messages for Inventor connection issues
**Stopping Point:** Plan 05-01 complete; Phase 5 complete

### Commits This Session

| Hash | Description |
|------|-------------|
| c21a1f0 | chore(05-01): add click dependency and inventorexport entry point |
| ba01f8f | feat(05-01): implement CLI module with click command |
| bf72d54 | feat(05-01): add __main__.py for module execution |

### Next Session

**Resume At:** Phase 6 (Additional Formats)
**Context Needed:** URDF/MuJoCo format specifications
**First Action:** `/gsd:plan-phase 6` to create format writer plans

---

*State initialized: 2026-01-19*
*Last updated: 2026-01-20 after 05-01 completion*
