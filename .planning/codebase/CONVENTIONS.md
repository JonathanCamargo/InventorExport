# Coding Conventions

**Analysis Date:** 2026-01-18

## Naming Patterns

**Files:**
- Module files use PascalCase: `Export.bas`, `Main.bas`, `Misc.bas`
- Module names match file names via `Attribute VB_Name` declaration

**Functions/Subroutines:**
- Public Subs use PascalCase: `ExportToSTEP`, `AppendMaterial`, `CalculateRotationAngles`
- Private Functions use PascalCase: `FindMinAbsIndex`, `Acos`
- Entry point is `Main()` in `Main.bas`
- Helper functions grouped in `Misc.bas`

**Variables:**
- Hungarian notation with type prefix: `oDoc` (object Document), `oApp` (object Application)
- Camel/lower prefix for primitives: `fileName`, `materialName`, `exportPath`
- Matrix elements use descriptive names: `a11`, `a12`, `a13` for matrix cells
- Constants use UPPER_SNAKE or PascalCase: `PI`, `TODEGREES`, `vbDoubleQuote`

**Parameters:**
- Use descriptive names: `name`, `id`, `location`, `orientation`
- ByVal for input parameters, ByRef for output arrays

## Code Style

**Formatting:**
- No external formatter configured
- Manual formatting with inconsistent spacing
- Some files have double line spacing (likely from copy/paste)

**Indentation:**
- 4 spaces or tabs (inconsistent)
- Single indentation for block contents

**Linting:**
- No linting tools configured
- Relies on VBA editor built-in syntax checking

## Module Organization

**Export.bas:**
- Contains all export-related functions
- STEP file export functions
- Adams View command file generation (materials, rigid bodies, geometry)

**Main.bas:**
- Entry point `Main()` subroutine
- Orchestrates the export workflow
- Iterates assemblies and calls Export functions

**Misc.bas:**
- Mathematical utility functions (`Atan2`, `Asin`, `Acos`)
- Rotation angle calculations
- File manipulation utilities (`AppendFiles`)
- Debug helpers (`clearDebugConsole`)

## Import/Reference Organization

**Inventor API References:**
- Use fully qualified types: `Inventor.Application`, `Inventor.Matrix`, `Inventor.Vector`
- Access via `ThisApplication` global object
- Document types: `AssemblyDocument`, `PartDocument`

**Object Access Pattern:**
```vb
Dim oApp As Inventor.Application
Set oApp = ThisApplication
Dim oDoc As AssemblyDocument
Set oDoc = oApp.ActiveDocument
```

## Error Handling

**Patterns:**
- Early exit with `MsgBox` for critical errors:
```vb
If oSTEPTranslator Is Nothing Then
    MsgBox "Could not access STEP translator."
    Exit Sub
End If
```
- `On Error GoTo` with labeled handlers for file operations:
```vb
On Error GoTo ErrHandler
' ... code ...
ErrHandler:
    MsgBox "Error # " & Err & ": " & Error(Err)
    Resume CloseFiles
```
- Cleanup sections with labels: `CloseFiles:`

**When to Use:**
- Use `MsgBox` for user-facing errors
- Use `On Error GoTo` for file I/O operations
- Always close file handles in error handlers

## Logging/Debugging

**Framework:** VBA `Debug.Print` (Immediate Window)

**Patterns:**
- Status messages for workflow progress:
```vb
Debug.Print ("Begining")
Debug.Print ("Looking for referenced files and materials")
Debug.Print ("Saving rigid bodies' configuration")
```
- Data inspection for debugging:
```vb
Debug.Print ("Export to: " & oData.fileName)
Debug.Print ("Material: " & materialName)
Debug.Print ("ROT MATRIX:")
Debug.Print (a11 & " " & a12 & " " & a13)
```
- Console clearing helper: `Call clearDebugConsole`

## Comments

**When to Comment:**
- Configuration options with magic numbers:
```vb
' 2 = AP 203 - Configuration Controlled Design
' 3 = AP 214 - Automotive Design
oOptions.value("ApplicationProtocolType") = 3
```
- Section markers for workflow steps:
```vb
' ------------------------------------ '
'First erase previous tmp files
'--------------------------------------'
```
- Algorithm explanation for complex math
- TODO markers for incomplete functionality

**Style:**
- Single quote comments
- No formal documentation standard (no XML docs)

## Function Design

**Size:**
- Small focused functions (10-50 lines typical)
- `Main()` is the largest at ~130 lines

**Parameters:**
- Input values passed ByVal (default)
- Output arrays passed ByRef explicitly
- Use Inventor types for 3D data: `Vector`, `Matrix`, `Point`

**Return Values:**
- Subroutines (`Sub`) for actions with side effects
- Functions (`Function`) return calculated values
- Use ByRef parameters for multiple outputs

## Module Design

**Exports:**
- All main functions declared `Public Sub` or `Public Sub`
- Helper functions declared `Private Function`
- Constants declared `Public Const` at module level

**File I/O Pattern:**
```vb
Open fileName For Append As #1
Print #1, "content"
Close #1
```

**File Handle Management:**
- Use fixed file numbers (#1) for simple operations
- Use `FreeFile()` for multiple simultaneous files

## String Handling

**Constants:**
```vb
Public Const vbDoubleQuote As String = """"
```

**Concatenation:**
- Use `&` operator for string concatenation
- Use `vbTab` for tab characters in output

## Mathematical Operations

**Custom Implementations Required:**
- VBA lacks standard trig functions
- Implement manually: `Acos()`, `Asin()`, `Atan2()`
- Use `Math.Atn()` as base for implementations

**Constants:**
```vb
Const PI = 3.14159265358979
Const TODEGREES As Double = 180 / PI
```

---

*Convention analysis: 2026-01-18*
