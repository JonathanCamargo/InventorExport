# Codebase Structure

**Analysis Date:** 2026-01-18

## Directory Layout

```
D:/git/inventorexport/
├── Main.bas                    # Entry point - orchestrates export workflow
├── Export.bas                  # STEP export and Adams View command generation
├── Misc.bas                    # Math utilities and file helpers
├── Inventor2AdamsView.ivb      # Compiled VBA project binary (OLE compound doc)
├── LICENSE                     # MIT License
├── .planning/                  # GSD planning directory
│   └── codebase/               # Architecture documentation
└── .claude/                    # Claude configuration
    └── settings.json           # Claude settings
```

## Directory Purposes

**Root Directory:**
- Purpose: Contains all source modules and project file
- Contains: VBA source files (`.bas`), compiled project (`.ivb`), license
- Key files: `Main.bas` (entry point), `Inventor2AdamsView.ivb` (loadable project)

**.planning/codebase/:**
- Purpose: Architecture and codebase documentation for GSD workflow
- Contains: Markdown analysis documents
- Key files: `ARCHITECTURE.md`, `STRUCTURE.md`

## Key File Locations

**Entry Points:**
- `D:/git/inventorexport/Main.bas`: Primary `Main()` subroutine - executes full export
- `D:/git/inventorexport/Export.bas`: Contains `ExportActiveToSTEP()` standalone utility

**Configuration:**
- No external configuration files
- Hardcoded paths reference Inventor's `ActiveDesignProject.workspacePath`

**Core Logic:**
- `D:/git/inventorexport/Main.bas`: Assembly traversal, material collection, occurrence iteration
- `D:/git/inventorexport/Export.bas`: STEP translation, Adams command syntax generation
- `D:/git/inventorexport/Misc.bas`: Euler angle decomposition from rotation matrices

**Testing:**
- No test files present

## Naming Conventions

**Files:**
- PascalCase for VBA modules: `Main.bas`, `Export.bas`, `Misc.bas`
- Compiled project uses product name: `Inventor2AdamsView.ivb`

**Subroutines/Functions:**
- PascalCase: `Main()`, `ExportToSTEP()`, `AppendRigidBody()`
- Private functions prefixed with module context: `FindMinAbsIndex()`

**Variables:**
- Hungarian notation for Inventor objects: `oDoc`, `oApp`, `oMatrix`
- Descriptive camelCase for local data: `componentName`, `materialName`, `exportPath`

## Where to Add New Code

**New Feature:**
- If related to file export formats: Add to `D:/git/inventorexport/Export.bas`
- If related to assembly traversal or main workflow: Modify `D:/git/inventorexport/Main.bas`
- If mathematical or utility function: Add to `D:/git/inventorexport/Misc.bas`

**New Module:**
- Create new `.bas` file in root directory
- Add corresponding attribute line: `Attribute VB_Name = "ModuleName"`
- Import into `Inventor2AdamsView.ivb` project within Inventor VBA IDE

**New Export Target (non-Adams):**
- Create new module following `Export.bas` pattern
- Implement `AppendXxx()` functions for output format
- Modify `Main.bas` to call new append functions

## Special Directories

**EXPORT/ (Runtime Generated):**
- Purpose: Output directory for generated STEP files and Adams command file
- Generated: Yes - created at runtime in Inventor workspace
- Committed: No - not in repository, lives in user's Inventor project workspace
- Contents: `output.cmd`, `Materials.txt`, `RigidBodies.txt`, `*.stp` files

**Base Template Files (External Dependency):**
- Location: `{workspacePath}/EXPORT/Base1.txt`, `{workspacePath}/EXPORT/Base2.txt`
- Purpose: Adams View command file header/footer templates
- Note: These files must exist in user's workspace; not included in repository

## File Type Reference

| Extension | Purpose | Tool |
|-----------|---------|------|
| `.bas` | VBA source module | Text editor / Inventor VBA IDE |
| `.ivb` | Compiled VBA project | Inventor VBA IDE only |
| `.stp` | STEP geometry output | CAD viewers |
| `.cmd` | Adams View command script | MSC Adams View |
| `.txt` | Intermediate data files | Generated at runtime |

---

*Structure analysis: 2026-01-18*
