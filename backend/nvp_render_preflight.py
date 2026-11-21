"""NVP STACK-02C3B6: read-only, project-bound Blender source preflight.

This is an exact source preview for a director-approved *proxy* world, not a
human approval, an executable job, a Digital Take Package, or a model render.
It never launches Blender, issues native permissions, or claims GPU budget.
The host must revalidate the exact source and authorization before execution.
"""
from __future__ import annotations

import hashlib

from backend.nvp_production_scene import compact, blender_script
from backend.nvp_studio import Studio
from backend.nvp_world_state import WorldState

FORMAT="nvp.production.proxy_render_preflight.v1"


def _sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def _capture(studio:Studio,project_id:str,scene_id:str):
    if not isinstance(studio,Studio):
        raise TypeError("NVP Studio is required")
    if not isinstance(project_id,str) or not isinstance(scene_id,str):
        raise ValueError("Project and scene IDs required")

    project=studio.get_project(project_id)
    if not any(scene["id"]==scene_id for scene in project["scenes"]):
        raise KeyError("Scene is not in this project")
    world=WorldState(studio).read(project_id,scene_id)
    if world["stale"] or "manifest" not in world:
        raise RuntimeError("World changed; explicitly review/rebase the scene before render preflight")

    manifest=world["manifest"]
    if manifest.get("project_id")!=project_id or manifest.get("scene_id")!=scene_id:
        raise RuntimeError("Approved world belongs to a different project or scene")
    if manifest.get("format")!="nvp.production.proxy.v1":
        raise RuntimeError("Unexpected approved world format")
    if not isinstance(world["revision"],int) or type(world["revision"]) is bool:
        raise RuntimeError("Invalid production world revision")
    if not isinstance(project["revision"],int) or type(project["revision"]) is bool:
        raise RuntimeError("Invalid screenplay revision")
    source=compact(manifest).encode("utf8")
    script=blender_script(manifest).encode("utf8")
    if not script or len(script)>8*1024*1024 or len(source)>4*1024*1024:
        raise RuntimeError("Unbounded Blender source; preflight refused")
    return {
        "project_revision":project["revision"],
        "world_revision":world["revision"],
        "world_base_plan_revision":world["base_plan_revision"],
        "layout_sha256":manifest["layout_sha256"],
        "world_sha256":_sha(source),
        "script_sha256":_sha(script),
        "world_bytes":len(source),
        "script_bytes":len(script),
        "source":source,
        "script":script,
        "instance_count":len(manifest["instances"]),
        "has_editable_fields":bool(world["fields"]),
    }


def preflight_scene(studio:Studio,project_id:str,scene_id:str):
    """Capture twice to detect races; return no executable/path or grant."""
    first=_capture(studio,project_id,scene_id)
    second=_capture(studio,project_id,scene_id)
    for field in ("project_revision","world_revision","world_base_plan_revision",
                  "layout_sha256","world_sha256","script_sha256"):
        if first[field]!=second[field]:
            raise RuntimeError("Project/world was modified during preflight; retry after review")
    return {
        "format":FORMAT,
        "project_id":project_id,
        "scene_id":scene_id,
        "project_revision":first["project_revision"],
        "world_revision":first["world_revision"],
        "world_base_plan_revision":first["world_base_plan_revision"],
        "approved_layout_sha256":first["layout_sha256"],
        "world_sha256":first["world_sha256"],
        "blender_script_sha256":first["script_sha256"],
        "world_bytes":first["world_bytes"],
        "script_bytes":first["script_bytes"],
        "instance_count":first["instance_count"],
        "has_editable_fields":first["has_editable_fields"],
        "source_kind":"director_approved_proxy_world_only",
        "output_kind":"none_preflight_only",
        "execution":"not_started",
        "native_approval":"not_granted",
        "resource_admission":"not_checked",
        "limitations":[
            "Preflight is a read-only source snapshot, not permission to launch Blender",
            "Only procedural scene proxies are covered; no finished Digital Take Package",
            "No OS or GPU memory budget was measured by this source check",
        ]
    }


def verify_scene_preflight(studio:Studio,proof:dict)->bool:
    """Fail closed when source, project, scene, plan, script or revision changes.

    Even a successful result is NOT a creator approval. Native dispatch must
    recheck using its own host-held approval/effect and resource-admission rules.
    """
    if not isinstance(proof,dict) or proof.get("format")!=FORMAT:
        raise ValueError("Unknown NVP render source proof format")
    required={"project_id","scene_id","project_revision","world_revision",
              "world_base_plan_revision","approved_layout_sha256",
              "world_sha256","blender_script_sha256"}
    if not required.issubset(proof):
        raise ValueError("Incomplete NVP render source proof")
    current=preflight_scene(studio,proof["project_id"],proof["scene_id"])
    # Compare the complete immutable preview, including limitations,
    # explicit non-authority and byte/object counts. Never allow a caller to
    # flip native_approval or execution state within a self-described proof.
    if current != proof:
        raise RuntimeError("Production source changed or preflight evidence was altered")
    return True
