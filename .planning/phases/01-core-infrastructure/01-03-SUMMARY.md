---
phase: 01-core-infrastructure
plan: 03
subsystem: com-management
tags: [com, pywin32, context-manager, lifecycle]

dependency-graph:
  requires:
    - 01-01 (logging infrastructure)
  provides:
    - com-connection-management
    - inventor-app-context-manager
    - assembly-document-access
  affects:
    - phase-04 (inventor-extraction)
    - phase-05 (cli)

tech-stack:
  added:
    - pythoncom (part of pywin32)
    - win32com.client (part of pywin32)
  patterns:
    - Context managers for COM lifecycle
    - Explicit COM reference cleanup in finally blocks
    - Custom exceptions for clear error reporting

key-files:
  created:
    - src/inventor_exporter/core/com.py
  modified:
    - src/inventor_exporter/core/__init__.py

decisions:
  - decision: No explicit CoInitialize in context manager
    rationale: Main thread auto-initializes COM; only worker threads need explicit init (not implemented in Phase 1)
    phase: 01-03
  - decision: Use hresult -2147221021 for MK_E_UNAVAILABLE detection
    rationale: Standard COM error code for "object not running", documented pywin32 pattern
    phase: 01-03
  - decision: Delete COM references in finally block
    rationale: Ensures deterministic cleanup even on exceptions, prevents memory leaks
    phase: 01-03

metrics:
  duration: ~2 minutes
  completed: 2026-01-19
---

# Phase 01 Plan 03: COM Connection Management Summary

**One-liner:** Context managers for Inventor COM connection (inventor_app) and assembly access (active_assembly) with deterministic cleanup and clear error messages.

## What Was Built

### COM Module (com.py)

Created `src/inventor_exporter/core/com.py` with:

**Custom Exceptions:**
- `InventorNotRunningError` - Raised when Inventor is not running
- `NotAssemblyError` - Raised when no document is open or document is not an assembly

**Context Managers:**
- `inventor_app()` - Connects to running Inventor instance via `win32com.client.GetActiveObject`
  - Logs connection events at DEBUG level
  - Catches `pythoncom.com_error` with hresult -2147221021 (MK_E_UNAVAILABLE)
  - Converts to `InventorNotRunningError` with helpful message
  - Deletes COM reference in finally block

- `active_assembly(app)` - Retrieves and validates active assembly document
  - Validates document is not None
  - Validates DocumentType == 12291 (kAssemblyDocumentObject)
  - Raises `NotAssemblyError` with document type in message if validation fails
  - Deletes doc reference in finally block

### Updated Core Exports

Updated `src/inventor_exporter/core/__init__.py` to export:
- `inventor_app`, `active_assembly`
- `InventorNotRunningError`, `NotAssemblyError`

Organized `__all__` by category: Logging, Units, Rotation, COM

## Key Commits

| Hash | Description |
|------|-------------|
| c30f08f | Create COM context manager for Inventor connection |
| 7b3792a | Export COM utilities from core module |

## Verification Results

All verification checks passed:
- Module imports successfully
- `inventor_app` is a proper context manager
- `InventorNotRunningError` raised correctly when Inventor not running
- `NotAssemblyError` is subclass of Exception
- All Phase 1 exports available from `inventor_exporter.core`
- Logging integration works (DEBUG logs show connection attempts)

## Requirements Satisfied

- **INFRA-01:** Python connects to Inventor via COM with proper lifecycle management
- **INFRA-02:** COM objects are cleaned up deterministically (context managers, no memory leaks)

## Deviations from Plan

None - plan executed exactly as written.

## Phase 1 Complete

Phase 01 (Core Infrastructure) is now complete with all 3 plans executed:

| Plan | Name | Status |
|------|------|--------|
| 01-01 | Project Foundation | Complete |
| 01-02 | Rotation Conversion | Complete |
| 01-03 | COM Management | Complete |

### Phase 1 Deliverables

The `inventor_exporter.core` module now provides:

**Logging:**
- `setup_logging(log_file, console_level, file_level)`
- `get_logger(name)`

**Units:**
- `LengthUnit` enum
- `Position` namedtuple
- `InventorUnits` class with conversion methods

**Rotation:**
- `EulerConvention` enum (ADAMS_ZXZ, URDF_RPY)
- `rotation_to_euler(matrix, convention, degrees)`
- `rotation_to_quaternion(matrix, scalar_first, canonical)`
- `rotation_to_format(matrix, target_format)`

**COM:**
- `inventor_app()` context manager
- `active_assembly(app)` context manager
- `InventorNotRunningError` exception
- `NotAssemblyError` exception

## Next Phase Readiness

Ready for:
- **Phase 02:** Intermediate representation design (uses logging)
- **Phase 04:** Inventor extraction (uses COM, units, rotation)

No blockers identified.
