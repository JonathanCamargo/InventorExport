# Technology Stack

**Analysis Date:** 2026-01-18

## Languages

**Primary:**
- VBA (Visual Basic for Applications) - All application logic

**Secondary:**
- None

## Runtime

**Environment:**
- Autodesk Inventor VBA Runtime (embedded in Inventor application)
- Requires Autodesk Inventor Professional to execute

**Package Manager:**
- None - VBA has no external package management

**Lockfile:**
- Not applicable

## Frameworks

**Core:**
- Autodesk Inventor API - CAD automation and document manipulation
- VBA Standard Library - Core language features

**Testing:**
- None detected

**Build/Dev:**
- Inventor VBA Editor (integrated development environment)

## Key Dependencies

**Critical:**
- `Inventor.Application` - Main Inventor API entry point
- `TranslatorAddIn` - STEP file export capability (AddIn ID: `{90AF7F40-0C01-11D5-8E83-0010B541CD80}`)
- `AssemblyDocument` / `PartDocument` - CAD document handling
- `ComponentOccurrence` - Assembly component traversal
- `Matrix` / `Vector` / `Point` - Geometric transformations

**Infrastructure:**
- VBA File I/O (`Open`, `Print`, `Close`) - Text file generation
- VBA Math functions (`Sqr`, `Atn`, `Abs`) - Rotation angle calculations

## Configuration

**Environment:**
- Inventor Design Project workspace path determines export location
- Export files written to `{WorkspacePath}\EXPORT\` directory
- No environment variables used

**Build:**
- `Inventor2AdamsView.ivb` - Compiled VBA project binary (205KB)
- Source modules: `Main.bas`, `Export.bas`, `Misc.bas`

## Platform Requirements

**Development:**
- Windows OS (Inventor is Windows-only)
- Autodesk Inventor Professional with VBA enabled
- Inventor VBA Editor access

**Production:**
- Same as development - executes within Inventor environment
- STEP Translator Add-In must be available in Inventor

## File Format Notes

**Input:**
- `.iam` (Inventor Assembly) - Primary input document
- `.ipt` (Inventor Part) - Referenced part documents

**Output:**
- `.stp` (STEP AP214) - Exported geometry files
- `.txt` (Text) - Material and rigid body definition files
- `.cmd` (Command) - Adams View command script

---

*Stack analysis: 2026-01-18*
