"""NVP B12 — portable, immutable OpenTimelineIO editorial interchange and MOV handoff.

No homegrown timeline parser: OpenTimelineIO 0.18.1 owns the edit schema.
Use the original frozen take's actual shot cuts, verified B11 SDR16 PNGs,
and the already-established NVP ProRes/DNxHR encoders and decoded-video audit.

This module is WORKER-SIDE ONLY. It does not authorize file-writing jobs:
the trusted native NVP B12 host must resource-admit and supervise it.
An OTIO is *not* the media; a portable handoff also needs the actual PNGs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_b11_editorial import verify_sdr_review,normalize_near_opaque_preview_alpha
from backend.nvp_color_ocio import _ffmpeg_bin,_run,decode_scene_linear_exr
from backend.nvp_color_mastering import (
    PROFILES,MAX_RASTER_PIXELS,_yuv_reference,encode_mov,video_audit,
    mastering_policy,grade_recipe,grade_pixels,view_to_rgb48)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_film_index import _id
from backend.nvp_presentation_pipeline import _png_info

FORMAT="nvp.presentation.b12.editorial_delivery.v1"
RATE=24
MAX_FRAMES=120
MAX_MEDIA_BYTES=2*1024**3
OTIO_VERSION="0.18.1"
SHA_PATTERN=re.compile(r"[0-9a-f]{64}\Z")


def _sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            digest.update(part)
    return digest.hexdigest()


def _otio():
    import opentimelineio as otio
    if getattr(otio,"__version__",None)!=OTIO_VERSION:
        # Some OTIO wheels expose only the version module.
        from importlib.metadata import version
        if version("OpenTimelineIO")!=OTIO_VERSION:
            raise RuntimeError("NVP B12 requires exact official OpenTimelineIO 0.18.1")
    return otio


def _write_new(path:Path,raw:bytes):
    """Never overwrite an existing delivery source; synchronize each file."""
    if not isinstance(raw,bytes):
        raise TypeError("Media must be immutable binary bytes")
    if path.is_symlink() or path.exists():
        raise RuntimeError("NVP export path already exists or is symlinked")
    with path.open("xb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def _review(capture,project_id,review_id):
    proof=verify_sdr_review(capture,project_id,review_id,decode_png=False)
    doc=capture.index.read_revision(project_id,review_id)
    d=doc["data"]
    if (doc["kind"]!="presentation" or doc["revision"]!=1 or
        proof["review_frame_count"]!=d["frame_count"] or
        d["fps"]!=RATE or not 1<=d["frame_count"]<=MAX_FRAMES):
        raise RuntimeError("B12 requires accepted complete 24fps B11 SDR16 original")
    return doc,d,proof


def _shot_for_frame(cuts,n):
    for item in cuts:
        if item["start_frame"]<=n<item["stop_frame_exclusive"]:
            return item["shot_id"]
    raise RuntimeError("Frame missing its frozen camera cut")


def build_otio(cuts,*,project_id,source_take_id,review_id,frame_count,
               base="media/"):
    """Make one original-shot-per-clip, contiguous, true image-sequence edit."""
    if base!="media/":
        raise ValueError("Only portable package-relative media references are permitted")
    otio=_otio()
    track=otio.schema.Track(name="Frozen original camera cuts",
                            kind=otio.schema.TrackKind.Video)
    cursor=1
    for n,cut in enumerate(cuts):
        first=cut["start_frame"]
        last=cut["stop_frame_exclusive"]
        if (type(first) is not int or type(last) is not int or
            first!=cursor or not first<last<=frame_count+1):
            raise RuntimeError("Noncontiguous frozen editor camera cuts")
        duration=last-first
        duration_time=otio.opentime.RationalTime(duration,RATE)
        zero=otio.opentime.RationalTime(0,RATE)
        period=otio.opentime.TimeRange(zero,duration_time)
        sequence=otio.schema.ImageSequenceReference(
            target_url_base=base,name_prefix="review_",name_suffix=".png",
            start_frame=first,frame_step=1,rate=RATE,frame_zero_padding=6,
            missing_frame_policy=otio.schema.ImageSequenceReference.MissingFramePolicy.error,
            available_range=period,
            metadata={"nvp":{"original_start_frame":first,
                             "original_end_frame_exclusive":last}})
        clip=otio.schema.Clip(
            name=str(cut["shot_id"]),media_reference=sequence,
            source_range=period,
            metadata={"nvp":{"shot_id":str(cut["shot_id"]),
                             "start_frame_in_frozen_take":first,
                             "end_frame_exclusive":last}})
        track.append(clip)
        cursor=last
    if cursor!=frame_count+1:
        raise RuntimeError("OTIO timeline left off original frozen picture frames")
    timeline=otio.schema.Timeline(name="NVP frozen take editorial",
                                 tracks=[track],
                                 metadata={"nvp":{"project_id":project_id,
                                                  "source_take_id":source_take_id,
                                                  "review_id":review_id,
                                                  "fps":RATE,"frames":frame_count,
                                                  "soundtrack_present":False}})
    return timeline


def verify_otio_document(raw:bytes,cuts,frame_count):
    """Independently parse the real OpenTimelineIO wire format and time math."""
    otio=_otio()
    timeline=otio.adapters.read_from_string(raw.decode("utf8"),adapter_name="otio_json")
    tracks=list(timeline.tracks)
    if len(tracks)!=1 or tracks[0].kind!=otio.schema.TrackKind.Video:
        raise RuntimeError("Interchange must be one truthful native video track")
    clips=list(tracks[0])
    if len(clips)!=len(cuts):
        raise RuntimeError("OTIO shot count does not match frozen take")
    expected=1
    for clip,cut in zip(clips,cuts):
        duration=cut["stop_frame_exclusive"]-cut["start_frame"]
        ref=clip.media_reference
        if (not isinstance(clip,otio.schema.Clip) or
            not isinstance(ref,otio.schema.ImageSequenceReference) or
            clip.name!=str(cut["shot_id"]) or
            ref.start_frame!=expected or ref.frame_step!=1 or
            ref.frame_zero_padding!=6 or ref.rate!=RATE or
            ref.target_url_base!="media/" or
            ref.name_prefix!="review_" or ref.name_suffix!=".png" or
            ref.missing_frame_policy!=otio.schema.ImageSequenceReference.MissingFramePolicy.error or
            clip.source_range.start_time.value!=0 or
            clip.source_range.duration.value!=duration or
            clip.source_range.duration.rate!=RATE or
            ref.available_range.duration.value!=duration):
            raise RuntimeError("OTIO clip source image range/camera cut drift")
        if (ref.target_url_for_image_number(0)!=
            "media/review_%06d.png"%expected or
            ref.target_url_for_image_number(duration-1)!=
            "media/review_%06d.png"%(expected+duration-1)):
            raise RuntimeError("OTIO image-sequence URI is not fully portable")
        expected+=duration
    if expected!=frame_count+1:
        raise RuntimeError("OTIO lost or repeated original film frames")
    if timeline.duration().value!=frame_count or timeline.duration().rate!=RATE:
        raise RuntimeError("OTIO changed frozen 24fps total running time")
    return {"clips":len(clips),"frames":frame_count,
            "fps":RATE,"duration_seconds":frame_count/RATE,
            "parsed_with_official_otio":True}


def _relative_filename(frame):
    if type(frame) is not int or not 1<=frame<=MAX_FRAMES:
        raise ValueError("Invalid original film frame number")
    return "review_%06d.png"%frame


def _rgb48_from_png(png:Path,ffmpeg,width,height):
    raw=_run([ffmpeg,"-nostdin","-v","error","-xerror",
             "-i",str(png),"-frames:v","1",
             "-pix_fmt","rgb48le","-f","rawvideo","-"],
             label="Independent editorial RGB48 PNG readback")
    if len(raw)!=width*height*6:
        raise RuntimeError("Review image RGB48 decoded length mismatch")
    return raw


def _master_rgb48_from_original_float32(capture,project_id,rows,
                                        dest:Path,ffmpeg,width,height,*,
                                        verify_expected=False):
    """Reuse COLOR-01B2 genuine Rec.1886 display processor, not sRGB PNG.

    A ProRes/DNxHR tagged BT.709 MOV must not simply copy already
    display-encoded sRGB PNG RGB48 values. Use original authoritative B9
    FLOAT32 pixels plus the established ACES2 Rec.1886/Rec.709 view,
    preserving B9 alpha and only normalizing tightly bounded B11 AA alpha
    in a derived CPU buffer before color conversion.
    """
    policy,cpu=mastering_policy()
    neutral=grade_recipe()
    with dest.open("xb") as out:
        for row in rows:
            original=capture.index.verify_media_file(
                project_id,row["source_exr_sha256"],"image/x-exr")
            source=decode_scene_linear_exr(
                Path(original["path"]),ffmpeg,(width,height))
            opaque,alpha_audit=normalize_near_opaque_preview_alpha(source)
            graded=grade_pixels(opaque,neutral)
            rgb48,stats=view_to_rgb48(graded,cpu)
            hash_rgb=_sha_bytes(rgb48)
            if verify_expected:
                if (row.get("master_rgb48_sha256")!=hash_rgb or
                    row.get("master_clip_audit")!=stats):
                    raise RuntimeError("Replayed original FLOAT32 Rec.1886 master pixels differ")
            else:
                row["master_rgb48_sha256"]=hash_rgb
                row["master_clip_audit"]=stats
            out.write(rgb48)
        out.flush()
        os.fsync(out.fileno())
    return policy,neutral


def create_editorial_handoff(capture:DigitalCapture,project_id,review_id,
                              delivery_id,output_root,*,profiles=(),
                              ffmpeg=None,ffprobe=None):
    """Worker-only. Full portable media and OTIO, optional verified MOV candidates."""
    _id(delivery_id,"new immutable interchange delivery")
    if not isinstance(capture,DigitalCapture):
        raise TypeError("NVP FilmIndex DigitalCapture required")
    if type(profiles) not in (list,tuple) or len(profiles)!=len(set(profiles)) or (
        any(p not in PROFILES for p in profiles)):
        raise ValueError("Unknown or repeated professional delivery codec")
    doc,data,proof=_review(capture,project_id,review_id)
    try:
        capture.index.read_revision(project_id,delivery_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("FilmIndex delivery exists; no overwriting original media")
    root=Path(output_root)
    if root.is_symlink():
        raise RuntimeError("Untrusted output root is a symlink")
    root=root.resolve()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    bundle=root/("handoff_"+hashlib.sha256((project_id+"|"+delivery_id).encode()).hexdigest()[:24])
    bundle.mkdir(mode=0o700,exist_ok=False)
    media=bundle/"media"
    media.mkdir(mode=0o700,exist_ok=False)
    width,height=data["width"],data["height"]
    count=data["frame_count"]
    if width*height*6*count>MAX_MEDIA_BYTES:
        raise RuntimeError("Proposed media handoff exceeds bounded disk policy")
    if profiles and (width*height>MAX_RASTER_PIXELS or width%2 or height%2 or
                     not 2<=count<=MAX_FRAMES):
        raise RuntimeError("Codec delivery exceeds already verified picture codec limits")
    native=_ffmpeg_bin(ffmpeg)
    if profiles and not shutil.which(ffprobe or "ffprobe"):
        raise RuntimeError("Independent FFprobe required for codec publication")
    frame_meta=[]
    rgbraw=bundle/"rec1886_bt709_master_rgb48le.raw"
    for row in data["review_frames"]:
        frame=row["frame"]
        if frame!=len(frame_meta)+1:
            raise RuntimeError("Source B11 RGB sequence contains a gap")
        blob=capture.index.get_blob(project_id,row["png16_sha256"])
        if (_png_info(blob)!=(width,height) or blob[24]!=16 or blob[25]!=2):
            raise RuntimeError("B11 source is not a true 16-bit RGB PNG")
        target=media/_relative_filename(frame)
        _write_new(target,blob)
        if _sha_file(target)!=row["png16_sha256"]:
            raise RuntimeError("Portable media bytes differ from indexed review")
        decoded=_rgb48_from_png(target,native,width,height)
        if _sha_bytes(decoded)!=row["decoded_rgb48le_sha256"]:
            raise RuntimeError("Portable media pixels differ from original official ACES2 SDR output")
        frame_meta.append({
            "frame":frame,"shot_id":_shot_for_frame(data["cutlist"],frame),
            "media_path":"media/"+_relative_filename(frame),
            "source_exr_sha256":row["source_exr_sha256"],
            "png16_sha256":row["png16_sha256"],
            "rgb48_sha256":_sha_bytes(decoded),
            "bytes":len(blob),
        })
    # The OTIO PNG review is sRGB, whereas technical video is explicitly
    # tagged Rec.709. Never pass sRGB-derived PNG RGB codes directly into
    # an encoder claiming the Rec.1886/709 display mastering recipe.
    master_policy,master_grade=None,None
    if profiles:
        master_policy,master_grade=_master_rgb48_from_original_float32(
            capture,project_id,frame_meta,rgbraw,native,width,height)
    cutlist=data["cutlist"]
    timeline=build_otio(cutlist,project_id=project_id,
                       source_take_id=data["source_take_id"],
                       review_id=review_id,frame_count=count)
    otio_path=bundle/"timeline.otio"
    # Use official OTIO adapter, not NVP-created faux JSON.
    _otio().adapters.write_to_file(timeline,str(otio_path),adapter_name="otio_json")
    otio_bytes=otio_path.read_bytes()
    otio_proof=verify_otio_document(otio_bytes,cutlist,count)
    media_digest=capture.index.put_blob(project_id,otio_bytes,
                                         "application/vnd.opentimelineio+json")
    if media_digest!=_sha_file(otio_path):
        raise RuntimeError("Stored OTIO timeline bytes differ from portable package")
    videos=[]
    for profile in profiles:
        ref=bundle/(profile+".ref_yuv422p10le")
        _yuv_reference(rgbraw,ref,width=width,height=height,frames=count,ffmpeg=native)
        movie=bundle/(profile+".mov")
        encode_mov(rgbraw,movie,profile,width=width,height=height,frames=count,ffmpeg=native)
        audit=video_audit(movie,profile=profile,width=width,height=height,
                          frames=count,ffmpeg=native,ffprobe=ffprobe or "ffprobe",
                          reference_yuv=ref)
        indexed=capture.index.put_media_file(project_id,movie,"video/quicktime")
        if indexed["sha256"]!=_sha_file(movie):
            raise RuntimeError("MOV differs between decoded audit and FilmIndex")
        videos.append({"profile":profile,"relative_path":movie.name,
                       "sha256":indexed["sha256"],"bytes":indexed["size_bytes"],
                       "video_audit":audit,"audio_included":False,
                       "mastering_view":"ACES2_Rec1886_Rec709_100nit",
                       "source_precision":"original_RGBA_FLOAT32",
                       "approved_picture_lock":False})
    # Intermediate full RGB48 and YUV are reconstructible; never retain
    # large uncompressed working surfaces after a verified encode.
    rgbraw.unlink(missing_ok=True)
    for profile in profiles:
        (bundle/(profile+".ref_yuv422p10le")).unlink(missing_ok=True)
    document={
        "format":FORMAT,"status":"technical_editorial_delivery_unapproved",
        "project_id":project_id,"source_review_id":review_id,
        "source_review_sha256":doc["document_sha256"],
        "source_take_id":data["source_take_id"],
        "source_take_sha256":data["source_take_sha256"],
        "source_float32_presentation_id":data["source_presentation_id"],
        "source_float32_presentation_sha256":data["source_presentation_sha256"],
        "fps":RATE,"frame_count":count,"resolution":[width,height],
        "color_policy":data["color_policy"],
        "otio_version":OTIO_VERSION,
        "otio_schema_accepted":otio_proof,
        "otio_sha256":media_digest,"portable_otio_path":"timeline.otio",
        "camera_cutlist":cutlist,"media_frames":frame_meta,
        "video_candidates":videos,
        "media_color":"ACES2_SDR100_sRGB_16bit_RGB",
        "technical_video_color":"ACES2_Rec1886_BT709_10bit_YUV422" if profiles else None,
        "mastering_color_policy":master_policy,
        "mastering_grade_recipe":master_grade,
        "technical_mov_not_derived_from_srgb_png_codes":bool(profiles),
        "authoritative_source_modified":False,
        "audio_present":False,"approved_picture_lock":False,
        "final_delivery_master":False,"dcp_delivered":False,
    }
    deps=[{"object_id":review_id,"revision":1,"role":"presentation"},
          {"object_id":data["source_presentation_id"],"revision":1,"role":"presentation"},
          {"object_id":data["source_take_id"],"revision":1,"role":"source_take"}]
    # Include a content hash manifest inside the portable directory before
    # FilmIndex publication. The FilmIndex revision remains authoritative.
    _write_new(bundle/"package_manifest.json",
               json.dumps(document,sort_keys=True,indent=2).encode("utf8"))
    record=capture.index.register_revision(
        project_id,delivery_id,"presentation",document,dependencies=deps)
    proof=verify_editorial_handoff(capture,project_id,delivery_id,bundle,
                                   check_decode=True,ffmpeg=native,
                                   ffprobe=ffprobe or "ffprobe")
    return {**proof,"filmindex_document_sha256":record["document_sha256"],
            "package_directory":str(bundle)}


def verify_editorial_handoff(capture,project_id,delivery_id,bundle, *,
                             check_decode=False,ffmpeg=None,ffprobe=None):
    """Verify self-contained OTIO+media and immutable FilmIndex provenance."""
    doc=capture.index.read_revision(project_id,delivery_id)
    data=doc["data"]
    if (doc["kind"]!="presentation" or doc["revision"]!=1 or
        data.get("format")!=FORMAT or data.get("project_id")!=project_id or
        data.get("status")!="technical_editorial_delivery_unapproved" or
        data.get("fps")!=RATE or
        data.get("authoritative_source_modified") is not False or
        data.get("audio_present") is not False or
        data.get("approved_picture_lock") is not False or
        data.get("final_delivery_master") is not False or
        data.get("dcp_delivered") is not False):
        raise RuntimeError("Delivery is mislabelled as final or source is unverified")
    source,review,accepted=_review(capture,project_id,data["source_review_id"])
    if (source["document_sha256"]!=data["source_review_sha256"] or
        review["source_take_id"]!=data["source_take_id"] or
        review["source_take_sha256"]!=data["source_take_sha256"] or
        review["source_presentation_id"]!=data["source_float32_presentation_id"] or
        review["source_presentation_sha256"]!=data["source_float32_presentation_sha256"] or
        review["color_policy"]!=data["color_policy"] or
        review["cutlist"]!=data["camera_cutlist"] or
        review["frame_count"]!=data["frame_count"] or
        [review["width"],review["height"]]!=data["resolution"]):
        raise RuntimeError("Source film, edit cuts, color policy or reviewed frames changed")
    deps=sorted([
        {"object_id":data["source_review_id"],"revision":1,"role":"presentation"},
        {"object_id":data["source_float32_presentation_id"],"revision":1,"role":"presentation"},
        {"object_id":data["source_take_id"],"revision":1,"role":"source_take"}],
        key=lambda x:(x["object_id"],x["revision"],x["role"]))
    if doc["dependencies"]!=deps:
        raise RuntimeError("Editorial delivery FilmIndex source dependencies differ")
    package=Path(bundle)
    if not package.is_dir() or package.is_symlink():
        raise RuntimeError("Editorial media directory unavailable or symlinked")
    path=package/"timeline.otio"
    if path.is_symlink():
        raise RuntimeError("Portable OTIO has unsafe symlink")
    otio_bytes=path.read_bytes()
    if (_sha_bytes(otio_bytes)!=data["otio_sha256"] or
        capture.index.get_blob(project_id,data["otio_sha256"])!=otio_bytes or
        verify_otio_document(otio_bytes,data["camera_cutlist"],
                             data["frame_count"])!=data["otio_schema_accepted"]):
        raise RuntimeError("Official OTIO serialized edit changed")
    manifest=package/"package_manifest.json"
    if manifest.is_symlink() or json.loads(manifest.read_text("utf8"))!=data:
        raise RuntimeError("Portable editorial receipt differs from FilmIndex source")
    if ([row["frame"] for row in data["media_frames"]]!=
        list(range(1,data["frame_count"]+1)) or
        data["otio_version"]!=OTIO_VERSION):
        raise RuntimeError("Package has omitted or duplicated editorial frames")
    native=_ffmpeg_bin(ffmpeg) if check_decode else None
    for source_row,row in zip(review["review_frames"],data["media_frames"]):
        if (row["frame"]!=source_row["frame"] or
            row["shot_id"]!=source_row["shot_id"] or
            row["source_exr_sha256"]!=source_row["source_exr_sha256"] or
            row["png16_sha256"]!=source_row["png16_sha256"] or
            row["rgb48_sha256"]!=source_row["decoded_rgb48le_sha256"] or
            row["media_path"]!="media/"+_relative_filename(row["frame"])):
            raise RuntimeError("Portable editorial image lost source/camera/time")
        file=package/"media"/_relative_filename(row["frame"])
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("Export media missing or symlinked")
        if (_sha_file(file)!=row["png16_sha256"] or
            file.stat().st_size!=row["bytes"] or
            capture.index.get_blob(project_id,row["png16_sha256"])!=file.read_bytes()):
            raise RuntimeError("Portable editorial media differs from approved source")
        if native and _sha_bytes(_rgb48_from_png(file,native,*data["resolution"]))!=row["rgb48_sha256"]:
            raise RuntimeError("Decoded portable editorial RGB48 image changed")
    if data["video_candidates"]:
        master_policy,_=mastering_policy()
        if (data.get("mastering_color_policy")!=master_policy or
            data.get("mastering_grade_recipe")!=grade_recipe() or
            data.get("technical_video_color")!="ACES2_Rec1886_BT709_10bit_YUV422" or
            data.get("technical_mov_not_derived_from_srgb_png_codes") is not True):
            raise RuntimeError("Technical video Rec.1886 color authority or neutral grade is invalid")
    elif (data.get("mastering_color_policy") is not None or
          data.get("mastering_grade_recipe") is not None or
          data.get("technical_mov_not_derived_from_srgb_png_codes") is not False):
        raise RuntimeError("Video mastering policy claimed without any actual encoded MOV")
    for item in data["video_candidates"]:
        if item["profile"] not in PROFILES or item["relative_path"]!=item["profile"]+".mov":
            raise RuntimeError("Unrecognized editorial video delivery candidate")
        file=package/item["relative_path"]
        if file.is_symlink() or not file.is_file():
            raise RuntimeError("Professional candidate video missing")
        video=capture.index.verify_media_file(project_id,item["sha256"],"video/quicktime")
        if (_sha_file(file)!=item["sha256"] or video["size_bytes"]!=item["bytes"]):
            raise RuntimeError("Professional candidate video differs from FilmIndex")
        if (item.get("audio_included") is not False or
            item.get("approved_picture_lock") is not False or
            item.get("mastering_view")!="ACES2_Rec1886_Rec709_100nit" or
            item.get("source_precision")!="original_RGBA_FLOAT32"):
            raise RuntimeError("Technical MOV source/Rec.1886 view misrepresented as final master")
        if native:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="nvp-b12-rec1886-replay-") as tmp:
                folder=Path(tmp)
                master_raw=folder/"original_linear_aces2_rec1886_rgb48le.raw"
                policy,grade=_master_rgb48_from_original_float32(
                    capture,project_id,data["media_frames"],master_raw,native,
                    data["resolution"][0],data["resolution"][1],
                    verify_expected=True)
                if policy!=data["mastering_color_policy"] or grade!=data["mastering_grade_recipe"]:
                    raise RuntimeError("Native technical MOV master view changed after publication")
                ref_yuv=folder/"fresh_bt709_reference.yuv"
                _yuv_reference(master_raw,ref_yuv,width=data["resolution"][0],
                               height=data["resolution"][1],frames=data["frame_count"],
                               ffmpeg=native)
                audit=video_audit(file,profile=item["profile"],
                      width=data["resolution"][0],height=data["resolution"][1],
                      frames=data["frame_count"],ffmpeg=native,
                      ffprobe=ffprobe or "ffprobe",reference_yuv=ref_yuv)
                if (audit["metadata"]!=item["video_audit"]["metadata"] or
                    audit["decoded"]["decoded_yuv10_sha256"]!=
                    item["video_audit"]["decoded"]["decoded_yuv10_sha256"] or
                    audit["decoded"]["reference_yuv10_sha256"]!=
                    item["video_audit"]["decoded"]["reference_yuv10_sha256"] or
                    audit["decoded"]["reference_comparison"]!="passed_bounded_lossy_10bit_yuv" or
                    audit["decoded"]["illegal_samples"]!=0):
                    raise RuntimeError("Video differs from original Float32 Rec.1886 color reference")
    return {"format":FORMAT,"status":"VERIFIED_PORTABLE_EDITORIAL_HANDOFF",
            "project_id":project_id,"delivery_id":delivery_id,
            "source_take_id":data["source_take_id"],
            "frames":data["frame_count"],"fps":RATE,
            "cut_count":len(data["camera_cutlist"]),
            "official_otio_parsed":True,
            "portable_media_all_present":True,
            "full_rgb48_independent_decode":bool(check_decode),
            "video_candidates_verified":[x["profile"] for x in data["video_candidates"]],
            "source_float32_exr_unchanged":True,
            "audio_mixed":False,"final_master_approved":False}
