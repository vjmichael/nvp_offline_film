"""P1-A — immutable original microphone worker attestations linked to a Digital Take.

The trusted filming host validates these records against the bytes it itself
spooled and the exact original source event. The recorded worker receipts
are provenance, NOT stand-alone proof of physical microphone custody, a
reviewed redistributable worker, EFS key recovery or creator permission.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex

FORMAT="nvp.w1g.original_microphone_worker_audit.v1"
SHA=re.compile(r"[0-9a-f]{64}\Z")
JOB=re.compile(r"w1g_[0-9a-f]{24}\Z")
MAX_WINDOWS=128
MAX_AUDIT_BYTES=128*1024
AUDIT_FIELDS=frozenset((
    "format","project_id","take_id","source_id","scene_id",
    "scene_document_sha256","camera_timeline_document_sha256",
    "subject_id","emitter_path","start_tick","end_tick",
    "original_pcm_sha256","sample_count","window_count",
    "native_worker_receipts","all_window_results_and_os_custody_verified",
    "device_capture_implemented_by_compiled_worker",
    "immutable_take_published","physical_microphone_hardware_accepted",
))
WINDOW_FIELDS=frozenset((
    "job_id","first_sample","sample_count","window_pcm_sha256",
    "worker_result_sha256","original_native_kernel_custody_verified"
))


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def audit_sha256(value):
    return sha256(canonical(value)).hexdigest()


def validate_original_audit(audit,*,project_id,take_id,scene_id,scene_sha,
                            camera_sha,recording,source_sha,samples):
    if (type(audit) is not dict or set(audit)!=AUDIT_FIELDS or
        len(canonical(audit))>MAX_AUDIT_BYTES):
        raise PermissionError("Incomplete, oversized or extra native capture audit fields")
    if (audit["format"]!=FORMAT or audit["project_id"]!=project_id or
        audit["take_id"]!=take_id or audit["scene_id"]!=scene_id or
        audit["scene_document_sha256"]!=scene_sha or
        audit["camera_timeline_document_sha256"]!=camera_sha or
        audit["source_id"]!=recording["source_id"] or
        audit["subject_id"]!=recording["subject_id"] or
        audit["emitter_path"]!=recording["usd_prim_path"] or
        audit["start_tick"]!=str(recording["start_tick"]) or
        audit["end_tick"]!=str(recording["end_tick"]) or
        audit["original_pcm_sha256"]!=source_sha or
        audit["sample_count"]!=samples or
        audit["all_window_results_and_os_custody_verified"] is not True or
        audit["device_capture_implemented_by_compiled_worker"] is not False or
        audit["immutable_take_published"] is not False or
        audit["physical_microphone_hardware_accepted"] is not False):
        raise PermissionError("Native capture audit does not match the original Film Time/source")
    count=audit["window_count"]
    windows=audit["native_worker_receipts"]
    if (type(count) is not int or not 1<=count<=MAX_WINDOWS or
        type(windows) is not list or len(windows)!=count):
        raise PermissionError("Missing or unbounded original native capture window receipts")
    position=0
    jobs=set()
    for entry in windows:
        if (type(entry) is not dict or set(entry)!=WINDOW_FIELDS or
            type(entry["job_id"]) is not str or
            not JOB.fullmatch(entry["job_id"]) or
            type(entry["first_sample"]) is not int or
            entry["first_sample"]!=position or
            type(entry["sample_count"]) is not int or
            not 0<entry["sample_count"]<=2*1024*1024 or
            entry["original_native_kernel_custody_verified"] is not True or
            entry["job_id"] in jobs or
            any(type(entry[x]) is not str or not SHA.fullmatch(entry[x])
                for x in ("window_pcm_sha256","worker_result_sha256"))):
            raise PermissionError("Forged, discontinuous or duplicated native worker window receipt")
        jobs.add(entry["job_id"])
        position+=entry["sample_count"]
    if position!=samples:
        raise PermissionError("Compiled worker audit windows do not cover every original sample")
    return json.loads(canonical(audit))


def verify_published_native_attestations(index: FilmIndex,project_id,take_id,
                                         manifest,temporal):
    """Read-only verification against original stored audio blob bytes/events.

    This returns False on historical Takes without the optional native
    capture provenance. It does not infer physical OS authorization merely
    from persisted JSON fields.
    """
    attestations=manifest.get("native_original_capture_attestations")
    if attestations is None:
        if "native_original_capture_attestations_sha256" in manifest:
            raise PermissionError("Orphaned native Take attestation hash")
        return False
    if (type(attestations) is not list or
        not 1<=len(attestations)<=32 or
        manifest.get("native_original_capture_attestations_sha256")!=
            audit_sha256(attestations)):
        raise PermissionError("Immutable Take native capture attestation hash changed")
    from backend.nvp_exact_time_shots import ExactTimeShotSequence
    original_camera=ExactTimeShotSequence(index).read(
        project_id,manifest["original_camera_timeline_id"],
        manifest["original_camera_timeline_revision"])
    if (original_camera["document_sha256"]!=
            manifest["original_camera_timeline_sha256"] or
        original_camera["scene_id"]!=manifest["scene_id"] or
        original_camera["scene_revision"]!=manifest["scene_revision"] or
        original_camera["scene_document_sha256"]!=
            manifest["scene_document_sha256"] or
        original_camera["duration_tick"]!=
            manifest["duration_tick"]):
        raise PermissionError("Original camera FilmIndex revision no longer matches frozen native Take")
    from backend.nvp_temporal_ledger import TemporalLedger
    ledger=TemporalLedger(index)
    events=ledger.events_in(
        project_id,manifest["timeline_id"],manifest["timeline_revision"],
        start_tick=0,end_tick=int(manifest["duration_tick"]),limit=500)
    if events.get("next_cursor") is not None:
        raise PermissionError("Cannot verify a partial original filming event set")
    audio_events=[e for e in events["events"] if e["event_kind"] in ("sound","dialogue")]
    if len(audio_events)!=len(attestations):
        raise PermissionError("Native Take audits do not cover every original sound event")
    by_source={e["source_id"]:e for e in audio_events}
    if len(by_source)!=len(audio_events):
        raise PermissionError("Native source identities collide in published timeline")
    seen=set()
    for att in attestations:
        if type(att) is not dict:
            raise PermissionError("Original Take attestation must be a dictionary")
        sid=att.get("source_id")
        if sid not in by_source or sid in seen:
            raise PermissionError("Foreign or repeated published native capture source")
        seen.add(sid)
        event=by_source[sid]
        source=RecordedSoundSources(index).describe(
            project_id,sid,event["source_revision"])
        record=source["data"]
        digest=sha256()
        samples=0
        original_windows=att.get("native_worker_receipts")
        if type(original_windows) is not list or not original_windows:
            raise PermissionError("Missing original native worker source windows")
        current=0
        remaining=original_windows[0].get("sample_count",0)*2
        window_digest=sha256()
        if type(remaining) is not int or remaining<=0:
            raise PermissionError("Invalid original worker window size")
        for chunk in record["chunks"]:
            blob=index.get_blob(project_id,chunk["blob_sha256"])
            if (type(blob) is not bytes or len(blob)!=chunk["byte_count"] or
                len(blob)%2 or chunk["first_sample"]!=samples):
                raise PermissionError("Original PCM immutable chunk content changed")
            digest.update(blob)
            samples+=len(blob)//2
            # Original FilmIndex PCM chunks are 1MiB, but compiled-worker
            # windows are 4MiB. Reconstruct each SHA incrementally across
            # immutable chunk boundaries without materializing the Take.
            pos=0
            while pos<len(blob):
                if current>=len(original_windows) or remaining<=0:
                    raise PermissionError("Original worker window mapping overflow")
                size=min(remaining,len(blob)-pos)
                window_digest.update(blob[pos:pos+size])
                pos+=size
                remaining-=size
                if remaining==0:
                    if window_digest.hexdigest()!=original_windows[current].get(
                            "window_pcm_sha256"):
                        raise PermissionError("Native worker window digest differs from published original PCM")
                    current+=1
                    if current<len(original_windows):
                        remaining=original_windows[current].get("sample_count",0)*2
                        if type(remaining) is not int or remaining<=0:
                            raise PermissionError("Invalid following native worker sample count")
                        window_digest=sha256()
        if (samples!=record["sample_count"] or
            current!=len(original_windows)):
            raise PermissionError("Published original samples did not fill every native worker window")
        validate_original_audit(
            att,project_id=project_id,take_id=take_id,
            scene_id=manifest["scene_id"],
            scene_sha=manifest["scene_document_sha256"],
            camera_sha=manifest["original_camera_timeline_sha256"],
            recording={"source_id":sid,"subject_id":event["subject_id"],
                       "usd_prim_path":event["payload"]["usd_prim_path"],
                       "start_tick":event["start_tick"],"end_tick":event["end_tick"]},
            source_sha=digest.hexdigest(),samples=samples)
        if event["payload"].get("native_capture_audit_sha256")!=audit_sha256(att):
            raise PermissionError("Native audit is not bound to original sound timeline event")
    return True
