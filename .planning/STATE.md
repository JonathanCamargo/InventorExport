# Project State: Inventor Assembly Exporter

## Project Reference

**Core Value:** Adding a new export format should only require implementing a format-specific writer

**Current Focus:** Phase 6 - Additional Writers (1 of 4 plans complete)

## Current Position

**Phase:** 6 of 6 (Additional Writers)
**Plan:** 1 of 4 complete
**Status:** In progress
**Last activity:** 2026-01-20 - Completed 06-01-PLAN.md (mesh conversion infrastructure)

**Progress:** [##############] 14/17 plans complete (Phases 1-5 complete, Phase 6 started)

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases Completed | 5/6 (Phase 6 in progress) |
| Plans Completed | 14 (01-01, 01-02, 01-03, 02-01, 02-02, 03-01, 03-02, 04-01, 04-02, 04-03, 04-04, 05-01, 05-02, 06-01) |
| Requirements Done | 31/34 (INFRA-01-06, MODEL-01-06, WRITER-01-06, EXTRACT-01-07, CLI-01-05) |
| Tests | 78 passing |

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
| ClickException for errors | Clean user-facing messages, no tracebacks | 05-02 |
| Binary STL over ASCII | 5-10x smaller file sizes | 06-01 |
| CadQuery over PythonOCC | pip installable, cleaner API | 06-01 |
| Caching by mesh name | Avoid redundant conversions | 06-01 |

### Technical Notes

- pywin32 for COM automation (verify Python 3.13 compatibility before use)
- lxml for XML generation (URDF, MuJoCo)
- cadquery for STEP to STL mesh conversion
- click for CLI framework
- dataclasses for intermediate representation
- scipy.spatial.transform for rotation math
- pytest for testing (78 tests passing)

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
| Phase 6 | MEDIUM | Mesh conversion complete; format writers next |

### Critical Pitfalls (from research)

1. **COM lifecycle** - Use context managers, explicit cleanup, gc.collect()
2. **Euler angles** - Format-specific rotation orders; use scipy or verified implementations
3. **Unit conversion** - Inventor uses cm internally; URDF/MuJoCo use meters; ADAMS uses mm
4. **Transform accumulation** - Matrix multiplication order matters for nested assemblies
5. **Inertia tensors** - Reference frame transformations with parallel axis theorem
6. **STL Binary vs ASCII** - Always use binary STL for smaller files

### Open TODOs

- [ ] Verify pywin32 compatibility with Python 3.13
- [ ] Determine ADAMS version targeting
- [ ] Golden file comparison with VBA output (deferred until test assembly available)

### Blockers

None currently.

## Session Continuity

### Last Session

**Date:** 2026-01-20
**Work Done:** Completed 06-01-PLAN.md (mesh conversion infrastructure)
- Added lxml>=4.9 and cadquery>=2.2 dependencies
- Created mesh_converter.py with convert_step_to_stl() and MeshConverter class
- Graceful handling of missing cadquery dependency
**Stopping Point:** Plan 06-01 complete

### Commits This Session

| Hash | Description |
|------|-------------|
| 475e472 | chore(06-01): add lxml and cadquery dependencies |
| c486929 | feat(06-01): add STEP to STL mesh converter module |

### Next Session

**Resume At:** Plan 06-02 (URDF writer)
**Context Needed:** URDF format specification from 06-RESEARCH.md
**First Action:** Execute 06-02-PLAN.md

---

*State initialized: 2026-01-19*
*Last updated: 2026-01-20 after 06-01 completion*
