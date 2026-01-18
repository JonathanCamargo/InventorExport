# External Integrations

**Analysis Date:** 2026-01-18

## APIs & External Services

**Autodesk Inventor API:**
- Purpose: CAD document access, geometry extraction, file export
- Access Method: COM automation via VBA
- Key Objects:
  - `ThisApplication` - Global Inventor application instance
  - `ThisApplication.ApplicationAddIns` - Translator plugins
  - `ThisApplication.TransientObjects` - Temporary object creation
  - `ThisApplication.TransientGeometry` - Geometric primitive creation
  - `ThisApplication.DesignProjectManager` - Project/workspace paths
  - `ThisApplication.ActiveMaterialLibrary` - Material property access

**STEP Translator Add-In:**
- Purpose: Export CAD geometry to STEP format
- AddIn ID: `{90AF7F40-0C01-11D5-8E83-0010B541CD80}`
- Protocol: AP214 (Automotive Design) configured
- Access: `ThisApplication.ApplicationAddIns.ItemById()`

## Data Storage

**Databases:**
- None

**File Storage:**
- Local filesystem only
- Export directory: `{ActiveDesignProject.WorkspacePath}\EXPORT\`
- Generated files:
  - `output.cmd` - Main Adams View command script
  - `Materials.txt` - Material definitions
  - `RigidBodies.txt` - Rigid body configurations
  - `{PartName}.stp` - Individual STEP geometry files
  - `Base1.txt`, `Base2.txt` - Template fragments (required, not generated)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None - Runs in local Inventor session
- Inherits Inventor application permissions

## Monitoring & Observability

**Error Tracking:**
- Basic `MsgBox` error dialogs for user notification
- `On Error GoTo` handlers in file operations

**Logs:**
- `Debug.Print` statements to Inventor VBA Immediate window
- No persistent logging

## CI/CD & Deployment

**Hosting:**
- Local installation only
- Manual deployment of `.ivb` file to Inventor Add-Ins location

**CI Pipeline:**
- None

## Environment Configuration

**Required env vars:**
- None - Configuration is internal to Inventor

**Required setup:**
- Active Inventor Design Project with workspace path configured
- `EXPORT` folder must exist in workspace path
- Template files `Base1.txt` and `Base2.txt` must exist in EXPORT folder

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Target System Integration

**MSC Adams View:**
- Purpose: Multi-body dynamics simulation software
- Integration: Command file generation (`.cmd` format)
- Generated constructs:
  - Material definitions (`material create`)
  - Rigid body parts (`part create rigid_body name_and_position`)
  - Mass properties (`part create rigid_body mass_properties`)
  - Geometry imports (`file geometry read`)
  - Geometry attributes (`geometry attributes`)
- Coordinate system: Model-relative with ground reference

---

*Integration audit: 2026-01-18*
