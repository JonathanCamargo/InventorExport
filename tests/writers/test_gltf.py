"""Unit tests for glTF/GLB writer."""

import base64
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from inventor_exporter.model import (
    AssemblyModel,
    Body,
    Inertia,
    Material,
    Transform,
)
from inventor_exporter.writers import WriterRegistry, get_writer
from inventor_exporter.writers.gltf import GLTFWriter, load_stl


GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


@pytest.fixture
def simple_material():
    return Material(name="steel", density=7800.0)


@pytest.fixture
def simple_transform():
    return Transform(position=np.array([1.0, 2.0, 3.0]))


@pytest.fixture
def simple_body(simple_transform, simple_material):
    return Body(
        name="link1",
        transform=simple_transform,
        material_name=simple_material.name,
    )


@pytest.fixture
def simple_assembly(simple_body, simple_material):
    return AssemblyModel(
        name="TestAssembly",
        bodies=(simple_body,),
        materials=(simple_material,),
    )


def _cube_stl(path: Path, size: float = 10.0) -> Path:
    """Write a simple binary STL cube (in mm) for embedding tests."""
    s = size / 2.0
    # 12 triangles, indexed as a triangle soup
    v = np.array(
        [
            # faces of a cube: 2 triangles * 6 faces = 36 vertices
        ]
    )
    quads = [
        [(s, s, s), (s, -s, s), (-s, -s, s), (-s, s, s)],  # +z
        [(s, s, -s), (-s, s, -s), (-s, -s, -s), (s, -s, -s)],  # -z
        [(s, s, s), (s, s, -s), (s, -s, -s), (s, -s, s)],  # +x
        [(-s, s, s), (-s, -s, s), (-s, -s, -s), (-s, s, -s)],  # -x
        [(s, s, s), (-s, s, s), (-s, s, -s), (s, s, -s)],  # +y
        [(s, -s, s), (s, -s, -s), (-s, -s, -s), (-s, -s, s)],  # -y
    ]
    triangular_v = []
    for quad in quads:
        triangular_v.extend([quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]])
    v = np.array(triangular_v)

    header = b"\0" * 80
    count = struct.pack("<I", len(v) // 3)
    dtype = np.dtype(
        [
            ("normal", "<f4", (3,)),
            ("vertices", "<f4", (3, 3)),
            ("attr", "<u2"),
        ]
    )
    triangles = np.zeros(len(v) // 3, dtype=dtype)
    triangles["vertices"] = v.reshape(-1, 3, 3)
    path.write_bytes(header + count + triangles.tobytes())
    return path


def _parse_glb(data: bytes) -> dict:
    """Parse GLB container; return decoded JSON document with '_bin' attached."""
    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == GLB_MAGIC
    assert version == GLB_VERSION
    assert length == len(data)

    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    assert chunk_type == CHUNK_JSON
    doc = json.loads(data[20 : 20 + chunk_len].decode("utf-8"))

    offset = 20 + chunk_len
    if offset < len(data):
        bin_len, bin_type = struct.unpack_from("<II", data, offset)
        assert bin_type == CHUNK_BIN
        doc["_bin"] = data[offset + 8 : offset + 8 + bin_len]
    return doc


def _resolve_accessor(doc: dict, accessor_index: int) -> np.ndarray:
    """Decode a VEC3 float accessor from the GLB document."""
    accessor = doc["accessors"][accessor_index]
    view = doc["bufferViews"][accessor["bufferView"]]
    bin_data = doc.get("_bin", b"")
    raw = bin_data[view["byteOffset"] : view["byteOffset"] + view["byteLength"]]
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 3)


class TestGLTFWriterRegistration:
    """Tests for writer registration."""

    def test_gltf_writer_registered(self):
        assert "gltf" in WriterRegistry.list_formats()

    def test_glb_alias_registered(self):
        assert "glb" in WriterRegistry.list_formats()

    def test_writer_properties(self):
        writer = get_writer("gltf")
        assert writer.format_name == "gltf"
        assert writer.file_extension == ".glb"


class TestGLBOutput:
    """Tests for binary GLB output."""

    def test_write_glb_creates_file(self, simple_assembly, tmp_path):
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_glb_container_structure(self, simple_assembly, tmp_path):
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert doc["asset"]["version"] == "2.0"
        assert doc["scene"] == 0
        assert len(doc["scenes"]) == 1
        # buffers omitted entirely when no geometry is embedded (valid per
        # spec), otherwise exactly one buffer.
        if "buffers" in doc:
            assert len(doc["buffers"]) == 1

    def test_glb_handles_no_geometry(self, simple_assembly, tmp_path):
        """Assembly without geometry should still produce a valid GLB."""
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert "meshes" not in doc or not doc["meshes"]
        # Root rotation node present but no geometry chunks
        assert len(doc["scenes"][0]["nodes"]) == 1

    def test_glb_json_chunk_padding(self, simple_assembly, tmp_path):
        """GLB JSON chunk must be 4-byte aligned with spaces."""
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        data = output_path.read_bytes()
        chunk_len, _ = struct.unpack_from("<II", data, 12)
        assert chunk_len % 4 == 0


class TestGLTFJsonOutput:
    """Tests for JSON glTF output."""

    def test_write_json_creates_file(self, simple_assembly, tmp_path):
        writer = get_writer("gltf")
        output_path = tmp_path / "model.gltf"
        writer.write(simple_assembly, output_path)
        assert output_path.exists()

    def test_json_is_parseable(self, simple_assembly, tmp_path):
        writer = get_writer("gltf")
        output_path = tmp_path / "model.gltf"
        writer.write(simple_assembly, output_path)

        doc = json.loads(output_path.read_text(encoding="utf-8"))
        assert doc["asset"]["version"] == "2.0"
        assert doc["asset"]["generator"].startswith("inventor-exporter")

    def test_json_uses_data_uri(self, simple_material, tmp_path):
        """JSON glTF should embed buffer as base64 data URI."""
        import cadquery as cq

        real_step = tmp_path / "real.step"
        cq.exporters.export(
            cq.Workplane("XY").box(5, 5, 5), str(real_step), exportType="STEP"
        )
        model = AssemblyModel(
            name="Asm",
            bodies=(
                Body(name="link1", transform=Transform(), geometry_file=real_step),
            ),
            materials=(simple_material,),
        )

        writer = get_writer("gltf")
        output_path = tmp_path / "model.gltf"
        writer.write(model, output_path)

        doc = json.loads(output_path.read_text(encoding="utf-8"))
        uri = doc["buffers"][0]["uri"]
        assert uri.startswith("data:application/octet-stream;base64,")
        # Buffers should decode without error
        base64.b64decode(uri.split(",", 1)[1])


class TestNodeHierarchy:
    """Tests for node structure."""

    def test_body_node_with_transform(self, simple_assembly, tmp_path):
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        # Node [0] is Y-up root; body node follows
        body_node = doc["nodes"][1]
        assert body_node["name"] == "link1"
        np.testing.assert_allclose(body_node["translation"], [1.0, 2.0, 3.0])
        # Identity rotation quaternion
        np.testing.assert_allclose(body_node["rotation"], [0, 0, 0, 1], atol=1e-12)

    def test_y_up_root_rotation(self, simple_assembly, tmp_path):
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        root = doc["nodes"][0]
        assert root["name"] == "world_y_up"
        q = root["rotation"]
        # -90 deg about X: q = (x, y, z, w) = (-sin45, 0, 0, cos45)
        assert q[3] == pytest.approx(np.cos(np.pi / 4), abs=1e-6)

    def test_no_y_up_when_disabled(self, simple_assembly, tmp_path):
        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert len(doc["scenes"][0]["nodes"]) == 1
        assert doc["nodes"][0]["name"] == "link1"


def _joint_pendulum_model(simple_material, with_geometry=False, tmp_path=None):
    """Two-body revolute pendulum: base -> arm via joint J1.

    With ``with_geometry=True`` each body gets a real STEP file so mesh
    embedding and skin attributes are exercised.
    """
    from inventor_exporter.model.constraint import ConstraintInfo

    b1 = Body(name="base", transform=Transform())
    b2 = Body(
        name="arm",
        transform=Transform(position=np.array([0.0, 0.0, 0.5])),
    )
    if with_geometry:
        import cadquery as cq

        s1 = tmp_path / "pend_base.step"
        s2 = tmp_path / "pend_arm.step"
        cq.exporters.export(
            cq.Workplane("XY").box(40.0, 40.0, 10.0), str(s1), exportType="STEP"
        )
        cq.exporters.export(
            cq.Workplane("XY").box(10.0, 10.0, 60.0), str(s2), exportType="STEP"
        )
        b1 = Body(name="base", transform=Transform(), geometry_file=s1)
        b2 = Body(
            name="arm",
            transform=Transform(position=np.array([0.0, 0.0, 0.5])),
            geometry_file=s2,
        )
    constraint = ConstraintInfo(
        type="rotational_joint",
        occurrence_one="arm",
        occurrence_two="base",
        name="J1",
        axis=(1.0, 0.0, 0.0),
        origin=(0.0, 0.0, 0.25),
    )
    return AssemblyModel(
        name="Pendulum",
        bodies=(b1, b2),
        materials=(simple_material,),
        constraints=(constraint,),
        ground_body="base",
    )


class TestSkeleton:
    """Tests for the glTF skin (armature) emitted from the kinematic tree."""

    def test_skin_emitted_with_joints(self, simple_material, tmp_path):
        model = _joint_pendulum_model(simple_material)
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert len(doc["skins"]) == 1
        skin = doc["skins"][0]
        assert skin["name"] == "Pendulum_armature"
        assert len(skin["joints"]) == 2

    def test_nodes_form_parent_child_hierarchy(self, simple_material, tmp_path):
        """Child 'arm' node must appear in parent 'base' node's children."""
        model = _joint_pendulum_model(simple_material)
        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        nodes = doc["nodes"]
        by_name = {n["name"]: n for n in nodes}
        parent = by_name["base"]
        child_idx = next(i for i, n in enumerate(nodes) if n["name"] == "arm")
        assert child_idx in parent.get("children", [])

    def test_mesh_nodes_carry_skin(self, simple_material, tmp_path):
        model = _joint_pendulum_model(
            simple_material, with_geometry=True, tmp_path=tmp_path
        )
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert "skins" in doc
        skinned = [n for n in doc["nodes"] if "mesh" in n]
        assert skinned
        assert all(n["skin"] == 0 for n in skinned)

    def test_joints_weights_attributes_present(self, simple_material, tmp_path):
        """Skinned primitives must have JOINTS_0 and WEIGHTS_0 accessors."""
        model = _joint_pendulum_model(
            simple_material, with_geometry=True, tmp_path=tmp_path
        )
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        for mesh in doc["meshes"]:
            attrs = mesh["primitives"][0]["attributes"]
            assert "JOINTS_0" in attrs
            assert "WEIGHTS_0" in attrs

            j = doc["accessors"][attrs["JOINTS_0"]]
            assert j["type"] == "VEC4"
            assert j["componentType"] == 5123  # UNSIGNED_SHORT (spec-required)

            w = doc["accessors"][attrs["WEIGHTS_0"]]
            assert w["type"] == "VEC4"

    def test_inverse_bind_matrices(self, simple_material, tmp_path):
        """Skin must carry inverse bind matrices matching the bind pose."""
        model = _joint_pendulum_model(
            simple_material, with_geometry=True, tmp_path=tmp_path
        )
        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        skin = doc["skins"][0]
        ibm_acc = doc["accessors"][skin["inverseBindMatrices"]]
        assert ibm_acc["type"] == "MAT4"
        assert ibm_acc["count"] == len(skin["joints"])

        view = doc["bufferViews"][ibm_acc["bufferView"]]
        raw = doc["_bin"][
            view["byteOffset"] : view["byteOffset"] + view["byteLength"]
        ]
        # glTF MAT4 is column-major; reshape+transpose -> math matrix
        matrices = np.frombuffer(raw, dtype="<f4").reshape(-1, 4, 4).transpose(0, 2, 1)

        # Vertices live in world (Y-up) space. Each IBM is the inverse of
        # Yup_root @ T_body -- compute expected directly the same way.
        zup_to_yup = np.array(
            [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]
        )
        yup = np.eye(4)
        yup[:3, :3] = zup_to_yup

        def _inv_global(pos, rot=None):
            t = np.eye(4)
            if rot is not None:
                t[:3, :3] = rot
            t[:3, 3] = pos
            return np.linalg.inv(yup @ t)

        # base is the tree root: no parent joint, so it keeps its own frame
        np.testing.assert_allclose(matrices[0], _inv_global([0, 0, 0]), atol=1e-6)

        # arm hangs off J1, whose axis is (1,0,0), so its bone is re-oriented
        # to put local +Z on that hinge.
        hinge_basis = np.array(
            [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        np.testing.assert_allclose(
            hinge_basis @ [0, 0, 1], [1, 0, 0], atol=1e-12
        )
        np.testing.assert_allclose(
            matrices[1], _inv_global([0.0, 0.0, 0.5], hinge_basis), atol=1e-6
        )

    def test_skin_disabled(self, simple_material, tmp_path):
        model = _joint_pendulum_model(
            simple_material, with_geometry=True, tmp_path=tmp_path
        )
        writer = GLTFWriter(enable_skin=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert "skins" not in doc
        for mesh in doc["meshes"]:
            assert "JOINTS_0" not in mesh["primitives"][0]["attributes"]

    def test_hierarchy_without_joints_still_links(self, simple_assembly, tmp_path):
        """Single body still produces a valid scene root linkage."""
        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(simple_assembly, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert doc["scenes"][0]["nodes"]
        assert "skins" in doc  # single bone armature still emitted




    def test_subassembly_joints_resolve_to_leaf_bodies(
        self, simple_material, tmp_path
    ):
        """Joints referencing subassembly names must build the kinematic
        chain over the leaf-part groups underneath them (regression:
        palletizer exported 19 flat bones, 0 links)."""
        from inventor_exporter.model.constraint import ConstraintInfo

        # Leaf parts named like Inventor instance parts, ancestors record
        # which subassembly they belong to
        bodies = (
            Body(name="1_30_00263_385", transform=Transform(), ancestors=("base_1",)),
            Body(name="1_30_00265_442", transform=Transform(), ancestors=("base_1",)),
            Body(name="1_30_00268_391", transform=Transform(), ancestors=("Link1_1",)),
            Body(name="1_30_00269_392", transform=Transform(), ancestors=("Link1_1",)),
            Body(name="1_30_00281_405", transform=Transform(), ancestors=("Link4_1",)),
        )
        joints = (
            ConstraintInfo(
                type="rotational_joint",
                occurrence_one="Link1:1",
                occurrence_two="base:1",
                name="Rotational:1",
            ),
            ConstraintInfo(
                type="rotational_joint",
                occurrence_one="Link4:1",
                occurrence_two="base:1",
                name="Rotational:2",
            ),
        )
        model = AssemblyModel(
            name="Palletizer",
            bodies=bodies,
            materials=(simple_material,),
            constraints=joints,
        )

        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        skin = doc["skins"][0]
        node_names = [doc["nodes"][j]["name"] for j in skin["joints"]]
        # 3 bones: base group, Link1 group, Link4 (single-member)
        assert len(skin["joints"]) == 3

        # Both joints must produce bone->bone edges
        links = [
            (doc["nodes"][n]["name"], doc["nodes"][c]["name"])
            for n in skin["joints"]
            for c in doc["nodes"][n].get("children", [])
            if c in skin["joints"]
        ]
        assert len(links) == 2
        # Both joints connect their moving group to the base group
        # (BFS root = base, both links are its children)
        parents = {a for a, _ in links}
        children = {b for _, b in links}
        assert len(children) == 2


class TestMeshEmbedding:
    """Tests for geometry embedding."""

    def test_mesh_embeds_step_geometry(self, simple_assembly, tmp_path):
        """STEP geometry is converted to STL and embedded in meters."""
        import cadquery as cq

        cq_box = cq.Workplane("XY").box(100.0, 50.0, 20.0)
        real_step = tmp_path / "real.step"
        cq.exporters.export(cq_box, str(real_step), exportType="STEP")

        body = Body(
            name="link1",
            transform=Transform(),
            material_name="steel",
            geometry_file=real_step,
        )
        model = AssemblyModel(
            name="MeshAsm", bodies=(body,), materials=simple_assembly.materials
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)
        doc = _parse_glb(output_path.read_bytes())

        assert len(doc["meshes"]) == 1
        primitive = doc["meshes"][0]["primitives"][0]
        positions = _resolve_accessor(doc, primitive["attributes"]["POSITION"])
        # Cube bounds in meters (100mm cube)
        assert positions.max() == pytest.approx(0.05, abs=1e-3)
        assert doc["buffers"][0]["byteLength"] > 0

    def test_mesh_normals_present(self, simple_assembly, tmp_path):
        import cadquery as cq

        real_step = tmp_path / "real.step"
        cq_box = cq.Workplane("XY").box(10.0, 10.0, 10.0)
        cq.exporters.export(cq_box, str(real_step), exportType="STEP")

        body = Body(
            name="link1",
            transform=Transform(),
            geometry_file=real_step,
        )
        model = AssemblyModel(name="Asm", bodies=(body,), materials=())

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        primitive = doc["meshes"][0]["primitives"][0]
        assert "NORMAL" in primitive["attributes"]

        normals = _resolve_accessor(doc, primitive["attributes"]["NORMAL"])
        lengths = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(lengths, 1.0, atol=1e-5)

    def test_missing_geometry_yields_warning_not_error(
        self, simple_material, tmp_path
    ):
        step_path = tmp_path / "missing.step"
        body = Body(
            name="link1", transform=Transform(), geometry_file=step_path
        )
        model = AssemblyModel(
            name="Asm", bodies=(body,), materials=(simple_material,)
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)  # should not raise

        doc = _parse_glb(output_path.read_bytes())
        assert not doc.get("meshes")


class TestMaterials:
    """Tests for PBR material emission."""

    def test_material_from_body(self, simple_material, tmp_path):
        import cadquery as cq

        real_step = tmp_path / "real.step"
        cq.exporters.export(
            cq.Workplane("XY").box(5, 5, 5), str(real_step), exportType="STEP"
        )
        model = AssemblyModel(
            name="Asm",
            bodies=(
                Body(
                    name="link1",
                    transform=Transform(),
                    material_name="steel",
                    geometry_file=real_step,
                ),
            ),
            materials=(simple_material,),
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        assert len(doc["materials"]) == 1
        material = doc["materials"][0]
        assert material["name"] == "steel"
        assert "pbrMetallicRoughness" in material
        base_color = material["pbrMetallicRoughness"]["baseColorFactor"]
        assert len(base_color) == 4
        # steel -> light gray
        assert base_color[0] == pytest.approx(0.7)

    def test_unknown_material_uses_default(self, tmp_path):
        import cadquery as cq

        real_step = tmp_path / "real.step"
        cq.exporters.export(
            cq.Workplane("XY").box(5, 5, 5), str(real_step), exportType="STEP"
        )
        model = AssemblyModel(
            name="Asm",
            bodies=(
                Body(
                    name="link1",
                    transform=Transform(),
                    material_name="unobtainium",
                    geometry_file=real_step,
                ),
            ),
            materials=(Material(name="unobtainium"),),
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        material = doc["materials"][0]
        base_color = material["pbrMetallicRoughness"]["baseColorFactor"]
        assert base_color[0] == pytest.approx(0.6)  # default gray


class TestKinematicStructure:
    """Tests for kinematic-tree-driven node hierarchy."""

    def test_joint_in_extras(self, simple_material, tmp_path):
        from inventor_exporter.model.constraint import ConstraintInfo

        b1 = Body(name="base", transform=Transform())
        b2 = Body(
            name="arm",
            transform=Transform(position=np.array([0.0, 0.0, 0.5])),
        )
        constraint = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="arm",
            occurrence_two="base",
            name="J1",
            axis=(0.0, 0.0, 1.0),
            origin=(0.0, 0.0, 0.25),
            limits=(-1.57, 1.57),
        )
        model = AssemblyModel(
            name="Pendulum",
            bodies=(b1, b2),
            materials=(simple_material,),
            constraints=(constraint,),
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        extras = doc["extras"]["constraints"]
        assert len(extras) == 1
        entry = extras[0]
        assert entry["type"] == "rotational_joint"
        assert entry["name"] == "J1"
        assert entry["axis"] == [0.0, 0.0, 1.0]
        assert entry["limits"] == [-1.57, 1.57]

    def test_world_origin_in_extras(self, simple_material, tmp_path):
        """A joint origin read off the geometry is emitted in world coords.

        Body nodes sit inside the world_y_up root, so their translations are
        still in assembly world space — the extras must use the same frame.
        """
        from inventor_exporter.model.constraint import ConstraintInfo

        b1 = Body(name="base", transform=Transform())
        b2 = Body(
            name="arm",
            transform=Transform(position=np.array([0.0, 0.0, 0.5])),
        )
        constraint = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="arm",
            occurrence_two="base",
            name="J1",
            axis=(0.0, 0.0, 1.0),
            origin=(0.0, 0.0, 0.25),
            origin_world=(0.1, 0.2, 0.3),
            origin_two_world=(0.1, 0.2, 0.35),
            origin_occurrence="arm",
        )
        model = AssemblyModel(
            name="Pendulum",
            bodies=(b1, b2),
            materials=(simple_material,),
            constraints=(constraint,),
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        entry = _parse_glb(output_path.read_bytes())["extras"]["constraints"][0]
        assert entry["origin"] == [0.1, 0.2, 0.3]
        assert entry["origin_two"] == [0.1, 0.2, 0.35]
        assert entry["origin_frame"] == "assembly_world"

    def test_local_origin_in_extras_is_frame_tagged(
        self, simple_material, tmp_path
    ):
        """Without world geometry, the local point is tagged with its frame."""
        from inventor_exporter.model.constraint import ConstraintInfo

        b1 = Body(name="base", transform=Transform())
        b2 = Body(
            name="arm",
            transform=Transform(position=np.array([0.0, 0.0, 0.5])),
        )
        constraint = ConstraintInfo(
            type="rotational_joint",
            occurrence_one="arm",
            occurrence_two="base",
            name="J1",
            origin=(0.0, 0.0, 0.25),
            origin_occurrence="inner_part",
        )
        model = AssemblyModel(
            name="Pendulum",
            bodies=(b1, b2),
            materials=(simple_material,),
            constraints=(constraint,),
        )

        writer = get_writer("glb")
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        entry = _parse_glb(output_path.read_bytes())["extras"]["constraints"][0]
        assert entry["origin"] == [0.0, 0.0, 0.25]
        assert entry["origin_frame"] == "inner_part"

    def test_rigid_group_merged_into_node(self, simple_material, tmp_path):
        from inventor_exporter.model.constraint import ConstraintInfo

        b1 = Body(
            name="part_a", transform=Transform(position=np.array([0, 0, 0]))
        )
        b2 = Body(
            name="part_b",
            transform=Transform(position=np.array([0.1, 0, 0])),
        )
        b3 = Body(
            name="part_c", transform=Transform(position=np.array([0.2, 0, 0]))
        )
        constraint = ConstraintInfo(
            type="rigid_joint",
            occurrence_one="part_a",
            occurrence_two="part_b",
            is_rigid=True,
        )
        model = AssemblyModel(
            name="Welded",
            bodies=(b1, b2, b3),
            materials=(simple_material,),
            constraints=(constraint,),
        )

        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        node_names = [n["name"] for n in doc["nodes"]]
        assert "part_a_part_b_group" in node_names

    def test_rigid_group_members_keep_meshes_one_bone(
        self, simple_material, tmp_path
    ):
        """Rigid-fused parts form ONE rigid body: single bone, but every
        member's mesh must still be embedded (regression for the dropped
        member-mesh bug)."""
        import cadquery as cq
        from inventor_exporter.model.constraint import ConstraintInfo

        s1 = tmp_path / "p1.step"
        s2 = tmp_path / "p2.step"
        cq.exporters.export(
            cq.Workplane("XY").box(20, 20, 20), str(s1), exportType="STEP"
        )
        cq.exporters.export(
            cq.Workplane("XY").box(10, 10, 10), str(s2), exportType="STEP"
        )

        b1 = Body(
            name="part_a", transform=Transform(), geometry_file=s1
        )
        b2 = Body(
            name="part_b",
            transform=Transform(position=np.array([0.1, 0, 0])),
            geometry_file=s2,
        )
        constraint = ConstraintInfo(
            type="rigid_joint",
            occurrence_one="part_a",
            occurrence_two="part_b",
            is_rigid=True,
        )
        model = AssemblyModel(
            name="Welded",
            bodies=(b1, b2),
            materials=(simple_material,),
            constraints=(constraint,),
            ground_body="part_a",
        )

        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())
        # Both member meshes survive
        assert len(doc["meshes"]) == 2
        # Exactly ONE bone (joint bodies fuse into one rigid body)
        skin = doc["skins"][0]
        assert len(skin["joints"]) == 1
        # Bone is the group node; both mesh nodes point at the same skin
        group_node = next(
            n for n in doc["nodes"] if n["name"] == "part_a_part_b_group"
        )
        skinned_nodes = [n for n in doc["nodes"] if "mesh" in n]
        assert len(skinned_nodes) == 2
        assert all(n["skin"] == 0 for n in skinned_nodes)
        # The part_b member node is a child of the group node
        assert all(
            i in group_node["children"]
            for i in range(len(doc["nodes"]))
            if "part_b" == doc["nodes"][i]["name"]
        )

    def test_rigid_group_member_baked_at_own_pose(
        self, simple_material, tmp_path
    ):
        """Each group member's mesh is baked with ITS OWN global transform.

        Regression: the bake matrix was looked up through _skin_bone_index,
        which for a group member points at the shared group node — so every
        member was placed at the group representative's pose. The first
        member happens to be the representative, so only the others moved.
        """
        import cadquery as cq
        from inventor_exporter.model.constraint import ConstraintInfo

        s1 = tmp_path / "p1.step"
        s2 = tmp_path / "p2.step"
        # 20 mm and 10 mm cubes, centred on their part origins
        cq.exporters.export(
            cq.Workplane("XY").box(20, 20, 20), str(s1), exportType="STEP"
        )
        cq.exporters.export(
            cq.Workplane("XY").box(10, 10, 10), str(s2), exportType="STEP"
        )

        offset = np.array([0.3, 0.0, 0.0])
        b1 = Body(name="part_a", transform=Transform(), geometry_file=s1)
        b2 = Body(
            name="part_b",
            transform=Transform(position=offset),
            geometry_file=s2,
        )
        model = AssemblyModel(
            name="Welded",
            bodies=(b1, b2),
            materials=(simple_material,),
            constraints=(
                ConstraintInfo(
                    type="rigid_joint",
                    occurrence_one="part_a",
                    occurrence_two="part_b",
                    is_rigid=True,
                ),
            ),
            ground_body="part_a",
        )

        writer = GLTFWriter(y_up=False)
        output_path = tmp_path / "model.glb"
        writer.write(model, output_path)

        doc = _parse_glb(output_path.read_bytes())

        def bounds(body_name):
            node = next(n for n in doc["nodes"] if n["name"] == body_name)
            prim = doc["meshes"][node["mesh"]]["primitives"][0]
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            return np.array(acc["min"]), np.array(acc["max"])

        a_min, a_max = bounds("part_a")
        b_min, b_max = bounds("part_b")

        # Vertices are baked into world space, so each centre must sit at
        # that body's own world position.
        np.testing.assert_allclose((a_min + a_max) / 2, [0, 0, 0], atol=1e-6)
        np.testing.assert_allclose((b_min + b_max) / 2, offset, atol=1e-6)
        # ...and each keeps its own size (10 mm vs 20 mm)
        np.testing.assert_allclose(a_max - a_min, [0.02] * 3, atol=1e-6)
        np.testing.assert_allclose(b_max - b_min, [0.01] * 3, atol=1e-6)


class TestValidation:
    """Tests for model validation."""

    def test_invalid_model_raises(self, tmp_path):
        model = AssemblyModel(name="", bodies=(), materials=())
        writer = get_writer("glb")
        with pytest.raises(ValueError, match="validation failed"):
            writer.write(model, tmp_path / "out.glb")

    def test_nonpositive_mass_raises(self, tmp_path):
        body = Body(
            name="link1",
            transform=Transform(),
            inertia=Inertia(mass=0.0),
        )
        model = AssemblyModel(name="Asm", bodies=(body,), materials=())
        writer = get_writer("glb")
        with pytest.raises(ValueError, match="non-positive mass"):
            writer.write(model, tmp_path / "out.glb")


class TestMeshTolerance:
    """Tests for mesh tolerance parameter."""

    def test_default_tolerance_is_0_5(self):
        writer = GLTFWriter()
        assert writer._mesh_tolerance == 0.5

    def test_tolerance_passed_to_converter(self, simple_material, tmp_path):
        """Writer should forward tolerance so coarser meshes are produced."""
        import cadquery as cq

        cylinder = cq.Workplane("XY").circle(50.0).extrude(100.0)
        step_path = tmp_path / "cyl.step"
        cq.exporters.export(cylinder, str(step_path), exportType="STEP")

        sizes = {}
        for tolerance in (0.05, 2.0):
            work_dir = tmp_path / f"run_{tolerance}"
            work_dir.mkdir()
            local_step = work_dir / "cyl.step"
            local_step.write_bytes(step_path.read_bytes())

            model = AssemblyModel(
                name="Asm",
                bodies=(
                    Body(
                        name="link1",
                        transform=Transform(),
                        geometry_file=local_step,
                    ),
                ),
                materials=(simple_material,),
            )

            writer = GLTFWriter(mesh_tolerance=tolerance)
            output_path = work_dir / "model.glb"
            writer.write(model, output_path)
            sizes[tolerance] = output_path.stat().st_size

        assert sizes[2.0] < sizes[0.05]


class TestStlLoading:
    """Tests for STL loading helper."""

    def test_load_binary_stl_roundtrip(self, tmp_path):
        stl_path = _cube_stl(tmp_path / "cube.stl", size=42.0)
        positions = load_stl(stl_path)
        assert positions.shape == (36, 3)
        assert positions.max() == pytest.approx(21.0)

    def test_load_ascii_stl(self, tmp_path):
        content = "\n".join(
            [
                "solid cube",
                "  facet normal 0 0 1",
                "    outer loop",
                "      vertex 0.0 0.0 0.0",
                "      vertex 1.0 0.0 0.0",
                "      vertex 0.0 1.0 0.0",
                "    endloop",
                "  endfacet",
                "endsolid cube",
            ]
        )
        stl_path = tmp_path / "ascii.stl"
        stl_path.write_text(content)
        positions = load_stl(stl_path)
        assert positions.shape == (3, 3)

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_stl(tmp_path / "nope.stl")

    def test_load_garbage_raises(self, tmp_path):
        path = tmp_path / "bad.stl"
        path.write_bytes(b"\xff" * 100)
        with pytest.raises(ValueError):
            load_stl(path)

class TestBonePlacement:
    """Bones must sit on the hinge they rotate about, not on the part origin.

    A CAD part origin is wherever the author put it — often at the link's
    *far* joint. A bone placed there swings the link about the wrong point,
    so the rest pose looks right but any articulation is wrong.
    """

    def _model(self, simple_material, tmp_path, joint_origin):
        import cadquery as cq
        from inventor_exporter.model.constraint import ConstraintInfo

        s1 = tmp_path / "p1.step"
        s2 = tmp_path / "p2.step"
        cq.exporters.export(
            cq.Workplane("XY").box(20, 20, 20), str(s1), exportType="STEP"
        )
        cq.exporters.export(
            cq.Workplane("XY").box(20, 20, 20), str(s2), exportType="STEP"
        )
        base = Body(name="base", transform=Transform(), geometry_file=s1)
        arm = Body(
            name="arm",
            transform=Transform(position=np.array([0.0, 0.0, 0.5])),
            geometry_file=s2,
        )
        return AssemblyModel(
            name="Arm",
            bodies=(base, arm),
            materials=(simple_material,),
            constraints=(
                ConstraintInfo(
                    type="rotational_joint",
                    occurrence_one="arm",
                    occurrence_two="base",
                    name="J1",
                    axis=(1.0, 0.0, 0.0),
                    origin_world=joint_origin,
                ),
            ),
            ground_body="base",
        )

    def _nodes(self, doc):
        return {n["name"]: n for n in doc["nodes"]}

    def test_child_bone_sits_on_the_hinge(self, simple_material, tmp_path):
        # Hinge deliberately away from BOTH body origins (base at 0,
        # arm at z=0.5, hinge at z=0.2).
        model = self._model(simple_material, tmp_path, (0.0, 0.0, 0.2))
        out = tmp_path / "m.glb"
        GLTFWriter(y_up=False).write(model, out)

        nodes = self._nodes(_parse_glb(out.read_bytes()))
        # base is the root, so it keeps its own origin
        np.testing.assert_allclose(
            nodes["base"]["translation"], [0, 0, 0], atol=1e-9
        )
        # arm's bone moves to the hinge, NOT to the arm's own origin
        np.testing.assert_allclose(
            nodes["arm"]["translation"], [0, 0, 0.2], atol=1e-9
        )

    def test_rest_pose_unaffected_by_bone_move(
        self, simple_material, tmp_path
    ):
        """Moving the bone must not move the geometry."""
        at_origin = self._model(simple_material, tmp_path, None)
        at_hinge = self._model(simple_material, tmp_path, (0.0, 0.0, 0.2))

        def arm_bounds(model, path):
            GLTFWriter(y_up=False).write(model, path)
            doc = _parse_glb(path.read_bytes())
            node = self._nodes(doc)["arm"]
            prim = doc["meshes"][node["mesh"]]["primitives"][0]
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            return np.array(acc["min"]), np.array(acc["max"])

        a_min, a_max = arm_bounds(at_origin, tmp_path / "a.glb")
        b_min, b_max = arm_bounds(at_hinge, tmp_path / "b.glb")
        np.testing.assert_allclose(a_min, b_min, atol=1e-9)
        np.testing.assert_allclose(a_max, b_max, atol=1e-9)
        # ...and the arm is still centred on its own world position
        np.testing.assert_allclose(
            (b_min + b_max) / 2, [0, 0, 0.5], atol=1e-6
        )

    def test_falls_back_to_body_origin_without_a_pivot(
        self, simple_material, tmp_path
    ):
        model = self._model(simple_material, tmp_path, None)
        out = tmp_path / "m.glb"
        GLTFWriter(y_up=False).write(model, out)
        nodes = self._nodes(_parse_glb(out.read_bytes()))
        np.testing.assert_allclose(
            nodes["arm"]["translation"], [0, 0, 0.5], atol=1e-9
        )

    def test_bone_z_aligns_with_hinge_axis(self, simple_material, tmp_path):
        """Every jointed bone puts its local +Z on the hinge.

        Without this the hinge lands on whichever local axis the CAD part
        frame happens to give it — roll on one link, pitch on the next — and
        a consumer cannot drive the rig uniformly, because glTF has no
        joint-axis field to consult.
        """
        import cadquery as cq
        from inventor_exporter.model.constraint import ConstraintInfo

        step = tmp_path / "p.step"
        cq.exporters.export(
            cq.Workplane("XY").box(20, 20, 20), str(step), exportType="STEP"
        )
        # Three links, three hinges deliberately on three different world axes
        axes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        bodies = [Body(name="l0", transform=Transform(), geometry_file=step)]
        constraints = []
        for i, ax in enumerate(axes, start=1):
            bodies.append(
                Body(
                    name=f"l{i}",
                    transform=Transform(position=np.array([0.0, 0.0, 0.1 * i])),
                    geometry_file=step,
                )
            )
            constraints.append(
                ConstraintInfo(
                    type="rotational_joint",
                    occurrence_one=f"l{i}",
                    occurrence_two=f"l{i-1}",
                    name=f"J{i}",
                    axis=ax,
                    origin_world=(0.0, 0.0, 0.1 * i),
                )
            )
        model = AssemblyModel(
            name="Chain",
            bodies=tuple(bodies),
            materials=(simple_material,),
            constraints=tuple(constraints),
            ground_body="l0",
        )

        out = tmp_path / "m.glb"
        GLTFWriter(y_up=False).write(model, out)
        doc = _parse_glb(out.read_bytes())
        nodes = {n["name"]: n for n in doc["nodes"]}

        def rot(q):
            x, y, z, w = q
            return np.array([
                [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
            ])

        # Bones nest, and parents now carry rotations, so compose to world
        world = {}

        def walk(i, R):
            n = doc["nodes"][i]
            Rw = R @ (rot(n["rotation"]) if "rotation" in n else np.eye(3))
            world[n.get("name")] = Rw
            for c in n.get("children", []):
                walk(c, Rw)

        for r in doc["scenes"][0]["nodes"]:
            walk(r, np.eye(3))

        for i, ax in enumerate(axes, start=1):
            R = world[f"l{i}"]
            np.testing.assert_allclose(R @ [0, 0, 1], ax, atol=1e-9)
            # basis stays right-handed and orthonormal
            np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-9)
            assert np.linalg.det(R) > 0

        assert doc["extras"]["conventions"]["bone_rotation_axis"] == [0, 0, 1]
