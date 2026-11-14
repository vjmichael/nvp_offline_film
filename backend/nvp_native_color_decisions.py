"""DA-06 replacement for the retired frame-based color preview API.

Color decisions stay typed DATA, linked to one immutable original
OpenUSD Digital Take. Presentation (not capture) can sample these controls
on demand through a renderer; no film-frame record, EXR worker, FFmpeg,
MOV, proxy, LUT baked onto original scene or approved master is emitted.
"""
from __future__ import annotations

import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha

FORMAT="nvp.data_first.color_decision.v1"
BOUNDS={
    "exposure_stops":(-6.,6.),
    "contrast":(0.1,3.),
    "saturation":(0.,3.),
    "temperature_kelvin":(2500.,12000.),
    "tint_magenta_green":(-1.,1.),
}


def validate_parameters(parameters):
    if type(parameters) is not dict or set(parameters)!=set(BOUNDS):
        raise ValueError("Native grade requires exact five named scalar controls")
    cleaned={}
    for name,(low,high) in BOUNDS.items():
        value=parameters[name]
        if (type(value) not in (float,int) or not math.isfinite(value) or
            not low<=value<=high):
            raise ValueError("Invalid native color-control "+name)
        cleaned[name]=float(value)
    return cleaned


class NativeColorDecisions:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Native color plan requires actual FilmIndex")
        self.index=index

    def publish(self,project_id,grade_id,*,take_id,take_sha256,
                parameters,expected_revision=0):
        _require_pid(project_id)
        _id(grade_id,"color decision")
        _id(take_id,"original frozen USD take")
        if grade_id==take_id:
            raise ValueError("Color plan cannot reuse source Take ID")
        _sha(take_sha256)
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Color plan version must be an exact integer")
        take=self.index.read_revision(project_id,take_id,1)
        if (take["kind"]!="take" or
            take["data"].get("format")!="nvp.digital_take.openusd_temporal.v1" or
            take["data"].get("frozen") is not True or
            take["document_sha256"]!=take_sha256):
            raise RuntimeError("Color plan cannot reinterpret historical frame-based capture")
        if expected_revision:
            old=self.read(project_id,grade_id,expected_revision)
            if old["take_id"]!=take_id or old["take_sha256"]!=take_sha256:
                raise RuntimeError("Cannot silently rebind grade to another original Take")
        doc={
            "format":FORMAT,"take_id":take_id,
            "take_sha256":take_sha256,
            "parameters":validate_parameters(parameters),
            "scope":"derived_color_presentation_only",
            "source_3d_scene_modified":False,
            "original_sound_modified":False,
            "rendered_frames":False,
            "flat_master_approved":False,
        }
        receipt=self.index.register_revision(
            project_id,grade_id,"style",doc,
            expected_revision=expected_revision,
            dependencies=[{
                "object_id":take_id,"revision":1,"role":"source_take"
            }])
        return self.read(project_id,grade_id,receipt["revision"])

    def read(self,project_id,grade_id,revision=None):
        _require_pid(project_id)
        _id(grade_id,"native color plan")
        record=self.index.read_revision(project_id,grade_id,revision)
        doc=record["data"]
        if (record["kind"]!="style" or doc.get("format")!=FORMAT or
            doc.get("scope")!="derived_color_presentation_only" or
            doc.get("source_3d_scene_modified") is not False or
            doc.get("flat_master_approved") is not False):
            raise RuntimeError("Not a valid native source-bound color plan")
        parameters=validate_parameters(doc["parameters"])
        take=self.index.read_revision(project_id,doc["take_id"],1)
        if (take["document_sha256"]!=doc["take_sha256"] or
            record["dependencies"]!=[{
                "object_id":doc["take_id"],"revision":1,"role":"source_take"
            }]):
            raise RuntimeError("Color decision source dependency changed")
        return {
            "format":FORMAT,"status":"EDITABLE_NONDESTRUCTIVE_COLOR_PLAN",
            "grade_id":grade_id,"revision":record["revision"],
            "document_sha256":record["document_sha256"],
            "take_id":doc["take_id"],"take_sha256":doc["take_sha256"],
            "parameters":parameters,
            "source_modified":False,"rendered_frames":False,
            "flat_master_approved":False,"ffmpeg_used":False,
        }
