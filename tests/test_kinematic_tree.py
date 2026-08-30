"""Tests for kinematic tree construction and closed-loop detection."""

import numpy as np
import pytest

from inventor_exporter.model.constraint import ConstraintInfo
from inventor_exporter.model.kinematic_tree import (
    KinematicTree,
    classify_joints,
    get_joint_origin_in_child_frame,
)


def _joint(name, occ1, occ2, joint_type="rotational_joint", **kwargs):
    """Helper to create a ConstraintInfo for testing."""
    return ConstraintInfo(
        type=joint_type,
        occurrence_one=occ1,
        occurrence_two=occ2,
        name=name,
        **kwargs,
    )


class TestClassifyJointsSimpleTree:
    """Tests with pure tree topologies (no loops)."""

    def test_empty_constraints(self):
        tree = classify_joints(["a", "b", "c"], [])
        assert tree.has_loops is False
        assert tree.cut_joints == []
        assert tree.root_bodies == ["a", "b", "c"]

    def test_single_joint(self):
        joints = [_joint("j1", "a", "b")]
        tree = classify_joints(["a", "b"], joints)
        assert tree.has_loops is False
        assert len(tree.parent_of) == 1
        assert len(tree.cut_joints) == 0

    def test_linear_chain(self):
        """a -- b -- c (3 bodies, 2 joints, no loops)."""
        joints = [
            _joint("j1", "a", "b"),
            _joint("j2", "b", "c"),
        ]
        tree = classify_joints(["a", "b", "c"], joints)
        assert tree.has_loops is False
        assert len(tree.parent_of) == 2
        assert len(tree.cut_joints) == 0

    def test_star_topology(self):
        """Hub with 3 spokes: a--hub, b--hub, c--hub."""
        joints = [
            _joint("j1", "a", "hub"),
            _joint("j2", "b", "hub"),
            _joint("j3", "c", "hub"),
        ]
        tree = classify_joints(["hub", "a", "b", "c"], joints)
        assert tree.has_loops is False
        assert len(tree.parent_of) == 3
        assert len(tree.cut_joints) == 0

    def test_ground_body_becomes_root(self):
        joints = [_joint("j1", "child", "parent")]
        tree = classify_joints(
            ["child", "parent"], joints, ground="parent",
        )
        assert "parent" in tree.root_bodies
        assert tree.parent_of.get("child") == "parent"

    def test_rigid_joints_ignored(self):
        joints = [
            _joint("j1", "a", "b", joint_type="rigid_joint", is_rigid=True),
        ]
        tree = classify_joints(["a", "b"], joints)
        assert tree.has_loops is False
        assert len(tree.parent_of) == 0

    def test_non_kinematic_types_ignored(self):
        joints = [_joint("j1", "a", "b", joint_type="mate")]
        tree = classify_joints(["a", "b"], joints)
        assert len(tree.parent_of) == 0


class TestClassifyJointsClosedLoops:
    """Tests with closed kinematic chains."""

    def test_triangle_loop(self):
        """a--b--c--a: 3 bodies, 3 joints = 1 loop."""
        joints = [
            _joint("j1", "a", "b"),
            _joint("j2", "b", "c"),
            _joint("j3", "c", "a"),
        ]
        tree = classify_joints(["a", "b", "c"], joints)
        assert tree.has_loops is True
        assert len(tree.cut_joints) == 1
        assert len(tree.parent_of) == 2  # spanning tree has 2 edges

    def test_four_bar_linkage(self):
        """Classic 4-bar: ground--a--b--c--ground (4 joints, 4 bodies)."""
        joints = [
            _joint("j1", "a", "ground"),
            _joint("j2", "b", "a"),
            _joint("j3", "c", "b"),
            _joint("j4", "c", "ground"),  # loop-closing joint
        ]
        tree = classify_joints(
            ["ground", "a", "b", "c"], joints, ground="ground",
        )
        assert tree.has_loops is True
        assert len(tree.cut_joints) == 1
        assert len(tree.parent_of) == 3  # spanning tree has 3 edges
        # All non-ground bodies have a parent
        assert "a" in tree.parent_of
        assert "b" in tree.parent_of
        assert "c" in tree.parent_of

    def test_double_loop(self):
        """Two loops sharing an edge: 4 bodies, 5 joints = 2 loops."""
        joints = [
            _joint("j1", "a", "b"),
            _joint("j2", "b", "c"),
            _joint("j3", "c", "a"),  # loop 1
            _joint("j4", "c", "d"),
            _joint("j5", "d", "a"),  # loop 2
        ]
        tree = classify_joints(["a", "b", "c", "d"], joints)
        assert tree.has_loops is True
        assert len(tree.cut_joints) == 2
        assert len(tree.parent_of) == 3  # spanning tree has 3 edges

    def test_describe_loops(self):
        joints = [
            _joint("j1", "a", "b"),
            _joint("j2", "b", "a"),
        ]
        tree = classify_joints(["a", "b"], joints)
        descriptions = tree.describe_loops()
        assert len(descriptions) == 1
        assert "cut joint" in descriptions[0]


class TestClassifyJointsFlipping:
    """Tests for parent/child role flipping detection."""

    def test_no_flip_when_occurrence_one_is_child(self):
        """Default: occurrence_one = child (BFS makes occurrence_two = parent)."""
        joints = [_joint("j1", "child", "parent")]
        tree = classify_joints(
            ["child", "parent"], joints, ground="parent",
        )
        assert tree.parent_of["child"] == "parent"
        assert "child" not in tree.flipped

    def test_flip_detected(self):
        """When BFS assigns occurrence_one as parent, flip is detected."""
        # j1 has occurrence_one="parent", occurrence_two="child"
        # BFS from ground="parent" will make parent=parent, child=child
        # occurrence_one="parent" != child="child", so NOT flipped
        # Wait — let me think again:
        # BFS from "parent": visits "parent" first.
        # Neighbor "child" gets parent_of["child"] = "parent"
        # occ_one_sanitized = "parent" != neighbor "child" → flipped!
        joints = [_joint("j1", "parent", "child")]
        tree = classify_joints(
            ["child", "parent"], joints, ground="parent",
        )
        assert tree.parent_of["child"] == "parent"
        assert "child" in tree.flipped

    def test_name_sanitization(self):
        """Occurrence names with colons are sanitized."""
        joints = [_joint("j1", "part:1", "part:2")]
        tree = classify_joints(
            ["part_1", "part_2"], joints, ground="part_2",
        )
        assert tree.parent_of["part_1"] == "part_2"


class TestGetJointOriginInChildFrame:
    """Tests for joint origin frame transformation."""

    def test_non_flipped_returns_origin_directly(self):
        c = _joint("j1", "child", "parent", origin=(1.0, 2.0, 3.0))
        result = get_joint_origin_in_child_frame(c, "child", flipped=False)
        assert result == (1.0, 2.0, 3.0)

    def test_flipped_uses_origin_two(self):
        c = _joint(
            "j1", "parent", "child",
            origin=(1.0, 0.0, 0.0),
            origin_two=(0.5, 0.5, 0.0),
        )
        result = get_joint_origin_in_child_frame(c, "child", flipped=True)
        assert result == (0.5, 0.5, 0.0)

    def test_flipped_transforms_when_no_origin_two(self):
        c = _joint("j1", "parent", "child", origin=(0.1, 0.0, 0.0))
        # Identity transforms for simplicity
        I = np.eye(3)
        parent_pos = np.array([1.0, 0.0, 0.0])
        child_pos = np.array([2.0, 0.0, 0.0])
        result = get_joint_origin_in_child_frame(
            c, "child", flipped=True,
            child_rotation=I, parent_rotation=I,
            child_position=child_pos, parent_position=parent_pos,
        )
        # world_pt = I @ [0.1, 0, 0] + [1, 0, 0] = [1.1, 0, 0]
        # child_local = I.T @ ([1.1, 0, 0] - [2, 0, 0]) = [-0.9, 0, 0]
        assert result is not None
        np.testing.assert_array_almost_equal(result, (-0.9, 0.0, 0.0))

    def test_flipped_fallback_when_no_transforms(self):
        c = _joint("j1", "parent", "child", origin=(1.0, 2.0, 3.0))
        result = get_joint_origin_in_child_frame(c, "child", flipped=True)
        # Best effort: returns origin as-is
        assert result == (1.0, 2.0, 3.0)


class TestClassifyJointsRigidGroups:
    """Tests for rigid-group-aware kinematic tree construction."""

    def test_five_bar_with_rigid_ground(self):
        """5-bar linkage: ground is a rigid group of 3 bodies.

        Topology (after rigid group merging):
            ground --R1-- arm1 --R4-- arm3
              |                        |
              R2                    Mate:1 (loop closure)
              |                        |
            arm2 ----R3---- arm4 ------+
        """
        bodies = ["case", "servo1", "servo2", "arm1", "arm2", "arm3", "arm4"]
        rigid_groups = {
            "servo2": ["case", "servo1", "servo2"],  # ground group
            "arm1": ["arm1"],
            "arm2": ["arm2"],
            "arm3": ["arm3"],
            "arm4": ["arm4"],
        }
        constraints = [
            # Rigid joints (within ground group)
            _joint("rigid1", "servo2", "case", joint_type="rigid_joint", is_rigid=True),
            _joint("rigid2", "case", "servo1", joint_type="rigid_joint", is_rigid=True),
            # Kinematic joints
            _joint("R1", "arm1", "servo2"),   # arm1 <-> ground via servo2
            _joint("R2", "servo1", "arm2"),   # arm2 <-> ground via servo1
            _joint("R3", "arm2", "arm4"),     # arm2 <-> arm4
            _joint("R4", "arm1", "arm3"),     # arm1 <-> arm3
            # Loop closure (mate between arm tips)
            _joint("Mate1", "arm4", "arm3", joint_type="mate"),
        ]
        # ground="case" maps to rep "servo2" via rigid group
        tree = classify_joints(
            bodies, constraints, ground="case", rigid_groups=rigid_groups,
        )

        # All 4 rotational joints should be tree joints (not cut)
        assert len(tree.parent_of) == 4
        assert "arm1" in tree.parent_of
        assert "arm2" in tree.parent_of
        assert "arm3" in tree.parent_of
        assert "arm4" in tree.parent_of

        # Parents of arm1/arm2 should be the ground rep
        assert tree.parent_of["arm1"] == "servo2"
        assert tree.parent_of["arm2"] == "servo2"

        # The mate should be the only cut joint (loop closure)
        assert len(tree.cut_joints) == 1
        assert tree.cut_joints[0].name == "Mate1"
        assert tree.cut_joints[0].type == "mate"

    def test_disconnected_without_rigid_groups(self):
        """Without rigid_groups, separate chains appear disconnected."""
        bodies = ["servo1", "servo2", "arm1", "arm2"]
        constraints = [
            _joint("R1", "arm1", "servo1"),
            _joint("R2", "servo2", "arm2"),
        ]
        # No rigid groups: servo1 and servo2 are separate
        tree = classify_joints(bodies, constraints)
        # BFS from most-connected body visits only one component.
        # The other component's joint becomes a cut joint — this was the bug.
        assert len(tree.parent_of) == 1  # only one component visited
        assert len(tree.cut_joints) == 1  # other joint misclassified

    def test_connected_with_rigid_groups(self):
        """With rigid_groups, the same chains are correctly connected."""
        bodies = ["servo1", "servo2", "arm1", "arm2"]
        rigid_groups = {
            "servo1": ["servo1", "servo2"],  # same rigid group
            "arm1": ["arm1"],
            "arm2": ["arm2"],
        }
        constraints = [
            _joint("R1", "arm1", "servo1"),
            _joint("R2", "servo2", "arm2"),
        ]
        tree = classify_joints(bodies, constraints, rigid_groups=rigid_groups)
        # Both joints should be tree joints
        assert len(tree.parent_of) == 2
        assert len(tree.cut_joints) == 0
        assert "arm1" in tree.parent_of
        assert "arm2" in tree.parent_of
        # Both arms parent to the group representative
        assert tree.parent_of["arm1"] == "servo1"
        assert tree.parent_of["arm2"] == "servo1"

    def test_ground_resolved_through_rigid_group(self):
        """Ground body mapped to its rigid group representative."""
        bodies = ["case", "servo", "arm"]
        rigid_groups = {
            "servo": ["case", "servo"],
            "arm": ["arm"],
        }
        constraints = [
            _joint("rigid1", "case", "servo", joint_type="rigid_joint", is_rigid=True),
            _joint("R1", "arm", "servo"),
        ]
        tree = classify_joints(
            bodies, constraints, ground="case", rigid_groups=rigid_groups,
        )
        # Ground "case" maps to rep "servo", which should be root
        assert "servo" in tree.root_bodies
        assert tree.parent_of["arm"] == "servo"

    def test_mate_closes_loop_between_tree_bodies(self):
        """A mate between two bodies already in the tree is a loop closure."""
        bodies = ["ground", "a", "b"]
        constraints = [
            _joint("R1", "a", "ground"),
            _joint("R2", "b", "ground"),
            _joint("mate1", "a", "b", joint_type="mate"),
        ]
        tree = classify_joints(bodies, constraints, ground="ground")
        assert len(tree.parent_of) == 2  # a and b are tree children
        assert len(tree.cut_joints) == 1
        assert tree.cut_joints[0].name == "mate1"
        assert tree.cut_joints[0].type == "mate"

    def test_mate_not_loop_if_bodies_not_connected(self):
        """A mate between disconnected bodies is not a loop closure."""
        bodies = ["a", "b", "c"]
        constraints = [
            _joint("mate1", "a", "b", joint_type="mate"),
        ]
        # No kinematic joints at all — no spanning tree
        tree = classify_joints(bodies, constraints)
        assert len(tree.cut_joints) == 0


class TestKinematicTreeProperties:
    """Tests for KinematicTree dataclass properties."""

    def test_has_loops_false(self):
        tree = KinematicTree()
        assert tree.has_loops is False

    def test_has_loops_true(self):
        tree = KinematicTree(
            cut_joints=[_joint("j1", "a", "b")],
        )
        assert tree.has_loops is True

    def test_describe_loops_empty(self):
        tree = KinematicTree()
        assert tree.describe_loops() == []


class TestWorldFrameJointOrigin:
    """Joint origins read off the geometry proxy are in world coordinates.

    ``origin``/``origin_two`` are in the local frame of whichever occurrence
    owns the joint geometry — a leaf part, even when the joint names a
    subassembly — so they cannot be placed without knowing that occurrence.
    ``origin_world`` is unambiguous and must win.
    """

    def test_world_origin_prefers_origin_one(self):
        c = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="a",
            occurrence_two="b",
            origin_world=(1.0, 2.0, 3.0),
            origin_two_world=(1.0, 2.5, 3.0),
        )
        assert c.world_origin() == (1.0, 2.0, 3.0)

    def test_world_origin_falls_back_to_origin_two(self):
        # A joint placed on a planar face or sketch circle yields an axis but
        # no centre for OriginOne; OriginTwo still places it on the axis.
        c = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="a",
            occurrence_two="b",
            origin_world=None,
            origin_two_world=(1.0, 2.5, 3.0),
        )
        assert c.world_origin() == (1.0, 2.5, 3.0)

    def test_world_origin_none_when_no_geometry(self):
        c = ConstraintInfo(
            type="rotational_joint", occurrence_one="a", occurrence_two="b",
        )
        assert c.world_origin() is None

    def test_child_frame_uses_world_origin(self):
        # Child sits at z=0.5, rotated 90 deg about Z. A joint at world
        # (0, 0, 0.5) is at the child's own origin.
        c = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="child",
            occurrence_two="parent",
            origin=(9.0, 9.0, 9.0),  # bogus local value; must be ignored
            origin_world=(0.0, 0.0, 0.5),
        )
        rot = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        result = get_joint_origin_in_child_frame(
            c, "child", flipped=False,
            child_rotation=rot, child_position=np.array([0.0, 0.0, 0.5]),
            parent_rotation=np.eye(3), parent_position=np.zeros(3),
        )
        np.testing.assert_array_almost_equal(result, [0.0, 0.0, 0.0])

    def test_child_frame_world_origin_wins_when_flipped(self):
        c = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="parent",
            occurrence_two="child",
            origin_two=(9.0, 9.0, 9.0),  # bogus; world origin must win
            origin_world=(0.0, 1.0, 0.0),
        )
        result = get_joint_origin_in_child_frame(
            c, "child", flipped=True,
            child_rotation=np.eye(3), child_position=np.array([0.0, 0.0, 1.0]),
            parent_rotation=np.eye(3), parent_position=np.zeros(3),
        )
        np.testing.assert_array_almost_equal(result, [0.0, 1.0, -1.0])

    def test_falls_back_to_local_origin_without_transforms(self):
        c = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="child",
            occurrence_two="parent",
            origin=(0.1, 0.2, 0.3),
            origin_world=(1.0, 1.0, 1.0),
        )
        assert get_joint_origin_in_child_frame(
            c, "child", flipped=False
        ) == (0.1, 0.2, 0.3)


class TestGroundRootsTheTree:
    """The grounded body must root the spanning tree.

    Regression: ``ground`` was never populated, so the root fell back to
    "most-connected". In a serial chain every interior body ties at degree
    2, so an arbitrary mid-chain link won and the skeleton came out
    inverted — the fixed base ended up a leaf.
    """

    def _chain(self):
        # base - l1 - l2 - l3 - l4 - l5, all revolute
        return ["base", "l1", "l2", "l3", "l4", "l5"], [
            _joint("j1", "l1", "base"),
            _joint("j2", "l2", "l1"),
            _joint("j3", "l3", "l2"),
            _joint("j4", "l5", "l4"),
            _joint("j5", "l3", "l4"),
        ]

    def test_ground_becomes_root(self):
        bodies, joints = self._chain()
        tree = classify_joints(bodies, joints, ground="base")
        assert tree.root_bodies == ["base"]
        assert "base" not in tree.parent_of
        assert tree.parent_of["l1"] == "base"
        assert tree.parent_of["l2"] == "l1"
        assert tree.parent_of["l3"] == "l2"
        assert tree.parent_of["l4"] == "l3"
        assert tree.parent_of["l5"] == "l4"
        assert tree.cut_joints == []

    def test_without_ground_root_is_not_the_base(self):
        # Documents the fallback this fix exists to avoid: with no ground,
        # a mid-chain body wins on degree and the base becomes a leaf.
        bodies, joints = self._chain()
        tree = classify_joints(bodies, joints)
        assert tree.root_bodies != ["base"]
        assert "base" in tree.parent_of

    def test_unknown_ground_name_falls_back(self):
        bodies, joints = self._chain()
        tree = classify_joints(bodies, joints, ground="not_a_body")
        assert len(tree.root_bodies) == 1

    def test_ground_given_as_subassembly_alias(self):
        # Joints name subassemblies; ground is resolved through the same
        # alias map, so a subassembly name must root the tree too.
        bodies = ["base_a", "base_b", "arm_a"]
        joints = [_joint("j1", "arm_1", "base_1")]
        aliases = {"base_1": ["base_a", "base_b"], "arm_1": ["arm_a"]}
        groups = {"base_a": ["base_a", "base_b"], "arm_a": ["arm_a"]}
        tree = classify_joints(
            bodies, joints, ground="base_1",
            rigid_groups=groups, occurrence_aliases=aliases,
        )
        # base_b has no parent because it is fused into base_a's group
        assert "base_a" in tree.root_bodies
        assert "base_a" not in tree.parent_of
        assert tree.parent_of["arm_a"] == "base_a"
