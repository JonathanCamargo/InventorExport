# Architecture

**Analysis Date:** 2026-01-18

## Pattern Overview

**Overall:** Autodesk Inventor VBA Macro - Procedural Script Architecture

**Key Characteristics:**
- Single-entry-point procedural design with `Main()` as orchestrator
- Module-based organization separating concerns by function domain
- Direct Inventor API integration via COM automation
- File-based output generation for Adams View multibody dynamics software

## Layers

**Entry/Orchestration Layer:**
- Purpose: Coordinates the entire export workflow from start to finish
- Location: `D:/git/inventorexport/Main.bas`
- Contains: Main subroutine, document iteration, assembly traversal logic
- Depends on: Export module, Misc module, Inventor API
- Used by: User (executed manually within Inventor)

**Export/Translation Layer:**
- Purpose: Handles STEP file export and Adams View command file generation
- Location: `D:/git/inventorexport/Export.bas`
- Contains: STEP translator wrapper, Adams View command generators
- Depends on: Inventor Translator AddIn API, file system
- Used by: Main module

**Utility Layer:**
- Purpose: Mathematical utilities and helper functions
- Location: `D:/git/inventorexport/Misc.bas`
- Contains: Rotation angle calculations, trigonometric functions, file operations
- Depends on: VBA Math library, Inventor TransientGeometry API
- Used by: Main module

## Data Flow

**Primary Export Flow:**

1. User opens assembly in Inventor and executes `Main()`
2. `Main()` retrieves active assembly document via `ThisApplication.ActiveDocument`
3. Iterates referenced part documents, extracts materials, calls `ExportToSTEP()` for each
4. Traverses all leaf occurrences (individual part instances) in assembly hierarchy
5. For each occurrence: extracts transformation matrix, calculates Euler angles via `CalculateRotationAngles()`
6. Appends rigid body definitions to temporary text files via `AppendRigidBody()`, `AppendMassProperties()`, `AppendGeometryProperties()`
7. Concatenates base template files and generated data into final `output.cmd`

**State Management:**
- No persistent state; each execution is stateless
- Temporary state held in local variables and intermediate files in `EXPORT/` folder
- Material tracking via in-memory array (`materials()`) during single execution

## Key Abstractions

**Inventor Document Hierarchy:**
- Purpose: Represents CAD assembly structure
- Examples: `AssemblyDocument`, `PartDocument`, `ComponentOccurrence`
- Pattern: COM object traversal via enumerators (`DocumentsEnumerator`, `ComponentOccurrencesEnumerator`)

**Transformation Matrix:**
- Purpose: Encapsulates part position and orientation in 3D space
- Examples: `Inventor.Matrix`, `Inventor.Vector`
- Pattern: Matrix decomposition to extract translation and rotation angles

**STEP Translator:**
- Purpose: Converts Inventor part geometry to neutral STEP format
- Examples: `TranslatorAddIn` identified by GUID `{90AF7F40-0C01-11D5-8E83-0010B541CD80}`
- Pattern: Plugin/AddIn pattern with options via `NameValueMap`

## Entry Points

**Main():**
- Location: `D:/git/inventorexport/Main.bas` line 2
- Triggers: Manual execution by user within Inventor VBA environment
- Responsibilities: Full assembly-to-Adams-View export pipeline

**ExportActiveToSTEP():**
- Location: `D:/git/inventorexport/Export.bas` line 43
- Triggers: Manual execution (standalone utility)
- Responsibilities: Export current active document to STEP (hardcoded path)

## Error Handling

**Strategy:** Minimal - relies on VBA default error propagation with selective handling

**Patterns:**
- Null check for STEP translator availability with `MsgBox` notification and early exit
- `On Error GoTo` handler in `AppendFiles()` for file operation failures
- No error handling in Main() - failures propagate to VBA runtime

## Cross-Cutting Concerns

**Logging:** Debug console output via `Debug.Print` statements throughout execution
**Validation:** None - assumes valid assembly document is active
**Authentication:** Not applicable - runs in context of Inventor user session

---

*Architecture analysis: 2026-01-18*
