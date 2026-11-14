"""P1-F Step 2: strict decoded geometry/skin audit for approved local GLB.

Legacy PROD-06C's structural glTF inspection guarantees bounded accessors,
but does not verify actual decoded positions and per-vertex joint weights.
This verifier reads the binary and rejects NaN/Inf, invalid joint indices,
un-normalized skinning, unsupported primitive modes, and malformed UVs.
It does not attempt Blender import, actual mesh deformation, or license review.
"""
from __future__ import annotations

import json
import math
import struct

_MAX_VERTICES = 250_000
_COMPONENT = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_ELEMENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _read_accessor(doc, binary, index, expected, components):
    accessors = doc["accessors"]
    views = doc["bufferViews"]
    if type(index) is not int or not 0 <= index < len(accessors):
        raise ValueError("Original GLB attribute accessor index invalid")
    a = accessors[index]
    component = a.get("componentType")
    shape = a.get("type")
    if component not in components or shape != expected:
        raise ValueError("GLB attribute type differs from reviewed skin contract")
    fmt, unit = _COMPONENT[component]
    n = _ELEMENTS[shape]
    width = unit * n
    if (type(a.get("count")) is not int or
            not 1 <= a["count"] <= _MAX_VERTICES * 4 or
            type(a.get("bufferView")) is not int or
            not 0 <= a["bufferView"] < len(views)):
        raise ValueError("Original GLB attribute count or buffer view invalid")
    view = views[a["bufferView"]]
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", width)
    end = view.get("byteOffset", 0) + view["byteLength"]
    if (not isinstance(start, int) or not isinstance(stride, int) or
            stride < width or start < 0 or
            start + (a["count"] - 1) * stride + width > min(len(binary), end)):
        raise ValueError("Decoded GLB vertex attribute escaped bounded binary view")
    unpack = struct.Struct("<" + fmt * n)
    values = [unpack.unpack_from(binary, start + i * stride)
              for i in range(a["count"])]
    return a, values


def audit_glb_skinned_mesh(payload, info):
    if type(payload) is not bytes or payload[:4] != b"glTF" or type(info) is not dict:
        raise ValueError("Only already-validated original GLB bytes are admissible")
    pos = 12
    jlen, jtype = struct.unpack_from("<II", payload, pos)
    pos += 8
    if jtype != 0x4E4F534A:
        raise ValueError("Original GLB JSON chunk missing")
    doc = json.loads(payload[pos:pos+jlen].rstrip(b" \x00").decode("utf8"))
    pos += jlen
    blen, btype = struct.unpack_from("<II", payload, pos)
    pos += 8
    if btype != 0x004E4942 or pos + blen != len(payload):
        raise ValueError("Original GLB BIN chunk is incomplete")
    raw = payload[pos:pos+blen]
    joints = doc["skins"][0]["joints"]
    count = 0
    triangles = 0
    uv_sets = 0
    normals_present = 0
    weight_max_error = 0.0
    bounds_min = [float("inf")] * 3
    bounds_max = [float("-inf")] * 3
    for node in doc["nodes"]:
        if node.get("skin") != 0:
            continue
        mesh = doc["meshes"][node["mesh"]]
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4:
                raise ValueError("Only independently audited triangle skin geometry allowed")
            attrs = primitive["attributes"]
            pa, positions = _read_accessor(
                doc, raw, attrs["POSITION"], "VEC3", {5126})
            ja, joint_values = _read_accessor(
                doc, raw, attrs["JOINTS_0"], "VEC4", {5121, 5123})
            wa, weights = _read_accessor(
                doc, raw, attrs["WEIGHTS_0"], "VEC4", {5121, 5123, 5126})
            if len(positions) != len(joint_values) or len(weights) != len(positions):
                raise ValueError("Original GLB joint/skin vertex counts disagree")
            if wa["componentType"] != 5126 and wa.get("normalized") is not True:
                raise ValueError("Integer GLB skin weights must be explicitly normalized")
            scalar = {5121: 255.0, 5123: 65535.0, 5126: 1.0}[wa["componentType"]]
            for coords, indexes, raw_weights in zip(positions, joint_values, weights):
                if any(not math.isfinite(x) or abs(x) > 1_000_000 for x in coords):
                    raise ValueError("Original GLB skinned vertex contains nonfinite coordinates")
                if any(i >= len(joints) for i in indexes):
                    raise ValueError("Original GLB vertex refers to a missing skin joint")
                actual = [float(w) / scalar for w in raw_weights]
                if any(not math.isfinite(w) or w < 0 or w > 1 for w in actual):
                    raise ValueError("Original GLB skin weights are invalid")
                error = abs(sum(actual) - 1.0)
                weight_max_error = max(weight_max_error, error)
                if error > 0.005:
                    raise ValueError("Original GLB skin weights must sum to one for each vertex")
                for axis in range(3):
                    bounds_min[axis] = min(bounds_min[axis], coords[axis])
                    bounds_max[axis] = max(bounds_max[axis], coords[axis])
            if "NORMAL" in attrs:
                _, normals = _read_accessor(doc, raw, attrs["NORMAL"], "VEC3", {5126})
                if len(normals) != len(positions) or any(
                    not math.isfinite(v) or abs(v) > 1e4
                    for n in normals for v in n
                ):
                    raise ValueError("Original GLB vertex normals invalid")
                normals_present += 1
            if "TEXCOORD_0" in attrs:
                ua, uv = _read_accessor(
                    doc, raw, attrs["TEXCOORD_0"], "VEC2", {5121, 5123, 5126})
                if (len(uv) != len(positions) or
                        (ua["componentType"] != 5126 and ua.get("normalized") is not True) or
                        any(not math.isfinite(v) or abs(v) > 1e6 for pair in uv for v in pair)):
                    raise ValueError("Original GLB PBR UV coordinates invalid")
                uv_sets += 1
            if "indices" in primitive:
                ia, indices = _read_accessor(
                    doc, raw, primitive["indices"], "SCALAR", {5121, 5123, 5125})
                values = [int(row[0]) for row in indices]
                if len(values) % 3 or any(i >= len(positions) for i in values):
                    raise ValueError("Original GLB triangle index array invalid")
                triangles += len(values) // 3
            else:
                if len(positions) % 3:
                    raise ValueError("Original GLB nonindexed triangles incomplete")
                triangles += len(positions) // 3
            count += len(positions)
    if count != info["skinned_vertices"] or count < 3:
        raise RuntimeError("Decoded original GLB vertex count differs from structural source")
    if triangles < 1 or triangles > _MAX_VERTICES * 4:
        raise ValueError("Original GLB polygon budget invalid")
    return {
        "format": "nvp.p1f.reviewed_glb_decoded_geometry.v1",
        "decoded_skinned_vertices": count,
        "decoded_triangles": triangles,
        "original_joint_count": len(joints),
        "normal_primitive_count": normals_present,
        "uv_primitive_count": uv_sets,
        "weight_max_sum_error": round(weight_max_error, 9),
        "bounds_min": [float(v) for v in bounds_min],
        "bounds_max": [float(v) for v in bounds_max],
        "actual_mesh_deformation_verified": False,
        "full_body_retarged_in_blender": False,
    }
