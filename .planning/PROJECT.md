# Inventor Assembly Exporter

## What This Is

A Python tool that exports Autodesk Inventor assemblies to multibody dynamics simulation formats. It connects to Inventor via COM automation, extracts assembly structure, part geometries, materials, and transformations, then generates output files for simulation software. The architecture supports multiple output formats through a plugin system.

## Core Value

Adding a new export format should only require implementing a format-specific writer — no changes to assembly traversal or data extraction logic.

## Current State

**Shipped:** v1.0 (2026-01-20)

**Capabilities:**
- `inventorexport` CLI tool connects to running Inventor instance
- Exports assemblies to 4 formats: ADAMS, URDF, SDF, MuJoCo
- Extracts materials, mass properties, and inertia tensors
- Generates STEP geometry files and STL meshes

**Stats:**
- 3,457 lines Python source
- 3,085 lines test code
- 146 tests passing
- 4 output formats

**Usage:**
```bash
inventorexport --format urdf --output model.urdf
inventorexport --list-formats
```

## Next Milestone Goals

Potential v1.1 features (not yet defined):
- Joint extraction from Inventor constraints
- Batch export of multiple assemblies
- Simplified collision geometry generation

## Constraints

- **Platform**: Windows only — Inventor is Windows-only, COM automation required
- **Runtime**: Requires Inventor installation with VBA/COM access enabled
- **Compatibility**: Must work with assemblies the VBA version handles

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over VBA | Better abstractions, testing, maintainability | Shipped v1.0 |
| Plugin architecture for formats | Core goal — easy format addition | 4 formats in v1.0 |
| CLI interface | Sufficient for automation, simpler than GUI | Click-based CLI |
| ETL pattern | Clean separation of extraction, model, writers | AssemblyModel IR |
| CadQuery for mesh conversion | pip installable, cleaner API than PythonOCC | Binary STL export |

---

<details>
<summary>Initial Requirements (Pre-v1.0)</summary>

### Validated (from VBA)

- Export Inventor assemblies to ADAMS View command files
- Export part geometries to STEP format
- Extract material properties from parts
- Calculate transformation matrices and Euler angles
- Generate rigid body definitions with mass properties

### Out of Scope (v1)

- GUI — CLI is sufficient for automation workflows
- Joint/constraint detection — deferred to v2

</details>

---
*Project initialized: 2026-01-19*
*v1.0 shipped: 2026-01-20*
