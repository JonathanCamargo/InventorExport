"""Import STL files and convert to Inventor IPT format.

Opens each STL in Inventor, converts the mesh to a base feature (BRep solid),
deletes the original mesh, and saves as .ipt.

Unit handling:
    STL files are unitless. Inventor interprets vertex coordinates using the
    default part template's length units at Documents.Open() time. If the
    template uses inches but the STL is in mm, vertices are 25.4x too large.
    This cannot be corrected after opening.

    To compensate, we detect the template units by opening a temporary blank
    part, compare with the user's --units flag, and prescale the STL binary
    data before opening in Inventor.
"""

import ctypes
import ctypes.wintypes
import logging
import os
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from inventor_exporter.core.com import inventor_app, late_bind

logger = logging.getLogger(__name__)

MESH_FEATURE_TYPE = 84052736

# Inventor UnitsTypeEnum values for length units
_LENGTH_UNITS = {
    "mm": 11267,   # kMillimeterLengthUnits
    "cm": 11266,   # kCentimeterLengthUnits
    "m":  11268,   # kMeterLengthUnits
    "in": 11272,   # kInchLengthUnits
    "ft": 11273,   # kFootLengthUnits
}

# Reverse map for logging
_LENGTH_UNIT_NAMES = {v: k for k, v in _LENGTH_UNITS.items()}

# Conversion factors from each unit to centimeters (Inventor internal unit)
_UNIT_TO_CM = {
    "mm": 0.1,
    "cm": 1.0,
    "m":  100.0,
    "in": 2.54,
    "ft": 30.48,
}

# Inventor DocumentTypeEnum
_kPartDocumentObject = 12290


def import_stl_folder(
    input_dir: Path,
    output_dir: Path | None = None,
    units: str = "mm",
) -> List[Path]:
    """Import all STL files from a folder, converting each to IPT.

    Args:
        input_dir: Directory containing STL files.
        output_dir: Output directory for IPT files. Defaults to input_dir.
        units: Length unit of the STL coordinates (mm, cm, m, in, ft).
            STL files are unitless; this tells Inventor how to interpret the
            vertex coordinates. Default "mm" (the de facto STL convention).
    """
    if output_dir is None:
        output_dir = input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    stl_files = sorted(input_dir.glob("*.stl"))
    if not stl_files:
        logger.warning(f"No STL files found in {input_dir}")
        return []

    logger.info(f"Found {len(stl_files)} STL files")

    created = []
    with inventor_app() as app:
        # Detect template units by probing the first STL file
        template_units = _detect_template_units(app, stl_files[0])
        if template_units is None:
            logger.warning("Could not detect template units, assuming they match --units")
            prescale = 1.0
        elif template_units == units:
            logger.info(f"Template units match STL units: {units}")
            prescale = 1.0
        else:
            prescale = _compute_prescale(template_units, units)
            logger.warning(
                f"Template uses '{template_units}' but STL units are '{units}'. "
                f"Prescaling vertices by {prescale:.6f} to compensate."
            )

        for stl_file in stl_files:
            try:
                ipt_path = import_single_stl(
                    app, stl_file, output_dir, prescale,
                )
                created.append(ipt_path)
                logger.info(f"Converted: {stl_file.name} -> {ipt_path.name}")
            except Exception as e:
                logger.error(f"Failed to convert {stl_file.name}: {e}")

    return created


def _find_mesh_in_browser(doc: Any) -> Tuple[Optional[Any], Optional[Any]]:
    """Find mesh feature browser node and NativeObject via Pane 2."""
    panes = late_bind(doc.BrowserPanes)
    pane = late_bind(panes.Item(2))
    top = late_bind(pane.TopNode)
    nodes = late_bind(top.BrowserNodes)

    for i in range(1, nodes.Count + 1):
        try:
            node = late_bind(nodes.Item(i))
            native = late_bind(node.NativeObject)
            if native.Type == MESH_FEATURE_TYPE:
                return node, native
        except Exception:
            continue

    return None, None


def _select_mesh(doc: Any, mesh_node: Any, mesh_obj: Any) -> bool:
    """Try multiple approaches to select the mesh feature."""
    for fn in [
        lambda: mesh_node.DoSelect(),
        lambda: setattr(mesh_node, 'Selected', True),
        lambda: (late_bind(doc.SelectSet).Clear(),
                 late_bind(doc.SelectSet).Select(mesh_obj)),
    ]:
        try:
            fn()
            return True
        except Exception:
            pass
    return False


def _auto_handle_mesh_dialog():
    """Background thread: find MeshEnabler dialog, click first unnamed radio
    button (Solid — first option in the Output group), then click OK."""
    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5
    BS_AUTORADIOBUTTON = 0x0009
    GWL_STYLE = -16

    # Wait for dialog — try multiple possible titles
    hwnd = 0
    titles = [
        "Mesh Enabler", "Convert to Base Feature",
        "Base Feature", "Mesh to BRep",
    ]
    for _ in range(100):
        time.sleep(0.1)
        for title in titles:
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                break
        if hwnd:
            break
    if not hwnd:
        logger.debug("    Dialog not found by title, searching all windows...")
        # Fallback: find any new dialog owned by Inventor
        return

    time.sleep(0.3)

    # Enumerate child controls
    controls = []

    @ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )
    def enum_callback(child_hwnd, lparam):
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(child_hwnd, class_name, 256)
        text = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(child_hwnd, text, 256)
        style = user32.GetWindowLongW(child_hwnd, GWL_STYLE)
        controls.append((child_hwnd, class_name.value, text.value, style))
        return True

    user32.EnumChildWindows(hwnd, enum_callback, 0)

    # The dialog has: Output (group), two unnamed radio buttons (Solid/Surface),
    # Delete Original (checkbox), OK, Cancel.
    # Click the FIRST unnamed radio button after the "Output" group = Solid.
    found_output_group = False
    solid_clicked = False
    for child_hwnd, cls, text, style in controls:
        if text == 'Output':
            found_output_group = True
            continue
        if found_output_group and cls.lower() == 'button' and text == '':
            # First unnamed button after Output group = Solid
            user32.SendMessageW(child_hwnd, BM_CLICK, 0, 0)
            logger.debug("    Clicked Solid (first radio after Output)")
            solid_clicked = True
            break

    time.sleep(0.2)

    # Click OK
    for child_hwnd, cls, text, style in controls:
        if text == 'OK':
            user32.SendMessageW(child_hwnd, BM_CLICK, 0, 0)
            logger.debug("    Clicked OK")
            break


def _dismiss_popups(stop: threading.Event):
    """Background thread: repeatedly scan for error/warning popups and click OK."""
    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5

    ENUM_CB_TYPE = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def _try_dismiss(title):
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        children = []

        @ENUM_CB_TYPE
        def cb(child, _lp):
            txt = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(child, txt, 256)
            children.append((child, txt.value))
            return True

        user32.EnumChildWindows(hwnd, cb, 0)
        for ch, txt in children:
            if txt in ("OK", "Close", "Yes"):
                user32.SendMessageW(ch, BM_CLICK, 0, 0)
                logger.debug(f"    Dismissed '{title}' popup")
                return True
        return False

    while not stop.is_set():
        for title in [
            "File delete Error on Save",
            "File delete Error",
            "Autodesk Inventor",
            "Error",
            "Warning",
        ]:
            _try_dismiss(title)
        stop.wait(0.1)


def _detect_template_units(app: Any, stl_path: Path) -> Optional[str]:
    """Detect the template units Inventor uses when opening an STL file.

    Opens the STL file, reads the document's LengthUnits, and closes it.
    This is more reliable than Documents.Add() which may use a different
    default template than Documents.Open() for mesh files.

    Args:
        app: Inventor.Application COM object.
        stl_path: An STL file to probe with.

    Returns:
        Unit key (e.g. "mm", "in") or None if detection fails.
    """
    try:
        doc = late_bind(app.Documents.Open(str(stl_path.resolve())))
        try:
            uom = late_bind(doc.UnitsOfMeasure)
            enum_val = uom.LengthUnits
            return _LENGTH_UNIT_NAMES.get(enum_val)
        finally:
            doc.Close(True)
    except Exception as e:
        logger.debug(f"Could not detect template units: {e}")
        return None


def _compute_prescale(template_units: str, stl_units: str) -> float:
    """Compute scale factor to compensate for unit mismatch.

    When Inventor opens an STL, it interprets raw vertex coordinates using
    the template's units. If the STL is in mm but the template is in
    inches, a vertex value of 52 becomes 52 inches instead of 52 mm.

    We prescale the STL vertices so that when Inventor misinterprets them,
    the resulting internal cm values are correct.

    Math: vertex_cm = raw_value * template_cm_per_unit
          We want:   vertex_cm = raw_value * stl_cm_per_unit
          So prescale raw_value by: stl_cm / template_cm

    Returns:
        Scale factor to multiply STL vertices by (1.0 if no correction needed).
    """
    stl_cm = _UNIT_TO_CM.get(stl_units)
    template_cm = _UNIT_TO_CM.get(template_units)
    if stl_cm is None or template_cm is None:
        return 1.0
    return stl_cm / template_cm


def _prescale_stl(stl_path: Path, scale: float) -> Path:
    """Create a prescaled copy of a binary STL file.

    Multiplies all vertex coordinates by the scale factor. Normals are
    left unchanged (uniform scaling preserves direction).

    Args:
        stl_path: Original STL file.
        scale: Uniform scale factor for vertices.

    Returns:
        Path to temporary scaled STL file, or the original path if the
        file is not binary STL (ASCII STL cannot be prescaled this way).
    """
    data = bytearray(stl_path.read_bytes())

    # Validate binary STL: 80-byte header + 4-byte count + 50 bytes per triangle
    if len(data) < 84:
        logger.warning(f"STL too small to prescale: {stl_path.name}")
        return stl_path

    n_triangles = struct.unpack_from('<I', data, 80)[0]
    expected_size = 84 + 50 * n_triangles

    if len(data) != expected_size:
        logger.warning(
            f"Cannot prescale {stl_path.name} (ASCII STL or unexpected size). "
            f"Geometry may have wrong scale."
        )
        return stl_path

    # Scale vertex coordinates (skip normals)
    # Each triangle: 12 bytes normal + 36 bytes vertices (3×3 floats) + 2 bytes attr
    for i in range(n_triangles):
        vertex_offset = 84 + i * 50 + 12  # skip header + normal
        for j in range(9):  # 3 vertices × 3 coordinates
            pos = vertex_offset + j * 4
            val = struct.unpack_from('<f', data, pos)[0]
            struct.pack_into('<f', data, pos, val * scale)

    fd, tmp_path = tempfile.mkstemp(suffix='.stl', dir=stl_path.parent)
    os.write(fd, bytes(data))
    os.close(fd)
    return Path(tmp_path)


def import_single_stl(
    app: Any, stl_path: Path, output_dir: Path, prescale: float = 1.0,
) -> Path:
    """Import a single STL file and save as IPT.

    Args:
        app: Inventor.Application COM object.
        stl_path: Path to the STL file.
        output_dir: Output directory for IPT file.
        prescale: Scale factor applied to STL vertices before opening
            to compensate for template unit mismatch. 1.0 = no change.
    """
    ipt_path = output_dir / (stl_path.stem + ".ipt")

    # Prescale STL if template units don't match source units
    actual_stl = stl_path
    if abs(prescale - 1.0) > 1e-6:
        actual_stl = _prescale_stl(stl_path, prescale)

    doc = late_bind(app.Documents.Open(str(actual_stl.resolve())))

    try:
        # Find and select mesh
        mesh_node, mesh_obj = _find_mesh_in_browser(doc)
        if mesh_obj is None:
            raise RuntimeError("No mesh feature found in browser")

        if not _select_mesh(doc, mesh_node, mesh_obj):
            raise RuntimeError("Could not select mesh feature")

        # Start dialog handler, then execute command (blocks until dialog done)
        dialog_thread = threading.Thread(
            target=_auto_handle_mesh_dialog, daemon=True
        )
        dialog_thread.start()

        ctrl_defs = late_bind(
            late_bind(app.CommandManager).ControlDefinitions
        )
        mesh_cmd = late_bind(ctrl_defs.Item("MeshEnablerCmd"))
        logger.debug(f"  Converting {stl_path.name}...")
        mesh_cmd.Execute()
        dialog_thread.join(timeout=5)

        # Re-get doc reference (may have changed after command)
        doc = late_bind(app.ActiveDocument)

        # Delete original mesh if still present
        mesh_node2, mesh_obj2 = _find_mesh_in_browser(doc)
        if mesh_obj2 is not None:
            try:
                mesh_obj2.Delete()
            except Exception:
                pass

        # Remove existing IPT if present
        if ipt_path.exists():
            try:
                ipt_path.unlink()
            except OSError:
                pass

        # Save a *copy* as IPT (SaveCopyAs=True) so Inventor doesn't try to
        # re-associate the document away from the open STL file, which causes
        # "File delete Error on Save" popups.  A dismisser thread handles the
        # cases where the popup still appears.
        stop_evt = threading.Event()
        dismisser = threading.Thread(
            target=_dismiss_popups, args=(stop_evt,), daemon=True
        )
        dismisser.start()

        ipt_str = str(ipt_path.resolve())
        doc.SaveAs(ipt_str, True)

        stop_evt.set()
        dismisser.join(timeout=3)

    finally:
        try:
            doc = late_bind(app.ActiveDocument)
            doc.Close(True)
        except Exception:
            pass
        # Clean up temp prescaled STL
        if actual_stl != stl_path:
            try:
                actual_stl.unlink()
            except OSError:
                pass

    return ipt_path
