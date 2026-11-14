"""P1-F: finite, source-bound full-body rest axes and measured sole/terrain audit.

An authored role map and an actual GLB transform hierarchy are required.
This is reviewable geometry evidence, NOT motion capture, skin deformation,
a Blender execution receipt, license clearance or private-worker authority.
No heuristic joint-name inference or Blender/script/file resolver is used.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import struct

ROLES = (
    "hips", "spine", "head",
    "upper_arm_l", "upper_arm_r",
    "thigh_l", "shin_l", "foot_l",
    "thigh_r", "shin_r", "foot_r",
)
PARENTS = {
    "spine": "hips", "head": "spine",
    "upper_arm_l": "spine", "upper_arm_r": "spine",
    "thigh_l": "hips", "shin_l": "thigh_l", "foot_l": "shin_l",
    "thigh_r": "hips", "shin_r": "thigh_r", "foot_r": "shin_r",
}
# Audit target axes are documented frame conventions, not guessed rig roles.
AXES = {
    "spine": (0., 0., 1.), "head": (0., 0., 1.),
    "upper_arm_l": (-1., 0., 0.), "upper_arm_r": (1., 0., 0.),
    "thigh_l": (-.15, 0., -1.), "thigh_r": (.15, 0., -1.),
    "shin_l": (0., 0., -1.), "shin_r": (0., 0., -1.),
    "foot_l": (0., -1., 0.), "foot_r": (0., -1., 0.),
}
MAX_NODES = 512
MAX_CONTACT_FRAMES = 2400


def _vec(v, name, bound=1_000_000.):
    if (type(v) not in (list, tuple) or len(v) != 3 or
            any(type(x) not in (float, int) or not math.isfinite(x) or
                abs(x) > bound for x in v)):
        raise ValueError("Invalid finite 3D " + name)
    return tuple(float(x) for x in v)


def _norm(v):
    return math.sqrt(sum(x*x for x in v))


def _unit(v):
    n = _norm(v)
    if n < 1e-8:
        raise ValueError("Degenerate joint axis / ground normal")
    return tuple(x/n for x in v)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _axis_correction(src, target):
    """Shortest-arc unit quaternion (w,x,y,z), stable at 180 degrees."""
    a, b = _unit(src), _unit(target)
    scalar = _dot(a, b)
    if scalar < -0.999999:
        base = (1., 0., 0.) if abs(a[0]) < .9 else (0., 1., 0.)
        c = _unit(_cross(a, base))
        return [0., *c]
    c = _cross(a, b)
    return [round(x, 10) for x in _unit4((1. + scalar, *c))]


def _unit4(v):
    n = math.sqrt(sum(x*x for x in v))
    if n < 1e-10:
        raise ValueError("Invalid rest-pose quaternion")
    return tuple(x/n for x in v)


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4))
             for c in range(4)] for r in range(4)]


def _trs(node):
    if "matrix" in node:
        if any(k in node for k in ("translation", "rotation", "scale")):
            raise ValueError("Conflicting original glTF transform declarations")
        a = node["matrix"]
        if (type(a) is not list or len(a) != 16 or
                any(type(v) not in (float, int) or not math.isfinite(v)
                    for v in a)):
            raise ValueError("Malformed rest matrix")
        m = [[float(a[4*c+r]) for c in range(4)] for r in range(4)]
    else:
        t = _vec(node.get("translation", [0, 0, 0]), "node translation")
        s = _vec(node.get("scale", [1, 1, 1]), "node scale", 1000.)
        q = node.get("rotation", [0., 0., 0., 1.])
        if (type(q) is not list or len(q) != 4 or
                any(type(v) not in (float, int) or not math.isfinite(v)
                    for v in q)):
            raise ValueError("Malformed rest quaternion")
        if abs(_norm(q) - 1.) > .002:
            raise ValueError("Unnormalized glTF rest quaternion")
        x, y, z, w = (float(v) for v in q)
        m = [
            [(1-2*(y*y+z*z))*s[0], 2*(x*y-z*w)*s[1], 2*(x*z+y*w)*s[2], t[0]],
            [2*(x*y+z*w)*s[0], (1-2*(x*x+z*z))*s[1], 2*(y*z-x*w)*s[2], t[1]],
            [2*(x*z-y*w)*s[0], 2*(y*z+x*w)*s[1], (1-2*(x*x+y*y))*s[2], t[2]],
            [0., 0., 0., 1.],
        ]
    if (any(abs(m[3][j] - [0., 0., 0., 1.][j]) > 1e-6
            for j in range(4)) or
            any(not math.isfinite(v) or abs(v) > 1_000_000
                for row in m for v in row)):
        raise ValueError("Rest transform is non-affine or nonfinite")
    cols = [tuple(m[r][i] for r in range(3)) for i in range(3)]
    lens = [_norm(c) for c in cols]
    if (min(lens) < .00001 or max(lens) > 1000 or
            abs(_dot(_cross(cols[0], cols[1]), cols[2])) < 1e-7):
        raise ValueError("Degenerate/mirrored rest transform determinant")
    # Negative determinants are rejected explicitly: handedness must be
    # a reviewed conversion, never silently inverted at render time.
    if _dot(_cross(cols[0], cols[1]), cols[2]) <= 0:
        raise ValueError("Mirrored bone rest pose requires explicit re-authoring")
    return m


def _glb_doc(payload):
    if (type(payload) is not bytes or len(payload) < 28 or
            payload[:4] != b"glTF" or
            struct.unpack_from("<II", payload, 4) != (2, len(payload))):
        raise ValueError("Full-body rest audit requires original immutable GLB 2.0")
    jlen, jkind = struct.unpack_from("<II", payload, 12)
    if jkind != 0x4E4F534A or jlen > 8_000_000 or 20 + jlen + 8 > len(payload):
        raise ValueError("Invalid bounded original GLB JSON")
    doc = json.loads(payload[20:20+jlen].decode("utf8").strip("\x00 "))
    if type(doc) is not dict or type(doc.get("nodes")) is not list:
        raise ValueError("Missing GLB skeleton nodes")
    return doc


def audit_full_body_rest_pose(payload, mapping, *, meters_per_source_unit=1.):
    """Audit actual authored joint hierarchy and compute per-bone axis corrections.

    A complete 11-role mapping is compulsory. The returned corrections are
    mathematical proposals; the compositor must still compare USD rest axes,
    apply its own approved source-timed pose, and measure mesh deformation.
    """
    from backend.nvp_character_assets import inspect_rigged_glb
    source = inspect_rigged_glb(payload)
    if (type(mapping) is not dict or set(mapping) != set(ROLES) or
            set(mapping.values()) - set(source["joint_names"]) or
            len(set(mapping.values())) != len(ROLES)):
        raise ValueError("Explicit unique complete full-body role mapping required")
    if (type(meters_per_source_unit) not in (int, float) or
            not math.isfinite(meters_per_source_unit) or
            not .001 <= meters_per_source_unit <= 100):
        raise ValueError("Reviewed source-unit calibration required")
    doc = _glb_doc(payload)
    nodes = doc["nodes"]
    if len(nodes) > MAX_NODES:
        raise ValueError("GLB hierarchy budget exceeded")
    skin = doc["skins"][0]
    by_name = {nodes[i]["name"]: i for i in skin["joints"]}
    parent = {}
    for i, node in enumerate(nodes):
        children = node.get("children", [])
        if type(children) is not list or len(children) != len(set(children)):
            raise ValueError("Invalid or duplicate skeleton descendants")
        for child in children:
            if (type(child) is not int or not 0 <= child < len(nodes) or
                    child == i or child in parent):
                raise ValueError("Cyclic, multiple-parent or invalid GLB hierarchy")
            parent[child] = i
    world = {}
    active = set()
    def resolve(i):
        if i in active:
            raise ValueError("Cyclic glTF rest hierarchy")
        if i not in world:
            active.add(i)
            local = _trs(nodes[i])
            world[i] = _mul(resolve(parent[i]), local) if i in parent else local
            active.remove(i)
        return world[i]
    for idx in range(len(nodes)):
        resolve(idx)
    # The hierarchy alone is not enough: independently decode the actual
    # inverse-bind floats and prove rest-pose skin matrices reconstruct the
    # authored mesh bind frame. This is more stringent than structural glTF.
    ibm_id = skin.get("inverseBindMatrices")
    accessors = doc.get("accessors", [])
    views = doc.get("bufferViews", [])
    if type(ibm_id) is not int or not 0 <= ibm_id < len(accessors):
        raise ValueError("Full-body skeletal rest proof requires explicit inverse binds")
    a = accessors[ibm_id]
    if (a.get("type") != "MAT4" or a.get("componentType") != 5126 or
            a.get("count") != len(skin["joints"])):
        raise ValueError("Original inverse bind matrix array differs from joints")
    v = views[a["bufferView"]]
    raw_start = 20 + struct.unpack_from("<I", payload, 12)[0] + 8
    data_offset = raw_start + v.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = v.get("byteStride", 64)
    if (stride < 64 or data_offset < raw_start or
            data_offset + (len(skin["joints"])-1)*stride+64 > len(payload)):
        raise ValueError("Inverse bind matrices escape original GLB binary")
    ibms = []
    for ordinal in range(len(skin["joints"])):
        flat = struct.unpack_from("<16f", payload, data_offset + ordinal*stride)
        if any(not math.isfinite(x) or abs(x) > 1e6 for x in flat):
            raise ValueError("Nonfinite original inverse bind rest matrix")
        ibms.append([[float(flat[4*c+r]) for c in range(4)] for r in range(4)])
    mesh_nodes = [i for i,n in enumerate(nodes) if n.get("skin") == 0]
    if not mesh_nodes:
        raise ValueError("No original full-body skin mesh node")
    mesh_world = world[mesh_nodes[0]]
    if any(any(abs(world[n][r][c]-mesh_world[r][c]) > .001
               for r in range(4) for c in range(4)) for n in mesh_nodes):
        raise ValueError("Multiple skinned meshes use different unreviewed bind spaces")
    if any(any(abs(rest[r][c]-mesh_world[r][c]) > .001
               for r in range(4) for c in range(4))
           for i,j in enumerate(skin["joints"])
           for rest in [_mul(world[j], ibms[i])]):
        raise ValueError("Inverse binds do not restore full-body mesh rest pose")
    # glTF is Y-up, while NVP's authoritative film geometry is Z-up.
    # Rotate +90 degrees around X: (x,y,z) -> (x,-z,y). Never
    # interpret native glTF-Y positions as source-stage-Z positions.
    def to_stage(joint):
        x, y, z = (world[joint][i][3] * meters_per_source_unit
                   for i in range(3))
        return (x, -z, y)
    positions = {role: to_stage(by_name[mapping[role]]) for role in ROLES}
    axes = {}
    for role, ancestor in PARENTS.items():
        child = by_name[mapping[role]]
        p = by_name[mapping[ancestor]]
        node = child
        while node in parent and node != p:
            node = parent[node]
        if node != p:
            raise ValueError("Mapped full-body bones violate reviewed anatomy hierarchy")
        vec = tuple(positions[role][i]-positions[ancestor][i] for i in range(3))
        length = _norm(vec)
        if not .015 <= length <= 3.:
            raise ValueError("Full-body bone rest length is zero or implausible")
        axes[role] = {
            "source_direction": [round(x, 8) for x in _unit(vec)],
            "bone_length_m": round(length, 8),
            "correction_wxyz": _axis_correction(vec, AXES[role]),
        }
    if positions["foot_l"][0] >= positions["foot_r"][0]:
        raise ValueError("Full-body left/right signed source axes crossed or ambiguous")
    return {
        "format": "nvp.p1f.full_body_rest_axes_audit.v1",
        "glb_sha256": sha256(payload).hexdigest(),
        "role_to_joint": {r: mapping[r] for r in ROLES},
        "meters_per_source_unit": float(meters_per_source_unit),
        "source_to_stage_axes": "glTF_Yup_to_OpenUSD_Zup_(x,-z,y)",
        "source_joint_positions_m": {r: list(positions[r]) for r in ROLES},
        "axis_corrections": axes,
        "glb_inverse_bind_rest_verified": True,
        "usd_rest_pose_equivalence_verified": False,
        "full_body_deformation_verified": False,
        "ground_contact_verified": False,
        "rendered_performance_verified": False,
    }


def audit_measured_foot_contact(samples, *, ground_source_sha256,
                                max_penetration_m=.008,
                                max_stance_height_m=.025,
                                max_stance_sliding_m=.035):
    """Check finite, observed sole and ground points; NOT an observation source.

    samples must be a sequential list of actual independent measurements:
    {frame, feet:{left/right:{sole:[x,y,z], ground:[x,y,z],
                             normal:[x,y,z], stance:bool}}}.
    Z is source stage up. A trusted renderer must attest the measurements
    and exact actor/camera/Take SHA separately before promoting acceptance.
    """
    if (type(ground_source_sha256) is not str or
            len(ground_source_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in ground_source_sha256)):
        raise ValueError("Original terrain geometry SHA256 required")
    limits = [max_penetration_m, max_stance_height_m, max_stance_sliding_m]
    if any(type(x) not in (int, float) or not math.isfinite(x) or
           not 0.0001 <= x <= .25 for x in limits):
        raise ValueError("Bounded director-approved foot contact tolerances required")
    if type(samples) is not list or not 2 <= len(samples) <= MAX_CONTACT_FRAMES:
        raise ValueError("Actual bounded sequential foot samples required")
    seen = {"left": 0, "right": 0}
    max_slide = 0.
    max_clearance = 0.
    max_penetration = 0.
    anchor = {"left": None, "right": None}
    start = None
    for offset, sample in enumerate(samples):
        if type(sample) is not dict or set(sample) != {"frame", "feet"}:
            raise ValueError("Unexpected unreviewed terrain measurement data")
        frame = sample["frame"]
        if type(frame) is not int:
            raise ValueError("Foot measurement frame must be integer")
        if start is None:
            start = frame
        if frame != start + offset:
            raise ValueError("Foot samples are gapped, duplicated or out of order")
        feet = sample["feet"]
        if type(feet) is not dict or set(feet) != {"left", "right"}:
            raise ValueError("Both actor sole contacts required per original frame")
        for side in ("left", "right"):
            f = feet[side]
            if type(f) is not dict or set(f) != {
                    "sole", "ground", "normal", "stance"} or type(f["stance"]) is not bool:
                raise ValueError("Incomplete observed sole/terrain witness")
            foot = _vec(f["sole"], "sole position")
            ground = _vec(f["ground"], "reviewed terrain point")
            normal = _vec(f["normal"], "terrain normal")
            if abs(_norm(normal) - 1.) > .002 or normal[2] < .25:
                raise ValueError("Invalid or downward ground normal / steep slope")
            # Signed point-plane gap, not world-Z: slopes are supported.
            gap = _dot(tuple(foot[i]-ground[i] for i in range(3)), normal)
            max_penetration = max(max_penetration, -gap)
            if gap < -max_penetration_m:
                raise ValueError("Original actor shoe penetrates reviewed terrain")
            if f["stance"]:
                seen[side] += 1
                max_clearance = max(max_clearance, abs(gap))
                if abs(gap) > max_stance_height_m:
                    raise ValueError("Stance foot hovers above reviewed terrain")
                if anchor[side] is None:
                    anchor[side] = foot
                dx = tuple(foot[i]-anchor[side][i] for i in range(3))
                tangent = tuple(dx[i]-_dot(dx, normal)*normal[i] for i in range(3))
                slide = _norm(tangent)
                max_slide = max(max_slide, slide)
                if slide > max_stance_sliding_m:
                    raise ValueError("Source foot slides during pinned stance window")
            else:
                anchor[side] = None
    if any(v < 2 for v in seen.values()):
        raise ValueError("Full-body contact audit requires two measured stance frames per foot")
    return {
        "format": "nvp.p1f.measured_sole_terrain_contact.v1",
        "ground_source_sha256": ground_source_sha256,
        "first_frame": start, "last_frame": start + len(samples)-1,
        "sample_count": len(samples), "stance_frames": seen,
        "max_stance_sliding_m": round(max_slide, 9),
        "max_stance_clearance_m": round(max_clearance, 9),
        "max_ground_penetration_m": round(max_penetration, 9),
        "numeric_contact_contract_passed": True,
        "blender_evaluated_mesh_verified": False,
        "independent_sample_provenance_verified": False,
        "private_worker_authorized": False,
    }
