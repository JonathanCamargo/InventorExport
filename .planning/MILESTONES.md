# Project Milestones: Inventor Assembly Exporter

## v1.0 MVP (Shipped: 2026-01-20)

**Delivered:** Python CLI tool that exports Autodesk Inventor assemblies to simulation formats (ADAMS, URDF, SDF, MuJoCo) with plugin-based architecture.

**Phases completed:** 1-6 (18 plans total)

**Key accomplishments:**
- COM automation infrastructure for Inventor connection with proper lifecycle management
- Format-agnostic intermediate representation (AssemblyModel, Body, Transform, Material, Inertia)
- Plugin architecture with FormatWriter Protocol and WriterRegistry
- Complete Inventor extraction pipeline (assembly traversal, STEP export, materials, mass properties)
- Click-based CLI with `inventorexport` command supporting 4 output formats
- Four format writers: ADAMS (.cmd), URDF (.urdf), SDF (.sdf), MuJoCo (.xml)

**Stats:**
- 3,457 lines of Python source code
- 3,085 lines of Python test code
- 146 tests passing
- 6 phases, 18 plans, 34 requirements
- 2 days from start to ship

**Git range:** `39177ea` → `v1.0`

**What's next:** v1.1 could add joint extraction from Inventor constraints, batch export, or simplified collision geometry.

---

*For full details, see `.planning/milestones/v1.0-ROADMAP.md`*
