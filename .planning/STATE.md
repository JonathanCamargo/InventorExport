# Project State: Inventor Assembly Exporter

## Project Reference

**Core Value:** Adding a new export format should only require implementing a format-specific writer

**Current Focus:** Phase 2 - Intermediate Representation (Data Model)

## Current Position

**Phase:** 2 of 6 (Intermediate Representation)
**Plan:** 1 of 3 complete
**Status:** In progress
**Last activity:** 2026-01-19 - Completed 02-01-PLAN.md

**Progress:** [###.......] 4/18 plans complete

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed | 1/6 |
| Plans Completed | 4 (01-01, 01-02, 01-03, 02-01) |
| Requirements Done | 6/34 (INFRA-01 through INFRA-06) |
| Current Phase Progress | 33% (1/3 plans) |

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

### Technical Notes

- pywin32 for COM automation (verify Python 3.13 compatibility before use)
- lxml for XML generation (URDF, MuJoCo)
- click for CLI framework
- dataclasses for intermediate representation
- scipy.spatial.transform for rotation math (or implement manually)

### Research Flags

| Phase | Research Level | Notes |
|-------|----------------|-------|
| Phase 1 | LOW | Standard patterns - COMPLETE |
| Phase 2 | LOW | Mathematical transforms - IN PROGRESS |
| Phase 3 | LOW | VBA provides reference |
| Phase 4 | MEDIUM | Verify Inventor COM API details |
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

### Blockers

None currently.

## Session Continuity

### Last Session

**Date:** 2026-01-19
**Work Done:** Executed 02-01-PLAN.md (Foundation dataclasses: Transform, Material, Inertia)
**Stopping Point:** Plan 02-01 complete; ready for 02-02

### Commits This Session

| Hash | Description |
|------|-------------|
| e7cd610 | feat(02-01): create Transform and Material dataclasses |
| b4dec2e | feat(02-01): create Inertia dataclass with tensor transformations |
| d906427 | feat(02-01): export model package public API |

### Next Session

**Resume At:** Phase 02, Plan 02 (Body dataclass)
**Context Needed:** None additional
**First Action:** Execute 02-02-PLAN.md (Body dataclass)

---

*State initialized: 2026-01-19*
*Last updated: 2026-01-19*
