# Technology Stack

**Project:** Inventor Assembly Exporter (Python Rewrite)
**Researched:** 2026-01-19
**Research Constraints:** WebSearch and WebFetch unavailable; recommendations based on training data with honest confidence assessment.

## Recommended Stack

### Core COM Automation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pywin32 | 306+ | COM automation with Inventor | De facto standard for Windows COM in Python. Provides `win32com.client` which mirrors the VBA `CreateObject` pattern. Mature (25+ years), well-documented, actively maintained. | HIGH |
| Python | 3.11-3.12 | Runtime | System has 3.13.3 but 3.11-3.12 offer better library compatibility. pywin32 typically lags Python releases by 6-12 months. Verify pywin32 3.13 support before using. | MEDIUM |

**Why pywin32 over comtypes:**

| Factor | pywin32 | comtypes |
|--------|---------|----------|
| Maturity | 25+ years, very stable | Mature but less widespread |
| Dynamic dispatch | Excellent via `win32com.client.Dispatch` | Requires code generation for type info |
| Early binding | `win32com.client.gencache.EnsureDispatch` | Native strength |
| Documentation | Extensive, many examples | Less documentation |
| CAD automation precedent | Standard for AutoCAD, SolidWorks, Inventor | Rarely seen in CAD automation |
| Debugging | Better error messages | More cryptic COM errors |

**Recommendation:** Use pywin32. It's what the community uses for Inventor automation, and late binding via `Dispatch` works well for the Inventor API.

### XML and Format Generation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| lxml | 5.x | XML generation (URDF, MuJoCo) | Faster than stdlib `xml.etree`, better XPath support, pretty-printing built-in. Preferred for XML-heavy workloads. | HIGH |
| xml.etree.ElementTree | stdlib | Fallback XML generation | Zero dependencies. Sufficient if lxml installation is problematic. | HIGH |

**Why lxml over stdlib xml.etree:**
- Pretty-printing: `lxml.etree.tostring(tree, pretty_print=True)` vs manual indentation
- Performance: 10-50x faster for large documents
- XPath: Full XPath 1.0 support for complex queries
- Validation: Optional XML Schema validation

**URDF-specific libraries:**

| Library | Assessment | Recommendation | Confidence |
|---------|------------|----------------|------------|
| urdfpy | Reads/writes URDF, depends on trimesh | AVOID for generation - overkill dependency chain for what we need | MEDIUM |
| yourdfpy | Similar to urdfpy | AVOID - same reasoning | MEDIUM |
| urdf-parser-py (ROS) | ROS ecosystem library | AVOID - unnecessary ROS dependency | HIGH |
| Custom with lxml | Direct XML construction | USE THIS - URDF is simple XML, direct generation is cleaner | HIGH |

**Rationale:** URDF is a well-documented XML format. The schema is simple: `<robot>` containing `<link>` and `<joint>` elements. Writing a 100-line URDF generator with lxml is cleaner than pulling in trimesh and numpy dependencies for mesh handling we don't need (Inventor exports geometry to STEP, not meshes).

### MuJoCo Format

| Technology | Approach | Confidence |
|------------|----------|------------|
| lxml | Direct MJCF XML generation | HIGH |

**Rationale:** MuJoCo's MJCF format is also XML. Same approach as URDF - direct generation with lxml. The `mujoco` Python package exists but is for simulation, not model authoring.

### Project Structure and CLI

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| click | 8.x | CLI framework | Clean decorator-based API, excellent help generation, better than argparse for multi-command CLIs | HIGH |
| typer | 0.9+ | Alternative CLI | Type-hint based, modern. Consider if team prefers typing over decorators. | MEDIUM |
| argparse | stdlib | Fallback CLI | Zero dependencies but verbose for complex CLIs | HIGH |

**Recommendation:** Use `click`. It's the standard for Python CLIs. Simple commands can use argparse, but once you have subcommands (export, validate, list-formats), click's syntax is much cleaner.

### Data Modeling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| dataclasses | stdlib | Internal data model | Built-in, sufficient for assembly/part/material models. No external dependency. | HIGH |
| pydantic | 2.x | Alternative data model | Validation, serialization built-in. Overkill for internal models but useful if exporting/importing intermediate formats. | MEDIUM |
| attrs | 23.x | Alternative data model | More features than dataclasses, less than pydantic. Middle ground. | MEDIUM |

**Recommendation:** Start with `dataclasses` for the assembly data model. If you later need JSON serialization of the intermediate representation, consider migrating to pydantic.

### Testing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pytest | 8.x | Test framework | De facto standard. Fixtures, parametrization, plugins. | HIGH |
| pytest-mock | 3.x | Mocking | Cleaner mock syntax with pytest | HIGH |

**COM testing strategy:** The Inventor COM connection cannot be easily mocked. Structure code so that:
1. Thin COM layer extracts data into Python dataclasses
2. Format writers accept dataclasses, not COM objects
3. Format writers are fully testable without Inventor

### Development Tools

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ruff | 0.1+ | Linting and formatting | Replaces flake8, black, isort in one fast tool | HIGH |
| mypy | 1.x | Type checking | Static type verification | HIGH |
| pyproject.toml | standard | Project config | Modern Python packaging standard | HIGH |

### Package Management

| Technology | Recommendation | Confidence |
|------------|----------------|------------|
| pip + venv | Use for simplicity | HIGH |
| uv | Consider - faster pip alternative | MEDIUM |
| poetry | Avoid - overkill for this project | HIGH |

**Recommendation:** `pip` with a `pyproject.toml` and `requirements.txt` for pinned versions. Poetry adds complexity without benefit for a Windows-only tool.

## Complete Recommended Stack Summary

```
Python 3.11 or 3.12 (verify pywin32 3.13 compatibility first)

Core:
  pywin32 >= 306        # COM automation
  click >= 8.0          # CLI
  lxml >= 5.0           # XML generation

Dev:
  pytest >= 8.0         # Testing
  pytest-mock >= 3.0    # Mock helpers
  ruff >= 0.1           # Linting/formatting
  mypy >= 1.0           # Type checking
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| COM automation | pywin32 | comtypes | Less documentation, less CAD automation precedent |
| XML generation | lxml | xml.etree | etree lacks pretty-print, slower |
| URDF | lxml (direct) | urdfpy | Heavy dependencies (trimesh, numpy) for simple XML |
| CLI | click | argparse | argparse verbose for multi-command CLIs |
| Data model | dataclasses | pydantic | Pydantic overkill for internal models |

## What NOT to Use

| Technology | Why Avoid |
|------------|-----------|
| comtypes for Inventor | Less community support for CAD automation, pywin32 is standard |
| urdfpy/yourdfpy | Pulls in trimesh, numpy, networkx - unnecessary for XML generation |
| mujoco package | For simulation, not model authoring |
| poetry | Overcomplicated for Windows-only single-purpose tool |
| pyinstaller (yet) | Premature - focus on working script first |
| pythonnet | .NET bridge, not COM - wrong tool for Inventor API |

## Installation

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Core dependencies
pip install pywin32 click lxml

# Dev dependencies
pip install pytest pytest-mock ruff mypy

# Generate COM type library cache (optional, for autocomplete)
# Run once after Inventor is installed:
# python -c "import win32com.client; win32com.client.gencache.EnsureDispatch('Inventor.Application')"
```

## pyproject.toml Structure

```toml
[project]
name = "inventor-exporter"
version = "0.1.0"
description = "Export Autodesk Inventor assemblies to simulation formats"
requires-python = ">=3.11"
dependencies = [
    "pywin32>=306",
    "click>=8.0",
    "lxml>=5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.0",
    "ruff>=0.1",
    "mypy>=1.0",
]

[project.scripts]
inventor-export = "inventor_exporter.cli:main"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

## Project Structure Convention

```
inventor-exporter/
├── pyproject.toml
├── README.md
├── src/
│   └── inventor_exporter/
│       ├── __init__.py
│       ├── cli.py                 # Click CLI entry point
│       ├── inventor/
│       │   ├── __init__.py
│       │   ├── connection.py      # COM connection management
│       │   ├── assembly.py        # Assembly traversal
│       │   └── extraction.py      # Data extraction from COM objects
│       ├── model/
│       │   ├── __init__.py
│       │   ├── assembly.py        # Assembly dataclass
│       │   ├── part.py            # Part dataclass
│       │   └── material.py        # Material dataclass
│       ├── writers/
│       │   ├── __init__.py
│       │   ├── base.py            # Abstract writer interface
│       │   ├── adams.py           # ADAMS View writer
│       │   ├── urdf.py            # URDF writer
│       │   └── mujoco.py          # MuJoCo writer
│       └── geometry/
│           ├── __init__.py
│           └── step_export.py     # STEP export via Inventor
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures
│   ├── test_model/                # Data model tests
│   ├── test_writers/              # Format writer tests (no Inventor needed)
│   └── integration/               # Full pipeline tests (needs Inventor)
└── .planning/
    └── ...
```

**Key principles:**
- `src/` layout prevents import confusion
- `inventor/` package isolates all COM interaction
- `model/` package defines pure Python dataclasses
- `writers/` package has one module per format
- Format writers accept dataclasses, not COM objects (testable)

## Inventor COM Connection Pattern

```python
# inventor/connection.py
import win32com.client

class InventorConnection:
    """Manages COM connection to Inventor."""

    def __init__(self):
        self._app = None

    def connect(self) -> None:
        """Connect to running Inventor instance."""
        try:
            self._app = win32com.client.GetActiveObject("Inventor.Application")
        except Exception:
            raise RuntimeError("Inventor is not running")

    @property
    def app(self):
        """Access Inventor.Application COM object."""
        if self._app is None:
            raise RuntimeError("Not connected to Inventor")
        return self._app

    @property
    def active_document(self):
        """Get active document, must be AssemblyDocument."""
        doc = self.app.ActiveDocument
        if doc is None:
            raise RuntimeError("No document open in Inventor")
        # DocumentType 12291 = kAssemblyDocumentObject
        if doc.DocumentType != 12291:
            raise RuntimeError("Active document is not an assembly")
        return doc
```

## Confidence Assessment Summary

| Area | Level | Reason |
|------|-------|--------|
| pywin32 for COM | HIGH | Industry standard, extensive precedent |
| lxml for XML | HIGH | Well-established, widely used |
| click for CLI | HIGH | De facto Python CLI standard |
| dataclasses | HIGH | Stdlib, no external dependency |
| Project structure | HIGH | Standard Python conventions |
| pywin32 Python 3.13 | LOW | Need to verify compatibility |
| URDF library avoidance | MEDIUM | Based on dependency analysis, not direct testing |

## Gaps and Open Questions

1. **pywin32 + Python 3.13 compatibility**: System has Python 3.13.3. Need to verify pywin32 works. Fallback: use Python 3.11 or 3.12.

2. **Inventor type library generation**: Early binding via `gencache.EnsureDispatch` provides better autocomplete but may require Inventor to be installed. Late binding (`Dispatch`) works without but no autocomplete.

3. **STEP export mechanism**: VBA uses `TranslatorAddIn` with GUID. Need to verify same approach works from Python COM.

4. **Coordinate system conventions**: ADAMS, URDF, and MuJoCo may use different coordinate conventions. Research needed during format writer implementation.

---

*Stack research: 2026-01-19*
*Note: WebSearch/WebFetch unavailable. Recommendations based on training data. Verify versions against current PyPI before finalizing.*
