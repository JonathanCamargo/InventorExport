---
phase: 05-cli-integration
plan: 01
subsystem: cli
tags: [click, cli, entry-point, command-line]

# Dependency graph
requires:
  - phase: 04-inventor-extraction-04
    provides: InventorClient for assembly extraction
  - phase: 03-adams-writer-01
    provides: WriterRegistry for format lookup
  - phase: 03-adams-writer-02
    provides: AdamsWriter registered in registry

provides:
  - inventorexport command-line entry point
  - python -m inventor_exporter module execution
  - --format, --output, --list-formats, --version options
  - User-friendly error messages for Inventor connection issues

affects:
  - End users can now run exports from command line
  - Phase 6 format writers automatically available via --list-formats

# Tech tracking
tech-stack:
  added:
    - click>=8.1 for CLI framework
  patterns:
    - Click command with options
    - Eager callback for --list-formats flag
    - Exception translation to ClickException

key-files:
  created:
    - src/inventor_exporter/cli.py
    - src/inventor_exporter/__main__.py
  modified:
    - pyproject.toml

key-decisions:
  - "Click over argparse: Cleaner decorators, better help formatting"
  - "is_eager=True for --list-formats: Runs before validation"
  - "ClickException for errors: Clean user-facing messages"
  - "Choice from WriterRegistry: Validates format at parse time"

patterns-established:
  - "CLI wires to existing modules without new logic"
  - "list_formats_callback pattern for eager flags"
  - "Exception translation layer at CLI boundary"

# Metrics
duration: 5min
completed: 2026-01-20
---

# Phase 05 Plan 01: CLI Entry Point Summary

**Click-based CLI wiring InventorClient and WriterRegistry with user-friendly error messages and format validation**

## Performance

- **Duration:** 5 min
- **Started:** 2026-01-20
- **Completed:** 2026-01-20
- **Tasks:** 3
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- Click dependency added to pyproject.toml
- `inventorexport` console script entry point configured
- CLI module with @click.command() decorated main()
- --format option with dynamic Choice validation from WriterRegistry
- --output option for output file path
- --list-formats flag shows available formats (eager)
- --version flag shows package version
- User-friendly error messages for Inventor connection issues
- `python -m inventor_exporter` module execution support

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Click dependency and entry point** - `c21a1f0` (chore)
2. **Task 2: Create CLI module with main command** - `ba01f8f` (feat)
3. **Task 3: Create __main__.py for module execution** - `bf72d54` (feat)

## Files Created/Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Modified - Added click>=8.1 and [project.scripts] |
| `src/inventor_exporter/cli.py` | Created - CLI module with main() command |
| `src/inventor_exporter/__main__.py` | Created - Module execution support |

## CLI Usage

### Basic Usage

```bash
# Show help
inventorexport --help
python -m inventor_exporter --help

# List available formats
inventorexport --list-formats
# Output:
# Available formats:
#   adams

# Export to ADAMS format
inventorexport --format adams --output model.cmd

# Show version
inventorexport --version
# Output: 0.1.0
```

### Error Messages

```bash
# Invalid format
inventorexport --format invalid --output test.txt
# Error: Invalid value for '--format' / '-f': 'invalid' is not 'adams'.

# Missing options
inventorexport
# Error: Missing option '--format' / '-f'. Choose from: adams

# Inventor not running (at runtime)
# Error: Inventor is not running. Please start Inventor and open an assembly.

# No assembly open (at runtime)
# Error: No assembly document is open in Inventor. Please open an assembly.
```

## Verification Results

| Check | Result |
|-------|--------|
| --help shows all options | PASS |
| --list-formats shows "adams" | PASS |
| --version shows "0.1.0" | PASS |
| Invalid format shows valid choices | PASS |
| Missing options shows usage error | PASS |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CLI framework | Click | Cleaner decorators, better help, shell completion |
| Format validation | click.Choice from registry | Validates at parse time, shows valid options |
| List formats | Eager callback | Runs before required option validation |
| Error translation | ClickException | Clean user messages, no tracebacks |

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

After updating to this version:

```bash
pip install -e .
# Now `inventorexport` command is available
```

## Next Phase Readiness

**Phase 5 CLI Integration:**
- Plan 01: CLI entry point (this plan) - COMPLETE

**Ready for Phase 6 (Additional Formats):**
- CLI automatically discovers new formats via WriterRegistry
- New writers just need to register to appear in --list-formats
- No CLI changes needed for URDF/MuJoCo writers

---
*Phase: 05-cli-integration*
*Completed: 2026-01-20*
