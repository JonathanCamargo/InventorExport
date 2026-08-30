"""glTF 2.0 / GLB writer.

Exports the assembly model to glTF 2.0 (Khronos) as either:

    - ``.glb``  binary container (JSON chunk + embedded BIN chunk), or
    - ``.gltf`` JSON with a base64 data-URI buffer (self-contained).

The output variant is chosen from the output file extension, so the same
writer serves both ``--format gltf`` and ``--format glb``.

Coordinate/units conventions:

    - glTF requires positions in **meters** and a right-handed **Y-up**
      coordinate system.
    - Body transforms in the IR are already in meters, so they are used
      directly.
    - STL meshes produced by the pipeline are in millimeters; vertex
      positions are scaled by 0.001 when embedded into the GLB buffer.
    - Y-up is handled by a single root rotation node (a -90 deg rotation
      about X). Disable with ``y_up=False`` to keep the assembly's
      native Z-up orientation.

Kinematics:

    - glTF 2.0 core has no mechanical-joint concept, but it DOES have an
      armature: the skin system. By default (``enable_skin=True``) the
      writer emits a <skin> whose joints follow the kinematic spanning
      tree (rigid groups merged into one bone with per-part meshes rigidly
      bound to it). Each mesh primitive carries JOINTS_0/WEIGHTS_0
      attributes and the skin carries inverse-bind matrices, so Blender,
      Unity, Unreal, and three.js import an animatable skeleton.
    - Loop-closing joints cannot live in the tree; they are written to the
      top-level ``extras`` object so downstream tools can reconstruct them.

Meshes:

    - Each body with geometry gets one glTF mesh (triangle soup, indexed
      implicitly via mode=4 TRIANGLES) with flat per-vertex normals.
    - Geometry is sourced from the STEP -> STL conversion pipeline; an
      existing STL on disk is reused without reconversion.
"""

import base64
import json
import logging
import struct
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from inventor_exporter import __version__
from inventor_exporter.core.rotation import rotation_to_quaternion
from inventor_exporter.model.kinematic_tree import classify_joints
from inventor_exporter.writers.mesh_converter import MeshConverter
from inventor_exporter.writers.registry import WriterRegistry

if TYPE_CHECKING:
    from inventor_exporter.model import AssemblyModel, Body
    from inventor_exporter.model.constraint import ConstraintInfo

logger = logging.getLogger(__name__)

_GLB_MAGIC = 0x46546C67  # "glTF"
_GLB_VERSION = 2
_CHUNK_JSON = 0x4E4F534A  # "JSON"
_CHUNK_BIN = 0x004E4942  # "BIN\0"

_COMPONENT_FLOAT = 5126
_COMPONENT_UNSIGNED_SHORT = 5123
_TYPE_VEC3 = "VEC3"
_TYPE_VEC4 = "VEC4"
_TYPE_MAT4 = "MAT4"
_TYPE_SCALAR = "SCALAR"
_MODE_TRIANGLES = 4
_TARGET_ARRAY_BUFFER = 34962

_MM_TO_M = 0.001

_DEFAULT_COLORS = {
    "steel": "0.7 0.7 0.7 1.0",
    "aluminum": "0.8 0.8 0.85 1.0",
    "plastic": "0.3 0.3 0.3 1.0",
    "rubber": "0.2 0.2 0.2 1.0",
    "default": "0.6 0.6 0.6 1.0",
}

# Z-up -> Y-up: rotate -90 degrees about X. (x, y, z)_Zup -> (x, z, -y)_Yup
_ZUP_TO_YUP = np.array(
    [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]
)

_STL_TRIANGLE_DTYPE = np.dtype(
    [
        ("normal", "<f4", (3,)),
        ("vertices", "<f4", (3, 3)),
        ("attr", "<u2"),
    ]
)


def load_stl(stl_path: Path) -> np.ndarray:
    """Load triangle vertex positions from a binary or ASCII STL file.

    Args:
        stl_path: Path to the STL file.

    Returns:
        (N, 3) float32 array of vertex positions (N = 3 * triangle count).
        Units are whatever the STL file uses (the export pipeline writes mm).

    Raises:
        FileNotFoundError: If the STL file does not exist.
        ValueError: If the file cannot be parsed as STL.
    """
    if not stl_path.exists():
        raise FileNotFoundError(f"STL file not found: {stl_path}")

    data = stl_path.read_bytes()

    positions = _try_load_binary_stl(data)
    if positions is not None:
        return positions

    positions = _load_ascii_stl(data)
    if positions is None:
        raise ValueError(f"Failed to parse STL file: {stl_path}")
    return positions


def _try_load_binary_stl(data: bytes) -> Optional[np.ndarray]:
    """Parse a binary STL payload; return None if the file is not binary STL."""
    if len(data) < 84:
        return None
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * _STL_TRIANGLE_DTYPE.itemsize
    if count == 0 or len(data) < expected:
        return None
    triangles = np.frombuffer(data, dtype=_STL_TRIANGLE_DTYPE, count=count, offset=84)
    vertices = triangles["vertices"].reshape(-1, 3)
    return np.ascontiguousarray(vertices, dtype=np.float32)


def _load_ascii_stl(data: bytes) -> Optional[np.ndarray]:
    """Parse an ASCII STL payload; return None if no vertices are found."""
    vertices: list[tuple[float, float, float]] = []
    for line in data.decode("ascii", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                return None
    if not vertices:
        return None
    return np.asarray(vertices, dtype=np.float32)


def _flat_normals(positions: np.ndarray) -> np.ndarray:
    """Compute flat per-vertex normals for a triangle soup.

    Args:
        positions: (N, 3) float array with N divisible by 3.

    Returns:
        (N, 3) float32 unit face normals repeated per triangle vertex.
    """
    tri = positions.reshape(-1, 3, 3)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    safe = np.where(norms > 1e-12, norms, 1.0)
    normals = normals / safe
    return np.ascontiguousarray(np.repeat(normals, 3, axis=0), dtype=np.float32)


def _transform_to_matrix(transform) -> np.ndarray:
    """Convert a Transform (position + rotation) to a 4x4 homogeneous matrix."""
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = transform.rotation
    T[:3, 3] = transform.position
    return T


@WriterRegistry.register("gltf")
@WriterRegistry.register("glb")
class GLTFWriter:
    """glTF 2.0 writer (binary GLB or JSON glTF, based on output extension).

    Attributes:
        format_name: "gltf"
        file_extension: ".glb"
    """

    format_name: str = "gltf"
    file_extension: str = ".glb"

    def __init__(
        self,
        y_up: bool = True,
        mesh_subdir: str = "meshes",
        mesh_tolerance: float = 0.5,
        enable_skin: bool = True,
    ):
        """Initialize writer.

        Args:
            y_up: Wrap the scene in a root node rotating Z-up to glTF's
                required Y-up orientation. Default True.
            mesh_subdir: Subdirectory (relative to the output file) where
                intermediate STL meshes are produced. Default "meshes".
            mesh_tolerance: Linear deflection in mm for STEP meshing.
                Higher = coarser mesh = smaller file. Default 0.5 (web
                delivery target; URDF/MuJoCo use 0.1).
            enable_skin: Emit a glTF skin (armature) whose joints follow
                the kinematic spanning tree, with meshes rigid-skinned to
                their bones. Default True.
        """
        self._y_up = y_up
        self._mesh_subdir = mesh_subdir
        self._mesh_tolerance = mesh_tolerance
        self._enable_skin = enable_skin
        self._reset()

    def _reset(self) -> None:
        self._bin = bytearray()
        self._buffer_views: list[dict] = []
        self._accessors: list[dict] = []
        self._meshes: list[dict] = []
        self._materials: list[dict] = []
        self._nodes: list[dict] = []
        self._skins: list[dict] = []
        self._material_index: dict[str, int] = {}
        self._mesh_index_by_body: dict[str, int] = {}
        self._skin_bone_index: dict[str, int] = {}
        self._skin_global: dict[int, np.ndarray] = {}
        # Global transform of the node that CARRIES each body's mesh. For a
        # rigid-group member this is its own sub-node, not the group bone.
        self._mesh_node_global: dict[str, np.ndarray] = {}
        self._global_root: np.ndarray = np.eye(4)

    def write(self, model: "AssemblyModel", output_path: Path) -> None:
        errors = model.validate()
        if errors:
            raise ValueError(
                "Model validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        self._reset()

        output_dir = output_path.parent
        converter = MeshConverter(output_dir, mesh_subdir=self._mesh_subdir)

        gltf = self._build_gltf(model, converter)

        if self._enable_skin:
            self._add_skin(model, gltf)

        if output_path.suffix.lower() == ".glb":
            self._write_glb(gltf, output_path)
        else:
            self._write_gltf_json(gltf, output_path)
        logger.info("Wrote %s to %s", self.format_name, output_path)

        # Bone/hierarchy summary so users can verify the kinematic
        # mapping at a glance (visible with --verbose)
        if self._skins:
            skin = self._skins[0]
            bone_names = [
                self._nodes[j].get("name", f"node{j}") for j in skin["joints"]
            ]
            logger.info(
                "Armature: %d bone(s) from %d body/bodies: %s",
                len(bone_names),
                len(model.bodies),
                ", ".join(bone_names),
            )
            for c in model.constraints:
                if c.is_rigid:
                    logger.debug(
                        "Rigid: %s + %s (fused, no relative motion)",
                        c.occurrence_one, c.occurrence_two,
                    )
                elif c.type in (
                    "rotational_joint", "slider_joint", "cylindrical_joint",
                    "planar_joint", "ball_joint",
                ):
                    logger.info(
                        "Joint: %s (%s) %s <-> %s [axis=%s]",
                        c.name or c.type, c.type,
                        c.occurrence_one, c.occurrence_two,
                        c.axis,
                    )
        else:
            logger.warning(
                "No armature emitted (no bodies?) - nodes are static"
            )

    # ------------------------------------------------------------------
    # Document assembly
    # ------------------------------------------------------------------

    def _build_gltf(
        self, model: "AssemblyModel", converter: MeshConverter
    ) -> dict:
        scene_nodes = self._build_nodes(model, converter)

        gltf: dict = {
            "asset": {
                "version": "2.0",
                "generator": f"inventor-exporter {__version__}",
            },
            "scene": 0,
            "scenes": [{"nodes": scene_nodes}],
            "nodes": self._nodes,
        }

        if self._meshes:
            gltf["meshes"] = self._meshes
            gltf["materials"] = self._materials
            gltf["bufferViews"] = self._buffer_views
            gltf["accessors"] = self._accessors

        extras = self._constraint_extras(model)
        if extras:
            gltf["extras"] = {
                # glTF has no joint-axis field, so state the rig conventions
                # a consumer needs in order to drive it.
                "conventions": {
                    "bone_rotation_axis": [0.0, 0.0, 1.0],
                    "bone_origin": "joint_pivot",
                    "frame": "assembly_world",
                },
                "constraints": extras,
            }

        return gltf

    def _build_nodes(
        self, model: "AssemblyModel", converter: MeshConverter
    ) -> list[int]:
        aliases = model.occurrence_aliases()
        groups = model.rigid_groups(occurrence_aliases=aliases)
        ktree = classify_joints(
            [b.name for b in model.bodies],
            model.constraints,
            ground=model.ground_body,
            rigid_groups=groups,
            occurrence_aliases=aliases,
        )
        self._ktree = ktree
        self._groups = groups

        emitted: set[str] = set()
        root_indices: list[int] = []

        # Reserve index 0 for the Y-up root so body nodes start a 1
        root_index = None
        if self._y_up:
            root_index = self._append_node(
                {"name": "world_y_up", "rotation": list(
                    rotation_to_quaternion(_ZUP_TO_YUP, scalar_first=False)
                )}
            )
            global_root = np.eye(4, dtype=np.float64)
            global_root[:3, :3] = _ZUP_TO_YUP
        else:
            global_root = np.eye(4)
        self._global_root = global_root

        def _is_in_tree(body_name: str) -> bool:
            # A body is part of the tree if its group rep has a parent
            rep = body_to_rep_map.get(body_name)
            return rep is not None and rep in ktree.parent_of

        body_to_rep_map: dict[str, str] = {}
        for rep, members in groups.items():
            for m in members:
                body_to_rep_map[m] = rep

        # Roots = groups whose representative has no parent in the tree.
        for rep, members in groups.items():
            if rep in ktree.parent_of:
                continue
            if any(m in emitted for m in members):
                continue
            first = model.get_body(members[0])
            if first is None:
                continue
            root_indices.append(
                self._add_body_node(
                    first, None, model, groups, ktree, emitted, converter,
                    parent_global=global_root,
                )
            )

        # Safety net for any body not reached through the tree
        for body in model.bodies:
            if body.name not in emitted and not _is_in_tree(body.name):
                root_indices.append(
                    self._add_body_node(
                        body, None, model, groups, ktree, emitted, converter,
                        parent_global=global_root,
                    )
                )
        for body in model.bodies:
            if body.name not in emitted and _is_in_tree(body.name):
                # Reached through a parent - emitted during traversal
                if body.name not in emitted:
                    self._add_body_node(
                        body, None, model, groups, ktree, emitted, converter,
                        parent_global=global_root,
                    )

        if root_index is not None:
            if root_indices:
                self._nodes[root_index]["children"] = root_indices
                return [root_index]
            # No bodies: drop the placeholder root
            self._nodes.pop(root_index)
            return []
        return root_indices

    def _parent_joint_for(self, body: "Body", groups, ktree):
        """The joint connecting this body to its parent in the tree, if any."""
        rep = None
        for r, members in groups.items():
            if body.name in members:
                rep = r
                break
        if rep is None:
            rep = body.name
        if rep not in ktree.parent_of:
            return None
        return ktree.joint_for.get(rep)

    def _pivot_for(self, body: "Body", groups, ktree) -> Optional[np.ndarray]:
        """World-frame hinge this body rotates about, if it has a parent joint.

        Returns None for the root (nothing to rotate about) and for joints
        whose origin geometry yielded no on-axis point, leaving the body's
        own origin as the bone position.
        """
        joint = self._parent_joint_for(body, groups, ktree)
        if joint is None:
            return None
        origin = joint.world_origin()
        return None if origin is None else np.asarray(origin, dtype=np.float64)

    def _bone_basis_for(self, body: "Body", groups, ktree) -> Optional[np.ndarray]:
        """Orientation putting local +Z on the hinge axis.

        glTF has no joint-axis field — a bone is a plain node — so unless a
        convention is imposed, the hinge lands on whichever local axis the CAD
        part frame happens to give it (roll on one link, pitch on the next).
        Aligning local +Z with every hinge means one rotation about Z drives
        any joint, matching URDF's default axis and the DH convention.

        The roll about that axis is pinned to the body's own frame (its X, or
        its Y where X is near-parallel to the hinge) so the result is stable
        and reproducible rather than arbitrary.

        Returns None when there is no parent joint or no axis was recovered,
        leaving the body's own orientation in place.
        """
        joint = self._parent_joint_for(body, groups, ktree)
        if joint is None or joint.axis is None:
            return None

        z = np.asarray(joint.axis, dtype=np.float64)
        norm = np.linalg.norm(z)
        if norm < 1e-12:
            return None
        z = z / norm

        body_rot = np.asarray(body.transform.rotation, dtype=np.float64)
        ref = body_rot[:, 0]
        if abs(float(ref @ z)) > 0.9:
            ref = body_rot[:, 1]
        x = ref - (ref @ z) * z
        nx = np.linalg.norm(x)
        if nx < 1e-9:
            return None
        x = x / nx
        y = np.cross(z, x)
        return np.column_stack([x, y, z])

    def _add_body_node(
        self,
        body: "Body",
        parent_body,
        model: "AssemblyModel",
        groups: dict[str, list[str]],
        ktree,
        emitted: set[str],
        converter: MeshConverter,
        parent_global: Optional[np.ndarray] = None,
    ) -> int:
        group_members = None
        for _rep, members in groups.items():
            if body.name in members and len(members) > 1:
                group_members = members
                break

        # Bone frame: the body's orientation, but positioned at the hinge it
        # rotates about. A part origin is wherever the CAD author put it —
        # frequently at the link's *far* joint — and a bone that does not sit
        # on its pivot swings the link about the wrong point. Meshes are baked
        # from their own absolute frames below, so moving the bone changes the
        # articulation only, never the rest pose.
        bone_world = _transform_to_matrix(body.transform)
        pivot = self._pivot_for(body, groups, ktree)
        if pivot is not None:
            bone_world[:3, 3] = pivot
        basis = self._bone_basis_for(body, groups, ktree)
        if basis is not None:
            bone_world[:3, :3] = basis

        parent_frame = (
            self._global_root if parent_global is None else parent_global
        )
        global_matrix = self._global_root @ bone_world
        local = np.linalg.inv(parent_frame) @ global_matrix

        node = {"name": body.name}
        node["translation"] = [float(v) for v in local[:3, 3]]
        node["rotation"] = list(
            rotation_to_quaternion(local[:3, :3], scalar_first=False)
        )

        if group_members:
            node["name"] = "_".join(group_members[:2]) + "_group"
            idx = self._append_node(node)
            emitted.update(group_members)

            # Rigid-fused members: each keeps its own mesh (posed relative
            # to the group node); they all share the group's single bone.
            if self._enable_skin:
                self._skin_bone_index[body.name] = idx
                self._skin_global[idx] = global_matrix
            group_members_children: list[int] = []
            for member_name in group_members:
                member = model.get_body(member_name)
                if member is None:
                    continue
                member_global = self._global_root @ _transform_to_matrix(
                    member.transform
                )
                member_local = np.linalg.inv(global_matrix) @ member_global
                member_node = {
                    "name": member.name,
                    "translation": [float(v) for v in member_local[:3, 3]],
                    "rotation": list(
                        rotation_to_quaternion(
                            member_local[:3, :3], scalar_first=False
                        )
                    ),
                }
                member_node_idx = self._append_node(member_node)
                group_members_children.append(member_node_idx)

                mesh_index = self._mesh_index_for(member, converter)
                if mesh_index is not None:
                    member_node["mesh"] = mesh_index
                    if self._enable_skin:
                        self._mesh_index_by_body[member.name] = mesh_index
                        self._skin_global[member_node_idx] = member_global
                        self._mesh_node_global[member.name] = member_global
                        # Every member's vertices bind to the group bone;
                        # member nodes are visual sub-frames of that bone.
                        if member.name not in self._skin_bone_index:
                            self._skin_bone_index[member.name] = idx

        else:
            mesh_index = self._mesh_index_for(body, converter)
            if mesh_index is not None:
                node["mesh"] = mesh_index
            idx = self._append_node(node)
            emitted.add(body.name)

            if self._enable_skin:
                self._skin_bone_index[body.name] = idx
                self._skin_global[idx] = global_matrix
                if mesh_index is not None:
                    # The mesh rides on the bone node here, but the bone may
                    # have been moved to the pivot — bake from the body's own
                    # frame so the geometry stays where the CAD put it.
                    self._mesh_node_global[body.name] = (
                        self._global_root @ _transform_to_matrix(body.transform)
                    )

        # Link children into this node's children array.
        # Spanning-tree edges are keyed by group representative (which for
        # subassembly-fused groups is the alias name, not a leaf body), so
        # consult the rep's children as well as member names.
        children: list[int] = group_members_children if group_members else []
        rep = None
        for r, mem in groups.items():
            if body.name in mem:
                rep = r
                break
        if group_members:
            child_lookup = list(group_members)
            if rep is not None and rep not in child_lookup:
                child_lookup.append(rep)
        else:
            child_lookup = [body.name]
            if rep is not None and rep != body.name and rep not in child_lookup:
                child_lookup.append(rep)
        def _resolve_to_body(node_name: str):
            # child_name may be an alias rep (not a body name) - resolve
            # to one of that group's member bodies so the group node
            # gets emitted. Also match the group key itself, since
            # alias-named groups list only body names in members.
            direct = model.get_body(node_name)
            if direct is not None:
                return direct
            for r, mem in groups.items():
                if node_name == r or node_name in mem:
                    return model.get_body(mem[0])
            return None

        for lookup_name in child_lookup:
            for child_name in ktree.children_of.get(lookup_name, []):
                if child_name in emitted:
                    continue
                child_body = _resolve_to_body(child_name)
                if child_body is None:
                    continue
                children.append(
                    self._add_body_node(
                        child_body, body, model, groups, ktree, emitted, converter,
                        parent_global=global_matrix,
                    )
                )

        if children:
            node["children"] = children

        return idx

    def _append_node(self, node: dict) -> int:
        index = len(self._nodes)
        self._nodes.append(node)
        return index

    # ------------------------------------------------------------------
    # Meshes and materials
    # ------------------------------------------------------------------

    def _mesh_index_for(
        self, body: "Body", converter: MeshConverter
    ) -> Optional[int]:
        if body.name in self._mesh_index_by_body:
            return self._mesh_index_by_body[body.name]
        if body.geometry_file is None:
            return None
        # Angular tolerance ramped with linear tolerance: cylindrical/round
        # features are angle-dominated, so a coarse linear deflection needs a
        # coarse angular deflection too (e.g. tol=0.5 -> 0.3 rad).
        angular = max(0.1, min(0.6, 0.3 * (self._mesh_tolerance / 0.5)))
        try:
            stl_rel = converter.convert(
                body.geometry_file,
                body.name,
                tolerance=self._mesh_tolerance,
                angular_tolerance=angular,
            )
            stl_abs = converter.output_dir / stl_rel
            positions = load_stl(stl_abs)
        except Exception as e:
            logger.warning("Failed to convert mesh for %s: %s", body.name, e)
            return None
        index = self._add_mesh(body.name, positions, body)
        self._mesh_index_by_body[body.name] = index
        return index

    def _add_mesh(
        self, name: str, positions_mm: np.ndarray, body: "Body"
    ) -> int:
        positions = np.ascontiguousarray(positions_mm, dtype=np.float32) * _MM_TO_M
        normals = _flat_normals(positions)

        pos_view = self._add_buffer_view(positions.tobytes())
        norm_view = self._add_buffer_view(normals.tobytes())
        pos_acc = self._add_accessor(
            pos_view,
            count=len(positions),
            minimum=positions.min(axis=0).tolist(),
            maximum=positions.max(axis=0).tolist(),
        )
        norm_acc = self._add_accessor(norm_view, count=len(normals))

        primitive: dict = {
            "attributes": {"POSITION": pos_acc, "NORMAL": norm_acc},
            "mode": _MODE_TRIANGLES,
        }
        material_index = self._material_index_for(body)
        if material_index is not None:
            primitive["material"] = material_index

        self._meshes.append({"name": name, "primitives": [primitive]})
        return len(self._meshes) - 1

    def _material_index_for(self, body: "Body") -> Optional[int]:
        name = body.material_name if body.material_name else "default"
        if name in self._material_index:
            return self._material_index[name]

        color = self._color_for(name)
        material = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": list(color),
                "metallicFactor": 0.1,
                "roughnessFactor": 0.6,
            },
        }
        self._materials.append(material)
        index = len(self._materials) - 1
        self._material_index[name] = index
        return index

    def _color_for(self, material_name: str) -> tuple[float, float, float, float]:
        name_lower = material_name.lower()
        for material_type, color_str in _DEFAULT_COLORS.items():
            if material_type in name_lower:
                values = tuple(float(v) for v in color_str.split())
                assert len(values) == 4
                return values
        values = tuple(float(v) for v in _DEFAULT_COLORS["default"].split())
        return values

    # ------------------------------------------------------------------
    # Skin (armature)
    # ------------------------------------------------------------------

    def _add_skin(self, model: "AssemblyModel", gltf: dict) -> None:
        """Build the glTF skin from body nodes and rigid-skin all meshes.

        Standard rigid-skinning pattern:

        - Vertices are transformed into world space (including the Y-up
          root rotation, so IBM and vertices share one coordinate frame).
        - JOINTS_0 holds *skin-relative* bone indices (0..n-1); unused
          VEC4 slots are zero (non-zero + zero-weight trips validators).
        - Inverse bind matrices = inverse of the joint node's global
          transform at bind pose, so at rest
          ``global_joint @ IBM @ v`` evaluates to ``v`` exactly.
        - Joint nodes keep their hierarchical local transforms (they are
          the animatable skeleton); mesh nodes keep their transforms so
          static (skin-ignorant) viewers still place geometry correctly.

        Args:
            model: Assembly model.
            gltf: Partial glTF document being assembled.
        """
        joint_bodies = [
            b for b in model.bodies if b.name in self._skin_bone_index
        ]
        if not joint_bodies:
            return

        # Rigid-fused members map to their group's shared bone node; a body
        # may share a bone with others, so dedupe by node index. JOINTS_0
        # values are positions in this deduped joint list.
        bone_node_indices: list[int] = []
        seen_nodes: set[int] = set()
        for b in joint_bodies:
            node_idx = self._skin_bone_index[b.name]
            if node_idx not in seen_nodes:
                seen_nodes.add(node_idx)
                bone_node_indices.append(node_idx)

        # Skin-relative joint index for each body
        node_to_joint = {
            node_idx: j for j, node_idx in enumerate(bone_node_indices)
        }
        joint_index_of = {
            b.name: node_to_joint[self._skin_bone_index[b.name]]
            for b in joint_bodies
        }

        # Inverse bind matrices: inverse global transform at bind pose.
        # One IBM per (deduped) joint; glTF MAT4 arrays are column-major:
        # flatten the transpose.
        inv_bind: list[np.ndarray] = []
        for node_idx in bone_node_indices:
            global_matrix = self._skin_global[node_idx]
            inv_bind.append(np.linalg.inv(global_matrix).astype(np.float32))

        skin = {
            "name": f"{model.name}_armature",
            "joints": bone_node_indices,
        }

        # Inverse bind matrices require buffer-backed accessors; only add
        # them when geometry exists (otherwise the GLB has no buffer and
        # the reference dangles - validator UNRESOLVED_REFERENCE). IBMs
        # without skinned meshes convey no information anyway.
        if self._meshes:
            ibm_bytes = b"".join(
                m.T.astype("<f4").tobytes() for m in inv_bind
            )
            ibm_view = self._add_buffer_view_aligned(ibm_bytes)
            ibm_acc = self._add_accessor(
                ibm_view,
                count=len(inv_bind),
                type_=_TYPE_MAT4,
            )
            skin["inverseBindMatrices"] = ibm_acc
            # skeleton must be the common root of all joints (validator
            # SKIN_SKELETON_INVALID); that is the joint node whose group
            # rep has no tree parent. Omit if indeterminable (optional
            # field per spec).
            # Skeleton must be a common root of ALL joints. Use the node
            # graph itself: the bone node that no other bone lists as a
            # child. (Rep-name heuristics break because the writer renames
            # group nodes.)
            bone_set = set(bone_node_indices)
            has_parent = set()
            for node_idx in bone_node_indices:
                for child in self._nodes[node_idx].get("children", []):
                    if child in bone_set:
                        has_parent.add(child)
            roots = [n for n in bone_node_indices if n not in has_parent]
            if len(roots) == 1:
                skin["skeleton"] = roots[0]
        self._skins.append(skin)
        skin_index = len(self._skins) - 1

        # Skin every mesh: world-space vertices + JOINTS_0/WEIGHTS_0
        for b in joint_bodies:
            mesh_index = self._mesh_index_by_body.get(b.name)
            if mesh_index is None:
                continue
            node_idx = self._skin_bone_index[b.name]
            # Bake with the matrix of the node that carries this mesh, NOT
            # the bone's. For a rigid-group member the two differ: the bone
            # is the shared group node, so using it would place every member
            # at the group representative's pose.
            bake_matrix = self._mesh_node_global.get(
                b.name, self._skin_global[node_idx]
            )
            self._transform_mesh_to_world(mesh_index, bake_matrix)
            self._skin_mesh(mesh_index, joint_index_of[b.name])

        # Attach skin to nodes that reference meshes
        for node in self._nodes:
            if "mesh" in node:
                node["skin"] = skin_index

        # gltf dict was built before this method runs - attach now
        gltf["skins"] = self._skins

    def _transform_mesh_to_world(
        self, mesh_index: int, global_matrix: np.ndarray
    ) -> None:
        """Re-express a mesh's vertices in world space in-place.

        The rigid skinned-vertex formula uses *global* joint matrices and
        inverse binds in the same frame; vertices must therefore live in
        that frame (world, Y-up) rather than the body-local frame.
        Normals are recomputed from the transformed positions (flat
        shading), preserving their validity under the rigid transform.
        Accessor min/max bounds are updated since positions change.
        """
        mesh = self._meshes[mesh_index]
        primitive = mesh["primitives"][0]
        pos_acc_index = primitive["attributes"]["POSITION"]
        acc = self._accessors[pos_acc_index]
        pos_view = self._buffer_views[acc["bufferView"]]
        off, ln = pos_view["byteOffset"], pos_view["byteLength"]

        positions = (
            np.frombuffer(bytes(self._bin[off : off + ln]), dtype="<f4")
            .reshape(-1, 3)
            .astype(np.float64)
        )
        R = global_matrix[:3, :3]
        t = global_matrix[:3, 3]
        world = positions @ R.T + t

        self._bin[off : off + ln] = np.ascontiguousarray(
            world, dtype="<f4"
        ).tobytes()
        acc["min"] = world.min(axis=0).tolist()
        acc["max"] = world.max(axis=0).tolist()

        # Recompute flat normals in the new frame
        norm_acc_index = primitive["attributes"].get("NORMAL")
        if norm_acc_index is not None:
            nacc = self._accessors[norm_acc_index]
            nview = self._buffer_views[nacc["bufferView"]]
            noff, nlen = nview["byteOffset"], nview["byteLength"]
            world_f32 = world.astype(np.float32)
            normals = _flat_normals(world_f32)
            self._bin[noff : noff + nlen] = normals.tobytes()
            nacc.pop("min", None)
            nacc.pop("max", None)

    def _skin_mesh(self, mesh_index: int, joint_index: int) -> None:
        """Add rigid JOINTS_0/WEIGHTS_0 attributes to a mesh primitive.

        Per the glTF 2.0 spec, JOINTS_0 componentType must be UNSIGNED_BYTE
        (5121) or UNSIGNED_SHORT (5123) - never UNSIGNED_INT. Values are
        *skin-relative* joint indices. Unused VEC4 slots are zeroed: a
        non-zero joint index with zero weight is a validator error
        (ACCESSOR_JOINTS_USED_ZERO_WEIGHT) and confuses some loaders.
        """
        mesh = self._meshes[mesh_index]
        primitive = mesh["primitives"][0]
        pos_acc = primitive["attributes"]["POSITION"]
        count = self._accessors[pos_acc]["count"]

        joints_data = np.zeros((count, 4), dtype=np.uint16)
        joints_data[:, 0] = joint_index
        weights_data = np.zeros((count, 4), dtype=np.float32)
        weights_data[:, 0] = 1.0

        j_view = self._add_buffer_view_aligned(joints_data.tobytes())
        j_view_view = self._buffer_views[j_view]
        j_view_view["target"] = _TARGET_ARRAY_BUFFER
        w_view = self._add_buffer_view(weights_data.tobytes())
        j_acc = self._add_accessor(
            j_view,
            count=count,
            type_=_TYPE_VEC4,
            component=_COMPONENT_UNSIGNED_SHORT,
        )
        w_acc = self._add_accessor(w_view, count=count, type_=_TYPE_VEC4)
        primitive["attributes"]["JOINTS_0"] = j_acc
        primitive["attributes"]["WEIGHTS_0"] = w_acc

    # ------------------------------------------------------------------
    # Buffer plumbing
    # ------------------------------------------------------------------

    def _add_buffer_view(self, data: bytes) -> int:
        pad = (-len(self._bin)) % 4
        if pad:
            self._bin.extend(b"\0" * pad)
        view = {
            "buffer": 0,
            "byteOffset": len(self._bin),
            "byteLength": len(data),
            "target": _TARGET_ARRAY_BUFFER,
        }
        self._bin.extend(data)
        self._buffer_views.append(view)
        return len(self._buffer_views) - 1

    def _add_buffer_view_aligned(self, data: bytes, alignment: int = 4) -> int:
        """Add a buffer view whose data starts at ``alignment``-byte boundary.

        Required for MAT4 inverse-bind-matrix data per the glTF spec
        (component alignment, 4 bytes for float; padded to 16 keeps
        matrices contiguous).
        """
        pad = (-len(self._bin)) % alignment
        if pad:
            self._bin.extend(b"\0" * pad)
        view = {
            "buffer": 0,
            "byteOffset": len(self._bin),
            "byteLength": len(data),
        }
        self._bin.extend(data)
        self._buffer_views.append(view)
        return len(self._buffer_views) - 1

    def _add_accessor(
        self,
        buffer_view: int,
        count: int,
        minimum: Optional[list[float]] = None,
        maximum: Optional[list[float]] = None,
        type_: str = _TYPE_VEC3,
        component: int = _COMPONENT_FLOAT,
    ) -> int:
        accessor: dict = {
            "bufferView": buffer_view,
            "componentType": component,
            "count": count,
            "type": type_,
        }
        if minimum is not None:
            accessor["min"] = minimum
        if maximum is not None:
            accessor["max"] = maximum
        self._accessors.append(accessor)
        return len(self._accessors) - 1

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _write_glb(self, gltf: dict, output_path: Path) -> None:
        if self._meshes:
            gltf["buffers"] = [{"byteLength": len(self._bin)}]

        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * ((-len(json_bytes)) % 4)

        bin_bytes = bytes(self._bin)
        has_bin = len(bin_bytes) > 0
        if has_bin:
            bin_bytes += b"\0" * ((-len(bin_bytes)) % 4)

        total_length = 12 + 8 + len(json_bytes)
        if has_bin:
            total_length += 8 + len(bin_bytes)

        with open(output_path, "wb") as f:
            f.write(struct.pack("<III", _GLB_MAGIC, _GLB_VERSION, total_length))
            f.write(struct.pack("<II", len(json_bytes), _CHUNK_JSON))
            f.write(json_bytes)
            if has_bin:
                f.write(struct.pack("<II", len(bin_bytes), _CHUNK_BIN))
                f.write(bin_bytes)

    def _write_gltf_json(self, gltf: dict, output_path: Path) -> None:
        if self._meshes:
            encoded = base64.b64encode(bytes(self._bin)).decode("ascii")
            gltf["buffers"] = [
                {
                    "byteLength": len(self._bin),
                    "uri": f"data:application/octet-stream;base64,{encoded}",
                }
            ]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(gltf, f, indent=2)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _constraint_extras(self, model: "AssemblyModel") -> list[dict]:
        entries: list[dict] = []
        for c in model.constraints:
            entry: dict = {"type": c.type}
            if c.name:
                entry["name"] = c.name
            entry["bodies"] = [c.occurrence_one, c.occurrence_two]
            entry["rigid"] = c.is_rigid
            # Axis and origin are in assembly world coordinates, the same
            # frame the body node translations use: those nodes sit *inside*
            # the world_y_up root, which carries the Z-up -> Y-up rotation.
            if c.axis is not None:
                entry["axis"] = [float(v) for v in c.axis]
            # Prefer the world-frame origin read off the joint geometry: it
            # needs no knowledge of which occurrence's local frame the point
            # belongs to. Fall back to the local-frame point, tagged with the
            # occurrence whose frame it is in so a consumer can place it.
            world_origin = c.world_origin()
            if world_origin is not None:
                entry["origin"] = [float(v) for v in world_origin]
                entry["origin_frame"] = "assembly_world"
                if c.origin_two_world is not None:
                    entry["origin_two"] = [float(v) for v in c.origin_two_world]
            elif c.origin is not None:
                entry["origin"] = [float(v) for v in c.origin]
                entry["origin_frame"] = c.origin_occurrence or "unknown"
            if c.limits is not None:
                entry["limits"] = [float(v) for v in c.limits]
            entries.append(entry)
        return entries