"""P1-F source-clock bone-axis retarget mathematics, without false render authority.

Conjugates an explicitly authored motion quaternion between independently
supplied 3D rest bases for all eleven required body roles. The authoritative
FilmIndex frozen Take and target GLB must be checked by the host before calling.
A vector-only bone axis cannot define twist: full unit rest orientations are
mandatory. This is NOT a Blender-deformed mesh or original motion validation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_p1f_full_body_retarget import ROLES, _vec


def _sha(value, name):
    if (type(value) is not str or len(value) != 64 or
            any(ch not in "0123456789abcdef" for ch in value)):
        raise ValueError("Exact original " + name + " SHA256 required")
    return value


def _q(values, label):
    if (type(values) not in (list, tuple) or len(values) != 4 or
            any(type(n) not in (float, int) or not math.isfinite(n)
                for n in values)):
        raise ValueError("Four finite rest or motion quaternion components required: " + label)
    norm = math.sqrt(sum(float(n)**2 for n in values))
    if abs(norm - 1.) > .001:
        raise ValueError("Quaternions must be normalized, never silently rescaled: " + label)
    return tuple(float(n)/norm for n in values)


def _mul(a, b):
    w, x, y, z = a
    W, X, Y, Z = b
    return (w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y,
            w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W)


def _inv(q):
    return (q[0], -q[1], -q[2], -q[3])


def _roles(value, label):
    if type(value) is not dict or set(value) != set(ROLES):
        raise ValueError("Full-body " + label + " must cover all original 11 roles")
    return {role: _q(value[role], label+":"+role) for role in ROLES}


def retarget_reviewed_full_body_motion(
    glb_rest_audit, *,
    original_actor_id, original_actor_document_sha256,
    original_take_document_sha256, original_source_tick,
    source_rest_wxyz, target_rest_wxyz, source_motion_delta_wxyz,
    original_root_translation_m,
):
    """Return a non-authorized derived pose tied to exact external source SHAs.

    All quaternions are WXYZ in a *common* Z-up actor frame. Source and target
    rest orientations are supplied explicitly, not guessed from names or bone
    direction. The caller must independently establish that the source
    quaternions came from the SHA-pinned OpenUSD skeleton at this tick.
    """
    if (type(glb_rest_audit) is not dict or
            glb_rest_audit.get("format") != "nvp.p1f.full_body_rest_axes_audit.v1" or
            glb_rest_audit.get("glb_inverse_bind_rest_verified") is not True or
            set(glb_rest_audit.get("role_to_joint", {})) != set(ROLES) or
            glb_rest_audit.get("full_body_deformation_verified") is not False):
        raise ValueError("Only original complete GLB rest-axis evidence admissible")
    source_glb_sha = _sha(glb_rest_audit.get("glb_sha256"), "GLB source")
    actor_sha = _sha(original_actor_document_sha256, "ActorID USD")
    take_sha = _sha(original_take_document_sha256, "Take")
    if (type(original_actor_id) is not str or
            not original_actor_id.startswith("ACT_") or
            type(original_source_tick) is not int or
            not 0 <= original_source_tick <= 2**53-1):
        raise ValueError("Original ActorID and exact integer Film Time required")
    srest = _roles(source_rest_wxyz, "source rest orientation")
    trest = _roles(target_rest_wxyz, "GLB target rest orientation")
    deltas = _roles(source_motion_delta_wxyz, "source motion delta")
    root = _vec(original_root_translation_m, "original USD root translation")
    posed = {}
    for role in ROLES:
        # A^-1 B D B^-1 A changes the source delta's rest basis,
        # preserving original rotation angle and forbidding a name-only copy.
        align = _mul(_inv(trest[role]), srest[role])
        derived = _mul(_mul(align, deltas[role]), _inv(align))
        normalized = _q(derived, "derived retargeted delta")
        posed[role] = [round(v, 12) for v in normalized]
    source_evidence = {
        "actor_document_sha256": actor_sha,
        "source_take_document_sha256": take_sha,
        "source_tick": original_source_tick,
        "source_rest_wxyz": source_rest_wxyz,
        "target_rest_wxyz": target_rest_wxyz,
        "source_motion_delta_wxyz": source_motion_delta_wxyz,
        "original_root_translation_m": list(root),
        "glb_rest_audit": glb_rest_audit,
    }
    canonical = json.dumps(source_evidence, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("ascii")
    return {
        "format": "nvp.p1f.reviewed_bone_axis_motion_math.v1",
        "status": "MATHEMATICAL_DERIVATIVE_NOT_DEFORMED",
        "actor_id": original_actor_id, "actor_document_sha256": actor_sha,
        "source_take_document_sha256": take_sha,
        "target_glb_sha256": source_glb_sha,
        "source_tick": original_source_tick,
        "original_root_translation_m": list(root),
        "source_evidence_sha256": sha256(canonical).hexdigest(),
        "retargeted_delta_wxyz": posed,
        "original_usd_rest_and_animation_independently_verified": False,
        "original_target_glb_blender_bones_independently_verified": False,
        "actual_mesh_deformation_verified": False,
        "contact_verified": False,
        "worker_authorized": False,
    }
