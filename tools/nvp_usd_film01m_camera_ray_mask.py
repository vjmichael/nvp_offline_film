"""USD-FILM-01M Blender primary-ray camera-specific occlusion adapter.

Only source-verified non-actor geometry paths are admitted by the NVP host.
An exact imported source object ancestry match is required; ambiguous names
are refused. Each edit reverts after one camera render. Walls are NOT deleted
from world/other camera views, lights, reflections or original USD layers.
This module deliberately has no bpy import so its control path can be unit
tested without claiming native Cycles pixels.
"""
from __future__ import annotations

from contextlib import contextmanager


def _name(obj):
    name = obj.name
    # Blender collision suffix is not an original USD source identity.
    if type(name) is not str or not name:
        raise ValueError("Blender imported object name missing")
    return name.split(".")[0]


def _ancestry(obj):
    names = []
    visited = set()
    node = obj
    while node is not None:
        identity = id(node)
        if identity in visited or len(names) >= 64:
            raise RuntimeError("Source object hierarchy cyclic or too deep")
        visited.add(identity)
        names.append(_name(node))
        node = node.parent
    return list(reversed(names))


def source_geometry_roots(objects, original_prim_paths):
    """Return exact recognized imported geometry roots, fail on ambiguity."""
    objects = list(objects)
    selected = []
    for original in original_prim_paths:
        if type(original) is not str or not original.startswith("/World/"):
            raise ValueError("Only source-verified original USD prim paths")
        tokens = original.split("/")[1:]
        matches = []
        for obj in objects:
            # Importer may retain a prefix outside /World. Compare the
            # complete original path as an ending sequence of hierarchy.
            ancestry = _ancestry(obj)
            if len(ancestry) >= len(tokens) and ancestry[-len(tokens):] == tokens:
                matches.append(obj)
        if len(matches) != 1:
            raise RuntimeError("Cannot uniquely resolve original wall/occluder in Blender")
        root = matches[0]
        if root.type not in ("MESH", "EMPTY"):
            raise PermissionError("Original camera-ray exemption target is not geometry")
        selected.append(root)
    return selected


@contextmanager
def per_camera_primary_ray_exclusions(imported_objects, original_prim_paths):
    """Apply selected camera-only Cycles ray masks, then always revert."""
    roots = source_geometry_roots(imported_objects, original_prim_paths)
    touched = {}
    try:
        for root in roots:
            descendants = [root] + list(root.children_recursive)
            for obj in descendants:
                if obj.type != "MESH":
                    continue
                if not hasattr(obj, "visible_camera"):
                    raise RuntimeError("Installed Blender has no primary-ray visibility")
                identity = id(obj)
                if identity not in touched:
                    touched[identity] = (obj, bool(obj.visible_camera))
                obj.visible_camera = False
        yield {"excluded_source_prims":list(original_prim_paths),
               "masked_mesh_object_count":len(touched),
               "preserved_diffuse_glossy_shadow_visibility":True}
    finally:
        for obj, original in touched.values():
            obj.visible_camera = original
