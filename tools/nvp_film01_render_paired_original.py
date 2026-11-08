"""FILM01 native paired artist review: ONE frozen OpenUSD project, TWO looks.

Full technical comparison intentionally uses the SAME immutable source
project/edit and original PCM for both renders. Independent CI projects
are NOT source-identical simply because their scripts are similar.
Does not claim cinema final approval, installed player verification or DCP.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review,FRAMES)
from backend.nvp_film01_native_avi import mux_original_native_avi
from tools.nvp_film01_native_visual_audio_qc import inspect_original_nvp_film
from tools.nvp_film01_compare_rendered_light import compare_native_light_versions

FORMAT="nvp.film01.30s.one_locked_source_two_artist_looks.v1"


def render_paired_original(source_root,output_dir,*,create_source=True):
    root=Path(source_root)
    dest=Path(output_dir)
    if (not root.is_absolute() or not dest.is_absolute() or
            root==dest or dest.exists() or dest.is_symlink()):
        raise PermissionError("Paired review needs a fresh absolute output folder")
    if type(create_source) is not bool:
        raise ValueError("Explicit original source creation intent required")
    if create_source:
        report=write_original_30s_source(
            root,approve_test_only=True)
    else:
        if not root.is_dir():
            raise FileNotFoundError("Pinned original source project unavailable")
        report=json.loads(
            (root/"original-source-report.json").read_text(encoding="utf-8"))
    if (report.get("target_frames")!=FRAMES or
            report.get("source_takes_frozen_and_verified") is not True or
            report.get("photorealistic_story_quality_approved") is not False):
        raise PermissionError("Not the genuine original bounded source film")
    dest.mkdir(parents=True,mode=0o700)
    images={}
    for name,light in (("baseline",False),("digital_gold_sun",True)):
        zip_path=dest/(name+".source_png_pcm.zip")
        movie=dest/(name+".playable_mjpeg_pcm.avi")
        qc=dest/(name+".visual_audio_qc.json")
        export=render_original_30s_review(
            root,zip_path,max_frames=FRAMES,apply_virtual_fx=light)
        if export["complete_720_frame_source_preview"] is not True:
            raise RuntimeError("Source preview not fully rendered")
        avi=mux_original_native_avi(
            zip_path,movie,expected_frames=FRAMES)
        if (avi["frames"]!=FRAMES or
                avi["playable_avi_container_written"] is not True or
                avi["creative_quality_approved"] is not False):
            raise RuntimeError("Not a native original playable 30-second AVI")
        review=inspect_original_nvp_film(
            zip_path,qc)
        if (review["virtual_fx_enabled"] is not light or
                review["human_visual_judgment_required"] is not True):
            raise RuntimeError("Artist light mode not confirmed in native QC")
        with ZipFile(zip_path) as original:
            source_manifest=json.loads(original.read(
                "original_30s_preview_receipt.json"))
        images[name]={
            "source_png_pcm":str(zip_path),"playable_review_avi":str(movie),
            "movie_SHA256":avi["file_sha256"],
            "original_source_WAV_SHA256":source_manifest["audio_wav_sha256"],
            "quality_control":str(qc),
            "frames":avi["frames"],
            "original_frozen_edit_sha256":report["edit_sha256"],
            "virtual_digital_lighting":light,
        }
    contact=dest/"baseline_vs_digital_gold_sun.side_by_side.png"
    comparison=dest/"baseline_vs_digital_gold_sun.metrics.json"
    compared=compare_native_light_versions(
        Path(images["baseline"]["source_png_pcm"]),
        Path(images["digital_gold_sun"]["source_png_pcm"]),
        contact,comparison)
    if (compared["original_take_and_film_time_are_identical"] is not True or
            compared["original_sound_pcm_identical"] is not True or
            compared["all_720_frames_source_provenance_paired"] is not True or
            compared["real_pixels_modified_by_artist_lighting"] is not True):
        raise PermissionError("Two 30-second looks did not use identical original film")
    result={
        "format":FORMAT,"source_project_id":report["project_id"],
        "source_edit_sha256":report["edit_sha256"],
        "duration_seconds":30,"picture_fps":24,
        "same_original_project_edit_and_pcm_for_both_looks":True,
        "baseline":images["baseline"],
        "digital_gold_sun":images["digital_gold_sun"],
        "contact_sheet":str(contact),
        "look_comparison_report":str(comparison),
        "original_source_artifacts_present":True,
        "artistic_visual_quality_accepted":False,
        "external_installed_player_watched":False,
        "theatrical_DCI_validated":False,
    }
    (dest/"paired-original-30s-report.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",type=Path,required=True)
    cli.add_argument("--out-dir",type=Path,required=True)
    cli.add_argument("--consent",required=True)
    args=cli.parse_args()
    if args.consent!="I_APPROVE_DISPOSABLE_ORIGINAL_30S_CI_SOURCE":
        cli.error("Only test-authorized fresh original source accepted")
    result=render_paired_original(
        args.root.resolve(),args.out_dir.resolve())
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
