"""DA-01: Frame-independent, creator-authored OpenUSD camera shot timeline.

A shot means "observe this existing 3D world through this camera at
these exact Film Time ticks." It never copies performances, makes frames,
renders proxies, pre-mixes sound or creates a Digital Take on its own.
Finite authoring patches publish immutable revisioned TemporalLedger
camera events and use its compare-and-swap checks. Gaps are intentional.
"""
from __future__ import annotations

import re

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import MAX_CHECKPOINTS
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND,MAX_TICK,_int
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK

FORMAT="nvp.exact_time.usd_camera_shots.v1"
PATTERNS=frozenset(("master","single","two_shot","over_shoulder",
                    "reaction","insert","tracking","continuous"))
MAX_SHOTS=128
DECIMAL=re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
MAX_SOURCE_TICK=min(MAX_TICK,MAX_USD_EXACT_TICK)

def _tick(value,name,*,minimum=0,maximum=MAX_SOURCE_TICK):
    # JSON numbers in JS lose precision beyond 2**53. Film ticks cross
    # the interface exclusively as canonical base-10 strings.
    if type(value) is not str or not DECIMAL.fullmatch(value):
        raise ValueError(name+" must be canonical decimal Film Time ticks")
    n=int(value)
    return _int(n,name,minimum=minimum,maximum=maximum)


class ExactTimeShotSequence:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("DA-01 requires the actual FilmIndex")
        self.index=index
        self.timeline=TemporalLedger(index)
        self.scene=OpenUSDSceneBridge(index)

    def _scene(self,project_id,scene_id,revision):
        _require_pid(project_id)
        _id(scene_id,"authored OpenUSD scene")
        _int(revision,"source scene revision",minimum=1)
        source,stage=self.scene.open(project_id,scene_id,revision)
        if source["kind"]!="scene" or source["data"].get("prim_roles") is None:
            raise RuntimeError("Source is not a typed authored OpenUSD scene")
        cameras={p for p,role in source["data"]["prim_roles"].items()
                 if role=="camera"}
        if not cameras:
            raise ValueError("Native scene contains no authored camera")
        return source,cameras

    def publish(self,project_id,timeline_id,*,scene_id,scene_revision,
                duration_tick,shots,expected_revision=0):
        _require_pid(project_id)
        _id(timeline_id,"exact Film Time shot timeline")
        if timeline_id==scene_id:
            raise ValueError("A scene and its temporal timeline need distinct IDs")
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError("Invalid existing timeline revision")
        duration=_tick(duration_tick,"authored sequence end",minimum=1)
        if type(shots) is not list or not 1<=len(shots)<=MAX_SHOTS:
            raise ValueError("Author one to 128 exact Film Time shot observations")
        source,cameras=self._scene(project_id,scene_id,scene_revision)
        if expected_revision:
            original=self.read(project_id,timeline_id,expected_revision)
            if (original["scene_id"]!=scene_id or
                original["scene_revision"]!=scene_revision or
                original["scene_document_sha256"]!=source["document_sha256"]):
                raise RuntimeError("Cannot silently rebind old shots to another 3D scene")
        events=[]
        prev_end=0
        seen=set()
        for shot in shots:
            if type(shot) is not dict or set(shot)!={
                "shot_id","camera_path","start_tick","end_tick","pattern"
            }:
                raise ValueError("A shot requires exact typed camera, pattern and ticks")
            name=_id(shot["shot_id"],"shot ID")
            if name in seen:
                raise ValueError("A creator shot ID cannot be reused")
            seen.add(name)
            camera=shot["camera_path"]
            if camera not in cameras:
                raise ValueError("Shot references a camera not present in frozen source scene")
            pattern=shot["pattern"]
            if pattern not in PATTERNS:
                raise ValueError("Invalid creator shot observation pattern")
            start=_tick(shot["start_tick"],"shot start")
            end=_tick(shot["end_tick"],"shot end",minimum=1)
            if start<prev_end or end<=start or end>duration:
                raise ValueError("Shot times must be monotonic with positive duration; gaps allowed")
            prev_end=end
            events.append({
                "event_id":name,"event_kind":"camera","subject_id":"Camera",
                "start_tick":start,"end_tick":end,
                "source_id":scene_id,"source_revision":scene_revision,
                "payload":{"format":FORMAT,"usd_prim_path":camera,
                           "observation_pattern":pattern,
                           "world_duplicated":False,
                           "picture_frames_recorded":False},
            })
        # FilmIndex publication and complete SHA-based source verification
        # are transactional in TemporalLedger; no float rate is involved.
        record=self.timeline.publish(project_id,timeline_id,events,
            duration_tick=duration,expected_revision=expected_revision)
        return self.read(project_id,timeline_id,record["revision"])

    def read(self,project_id,timeline_id,revision):
        _require_pid(project_id)
        _id(timeline_id,"exact shot timeline")
        _int(revision,"timeline revision",minimum=1)
        record=self.index.read_revision(project_id,timeline_id,revision)
        doc=record["data"]
        if (record["kind"]!="temporal" or
            doc.get("authority")!="authored_action_time_not_output_frames" or
            doc.get("ticks_per_second")!=TICKS_PER_SECOND or
            type(doc.get("event_count")) is not int or
            not 1<=doc["event_count"]<=MAX_SHOTS):
            raise RuntimeError("Not a supported exact-time shot timeline")
        page=self.timeline.events_in(project_id,timeline_id,revision,
            start_tick=0,end_tick=doc["duration_tick"],limit=MAX_SHOTS+1)
        entries=page["events"]
        if page["next_cursor"] is not None or len(entries)!=doc["event_count"]:
            raise RuntimeError("Partial camera timeline has been refused")
        first=entries[0]
        sid=first["source_id"];srev=first["source_revision"]
        source,cameras=self._scene(project_id,sid,srev)
        last=0
        shots=[]
        for ev in entries:
            data=ev["payload"]
            if (ev["event_kind"]!="camera" or ev["subject_id"]!="Camera" or
                ev["source_id"]!=sid or
                ev["source_revision"]!=srev or
                ev["source_document_sha256"]!=source["document_sha256"] or
                data.get("format")!=FORMAT or
                data.get("observation_pattern") not in PATTERNS or
                data.get("usd_prim_path") not in cameras or
                data.get("world_duplicated") is not False or
                data.get("picture_frames_recorded") is not False or
                ev["start_tick"]<last or ev["end_tick"]<=ev["start_tick"] or
                ev["end_tick"]>doc["duration_tick"]):
                raise RuntimeError("Old frame-scoped/cross-scene timeline is not native")
            last=ev["end_tick"]
            shots.append({
                "shot_id":ev["event_id"],
                "camera_path":data["usd_prim_path"],
                "pattern":data["observation_pattern"],
                "start_tick":str(ev["start_tick"]),
                "end_tick":str(ev["end_tick"]),
                "gap_before_tick":str(ev["start_tick"]-(
                    shots[-1]["_end_numeric"] if shots else 0)),
                "_end_numeric":ev["end_tick"],
            })
        for row in shots:
            row.pop("_end_numeric",None)
        self.timeline.verify(project_id,timeline_id,revision)
        return {"format":FORMAT,
                "status":"SAVED_EXACT_FILM_TIME_SHOTS",
                "project_id":project_id,
                "timeline_id":timeline_id,
                "revision":revision,
                "document_sha256":record["document_sha256"],
                "scene_id":sid,
                "scene_revision":srev,
                "scene_document_sha256":source["document_sha256"],
                "duration_tick":str(doc["duration_tick"]),
                "ticks_per_second":TICKS_PER_SECOND,
                "shots":shots,"source_modified":False,
                "video_frames_created":False,
                "soundtrack_flattened":False,
                "digital_take_frozen":False}

    def checkpoints(self,project_id,timeline_id,revision):
        plan=self.read(project_id,timeline_id,revision)
        points={0}
        for shot in plan["shots"]:
            a=int(shot["start_tick"])
            b=int(shot["end_tick"])
            if a<int(plan["duration_tick"]):points.add(a)
            if b<int(plan["duration_tick"]):points.add(b)
        return sorted(points)[:MAX_CHECKPOINTS]
