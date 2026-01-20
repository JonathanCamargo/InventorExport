# Requirements: Inventor Assembly Exporter

**Defined:** 2026-01-19
**Core Value:** Adding a new export format should only require implementing a format-specific writer

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Infrastructure

- [x] **INFRA-01**: Python connects to Inventor via COM with proper lifecycle management
- [x] **INFRA-02**: COM objects are cleaned up deterministically (context managers, no memory leaks)
- [x] **INFRA-03**: Unit conversion utilities convert between Inventor internal units and export format units
- [x] **INFRA-04**: Transform utilities convert rotation matrices to Euler angles and quaternions
- [x] **INFRA-05**: Transform utilities handle format-specific rotation conventions (XYZ, RPY, quaternion)
- [x] **INFRA-06**: Logging infrastructure provides debug output and error tracking

### Data Model

- [x] **MODEL-01**: AssemblyModel dataclass represents complete assembly structure
- [x] **MODEL-02**: Body dataclass captures part instance with name, transform, geometry reference, material
- [x] **MODEL-03**: Material dataclass captures density and physical properties
- [x] **MODEL-04**: Transform dataclass captures position (translation) and orientation (rotation matrix)
- [x] **MODEL-05**: Inertia tensor handled with proper reference frame transformations
- [x] **MODEL-06**: Model validation catches invalid/incomplete data before export

### Extraction

- [x] **EXTRACT-01**: InventorClient connects to running Inventor instance
- [x] **EXTRACT-02**: Assembly traversal walks hierarchy and collects leaf occurrences
- [x] **EXTRACT-03**: Transformation extraction gets position and orientation from occurrence matrix
- [x] **EXTRACT-04**: Transform accumulation handles nested subassemblies correctly
- [x] **EXTRACT-05**: STEP export generates geometry files for each unique part
- [x] **EXTRACT-06**: Material extraction reads actual material properties from parts
- [x] **EXTRACT-07**: Mass property extraction gets mass and inertia tensor from Inventor

### Format Writing

- [x] **WRITER-01**: FormatWriter Protocol defines interface for all format writers
- [x] **WRITER-02**: WriterRegistry discovers and selects writers by format name
- [x] **WRITER-03**: ADAMS writer generates rigid body definitions (VBA parity)
- [x] **WRITER-04**: ADAMS writer generates material property section
- [x] **WRITER-05**: ADAMS writer generates geometry property section with STEP references
- [x] **WRITER-06**: ADAMS output matches VBA output for same input assembly
- [ ] **WRITER-07**: URDF writer generates valid URDF XML with bodies and geometry
- [ ] **WRITER-08**: URDF writer handles coordinate conventions (meters, RPY angles)
- [ ] **WRITER-09**: MuJoCo writer generates valid MJCF XML with bodies and geometry
- [ ] **WRITER-10**: MuJoCo writer handles coordinate conventions (meters, quaternions)

### CLI

- [ ] **CLI-01**: User can run exporter from command line
- [ ] **CLI-02**: User can select output format via --format flag (adams, urdf, mujoco)
- [ ] **CLI-03**: User can specify output path via --output flag
- [ ] **CLI-04**: User receives clear error messages for invalid input
- [ ] **CLI-05**: User can list available formats via --list-formats

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Joint Extraction

- **JOINT-01**: Constraint analysis detects joint relationships between parts
- **JOINT-02**: Joint type detection maps Inventor constraints to joint types (revolute, prismatic, fixed)
- **JOINT-03**: Joint limits extraction gets motion limits from Inventor constraints
- **JOINT-04**: URDF writer includes joint definitions
- **JOINT-05**: MuJoCo writer includes joint definitions

### Advanced Features

- **ADV-01**: Collision geometry generation (simplified meshes)
- **ADV-02**: Assembly validation before export
- **ADV-03**: Batch export of multiple assemblies

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| GUI interface | CLI sufficient for automation workflows; scope creep risk |
| Bi-directional sync | Massive complexity; read-only export is the goal |
| Multi-CAD support | Each CAD API is different; Inventor-only focus |
| Automatic mesh simplification | Export full geometry; let simulation tools simplify |
| Joint extraction (v1) | High complexity; research spike needed; achieves VBA parity first |
| Embedded geometry | STEP files referenced externally; no mesh embedding |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| INFRA-06 | Phase 1 | Complete |
| MODEL-01 | Phase 2 | Complete |
| MODEL-02 | Phase 2 | Complete |
| MODEL-03 | Phase 2 | Complete |
| MODEL-04 | Phase 2 | Complete |
| MODEL-05 | Phase 2 | Complete |
| MODEL-06 | Phase 2 | Complete |
| WRITER-01 | Phase 3 | Complete |
| WRITER-02 | Phase 3 | Complete |
| WRITER-03 | Phase 3 | Complete |
| WRITER-04 | Phase 3 | Complete |
| WRITER-05 | Phase 3 | Complete |
| WRITER-06 | Phase 3 | Complete |
| EXTRACT-01 | Phase 4 | Complete |
| EXTRACT-02 | Phase 4 | Complete |
| EXTRACT-03 | Phase 4 | Complete |
| EXTRACT-04 | Phase 4 | Complete |
| EXTRACT-05 | Phase 4 | Complete |
| EXTRACT-06 | Phase 4 | Complete |
| EXTRACT-07 | Phase 4 | Complete |
| CLI-01 | Phase 5 | Pending |
| CLI-02 | Phase 5 | Pending |
| CLI-03 | Phase 5 | Pending |
| CLI-04 | Phase 5 | Pending |
| CLI-05 | Phase 5 | Pending |
| WRITER-07 | Phase 6 | Pending |
| WRITER-08 | Phase 6 | Pending |
| WRITER-09 | Phase 6 | Pending |
| WRITER-10 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0

---
*Requirements defined: 2026-01-19*
*Last updated: 2026-01-19 after Phase 4 completion*
