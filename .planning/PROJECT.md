# Inventor Assembly Exporter

## What This Is

A Python tool that exports Autodesk Inventor assemblies to multibody dynamics simulation formats. It connects to Inventor via COM automation, extracts assembly structure, part geometries, materials, and transformations, then generates output files for simulation software. The architecture supports multiple output formats through a plugin system.

## Core Value

Adding a new export format should only require implementing a format-specific writer — no changes to assembly traversal or data extraction logic.

## Requirements

### Validated

- ✓ Export Inventor assemblies to ADAMS View command files — existing VBA
- ✓ Export part geometries to STEP format — existing VBA
- ✓ Extract material properties from parts — existing VBA
- ✓ Calculate transformation matrices and Euler angles — existing VBA
- ✓ Generate rigid body definitions with mass properties — existing VBA

### Active

- [ ] Python CLI that connects to Inventor via COM automation
- [ ] Abstract data model representing assembly structure (parts, transforms, materials)
- [ ] Format writer interface that output plugins implement
- [ ] ADAMS View format writer (parity with VBA implementation)
- [ ] STEP geometry export integrated with format writers

### Out of Scope

- MuJoCo XML format — deferred to v2, architecture will support it
- URDF format — deferred to v2, architecture will support it
- GUI — CLI is sufficient for automation workflows
- Joint/constraint detection — current VBA doesn't support this, future enhancement

## Context

**Current state:** Working VBA macro (`Inventor2AdamsView.ivb`) that exports to ADAMS View format. Code is procedural with ADAMS-specific logic hardcoded throughout, making it difficult to add new formats.

**Migration rationale:** Python offers better tooling, easier testing, cleaner abstractions for plugin architecture, and a larger ecosystem for future enhancements (e.g., XML/URDF libraries).

**Inventor integration:** Python can automate Inventor via `win32com.client` (pywin32). Same COM API the VBA code uses, just accessed from Python.

**Existing codebase analysis:** See `.planning/codebase/` for detailed architecture, conventions, and concerns from the VBA implementation.

## Constraints

- **Platform**: Windows only — Inventor is Windows-only, COM automation required
- **Runtime**: Requires Inventor installation with VBA/COM access enabled
- **Compatibility**: Must work with assemblies the VBA version handles

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over VBA | Better abstractions, testing, maintainability | — Pending |
| Plugin architecture for formats | Core goal — easy format addition | — Pending |
| CLI interface | Sufficient for automation, simpler than GUI | — Pending |

---
*Last updated: 2026-01-19 after initialization*
