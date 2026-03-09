"""Extract assembly constraints and joints from Inventor COM.

Reads both traditional assembly constraints (Mate, Flush, Insert, Angle,
Tangent) and newer assembly joints (Rigid, Rotational, Slider, Cylindrical,
Planar, Ball) from the active assembly.

All property access uses try/except for robustness with late-binding COM.
"""

import logging
from typing import List, Optional, Tuple

import pythoncom
import win32com.client.dynamic

from inventor_exporter.core.com import late_bind
from inventor_exporter.core.units import InventorUnits
from inventor_exporter.model.constraint import ConstraintInfo

logger = logging.getLogger(__name__)

# DISPID for Face.Geometry (inner surface geometry, e.g. Cylinder)
# Late binding can't resolve this on FaceProxy objects, so we invoke by DISPID.
_FACE_GEOMETRY_DISPID = 67119422


def extract_constraints_and_joints(asm_def) -> List[ConstraintInfo]:
    """Extract all constraints and joints from an assembly definition.

    Args:
        asm_def: Inventor AssemblyComponentDefinition COM object.

    Returns:
        List of ConstraintInfo for each constraint/joint found.
    """
    results: List[ConstraintInfo] = []

    # --- Traditional assembly constraints ---
    try:
        constraints = asm_def.Constraints
        count = constraints.Count
        logger.info("Found %d assembly constraints", count)
        for i in range(1, count + 1):
            try:
                info = _extract_constraint(constraints.Item(i))
                if info is not None:
                    results.append(info)
            except Exception as e:
                logger.warning("Failed to extract constraint %d: %s", i, e)
    except Exception as e:
        logger.warning("Could not access assembly constraints: %s", e)

    # --- Assembly joints (Inventor 2014+) ---
    try:
        joints = asm_def.Joints
        count = joints.Count
        logger.info("Found %d assembly joints", count)
        for i in range(1, count + 1):
            try:
                info = _extract_joint(joints.Item(i))
                if info is not None:
                    results.append(info)
            except Exception as e:
                logger.warning("Failed to extract joint %d: %s", i, e)
    except Exception as e:
        # Joints collection may not exist in older Inventor versions
        logger.info("Assembly joints not available: %s", e)

    return results


# ---------------------------------------------------------------------------
# Constraint extraction
# ---------------------------------------------------------------------------

def _occ_name_from_entity(entity):
    """Get the containing occurrence name from a constraint entity proxy."""
    try:
        return entity.ContainingOccurrence.Name
    except Exception:
        return None


def _extract_constraint(constraint) -> "ConstraintInfo | None":
    """Extract data from a single assembly constraint."""
    try:
        if getattr(constraint, "Suppressed", False):
            return None
    except Exception:
        pass

    name = ""
    try:
        name = constraint.Name
    except Exception:
        pass

    # --- Determine occurrences ---
    occ_one = None
    occ_two = None

    # Constraints reference geometry entities; the occurrence is on the entity.
    try:
        occ_one = _occ_name_from_entity(constraint.EntityOne)
    except Exception:
        pass
    if occ_one is None:
        try:
            occ_one = constraint.OccurrenceOne.Name
        except Exception:
            pass

    try:
        occ_two = _occ_name_from_entity(constraint.EntityTwo)
    except Exception:
        pass
    if occ_two is None:
        try:
            occ_two = constraint.OccurrenceTwo.Name
        except Exception:
            pass

    if occ_one is None and occ_two is None:
        logger.debug("Skipping constraint '%s': cannot determine occurrences", name)
        return None

    occ_one = occ_one or "unknown"
    occ_two = occ_two or "unknown"

    # --- Detect type and extract properties ---
    constraint_type = _detect_constraint_type(constraint)
    offset = _read_offset(constraint)
    angle = _read_angle(constraint)

    logger.debug(
        "Constraint: %s (%s) %s <-> %s", name, constraint_type, occ_one, occ_two
    )

    return ConstraintInfo(
        type=constraint_type,
        occurrence_one=occ_one,
        occurrence_two=occ_two,
        is_rigid=False,
        name=name,
        offset=offset,
        angle=angle,
    )


def _detect_constraint_type(constraint) -> str:
    """Determine constraint type by probing type-specific properties."""
    # Try the Type property (ObjectTypeEnum integer)
    type_val = None
    try:
        type_val = constraint.Type
    except Exception:
        pass

    # Probe for Mate / Flush (both have Offset)
    try:
        _ = constraint.Offset
        # Distinguish by SolutionType if possible
        try:
            sol = constraint.SolutionType
            # kFlushSolutionType = 0, kMateSolutionType = 1 (typical)
            if sol == 0:
                return "flush"
            return "mate"
        except Exception:
            return "mate_or_flush"
    except Exception:
        pass

    # Probe for Insert (has AxialOffset)
    try:
        _ = constraint.AxialOffset
        return "insert"
    except Exception:
        pass

    # Probe for Angle
    try:
        _ = constraint.Angle
        return "angle"
    except Exception:
        pass

    # Probe for Tangent (has InsideAlignment)
    try:
        _ = constraint.InsideAlignment
        return "tangent"
    except Exception:
        pass

    if type_val is not None:
        return f"constraint_{type_val}"
    return "unknown_constraint"


def _read_offset(constraint) -> "float | None":
    """Read distance offset (meters) from a Mate/Flush constraint."""
    try:
        raw = constraint.Offset
        val = raw.Value if hasattr(raw, "Value") else float(raw)
        return InventorUnits.length_to_meters(val)
    except Exception:
        return None


def _read_angle(constraint) -> "float | None":
    """Read angle (radians) from an Angle constraint."""
    try:
        raw = constraint.Angle
        return raw.Value if hasattr(raw, "Value") else float(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Joint extraction
# ---------------------------------------------------------------------------

# AssemblyJointTypeEnum (Inventor 2014+)
# Values from Definition.JointType (not the ObjectTypeEnum).
# 102402 confirmed as rotational; others assumed sequential.
_JOINT_TYPE_NAMES = {
    102401: "rigid_joint",
    102402: "rotational_joint",
    102403: "slider_joint",
    102404: "cylindrical_joint",
    102405: "planar_joint",
    102406: "ball_joint",
}


def _extract_axis_from_origin(defn, attr_name: str) -> Optional[Tuple[float, float, float]]:
    """Extract rotation axis from a joint origin's geometry.

    Tries multiple approaches since the origin geometry type varies:
    1. DISPID invoke on cylindrical face → Cylinder.AxisVector
    2. Geometry.AxisVector directly (work axis, edge)
    3. Geometry.Direction (line-based geometry)
    4. origin.Direction (some joint origin types)
    """
    try:
        origin = late_bind(getattr(defn, attr_name))
    except Exception as e:
        logger.debug("Could not access %s: %s", attr_name, e)
        return None

    # Approach 1: DISPID invoke for cylindrical face geometry
    try:
        face = late_bind(origin.Geometry)
        inner_raw = face._oleobj_.Invoke(
            _FACE_GEOMETRY_DISPID, 0, pythoncom.DISPATCH_PROPERTYGET, True
        )
        inner = win32com.client.dynamic.Dispatch(
            inner_raw.QueryInterface(pythoncom.IID_IDispatch)
        )
        av = inner.AxisVector
        return (float(av.X), float(av.Y), float(av.Z))
    except Exception:
        pass

    # Approach 2: Geometry.AxisVector directly (e.g. WorkAxis proxy)
    try:
        geom = late_bind(origin.Geometry)
        av = geom.AxisVector
        return (float(av.X), float(av.Y), float(av.Z))
    except Exception:
        pass

    # Approach 3: Geometry.Direction (line-based geometry)
    try:
        geom = late_bind(origin.Geometry)
        d = geom.Direction
        return (float(d.X), float(d.Y), float(d.Z))
    except Exception:
        pass

    # Approach 4: origin.Direction
    try:
        d = origin.Direction
        return (float(d.X), float(d.Y), float(d.Z))
    except Exception:
        pass

    # Approach 5: Geometry is a Line → Line.Direction
    try:
        geom = late_bind(origin.Geometry)
        line = late_bind(geom.Line)
        d = line.Direction
        return (float(d.X), float(d.Y), float(d.Z))
    except Exception:
        pass

    logger.debug("Could not extract axis from %s (all approaches failed)", attr_name)
    return None


def _extract_axis_from_definition(defn) -> Optional[Tuple[float, float, float]]:
    """Try to extract axis directly from joint definition properties."""
    # Try AxisVector on the definition itself
    try:
        av = defn.AxisVector
        return (float(av.X), float(av.Y), float(av.Z))
    except Exception:
        pass

    # Try AlignmentDirection
    try:
        d = defn.AlignmentDirection
        return (float(d.X), float(d.Y), float(d.Z))
    except Exception:
        pass

    # Try AngularPositionVector
    try:
        av = defn.AngularPositionVector
        return (float(av.X), float(av.Y), float(av.Z))
    except Exception:
        pass

    logger.debug("Could not extract axis from joint definition properties")
    return None


def _extract_joint(joint) -> "ConstraintInfo | None":
    """Extract data from a single assembly joint."""
    try:
        if getattr(joint, "Suppressed", False):
            return None
    except Exception:
        pass

    name = ""
    try:
        name = joint.Name
    except Exception:
        pass

    # --- Occurrences ---
    occ_one = None
    occ_two = None

    for attr_one, attr_two in [
        ("OccurrenceOne", "OccurrenceTwo"),
        ("AffectedOccurrenceOne", "AffectedOccurrenceTwo"),
    ]:
        if occ_one is None:
            try:
                occ_one = getattr(joint, attr_one).Name
            except Exception:
                pass
        if occ_two is None:
            try:
                occ_two = getattr(joint, attr_two).Name
            except Exception:
                pass

    occ_one = occ_one or "unknown"
    occ_two = occ_two or "unknown"

    # --- Joint type ---
    # joint.Type returns ObjectTypeEnum (e.g. kAssemblyJointObject),
    # the actual joint type enum is on the Definition.
    joint_type_val = None
    try:
        joint_type_val = joint.Definition.JointType
    except Exception:
        # Fallback: try joint.Type (older API versions)
        try:
            joint_type_val = joint.Type
        except Exception:
            pass

    joint_type = _JOINT_TYPE_NAMES.get(joint_type_val, f"joint_{joint_type_val}")
    if joint_type_val is not None and joint_type_val not in _JOINT_TYPE_NAMES:
        logger.warning("Unknown joint type value %d for '%s' — please report", joint_type_val, name)
    is_rigid = joint_type == "rigid_joint"

    # --- Geometry (axis, origin, limits) ---
    axis = None
    origin = None
    limits = None

    try:
        defn = joint.Definition

        # Axis direction — extracted from the cylindrical face geometry
        # on OriginOne (or OriginTwo as fallback).
        # Late binding can't resolve Face.Geometry on proxy objects,
        # so we invoke by DISPID to reach the inner Cylinder.AxisVector.
        axis = _extract_axis_from_origin(defn, "OriginOne")
        if axis is None:
            axis = _extract_axis_from_origin(defn, "OriginTwo")

        # Fallback: try to get axis from the definition's own properties
        if axis is None:
            axis = _extract_axis_from_definition(defn)

        # Origin points — from OriginOne.Point and OriginTwo.Point.
        #
        # IMPORTANT: Each origin point is in its occurrence's local (part)
        # frame, NOT in assembly world coordinates. The axis (from face
        # geometry via assembly proxy) IS in world coordinates.
        #
        # We extract both origin points so that the kinematic tree builder
        # can use the correct one depending on the spanning-tree parent/child
        # assignment (which may differ from Inventor's OccurrenceOne/Two
        # order).
        origin_source = "OriginOne"
        origin_two = None

        for attr in ("OriginOne", "OriginTwo"):
            try:
                pt = getattr(defn, attr).Point
                point = (
                    InventorUnits.length_to_meters(pt.X),
                    InventorUnits.length_to_meters(pt.Y),
                    InventorUnits.length_to_meters(pt.Z),
                )
                if attr == "OriginOne":
                    origin = point
                else:
                    origin_two = point
                    if origin is None:
                        origin = point
                        origin_source = "OriginTwo"
            except Exception:
                pass

        # Angular limits (rotational / cylindrical)
        try:
            if defn.HasAngularPositionLimits:
                lo = defn.AngularPositionStartLimit
                hi = defn.AngularPositionEndLimit
                limits = (
                    lo.Value if hasattr(lo, "Value") else float(lo),
                    hi.Value if hasattr(hi, "Value") else float(hi),
                )
        except Exception:
            pass

        # Linear limits (slider / cylindrical)
        if limits is None:
            try:
                if defn.HasLinearPositionStartLimit:
                    lo = defn.LinearPositionStartLimit
                    hi = defn.LinearPositionEndLimit
                    limits = (
                        InventorUnits.length_to_meters(
                            lo.Value if hasattr(lo, "Value") else float(lo)
                        ),
                        InventorUnits.length_to_meters(
                            hi.Value if hasattr(hi, "Value") else float(hi)
                        ),
                    )
            except Exception:
                pass

    except Exception as e:
        logger.debug("Could not read joint definition for '%s': %s", name, e)

    logger.debug("Joint: %s (%s) %s <-> %s", name, joint_type, occ_one, occ_two)

    return ConstraintInfo(
        type=joint_type,
        occurrence_one=occ_one,
        occurrence_two=occ_two,
        is_rigid=is_rigid,
        name=name,
        axis=axis,
        origin=origin,
        origin_two=origin_two,
        origin_source=origin_source,
        limits=limits,
    )
