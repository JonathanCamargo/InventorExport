"""Kinematic tree construction with closed-loop detection.

Given a set of bodies and joints, builds a spanning tree and identifies
cut joints that close kinematic loops.  Used by format writers to handle
assemblies with closed kinematic chains (4-bar linkages, parallel robots,
etc.).
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from inventor_exporter.model.constraint import ConstraintInfo

logger = logging.getLogger(__name__)

# Joint types that define kinematic parent-child relationships.
# Shared by all writers — import from here instead of duplicating.
KINEMATIC_JOINT_TYPES = {
    "rotational_joint",
    "slider_joint",
    "cylindrical_joint",
    "planar_joint",
    "ball_joint",
}


def _sanitize(name: str) -> str:
    """Sanitize occurrence name to match body names."""
    return name.replace(":", "_").replace(" ", "_")


@dataclass
class KinematicTree:
    """Result of kinematic tree classification.

    Attributes:
        parent_of: child body name -> parent body name (spanning tree).
        joint_for: child body name -> ConstraintInfo for its tree joint.
        children_of: parent body name -> list of child body names.
        cut_joints: Joints that close loops (not in spanning tree).
        root_bodies: Bodies with no parent in the tree.
        flipped: Set of child body names where the spanning tree assigned
            occurrence_two as child (opposite of the default occurrence_one
            = child assumption).  For these joints, ``constraint.origin``
            is in the parent's frame and may need transformation.
    """

    parent_of: dict[str, str] = field(default_factory=dict)
    joint_for: dict[str, ConstraintInfo] = field(default_factory=dict)
    children_of: dict[str, list[str]] = field(default_factory=dict)
    cut_joints: list[ConstraintInfo] = field(default_factory=list)
    root_bodies: list[str] = field(default_factory=list)
    flipped: set[str] = field(default_factory=set)

    @property
    def has_loops(self) -> bool:
        """True if the assembly contains closed kinematic loops."""
        return len(self.cut_joints) > 0

    def describe_loops(self) -> list[str]:
        """Human-readable descriptions of detected loops."""
        descriptions = []
        for i, cj in enumerate(self.cut_joints, 1):
            a = _sanitize(cj.occurrence_one)
            b = _sanitize(cj.occurrence_two)
            descriptions.append(
                f"Loop {i}: {cj.name or cj.type} connects "
                f"{a} <-> {b} (cut joint)"
            )
        return descriptions


def classify_joints(
    body_names: list[str],
    constraints: "tuple[ConstraintInfo, ...] | list[ConstraintInfo]",
    ground: str = "",
) -> KinematicTree:
    """Build spanning tree from joints, identify loop-closing cut joints.

    Uses BFS from a root body to build a spanning tree over the constraint
    graph.  Joints not in the spanning tree are classified as *cut joints*
    (they close kinematic loops).

    Args:
        body_names: All body names in the assembly.
        constraints: All constraints/joints from the assembly.
        ground: Optional ground/fixed body name.  If found in the graph,
            used as BFS root.  Otherwise picks the most-connected body.

    Returns:
        KinematicTree with spanning tree and cut joints separated.
    """
    body_set = set(body_names)

    # Collect kinematic (non-rigid) joints with valid body references
    kinematic_joints: list[ConstraintInfo] = []
    for c in constraints:
        if c.is_rigid or c.type not in KINEMATIC_JOINT_TYPES:
            continue
        a = _sanitize(c.occurrence_one)
        b = _sanitize(c.occurrence_two)
        if a in body_set and b in body_set and a != b:
            kinematic_joints.append(c)

    if not kinematic_joints:
        return KinematicTree(root_bodies=list(body_names))

    # Build undirected adjacency list
    adj: dict[str, list[tuple[str, ConstraintInfo]]] = defaultdict(list)
    for c in kinematic_joints:
        a = _sanitize(c.occurrence_one)
        b = _sanitize(c.occurrence_two)
        adj[a].append((b, c))
        adj[b].append((a, c))

    # Pick root: prefer ground body, then most-connected body
    connected_bodies = set(adj.keys())
    if ground and ground in connected_bodies:
        root = ground
    else:
        root = max(connected_bodies, key=lambda n: len(adj[n]))

    # BFS to build spanning tree
    visited: set[str] = {root}
    queue: deque[str] = deque([root])
    parent_of: dict[str, str] = {}
    joint_for: dict[str, ConstraintInfo] = {}
    children_of: dict[str, list[str]] = defaultdict(list)
    used_joints: set[int] = set()  # track by object id
    flipped: set[str] = set()

    while queue:
        current = queue.popleft()
        for neighbor, constraint in adj[current]:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append(neighbor)

            # current = parent, neighbor = child in spanning tree
            parent_of[neighbor] = current
            joint_for[neighbor] = constraint
            children_of[current].append(neighbor)
            used_joints.add(id(constraint))

            # Check if parent/child roles are flipped from Inventor's default.
            # Default assumption: occurrence_one = child, occurrence_two = parent.
            # Tree says: neighbor = child.
            occ_one_sanitized = _sanitize(constraint.occurrence_one)
            if occ_one_sanitized != neighbor:
                # occurrence_one is the parent, not child -> roles flipped
                flipped.add(neighbor)

    # Cut joints: kinematic joints not used in spanning tree
    cut_joints = [c for c in kinematic_joints if id(c) not in used_joints]

    # Root bodies: all bodies not assigned a parent
    root_bodies = [name for name in body_names if name not in parent_of]

    tree = KinematicTree(
        parent_of=dict(parent_of),
        joint_for=dict(joint_for),
        children_of=dict(children_of),
        cut_joints=cut_joints,
        root_bodies=root_bodies,
        flipped=flipped,
    )

    if cut_joints:
        logger.warning(
            "Detected %d closed kinematic loop(s):", len(cut_joints)
        )
        for desc in tree.describe_loops():
            logger.warning("  %s", desc)

    return tree


def get_joint_origin_in_child_frame(
    constraint: ConstraintInfo,
    child_name: str,
    flipped: bool,
    child_rotation: Optional[np.ndarray] = None,
    parent_rotation: Optional[np.ndarray] = None,
    child_position: Optional[np.ndarray] = None,
    parent_position: Optional[np.ndarray] = None,
) -> Optional[tuple[float, float, float]]:
    """Get joint origin point in the child body's local frame.

    Handles the case where the spanning tree flipped parent/child roles
    relative to Inventor's OccurrenceOne/Two assignment.

    Args:
        constraint: The joint constraint.
        child_name: Sanitized name of the child body in the spanning tree.
        flipped: True if occurrence_one is the parent (roles flipped).
        child_rotation: Child body's world-frame rotation (3x3).
        parent_rotation: Parent body's world-frame rotation (3x3).
        child_position: Child body's world-frame position (3,).
        parent_position: Parent body's world-frame position (3,).

    Returns:
        Origin point in child's local frame, or None if unavailable.
    """
    if not flipped:
        # Default: origin is from OriginOne = OccurrenceOne = child's frame
        return constraint.origin

    # Flipped: occurrence_one is parent, occurrence_two is child.
    # Use origin_two if available (it's in OccurrenceTwo's = child's frame).
    if constraint.origin_two is not None:
        return constraint.origin_two

    # Fallback: transform origin from parent's local frame to child's local.
    if (
        constraint.origin is not None
        and parent_rotation is not None
        and child_rotation is not None
        and parent_position is not None
        and child_position is not None
    ):
        origin = np.array(constraint.origin)
        # parent local -> world
        world_pt = parent_rotation @ origin + parent_position
        # world -> child local
        child_local = child_rotation.T @ (world_pt - child_position)
        return tuple(child_local)

    return constraint.origin  # best effort
