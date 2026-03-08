"""Import STL files and convert to Inventor IPT format.

Opens each STL in Inventor, converts the mesh to a base feature (BRep solid),
deletes the original mesh, and saves as .ipt.
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from inventor_exporter.core.com import inventor_app, late_bind

logger = logging.getLogger(__name__)

MESH_FEATURE_TYPE = 84052736


def import_stl_folder(input_dir: Path, output_dir: Path | None = None) -> List[Path]:
    """Import all STL files from a folder, converting each to IPT."""
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
        for stl_file in stl_files:
            try:
                ipt_path = import_single_stl(app, stl_file, output_dir)
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


def import_single_stl(app: Any, stl_path: Path, output_dir: Path) -> Path:
    """Import a single STL file and save as IPT."""
    ipt_path = output_dir / (stl_path.stem + ".ipt")

    doc = late_bind(app.Documents.Open(str(stl_path.resolve())))

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

    return ipt_path
