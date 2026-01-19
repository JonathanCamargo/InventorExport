# Roadmap: Inventor Assembly Exporter

**Created:** 2026-01-19
**Depth:** Comprehensive
**Phases:** 6
**Coverage:** 34/34 v1 requirements mapped

## Overview

This roadmap transforms the existing VBA-based Inventor exporter into a Python tool with plugin-based format support. Phases are ordered to validate foundational components before building dependent features: infrastructure and data model first, then ADAMS writer (validates IR against VBA output), then Inventor extraction (uses validated IR), then CLI (wires everything together), and finally additional format writers.

The phase structure follows the ETL pattern: build extraction utilities, define the intermediate representation, validate it with the first writer, then add extraction and CLI.

## Phases

### Phase 1: Core Infrastructure

**Goal:** Foundation utilities exist for COM lifecycle, unit conversion, rotation math, and logging.

**Dependencies:** None (foundational)

**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md - Logging infrastructure and unit conversion utilities
- [ ] 01-02-PLAN.md - Rotation conversion utilities (scipy-based)
- [ ] 01-03-PLAN.md - COM connection and lifecycle management

**Requirements:**
- INFRA-01: Python connects to Inventor via COM with proper lifecycle management
- INFRA-02: COM objects are cleaned up deterministically (context managers, no memory leaks)
- INFRA-03: Unit conversion utilities convert between Inventor internal units and export format units
- INFRA-04: Transform utilities convert rotation matrices to Euler angles and quaternions
- INFRA-05: Transform utilities handle format-specific rotation conventions (XYZ, RPY, quaternion)
- INFRA-06: Logging infrastructure provides debug output and error tracking

**Success Criteria:**
1. COM connection context manager connects to running Inventor instance and releases cleanly on exit
2. Unit converter correctly transforms internal cm to meters (for URDF/MuJoCo) and mm (for ADAMS)
3. Rotation converter produces correct Euler angles for known test matrices (verified against scipy)
4. Rotation converter produces correct quaternions for known test matrices
5. Logger writes structured output that can be enabled/disabled without code changes

---

### Phase 2: Data Model

**Goal:** Format-agnostic intermediate representation captures complete assembly structure.

**Dependencies:** Phase 1 (transform utilities)

**Requirements:**
- MODEL-01: AssemblyModel dataclass represents complete assembly structure
- MODEL-02: Body dataclass captures part instance with name, transform, geometry reference, material
- MODEL-03: Material dataclass captures density and physical properties
- MODEL-04: Transform dataclass captures position (translation) and orientation (rotation matrix)
- MODEL-05: Inertia tensor handled with proper reference frame transformations
- MODEL-06: Model validation catches invalid/incomplete data before export

**Success Criteria:**
1. AssemblyModel can be constructed from dictionary data and serialized back without loss
2. Body with transform, material, and geometry reference passes validation
3. Model with missing required fields (e.g., body without transform) fails validation with clear error
4. Inertia tensor transforms correctly when body origin differs from center of mass

---

### Phase 3: ADAMS Writer

**Goal:** First format writer validates IR design and achieves VBA output parity.

**Dependencies:** Phase 2 (data model)

**Requirements:**
- WRITER-01: FormatWriter Protocol defines interface for all format writers
- WRITER-02: WriterRegistry discovers and selects writers by format name
- WRITER-03: ADAMS writer generates rigid body definitions (VBA parity)
- WRITER-04: ADAMS writer generates material property section
- WRITER-05: ADAMS writer generates geometry property section with STEP references
- WRITER-06: ADAMS output matches VBA output for same input assembly

**Success Criteria:**
1. FormatWriter protocol can be implemented by a new writer class without modifying core code
2. WriterRegistry returns ADAMS writer when queried with "adams" format name
3. ADAMS output for test assembly matches VBA output (golden file comparison)
4. ADAMS rigid body definitions include correct position, orientation, and material references

---

### Phase 4: Inventor Extraction

**Goal:** Assembly data flows from Inventor into validated intermediate representation.

**Dependencies:** Phase 1 (COM utilities), Phase 2 (data model)

**Requirements:**
- EXTRACT-01: InventorClient connects to running Inventor instance
- EXTRACT-02: Assembly traversal walks hierarchy and collects leaf occurrences
- EXTRACT-03: Transformation extraction gets position and orientation from occurrence matrix
- EXTRACT-04: Transform accumulation handles nested subassemblies correctly
- EXTRACT-05: STEP export generates geometry files for each unique part
- EXTRACT-06: Material extraction reads actual material properties from parts
- EXTRACT-07: Mass property extraction gets mass and inertia tensor from Inventor

**Success Criteria:**
1. InventorClient connects to running Inventor instance and accesses active document
2. Assembly traversal returns all leaf occurrences with correct parent hierarchy
3. Nested subassembly transforms accumulate correctly (child position in world coordinates)
4. STEP files are generated for each unique part definition (not per occurrence)
5. Material density is extracted from Inventor material library (not hardcoded default)

---

### Phase 5: CLI Integration

**Goal:** User can run end-to-end export from command line.

**Dependencies:** Phase 3 (ADAMS writer), Phase 4 (extraction)

**Requirements:**
- CLI-01: User can run exporter from command line
- CLI-02: User can select output format via --format flag (adams, urdf, mujoco)
- CLI-03: User can specify output path via --output flag
- CLI-04: User receives clear error messages for invalid input
- CLI-05: User can list available formats via --list-formats

**Success Criteria:**
1. User runs `inventorexport --format adams --output model.cmd` and gets ADAMS file
2. User runs `inventorexport --list-formats` and sees available formats
3. User runs with invalid format and receives error message naming valid options
4. User runs without Inventor open and receives clear error about missing Inventor connection

---

### Phase 6: Additional Writers

**Goal:** URDF and MuJoCo formats extend export capabilities.

**Dependencies:** Phase 3 (writer infrastructure), Phase 5 (CLI)

**Requirements:**
- WRITER-07: URDF writer generates valid URDF XML with bodies and geometry
- WRITER-08: URDF writer handles coordinate conventions (meters, RPY angles)
- WRITER-09: MuJoCo writer generates valid MJCF XML with bodies and geometry
- WRITER-10: MuJoCo writer handles coordinate conventions (meters, quaternions)

**Success Criteria:**
1. URDF output passes XML schema validation
2. URDF uses meters for positions and RPY for orientations
3. MuJoCo output passes MJCF XML schema validation
4. MuJoCo uses meters for positions and quaternions for orientations
5. Both formats appear in --list-formats output after installation

---

## Progress

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 1 | Core Infrastructure | 6 | Complete ✓ |
| 2 | Data Model | 6 | Not Started |
| 3 | ADAMS Writer | 6 | Not Started |
| 4 | Inventor Extraction | 7 | Not Started |
| 5 | CLI Integration | 5 | Not Started |
| 6 | Additional Writers | 4 | Not Started |

**Total:** 34 requirements across 6 phases

---

## Dependency Graph

```
Phase 1: Core Infrastructure
    |
    v
Phase 2: Data Model
    |
    v
Phase 3: ADAMS Writer ----+
    |                     |
    v                     v
Phase 4: Extraction --> Phase 5: CLI
                          |
                          v
                    Phase 6: Additional Writers
```

---

*Roadmap created: 2026-01-19*
*Last updated: 2026-01-19 after Phase 1 completion*
