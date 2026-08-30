"""Extract assembly constraints and joints from Inventor COM.

Reads both traditional assembly constraints (Mate, Flush, Insert, Angle,
Tangent) and newer assembly joints (Rigid, Rotational, Slider, Cylindrical,
Planar, Ball) from the active assembly.

All property access uses try/except for robustness with late-binding COM.
"""

import logging
from typing import List, Optional, Tuple

import numpy as np
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

    # --- Extract face geometry for mate/flush constraints ---
    # These constraints reference planar faces; extract a representative
    # point so that the writer can place loop-closure anchors accurately
    # instead of relying on CoM-based heuristics.
    origin = None
    origin_two = None
    origin_source = "OriginOne"

    if constraint_type in ("mate", "flush", "mate_or_flush", "insert"):
        origin, origin_two = _extract_constraint_face_points(constraint)
        if origin is not None:
            logger.debug(
                "Constraint '%s': extracted face point origin=%s, origin_two=%s",
                name, origin, origin_two,
            )

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
        origin=origin,
        origin_two=origin_two,
        origin_source=origin_source,
    )


def _extract_face_point_local(entity) -> "tuple[float, float, float] | None":
    """Get a representative point from a constraint face entity, in occurrence-local coords.

    Tries PointOnFace first (returns a point on the face in assembly world
    coordinates), then falls back to Geometry.RootPoint.  The world-frame
    point is transformed to the containing occurrence's local (part) frame
    so it matches the convention used by joint origins.
    """
    try:
        face = late_bind(entity)
    except Exception:
        return None

    world_pt = None

    # Approach 1: PointOnFace — available on most Face/FaceProxy objects
    try:
        pt = face.PointOnFace
        world_pt = np.array([
            InventorUnits.length_to_meters(pt.X),
            InventorUnits.length_to_meters(pt.Y),
            InventorUnits.length_to_meters(pt.Z),
        ])
    except Exception:
        pass

    # Approach 2: Geometry.RootPoint (planar faces → Plane.RootPoint)
    if world_pt is None:
        try:
            geom = late_bind(face.Geometry)
            rp = geom.RootPoint
            world_pt = np.array([
                InventorUnits.length_to_meters(rp.X),
                InventorUnits.length_to_meters(rp.Y),
                InventorUnits.length_to_meters(rp.Z),
            ])
        except Exception:
            pass

    # Approach 3: face evaluator mid-parameter point
    if world_pt is None:
        try:
            evaluator = late_bind(face.Evaluator)
            param_range = evaluator.ParamRangeRect
            min_pt = param_range.MinPoint
            max_pt = param_range.MaxPoint
            mid_u = (min_pt.X + max_pt.X) / 2.0
            mid_v = (min_pt.Y + max_pt.Y) / 2.0
            pt = evaluator.GetPointAtParam(mid_u, mid_v)
            world_pt = np.array([
                InventorUnits.length_to_meters(pt.X),
                InventorUnits.length_to_meters(pt.Y),
                InventorUnits.length_to_meters(pt.Z),
            ])
        except Exception:
            pass

    if world_pt is None:
        return None

    # Transform world → occurrence-local using the occurrence's 4×4 matrix
    try:
        occ = entity.ContainingOccurrence
        matrix = occ.Transformation
        R = np.array([
            [matrix.Cell(1, 1), matrix.Cell(1, 2), matrix.Cell(1, 3)],
            [matrix.Cell(2, 1), matrix.Cell(2, 2), matrix.Cell(2, 3)],
            [matrix.Cell(3, 1), matrix.Cell(3, 2), matrix.Cell(3, 3)],
        ])
        t = np.array([
            InventorUnits.length_to_meters(matrix.Cell(1, 4)),
            InventorUnits.length_to_meters(matrix.Cell(2, 4)),
            InventorUnits.length_to_meters(matrix.Cell(3, 4)),
        ])
        local_pt = R.T @ (world_pt - t)
        return tuple(local_pt)
    except Exception as e:
        logger.debug("Could not transform face point to local: %s", e)
        return None


def _extract_constraint_face_points(
    constraint,
) -> "tuple[tuple[float,float,float]|None, tuple[float,float,float]|None]":
    """Extract representative face points from both entities of a mate/flush constraint.

    Returns (origin, origin_two) in each occurrence's local frame, matching
    the convention of joint OriginOne / OriginTwo.
    """
    origin = None
    origin_two = None

    try:
        origin = _extract_face_point_local(constraint.EntityOne)
    except Exception:
        pass

    try:
        origin_two = _extract_face_point_local(constraint.EntityTwo)
    except Exception:
        pass

    # If only EntityTwo succeeded, promote to origin
    if origin is None and origin_two is not None:
        origin = origin_two
        origin_two = None

    return origin, origin_two


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


class _OriginGeometry:
    """Geometry data read off one joint origin, in assembly world coords.

    Attributes:
        axis: Unit axis direction, or None.
        center: Point on the axis in meters, or None.
        occurrence: Name of the occurrence owning the geometry, or None.
    """

    __slots__ = ("axis", "center", "occurrence")

    def __init__(self, axis=None, center=None, occurrence=None):
        self.axis = axis
        self.center = center
        self.occurrence = occurrence


def _prop(obj, name):
    """Read a COM property, returning None if it is missing or errors.

    ``getattr(obj, name, None)`` is not enough: late-bound COM raises
    com_error ("Member not found") as well as AttributeError.
    """
    if obj is None:
        return None
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _vec(v) -> Optional[Tuple[float, float, float]]:
    """Read a COM Vector/UnitVector as a 3-tuple, rejecting 2D objects."""
    try:
        out = (float(v.X), float(v.Y), float(v.Z))
    except Exception:
        return None
    return out


def _unit(v: Optional[Tuple[float, float, float]]) -> Optional[Tuple[float, float, float]]:
    """Normalise a direction vector, discarding degenerate ones."""
    if v is None:
        return None
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return None
    return (v[0] / n, v[1] / n, v[2] / n)


def _inner_geometry(entity):
    """Get the curve/surface behind a Face/Edge proxy.

    ``entity.Geometry`` works for both, but late binding occasionally fails
    on Face proxies, so fall back to invoking Face.Geometry by DISPID.
    """
    try:
        return late_bind(entity.Geometry)
    except Exception:
        pass
    try:
        raw = entity._oleobj_.Invoke(
            _FACE_GEOMETRY_DISPID, 0, pythoncom.DISPATCH_PROPERTYGET, True
        )
        return win32com.client.dynamic.Dispatch(
            raw.QueryInterface(pythoncom.IID_IDispatch)
        )
    except Exception:
        return None


def _extract_origin_geometry(defn, attr_name: str) -> _OriginGeometry:
    """Read axis + on-axis point from a joint origin's geometry.

    A joint origin references an entity in the assembly (a circular edge, a
    cylindrical or planar face, a work axis, a sketch circle). The entity is
    an assembly *proxy*, so the geometry it exposes is already in assembly
    world coordinates — unlike ``origin.Point``, which is in the local frame
    of the part that owns the entity.

    Handles, in order:
        - Edge → Arc3d / Circle: ``.Normal`` is the axis, ``.Center`` the point
        - Edge → Line: ``.Direction``
        - Face → Cylinder / Cone: ``.AxisVector`` (+ ``.BasePoint`` if present)
        - Face → Plane: ``.Normal``
        - Work axis / other: ``.AxisVector`` or ``.Direction`` on the entity

    Returns:
        _OriginGeometry with whatever could be read (fields may be None).
    """
    result = _OriginGeometry()

    try:
        origin = late_bind(getattr(defn, attr_name))
    except Exception as e:
        logger.debug("Could not access %s: %s", attr_name, e)
        return result

    try:
        entity = late_bind(origin.Geometry)
    except Exception as e:
        logger.debug("%s has no Geometry: %s", attr_name, e)
        entity = None

    if entity is None:
        # Some origin types expose a direction directly.
        result.axis = _unit(_vec(_prop(origin, "Direction")))
        return result

    try:
        result.occurrence = entity.ContainingOccurrence.Name
    except Exception:
        pass

    inner = _inner_geometry(entity)

    if inner is not None:
        # Axis: circles/arcs/planes expose Normal, cylinders/cones AxisVector,
        # lines Direction.
        for prop in ("Normal", "AxisVector", "Direction"):
            axis = _unit(_vec(_prop(inner, prop)))
            if axis is not None:
                result.axis = axis
                break

        # On-axis point: circles and arcs expose Center; cylinders/cones a
        # BasePoint. A Plane's RootPoint is *not* on the rotation axis, so
        # it is deliberately not used here.
        for prop in ("Center", "BasePoint"):
            pt = _vec(_prop(inner, prop))
            if pt is not None:
                result.center = tuple(
                    InventorUnits.length_to_meters(c) for c in pt
                )
                break

    if result.axis is None:
        # Work axes and similar expose the direction on the entity itself.
        for prop in ("AxisVector", "Direction"):
            axis = _unit(_vec(_prop(entity, prop)))
            if axis is not None:
                result.axis = axis
                break

    if result.axis is None:
        logger.debug("Could not extract axis from %s", attr_name)

    return result


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
    origin_two = None
    origin_world = None
    origin_two_world = None
    origin_occurrence = None
    origin_two_occurrence = None
    origin_source = "OriginOne"
    limits = None

    try:
        defn = joint.Definition

        # Axis direction and an on-axis point, read from the origin geometry.
        # The entity is an assembly proxy, so both are in WORLD coordinates.
        geom_one = _extract_origin_geometry(defn, "OriginOne")
        geom_two = _extract_origin_geometry(defn, "OriginTwo")

        axis = geom_one.axis or geom_two.axis
        if axis is None:
            axis = _extract_axis_from_definition(defn)

        origin_world = geom_one.center
        origin_two_world = geom_two.center
        origin_occurrence = geom_one.occurrence
        origin_two_occurrence = geom_two.occurrence

        # Origin points — from OriginOne.Point and OriginTwo.Point.
        #
        # IMPORTANT: each point is in the local (part) frame of the
        # occurrence that owns the origin *geometry* — recorded above as
        # origin_occurrence — which for a joint placed on a subassembly is a
        # leaf part inside it, NOT OccurrenceOne/Two. Prefer origin_world.
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
        origin_world=origin_world,
        origin_two_world=origin_two_world,
        origin_occurrence=origin_occurrence,
        origin_two_occurrence=origin_two_occurrence,
        limits=limits,
    )
