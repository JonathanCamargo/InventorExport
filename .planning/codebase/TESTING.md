# Testing Patterns

**Analysis Date:** 2026-01-18

## Test Framework

**Runner:**
- Not configured
- No automated testing framework detected

**Assertion Library:**
- Not applicable

**Run Commands:**
```bash
# No automated test commands available
# Manual testing via Autodesk Inventor VBA environment
```

## Test File Organization

**Location:**
- No test files present

**Naming:**
- Not established

**Structure:**
- Not applicable

## Current Testing Approach

**Manual Testing Only:**
- Code is tested manually within Autodesk Inventor
- Run `Main()` subroutine from VBA editor
- Observe `Debug.Print` output in Immediate Window
- Verify generated files in `EXPORT\` folder

**Debug Output for Verification:**
```vb
Debug.Print ("Begining")
Debug.Print ("File: " & oRefDoc.DisplayName)
Debug.Print ("Material: " & materialName)
Debug.Print ("Export: " & componentName)
Debug.Print ("ROT MATRIX:")
Debug.Print (a11 & " " & a12 & " " & a13)
```

## Test Data

**Prerequisites:**
- Active Autodesk Inventor assembly document
- Assembly with part references
- Materials assigned to parts
- `EXPORT\` folder in workspace
- Template files: `Base1.txt`, `Base2.txt` in EXPORT folder

**Output Verification:**
- Check `EXPORT\output.cmd` for generated Adams View commands
- Check `EXPORT\Materials.txt` for material definitions
- Check `EXPORT\RigidBodies.txt` for body configurations
- Verify STEP files created for each part

## Mocking

**Framework:** Not applicable

**Patterns:**
- No mocking infrastructure exists
- Testing requires live Inventor application with open assembly

## Coverage

**Requirements:** None enforced

**Current State:**
- 0% automated test coverage
- All testing is manual integration testing

## Test Types

**Unit Tests:**
- Not implemented
- Mathematical functions in `Misc.bas` are testable candidates:
  - `Atan2()`
  - `Asin()`
  - `Acos()`
  - `FindMinAbsIndex()`
  - `CalculateRotationAngles()`

**Integration Tests:**
- Not implemented
- Full workflow tested manually

**E2E Tests:**
- Not implemented
- Would require Inventor automation

## Recommended Testing Approach

**If Tests Were Added:**

1. **Mathematical Functions (Unit Testable):**
   - Extract `Misc.bas` math functions
   - Test with known input/output pairs
   - Verify rotation angle calculations against reference values

2. **File Generation (Integration):**
   - Mock Inventor objects
   - Verify generated command file format
   - Validate STEP export calls

3. **Workflow (E2E):**
   - Requires Inventor automation scripting
   - Load test assembly
   - Run export
   - Validate all outputs

## Known Testing Gaps

**Untested Areas:**
- All mathematical calculations in `Misc.bas`
- File path generation logic
- Material property extraction
- STEP export configuration
- Command file syntax validity

**Risk:**
- Changes to rotation calculations could break Adams View import
- File format changes undetected until runtime failure

**Priority:**
- High: `CalculateRotationAngles()` - core geometric transformation
- Medium: File generation functions
- Low: Debug/utility functions

---

*Testing analysis: 2026-01-18*
