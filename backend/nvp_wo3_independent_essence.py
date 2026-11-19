"""WO3-05: full source-frame MXF/JPEG2000 decoder roundtrip gate.

The trusted host supplies exact SHA-reviewed native asdcplib unwrap and
OpenJPEG decode binaries. All source codestream SHA identities are checked
against the MXF essence extracted into private staging. Every extracted
picture frame must really decode to an XYZ12 PPM with matching source
dimensions, and the extracted 24bit PCM is checked sample-for-sample against
the approved original sound track.

The primary roundtrip shares producer libraries. Optional independent JasPer
readback and exact source-raster measurements extend evidence but do NOT
substitute for formal SMPTE schema/DCI compliance, color calibration, or
actual projector ingest.
"""
from __future__ import annotations
import hashlib
from backend.nvp_dci_dual_decode import compare_xyz12,summarize_xyz12
from pathlib import Path
import shutil
import wave

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_dci_codestream import MAX_FRAME_BYTES
from backend.nvp_dci_packets import ReelPacketAudit
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,common_codec_authority,_sha as _validate_sha256,MAX_STAGE_BYTES
from backend.nvp_wo3_dcp_structure import _asset_file,_linked_entry

FORMAT="nvp.wo3.native_full_essence_roundtrip.v1"
MAX_REEL_FRAMES=7200

def _hash_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _approved_digest_ledger(picture, sound, expected_frames):
    if type(picture) is not list:
        raise PermissionError("Expected original frame and sound SHA ledger required")
    # Snapshot before validation; never re-read a mutable caller list after approval.
    picture = tuple(picture)
    if len(picture) != expected_frames:
        raise PermissionError("Expected original frame and sound SHA ledger required")
    for digest in picture:
        _validate_sha256(digest)
    return picture, _validate_sha256(sound)


def _single_reel_tracks(tracks):
    if len(tracks) != 2:
        raise RuntimeError("One real picture and sound MXF track required")
    assets = {track["kind"]: track for track in tracks}
    if (set(assets) != {"picture", "sound"} or
        assets["picture"]["asset_id"] == assets["sound"]["asset_id"] or
        assets["picture"]["filename"].casefold() ==
        assets["sound"]["filename"].casefold()):
        raise RuntimeError("One distinct real picture and sound MXF track required")
    return assets


def _read_pcm24(audio, expected_frames):
    with wave.open(str(audio), "rb") as w:
        channels = w.getnchannels()
        samples = expected_frames * 2000
        if (w.getsampwidth() != 3 or w.getframerate() != 48000 or
            w.getnframes() != samples or channels not in (2, 6, 8) or
            w.getcomptype() != "NONE"):
            raise RuntimeError("MXF does not preserve source DCI PCM24 timing")
        source_pcm = w.readframes(samples)
    if len(source_pcm) != samples * channels * 3:
        raise RuntimeError("Native PCM WAV payload is truncated")
    return source_pcm

def _ppm_header(file,*,width,height):
    if _linked_entry(file) or not file.is_file():
        raise RuntimeError("Missing regular native decoder output")
    with file.open("rb") as handle:
        line1=handle.readline(20)
        line2=handle.readline(100)
        # Official OpenJPEG PPM exporter inserts a bounded version line.
        # It is not part of the image data or a color transform.
        if line2.startswith(b"# OpenJPEG-"):
            line2=handle.readline(40)
        line3=handle.readline(20)
        rest=handle.read(width*height*6+1)
    if (line1!=b"P6\n" or
        line2.strip()!=f"{width} {height}".encode("ascii") or
        line3.strip()!=b"4095" or
        len(rest)!=width*height*6 or
        any(rest[i]&0xf0 for i in range(0,len(rest),2))):
        raise RuntimeError("Actual native decoder produced invalid XYZ12 raster")
    return rest

def _verify_decoders(unwrap,decoder,secondary):
    if secondary is None:
        common_codec_authority(unwrap,decoder)
        return
    if (not isinstance(secondary,ApprovedCodecBinary) or secondary.product!="JasPer-nvp_decode"
            or secondary.sha256==decoder.sha256):
        raise PermissionError("Distinct source-reviewed JasPer decoder required")
    common_codec_authority(unwrap,decoder,secondary)

def _reference_ledger(hashes, reader, expected_frames):
    # Optional trusted host source reader, never derived from an extracted frame.
    if hashes is None and reader is None:
        return None
    if not callable(reader) or type(hashes) is not list or len(hashes)!=expected_frames:
        raise PermissionError("Exact ordered source-raster ledger and trusted reader required")
    return tuple(_validate_sha256(x) for x in hashes)


def _read_reference(reader,digest,width,height):
    raw=reader(digest)
    if type(raw) is not bytes or len(raw)!=width*height*6 or _hash_bytes(raw)!=digest:
        raise PermissionError("Original approved XYZ12 reference changed or incomplete")
    return raw


def decode_full_dcp_candidate(folder,*,unwrap:ApprovedCodecBinary,
                              decoder:ApprovedCodecBinary,
                              expected_picture_codestream_sha256,
                              expected_sound_pcm_sha256,
                              profile="2K_FLAT_24",
                              expected_frames, second_decoder=None,
                              expected_xyz12_sha256=None, reference_reader=None):
    if unwrap.product!="ASDCP-asdcp_unwrap" or (
        decoder.product!="OpenJPEG-opj_decompress"):
        raise PermissionError("Exact native MXF/JPEG2000 decoding capabilities required")
    if profile not in PROFILES or type(expected_frames) is not int or (
        not 1<=expected_frames<=MAX_REEL_FRAMES):
        raise ValueError("Bounded original cinema frame count/profile required")
    expected_picture_codestream_sha256, expected_sound_pcm_sha256 = (
        _approved_digest_ledger(expected_picture_codestream_sha256,
                                expected_sound_pcm_sha256, expected_frames))
    _verify_decoders(unwrap,decoder,second_decoder)
    refs=_reference_ledger(expected_xyz12_sha256,reference_reader,expected_frames)
    if refs is not None and second_decoder is None:
        raise PermissionError("Source comparison qualification requires both decoders")
    audit=inspect_dcp_structure(folder)
    if audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or (
        audit["reel_count"]!=1):
        raise RuntimeError("Only independently hashed single-reel DCP accepted")
    report=_decode_reel_tracks(folder,audit,audit["tracks"],unwrap=unwrap,decoder=decoder,
        expected_picture_codestream_sha256=expected_picture_codestream_sha256,
        expected_sound_pcm_sha256=expected_sound_pcm_sha256,profile=profile,expected_frames=expected_frames,second_decoder=second_decoder,reference_hashes=refs,reference_reader=reference_reader)
    if inspect_dcp_structure(folder)!=audit:
        raise PermissionError("Package changed during native verification")
    return report


def _decode_reel_tracks(folder,audit,tracks,*,unwrap,decoder,expected_picture_codestream_sha256,
                        expected_sound_pcm_sha256,profile,expected_frames,second_decoder=None,reference_hashes=None,reference_reader=None):
    assets=_single_reel_tracks(tracks)
    source=Path(folder).resolve(strict=True)
    if any(assets[k]["duration_frames"]!=expected_frames for k in assets):
        raise RuntimeError("Native package duration differs from approved frame count")
    if sum(audit["assets"][assets[k]["asset_id"]]["bytes"] for k in assets)>MAX_STAGE_BYTES//2:
        raise ValueError("Original bounded WO3 decoder reel exceeds staging budget")
    scope_hash=hashlib.sha256(("".join(expected_picture_codestream_sha256)+
                              expected_sound_pcm_sha256+"".join(reference_hashes or ())).encode("ascii")).hexdigest()
    with unwrap.stage(scope_hash) as root:
        for kind in ("picture","sound"):
            original=_asset_file(source,assets[kind]["filename"])
            dest=root/(kind+".mxf")
            with original.open("rb") as inp,dest.open("xb") as out:
                shutil.copyfileobj(inp,out)
            from backend.nvp_wo3_native_codecs import digest_file
            if digest_file(dest)!=audit["assets"][assets[kind]["asset_id"]]["sha256"]:
                raise RuntimeError("MXF changed during encrypted staging")
        unwrap.run(["-d",str(expected_frames),"picture.mxf","p_"],
                   cwd=root,timeout=3600)
        expected_names={f"p_{i:06d}.j2c" for i in range(expected_frames)}
        actual_names={p.name for p in root.iterdir() if p.name.casefold().startswith("p_")}
        if actual_names!=expected_names:
            raise RuntimeError("Native picture unwrap emitted missing or unexpected edit units")
        decoded_hashes=[]
        dual_receipts=[]
        source_comparisons=[]
        rate_audit=ReelPacketAudit(profile)
        width,height,_=PROFILES[profile]
        for i,expected in enumerate(expected_picture_codestream_sha256):
            name="p_"+str(i).zfill(6)+".j2c"
            j2k=root/name
            if not j2k.is_file() or _linked_entry(j2k):
                raise RuntimeError("Real MXF unwrap omitted an original picture")
            if not 80<=j2k.stat().st_size<=MAX_FRAME_BYTES:
                raise RuntimeError("Extracted native codestream exceeds bound")
            with j2k.open("rb") as stream:
                raw=stream.read(MAX_FRAME_BYTES+1)
            if _hash_bytes(raw)!=expected:
                raise RuntimeError("Decoded MXF source frame differs from approved J2K")
            rate_audit.add(raw)
            out="xyz_"+str(i).zfill(6)+".ppm"
            decoder.run(["-i",name,"-o",out],cwd=root,timeout=240)
            pixels=_ppm_header(root/out,width=width,height=height)
            if digest_file(j2k)!=expected:
                raise PermissionError("Exact extracted frame changed after primary decode")
            decoded_hashes.append(_hash_bytes(pixels))
            if second_decoder is not None:
                second_out="jasper_"+str(i).zfill(6)+".ppm"
                if digest_file(j2k)!=expected:
                    raise PermissionError("Exact extracted frame changed before secondary decode")
                second_process=second_decoder.run(["-i",name,"-o",second_out],cwd=root,timeout=240)
                if digest_file(j2k)!=expected:
                    raise PermissionError("Exact extracted frame changed after secondary decode")
                second_pixels=_ppm_header(root/second_out,width=width,height=height)
                dual_receipts.append({"frame":i,"codestream_sha256":expected,
                    "secondary_decoder_binary_sha256":second_decoder.sha256,
                    "execution_scope_sha256":second_process["execution_scope_sha256"],
                    **compare_xyz12(pixels,second_pixels)})
                if reference_hashes is not None:
                    reference_digest=reference_hashes[i]
                    reference=_read_reference(reference_reader,reference_digest,width,height)
                    source_comparisons.append({"frame":i,"codestream_sha256":expected,
                        "source_xyz12_sha256":reference_digest,
                        "source_to_openjpeg":compare_xyz12(reference,pixels),
                        "source_to_jasper":compare_xyz12(reference,second_pixels)})
                    del reference
                (root/second_out).unlink()
            j2k.unlink();(root/out).unlink()
        unwrap.run(["-d",str(expected_frames),"sound.mxf","audio"],
                   cwd=root,timeout=3600)
        # CineCert WavFileWriter::ST_NONE writes exactly file_prefix
        # (no automatically appended .wav extension).
        audio=root/"audio"
        if not audio.is_file() or _linked_entry(audio):
            raise RuntimeError("Real MXF sound unwrap did not create PCM WAV")
        source_pcm=_read_pcm24(audio,expected_frames)
        if _hash_bytes(source_pcm)!=expected_sound_pcm_sha256:
            raise RuntimeError("Real sound MXF altered source-approved PCM")
        def aggregate(rows):
            return summarize_xyz12(rows,expected_frames=expected_frames,pixels_per_frame=width*height)
        return {
            "format":FORMAT,"status":"ALL_NATIVE_ESSENCE_ROUNDTRIPPED",
            "frames_decoded":expected_frames,
            "decoded_frame_sha256":decoded_hashes,
            "picture_exact_codestream_sha_verified":True,
            "cinema_rate_constraints":rate_audit.finish(expected_frames),
            "pcm24_48000_sample_exact":True,
            "pcm_channel_count":len(source_pcm)//(expected_frames*2000*3),
            "pcm_sample_frames_per_channel":expected_frames*2000,
            "minimum_one_second_track_duration_verified":expected_frames>=24,
            "independent_second_decoder_verified":second_decoder is not None and len(dual_receipts)==expected_frames,
            "second_decoder_comparisons":dual_receipts,
            "second_decoder_summary":aggregate(dual_receipts) if second_decoder is not None else None,
            "source_xyz12_comparisons":source_comparisons,
            "source_xyz12_comparison_complete":reference_hashes is not None and len(source_comparisons)==expected_frames,
            "source_xyz12_summary":{k:aggregate(x[k] for x in source_comparisons) for k in ("source_to_openjpeg","source_to_jasper")} if reference_hashes is not None else None,
            "second_decoder_exact_agreement":bool(dual_receipts) and all(x["exact_decoder_agreement"] for x in dual_receipts),
            "second_decoder_reference_tolerance_verified":False,
            "second_decoder_iso_conformance_verified":False,
            "source_color_fidelity_verified":False,
            "theatrical_audio_channel_mapping_verified":False,
            "verified_source_sound_pcm_sha256":_hash_bytes(source_pcm),
            "asdcplib_unwrap_sha256":unwrap.sha256,
            "openjpeg_decoder_sha256":decoder.sha256,
            "reopened_package_integrity_verified":True,
            "formal_independent_dci_validator_passed":False,
            "physical_projection_accepted":False,
            "production_dcp_accepted":False,
            "original_source_modified":False,
            "ffmpeg_used":False,
        }


def decode_full_multireel_candidate(folder,*,unwrap,decoder,expected_reels,profile="2K_FLAT_24",second_decoder=None,reference_reader=None):
    """Decode every ordered feature track with the existing bounded native stage.

    Trusted caller supplies exact CPL reel asset IDs and codestream/PCM
    digests, not a claim derived from the output itself.
    """
    from copy import deepcopy
    if (unwrap.product!="ASDCP-asdcp_unwrap" or decoder.product!="OpenJPEG-opj_decompress"
            or profile not in PROFILES or type(expected_reels) is not list
            or not 2<=len(expected_reels)<=1000):
        raise PermissionError("Exact bounded native feature decode authority required")
    _verify_decoders(unwrap,decoder,second_decoder)
    expected=deepcopy(expected_reels)
    if reference_reader is not None and second_decoder is None:
        raise PermissionError("Source comparison qualification requires both decoders")
    keys={"picture_uuid","sound_uuid","frames","ordered_codestream_sha256","pcm_sha256"}
    if reference_reader is not None:keys.add("ordered_xyz12_sha256")
    for part in expected:
        if (type(part) is not dict or set(part)!=keys or
            type(part["frames"]) is not int or not 3<=part["frames"]<=MAX_REEL_FRAMES):
            raise PermissionError("Exact ordered reel decode scope required")
        part["ordered_codestream_sha256"],part["pcm_sha256"]=_approved_digest_ledger(
            part["ordered_codestream_sha256"],part["pcm_sha256"],part["frames"])
        part["reference_hashes"]=_reference_ledger(part.get("ordered_xyz12_sha256"),reference_reader,part["frames"])
    audit=inspect_dcp_structure(folder)
    if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
            audit["reel_count"]!=len(expected) or len(audit["tracks"])!=2*len(expected)):
        raise PermissionError("Feature package does not match approved reel count")
    all_ids=[x["asset_id"] for x in audit["tracks"]]
    all_names=[x["filename"].casefold() for x in audit["tracks"]]
    if len(set(all_ids))!=len(all_ids) or len(set(all_names))!=len(all_names):
        raise PermissionError("Feature track identities must be distinct")
    reports=[]
    for n,part in enumerate(expected):
        tracks=audit["tracks"][2*n:2*n+2]
        assets=_single_reel_tracks(tracks)
        if (assets["picture"]["asset_id"]!=part["picture_uuid"] or
            assets["sound"]["asset_id"]!=part["sound_uuid"] or
            audit["reel_durations"][n]!=part["frames"]):
            raise PermissionError("Approved feature reel identity/order changed")
        reports.append(_decode_reel_tracks(folder,audit,tracks,unwrap=unwrap,decoder=decoder,
            expected_picture_codestream_sha256=part["ordered_codestream_sha256"],
            expected_sound_pcm_sha256=part["pcm_sha256"],profile=profile,expected_frames=part["frames"],second_decoder=second_decoder,reference_hashes=part["reference_hashes"],reference_reader=reference_reader))
    if len({r["cinema_rate_constraints"]["wavelet_levels"] for r in reports})!=1:
        raise ValueError("Wavelet level count differs across feature reels")
    if inspect_dcp_structure(folder)!=audit:
        raise PermissionError("Feature package changed during native verification")
    frames=sum(x["frames_decoded"] for x in reports)
    width,height,_=PROFILES[profile]
    def feature_summary(rows):
        return summarize_xyz12(rows,expected_frames=frames,pixels_per_frame=width*height)
    if len({r["pcm_channel_count"] for r in reports})!=1:
        raise ValueError("PCM channel count differs across feature reels")
    return {"status":"ALL_NATIVE_FEATURE_ESSENCE_ROUNDTRIPPED","reel_count":len(reports),
            "frames_decoded":sum(x["frames_decoded"] for x in reports),
            "reels":reports,"all_reel_packet_coverage_verified":all(r["cinema_rate_constraints"]["packet_coverage_verified"] for r in reports),
            "all_tracks_minimum_one_second_verified":all(r["minimum_one_second_track_duration_verified"] for r in reports),
            "all_reels_pcm24_sample_exact":all(r["pcm24_48000_sample_exact"] for r in reports),
            "pcm_channel_count":reports[0]["pcm_channel_count"],
            "pcm_sample_frames_per_channel":sum(r["pcm_sample_frames_per_channel"] for r in reports),
            "theatrical_audio_channel_mapping_verified":False,
            "all_reels_independent_second_decoder_verified":all(r["independent_second_decoder_verified"] for r in reports),
            "all_reels_second_decoder_exact_agreement":all(r["second_decoder_exact_agreement"] for r in reports),
            "feature_second_decoder_summary":feature_summary(x for r in reports for x in r["second_decoder_comparisons"]) if second_decoder is not None else None,
            "all_reels_source_xyz12_comparison_complete":all(r["source_xyz12_comparison_complete"] for r in reports),
            "feature_source_xyz12_summary":{k:feature_summary(x[k] for r in reports for x in r["source_xyz12_comparisons"]) for k in ("source_to_openjpeg","source_to_jasper")} if reference_reader is not None else None,
            "production_dcp_accepted":False}
