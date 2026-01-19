# Research Summary

**Project:** Inventor Assembly Exporter (Python Rewrite)
**Synthesized:** 2026-01-19
**Research Files:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

## Executive Summary

This project rewrites an existing VBA-based Autodesk Inventor assembly exporter in Python, transforming it from a single-format tool (ADAMS View) into a multi-format exporter supporting ADAMS, URDF, and MuJoCo. The recommended approach uses **pywin32 for COM automation**, **lxml for XML generation**, and **dataclasses for the intermediate representation**. The architecture follows an **Extract-Transform-Load (ETL) pattern** with a plugin-based writer system that isolates format-specific logic from the extraction layer.

The existing VBA implementation provides a solid baseline for ADAMS export but has significant gaps: it lacks joint/constraint extraction (making exports "geometry dumps" rather than working simulation models), has incomplete inertia tensor calculation, and contains a potential gimbal lock bug in Euler angle computation. The Python rewrite should achieve **VBA parity first**, then address these gaps in subsequent phases. Joint extraction is identified as the highest-value differentiator but is also the highest complexity feature.

Critical risks center on **COM object lifecycle management** (memory leaks, stale references), **coordinate system mismatches** (Euler angle conventions, unit conversions), and **assembly hierarchy traversal** (transform accumulation through nested subassemblies). These must be addressed in the foundational phases before any format export work begins. The stack is well-established (pywin32 has 25+ years of maturity), but integration with Python 3.13 should be verified before committing to that version.

## Key Findings

### From STACK.md

| Technology | Purpose | Rationale |
|------------|---------|-----------|
| **pywin32 306+** | COM automation | De facto standard for Inventor automation; 25+ years mature; better documentation than comtypes |
| **Python 3.11-3.12** | Runtime | Verify pywin32 compatibility before using 3.13 |
| **lxml 5.x** | XML generation | Better than stdlib for URDF/MuJoCo; built-in pretty-print, faster performance |
| **click 8.x** | CLI framework | Clean decorator-based API for multi-command CLIs |
| **dataclasses** | Data model | Sufficient for internal IR; no external dependency |
| **pytest 8.x + ruff** | Testing/linting | Standard Python development tools |

**Critical decision:** Use lxml for direct URDF/MuJoCo XML generation rather than specialized libraries (urdfpy, yourdfpy) which pull in unnecessary dependencies (trimesh, numpy, networkx).

### From FEATURES.md

**Table Stakes (Must Have for MVP):**
- Assembly traversal with hierarchy preservation
- Transformation extraction (position + orientation)
- STEP geometry export
- Material extraction with actual property lookup
- Mass properties including inertia tensor
- ADAMS format writer (VBA parity)
- Format writer plugin interface

**Differentiators (High Value, Defer to v2):**
- Joint/constraint extraction (highest value but HIGH complexity)
- Automatic joint type detection
- URDF/MuJoCo writers (less valuable without joints)
- Collision geometry generation

**Anti-Features (Do Not Build):**
- GUI interface (scope creep)
- Bi-directional sync (massive complexity)
- Multi-CAD support (each API is different)
- Automatic simplification (export full geometry)

### From ARCHITECTURE.md

**Recommended Pattern:** Extract-Transform-Load (ETL) with three layers:
1. **Extraction Layer** - InventorClient pulls data via COM
2. **Intermediate Representation** - Format-agnostic AssemblyModel with Bodies, Joints, Materials
3. **Writer Layer** - Plugin-based format writers implementing FormatWriter Protocol

**Key Design Decisions:**
- Protocol-based interface for writers (static typing without inheritance coupling)
- Registry pattern for writer discovery
- Builder pattern for constructing AssemblyModel
- Decomposed writer classes (MaterialFormatter, BodyFormatter, JointFormatter per format)
- Geometry files referenced externally (STEP paths), not embedded

**Anti-Patterns to Avoid:**
- Format logic in extraction layer
- Passing COM objects through the system (convert to IR immediately)
- Monolithic writer classes
- String/dict-based IR (use typed dataclasses)

### From PITFALLS.md

**Critical Pitfalls (Must Address Early):**

| Pitfall | Phase | Prevention |
|---------|-------|------------|
| COM object lifetime mismanagement | Core | Context managers, explicit cleanup, gc.collect() |
| Euler angle gimbal lock / rotation order mismatch | Data Model | Use scipy.spatial.transform.Rotation; format-specific conversions |
| Coordinate system / unit mismatch | Data Model | Centralized UnitConverter class; explicit source/target units |
| Assembly hierarchy flattening errors | Extraction | Recursive traversal with accumulated transforms; matrix multiplication order |
| STEP export geometry mismatch | Export | Explicit translator options; validation |

**Moderate Pitfalls:**
- pythoncom thread apartment model (initialize COM per thread)
- Material property extraction complexity (physical vs appearance assets)
- File path encoding and special characters (sanitize per format)
- Inertia tensor reference frame confusion (parallel axis theorem)
- ADAMS View command syntax versioning

## Implications for Roadmap

### Suggested Phase Structure

Based on dependency analysis and risk mitigation, the following phase order is recommended:

#### Phase 1: Core Infrastructure
**Rationale:** COM lifecycle patterns and coordinate utilities are foundational to everything else. Getting these wrong causes cascading failures.

**Delivers:**
- COM connection manager with proper lifecycle
- Unit conversion utilities
- Rotation/transform utilities with format-specific output methods
- Name sanitization utilities
- Logging infrastructure

**Features:** None directly user-visible; enables all subsequent phases

**Pitfalls to Avoid:** #1 (COM lifetime), #6 (threading), #8 (file paths), #11 (debug pollution)

#### Phase 2: Data Model
**Rationale:** IR must be validated before building extraction or writers. Changes to IR after extraction is built are expensive.

**Delivers:**
- AssemblyModel, Body, Joint, Material, Transform dataclasses
- Model validation logic
- Transform math (rotation matrix to Euler/quaternion conversions)
- Inertia tensor handling with reference frame transformations

**Features:** Internal only; enables format writers

**Pitfalls to Avoid:** #2 (rotation order), #3 (units), #9 (inertia frames)

#### Phase 3: ADAMS Writer (First Format)
**Rationale:** ADAMS is closest to existing VBA. Can validate IR design against known-good output. Achieves first user-visible value.

**Delivers:**
- FormatWriter Protocol
- WriterRegistry
- ADAMSWriter with material, body, geometry sections
- Golden file tests

**Features from FEATURES.md:** ADAMS format writer, format writer plugin interface

**Pitfalls to Avoid:** #10 (ADAMS versioning), #8 (path sanitization)

#### Phase 4: Inventor Extraction
**Rationale:** Build extraction knowing the IR is validated by a working writer. This order catches IR design issues before extraction is built.

**Delivers:**
- InventorClient with COM connection
- Assembly traversal (leaf occurrences with hierarchy)
- Transform extraction
- Material/mass property extraction
- STEP export integration

**Features from FEATURES.md:** Assembly traversal, transformation extraction, STEP export, material extraction, mass properties

**Pitfalls to Avoid:** #1 (COM), #4 (hierarchy), #5 (STEP), #7 (materials), #14 (GUIDs)

#### Phase 5: CLI Integration
**Rationale:** Wire everything together for end-to-end usage. At this point core functionality works.

**Delivers:**
- Click-based CLI
- Format selection (--format=adams)
- Output path handling
- Validation and error reporting

**Features:** User-facing CLI, validation of output

#### Phase 6: Additional Writers (Parallel)
**Rationale:** Once IR is stable and ADAMS works, additional formats can be developed in parallel.

**Delivers:**
- URDFWriter (XML generation with lxml)
- MuJoCoWriter (MJCF XML generation)
- Format-specific tests

**Features from FEATURES.md:** Multi-format export (core project goal)

**Pitfalls to Avoid:** #2 (URDF uses RPY, MuJoCo uses quaternions), #3 (both use meters)

**Note:** URDF and MuJoCo are less valuable without joint extraction. Consider them "geometry only" exports until Phase 7.

#### Phase 7: Joint Extraction (v2)
**Rationale:** Highest value differentiator but highest complexity. Deferred to v2 to achieve VBA parity first.

**Delivers:**
- Constraint analysis
- Joint type detection heuristics
- Joint limits extraction
- Full URDF/MuJoCo model generation

**Features from FEATURES.md:** Joint/constraint extraction, joint type detection, joint limits

**Research Flag:** This phase needs dedicated research spike before implementation.

### Research Flags

| Phase | Research Needed | Notes |
|-------|-----------------|-------|
| Phase 1 (Core) | LOW | Standard patterns, well-documented |
| Phase 2 (Model) | LOW | Mathematical transformations, scipy handles complexity |
| Phase 3 (ADAMS) | LOW | Existing VBA provides reference; may need version check |
| Phase 4 (Extraction) | MEDIUM | Verify Inventor COM API details during implementation |
| Phase 5 (CLI) | LOW | Standard click patterns |
| Phase 6 (Writers) | MEDIUM | Verify current URDF/MuJoCo specs; training data may be stale |
| Phase 7 (Joints) | HIGH | No existing implementation; constraint-to-joint mapping is poorly defined |

**Recommendation:** Run `/gsd:research-phase` for Phase 4 (Inventor COM API details) and Phase 7 (joint extraction strategy) before detailed planning.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| **Stack** | HIGH | pywin32, lxml, click are well-established; versions may need verification |
| **Features** | HIGH | Based on direct VBA analysis + known format requirements |
| **Architecture** | HIGH | ETL pattern is well-established; protocol/registry patterns are standard |
| **Pitfalls** | MEDIUM-HIGH | COM pitfalls based on training data; math pitfalls are factual; format specifics need verification |

### Gaps to Address

1. **pywin32 + Python 3.13 compatibility:** System has 3.13.3 but pywin32 lags releases. Verify before committing to version.

2. **Inventor API specifics:** Mass property extraction, constraint API details need verification against current Inventor SDK docs during Phase 4.

3. **Format specification currency:** URDF and MuJoCo format details are from training data (potentially 6-18 months stale). Verify against current specifications during Phase 6.

4. **ADAMS version targeting:** VBA targets one version. Need to determine which ADAMS versions to support and verify command syntax.

5. **Joint extraction strategy:** No existing implementation or clear path. Requires dedicated research before Phase 7.

6. **scipy dependency:** Rotation math examples use scipy.spatial.transform. Decide whether to add scipy dependency or implement rotation conversions manually.

## Overall Assessment

**Readiness:** HIGH for MVP (Phases 1-5)

The project has clear requirements (VBA parity + extensibility), a well-defined stack, and established architectural patterns. The main risks are in foundational areas (COM lifecycle, coordinate transforms) which are addressed early in the phase order.

**Recommendation:** Proceed to roadmap creation. Prioritize Phases 1-5 for MVP. Defer joint extraction (Phase 7) to v2 but keep it in the roadmap as the primary value unlock.

## Sources

Aggregated from research files:

**Primary Sources:**
- Existing VBA codebase: Main.bas, Export.bas, Misc.bas
- Project context: .planning/PROJECT.md, .planning/codebase/*.md

**Format Specifications (training data - verify):**
- URDF: ROS wiki specification
- MuJoCo: DeepMind MJCF documentation
- ADAMS View: MSC Software documentation

**Technology Documentation (training data - verify versions):**
- pywin32: Python for Windows extensions
- lxml: XML processing library
- click: CLI creation library

---

*Research synthesis: 2026-01-19*
*Research files: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
