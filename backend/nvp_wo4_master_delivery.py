"""WO4-05 source-bound master to real WO3 JPEG2000/MXF/DCP bridge.

Requires an existing, native-approved WO4 mastering decision and exact source
bound XYZ12 frames plus PCM24 candidate. Uses the actual SHA-pinned OpenJPEG
and CineCert wrappers. A DCP published here is a structural candidate, never
a calibrated/production-ready cinema master.
"""
from __future__ import annotations
from hashlib import sha256
from uuid import uuid4
from io import BytesIO
import wave

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo4_mastering_decision import FORMAT as DECISION_FORMAT
from backend.nvp_wo4_pcm_master import FORMAT as SOUND_FORMAT
from backend.nvp_wo4_xyz12_master import FORMAT as PICTURE_FORMAT
from backend.nvp_wo3_native_codecs import encode_xyz12_frame
from backend.nvp_wo3_mxf_native import wrap_cinema_picture,wrap_cinema_pcm
from backend.nvp_wo3_dcp_package import publish_dcp_candidate

FORMAT="nvp.wo4.native_cinema_master_delivery_candidate.v1"


def publish_mastered_dcp(index:FilmIndex,pid,*,take_id,take_revision,take_sha256,
        mastering_decision_id,pictures,sound,encoder,wrapper,info,
        output_root,title,approve_package):
    if not isinstance(index,FilmIndex):
        raise PermissionError("Native FilmIndex required for mastered delivery")
    decision=index.read_revision(pid,mastering_decision_id)
    if (decision["kind"]!="presentation" or
            decision["data"].get("format")!=DECISION_FORMAT or
            decision["data"].get("source_take_sha256")!=take_sha256 or
            decision["data"].get("source_take_id")!=take_id or
            decision["data"].get("source_take_revision")!=take_revision or
            decision["data"].get("production_master_accepted") is not False):
        raise PermissionError("Exact approved prior mastering decision required")
    if (type(pictures) is not list or not 3<=len(pictures)<=7200 or
            type(sound) is not dict or sound.get("format")!=SOUND_FORMAT or
            len(pictures)!=sound.get("frame_count") or
            sound.get("original_take_sha256")!=take_sha256 or
            sound.get("master_pcm_sha256")!=decision["data"].get("sound_sha256")):
        raise PermissionError("Film-duration matched source picture/sound mastering required")
    wav=sound.get("wav_bytes")
    if type(wav) is not bytes:
        raise PermissionError("Native derived sound master missing")
    try:
        with wave.open(BytesIO(wav),"rb") as reader:
            if (reader.getnframes()!=len(pictures)*2000 or
                    reader.getframerate()!=48000 or
                    reader.getsampwidth()!=3 or
                    reader.getnchannels()!=len(sound.get("channel_order",[]))):
                raise PermissionError("Mastered sound timing/format invalid")
            actual_pcm=reader.readframes(reader.getnframes())
    except (wave.Error,EOFError) as exc:
        raise PermissionError("Invalid source-bound PCM WAV master") from exc
    if sha256(actual_pcm).hexdigest()!=sound.get("master_pcm_sha256"):
        raise PermissionError("Mastering decision does not match actual WAV samples")
    if not callable(approve_package):
        raise PermissionError("Creator native package approval callback required")
    profile=decision["data"]["picture_profile"]
    frames=[]
    approved_shas=decision["data"].get("ordered_picture_sha256")
    # Historical single-image decisions remain readable, but delivery only
    # allows an explicit ordered frame manifest created at creator approval.
    if (type(approved_shas) is not list or len(approved_shas)!=len(pictures)
            or decision["data"].get("picture_tick_step")!=294000000
            or decision["data"].get("picture_sha256")!=approved_shas[0]):
        raise PermissionError("An exact Film Time ordered master decision is required")
    for image,approved_sha in zip(pictures,approved_shas):
        if (image.get("format")!=PICTURE_FORMAT or image.get("profile")!=profile
                or image.get("original_take_sha256")!=take_sha256
                or image.get("xyz12_sha256")!=approved_sha
                or image.get("source_modified") is not False
                or image.get("production_picture_accepted") is not False
                or type(image.get("xyz12")) is not bytes
                or sha256(image["xyz12"]).hexdigest()!=approved_sha):
            raise PermissionError("Unapproved picture source or invalid XYZ12 integrity")
        frames.append(encode_xyz12_frame(
            encoder,image["xyz12"],profile=profile,
            source_presentation_sha256=take_sha256,creator_approved=True))
    pic=wrap_cinema_picture(wrapper,info,frames,
                            profile=profile,asset_uuid=str(uuid4()))
    snd=wrap_cinema_pcm(wrapper,info,sound["wav_bytes"],
                        frame_count=len(frames),asset_uuid=str(uuid4()),
                        origin_sha256=take_sha256)
    receipt=publish_dcp_candidate(
        index,pid,take_id=take_id,take_revision=take_revision,
        take_sha256=take_sha256,picture=pic,sound=snd,
        output_root=output_root,title=title,approve=approve_package)
    return {"format":FORMAT,"status":receipt["status"],
            "dcp_receipt":receipt,
            "approved_mastering_decision_id":mastering_decision_id,
            "original_take_sha256":take_sha256,
            "picture_codestream_sha256":[x["codestream_sha256"] for x in frames],
            "picture_mxf_sha256":pic["sha256"],
            "sound_mxf_sha256":snd["sha256"],
            "production_master_accepted":False,
            "independent_dci_validator_passed":False,
            "physical_projection_accepted":False,
            "source_modified":False,"ffmpeg_used":False}
