"""Compare actual baseline and artistic-lit NVP original FILM01 720-frame renders.

Both archives must independently prove genuine complete original OpenUSD
sources, EXACT SAME editorial Take/PCM, and different picture pixels.
Writes an artistic review contact sheet side-by-side, not a manufactured
new movie or DCI pass. This comparison runs when BOTH native artifacts exist.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image,ImageDraw

FORMAT="nvp.film01.real_visual_baseline_vs_virtual_lighting.v1"
FRAMES=720
SELECTED=(0,60,239,240,360,479,480,624,719)
THUMB=(320,180)


def compare_native_light_versions(baseline,fx_version,output_png,output_report):
    b=Path(baseline);f=Path(fx_version)
    png=Path(output_png);report=Path(output_report)
    if not all(x.is_absolute() for x in (b,f,png,report)):
        raise ValueError("Absolute immutable source and output paths required")
    if not (b.is_file() and f.is_file()) or b.is_symlink() or f.is_symlink():
        raise FileNotFoundError("Both genuine complete original film renders required")
    if any(x.exists() or x.is_symlink() for x in (png,report)):
        raise PermissionError("Do not overwrite earlier director lighting review")
    panels=[]
    with ZipFile(b) as base,ZipFile(f) as artist:
        a=json.loads(base.read("original_30s_preview_receipt.json"))
        z=json.loads(artist.read("original_30s_preview_receipt.json"))
        if any(receipt.get("all_720_frames_really_rendered") is not True or
               receipt.get("frames_rendered_from_usd")!=FRAMES or
               len(receipt.get("frame_receipts",[]))!=FRAMES or
               receipt.get("exact_pcm_samples")!=1440000
               for receipt in (a,z)):
            raise PermissionError("Cannot compare incomplete source-frame films")
        if (a.get("virtual_gold_and_sun_fx_applied_to_render") is not False or
                z.get("virtual_gold_and_sun_fx_applied_to_render") is not True):
            raise PermissionError("Source films are not baseline and virtual-light treatment")
        if (a["edit_sha256"]!=z["edit_sha256"] or
                a["audio_wav_sha256"]!=z["audio_wav_sha256"]):
            raise PermissionError("Cinematic comparison uses different editorial cut or sound")
        for i,(br,fx) in enumerate(zip(a["frame_receipts"],z["frame_receipts"])):
            if (br["frame_zero"]!=i or fx["frame_zero"]!=i or
                    br["original_source_take_sha256"]!=
                    fx["original_source_take_sha256"] or
                    br["source_film_tick"]!=fx["source_film_tick"] or
                    br["source_segment_id"]!=fx["source_segment_id"] or
                    fx.get("virtual_light_shader_used") is not True or
                    br.get("virtual_light_shader_used") is True):
                raise PermissionError("Original picture/time source differs between looks")
        base_wav=base.read("audio/original_source_review_48k_mono.wav")
        virtual_wav=artist.read("audio/original_source_review_48k_mono.wav")
        if base_wav!=virtual_wav or sha256(base_wav).hexdigest()!=a["audio_wav_sha256"]:
            raise PermissionError("Direct lighting changed the original recorded audio")
        for i in SELECTED:
            views=[]
            for archive,rec in ((base,a),(artist,z)):
                row=rec["frame_receipts"][i]
                raw=archive.read(f"preview_frames/frame_{i:04d}.png")
                if sha256(raw).hexdigest()!=row["frame_png_sha256"]:
                    raise PermissionError("Original compared source PNG changed")
                with Image.open(BytesIO(raw)) as im:
                    im.load()
                    if im.size!=(640,360) or im.mode!="RGB":
                        raise PermissionError("Not a native original RGB preview frame")
                    views.append(np.asarray(im,dtype=np.int16))
            x,y=views
            difference=np.abs(y-x)
            delta={
                "frame_zero":i,
                "original_segment_id":a["frame_receipts"][i]["source_segment_id"],
                "baseline_png_sha256":a["frame_receipts"][i]["frame_png_sha256"],
                "virtual_png_sha256":z["frame_receipts"][i]["frame_png_sha256"],
                "RGB_mean_delta_8bit":[round(float(d),3)
                  for d in np.mean(y.astype(np.float32)-x,axis=(0,1))],
                "mean_absolute_RGB_8bit_change":round(float(
                    np.mean(difference)),4),
                "fraction_pixels_changed_gt_8bit":round(float(
                    np.mean(np.any(difference>8,axis=2))),6),
            }
            view0=Image.fromarray(x.astype(np.uint8),"RGB").resize(
                THUMB,Image.Resampling.LANCZOS)
            view1=Image.fromarray(y.astype(np.uint8),"RGB").resize(
                THUMB,Image.Resampling.LANCZOS)
            panels.append((view0,view1,delta))
    if not any(x[2]["fraction_pixels_changed_gt_8bit"]>0 for x in panels):
        raise RuntimeError("Digital lighting did not visibly change any original source pixels")
    width=3*(2*THUMB[0]+18)+16
    height=3*(THUMB[1]+38)+16
    img=Image.new("RGB",(width,height),(22,23,30))
    draw=ImageDraw.Draw(img)
    for n,(baseline_tile,fx_tile,delta) in enumerate(panels):
        column=n%3;row=n//3
        x=8+column*(2*THUMB[0]+18)
        y=8+row*(THUMB[1]+38)
        img.paste(baseline_tile,(x,y));img.paste(fx_tile,(x+THUMB[0],y))
        draw.text((x,y+THUMB[1]+4),
                  f"{delta['frame_zero']/24:.2f}s  BASE  |  DIGITAL GOLD / SUN",
                  fill=(245,245,245))
        draw.text((x,y+THUMB[1]+18),
                  f"Pixel change >8: {delta['fraction_pixels_changed_gt_8bit']:.1%}",
                  fill=(180,180,190))
    pending=png.with_name(png.name+".partial")
    if pending.exists() or pending.is_symlink():
        raise FileExistsError("Old partially assembled look comparison exists")
    img.save(pending,format="PNG")
    with Image.open(pending) as check:
        check.load()
        if check.size!=(width,height) or check.format!="PNG":
            raise RuntimeError("Actual before/after comparison could not be reopened")
    pending.rename(png)
    result={
        "format":FORMAT,
        "baseline_source_archive_sha256":sha256(b.read_bytes()).hexdigest(),
        "virtual_light_source_archive_sha256":sha256(f.read_bytes()).hexdigest(),
        "original_edit_sha256":a["edit_sha256"],
        "original_audio_wav_sha256":a["audio_wav_sha256"],
        "original_take_and_film_time_are_identical":True,
        "original_sound_pcm_identical":True,
        "all_720_frames_source_provenance_paired":True,
        "sampled_real_picture_differences":[x[2] for x in panels],
        "side_by_side_contact_sha256":sha256(png.read_bytes()).hexdigest(),
        "real_pixels_modified_by_artist_lighting":True,
        "human_artistic_approval_required":True,
        "physical_bounce_GI_or_DCI_compliance_proven":False,
    }
    report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(
        description="Compare two FULL, genuine NVP original render archives")
    parser.add_argument("--baseline",required=True,type=Path)
    parser.add_argument("--virtual",required=True,type=Path)
    parser.add_argument("--out-png",required=True,type=Path)
    parser.add_argument("--out-report",required=True,type=Path)
    args=parser.parse_args()
    result=compare_native_light_versions(
        args.baseline.resolve(),args.virtual.resolve(),
        args.out_png.resolve(),args.out_report.resolve())
    print(json.dumps({
        "format":result["format"],
        "source_pair_verified":result["original_take_and_film_time_are_identical"],
        "sound_identical":result["original_sound_pcm_identical"],
        "sampled_pixel_differences":result["sampled_real_picture_differences"],
        "artist_approval_required":result["human_artistic_approval_required"],
    },indent=2))


if __name__=="__main__":
    main()
