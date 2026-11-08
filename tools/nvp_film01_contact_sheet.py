"""FILM01 contact sheet from exactly the original rendered OpenUSD frames.

Only genuine hash-verified PNGs in a completed 720-frame NVP source
archive may be used. This is a visual inspection derivative, not
generated story art, native scene source or film playback.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile
from PIL import Image,ImageDraw,ImageStat

FORMAT="nvp.film01.verified_original_frame_contact_sheet.v1"
SELECTED=(0,96,239,240,360,479,480,624,719)
THUMB=(320,180)
SPACING=16
HEADER=27
BG=(22,23,30)
OUTPUT_SIZE=(3*THUMB[0]+4*SPACING,
             3*(THUMB[1]+HEADER)+4*SPACING)


def create_original_contact_sheet(source_zip,output_png,receipt_json):
    source=Path(source_zip)
    target=Path(output_png)
    proof=Path(receipt_json)
    for path in (target,proof):
        if not path.is_absolute() or path.exists() or path.is_symlink():
            raise PermissionError("Contact sheet needs fresh absolute output paths")
    if not source.is_absolute() or not source.is_file() or source.is_symlink():
        raise PermissionError("Only an actual completed original NVP source may be viewed")
    tiles=[]
    with ZipFile(source,"r") as z:
        manifest=json.loads(z.read("original_30s_preview_receipt.json"))
        if (manifest["all_720_frames_really_rendered"] is not True or
                manifest["frames_rendered_from_usd"]!=720 or
                len(manifest["frame_receipts"])!=720 or
                manifest["dci_master_or_dcp_created"] is not False):
            raise PermissionError("Only complete original 720-frame source review accepted")
        for frame in SELECTED:
            row=manifest["frame_receipts"][frame]
            if row["frame_zero"]!=frame or not row["original_source_take_sha256"]:
                raise PermissionError("Story source frame order/provenance missing")
            raw=z.read(f"preview_frames/frame_{frame:04d}.png")
            if sha256(raw).hexdigest()!=row["frame_png_sha256"]:
                raise PermissionError("Original OpenUSD frame pixels changed")
            with Image.open(BytesIO(raw)) as im:
                im.load()
                if im.format!="PNG" or im.mode!="RGB" or im.size!=(640,360):
                    raise RuntimeError("Unexpected original scene image geometry")
                brightness=ImageStat.Stat(im).mean
                tile=im.resize(THUMB,resample=Image.Resampling.LANCZOS)
                tiles.append((frame,tile.copy(),row,
                              [round(v,2) for v in brightness]))
    out=Image.new("RGB",OUTPUT_SIZE,BG)
    draw=ImageDraw.Draw(out)
    original_start_takes={
        row["original_source_take_sha256"] for frame,_,row,_ in tiles
        if frame in (0,240,480)
    }
    if len(original_start_takes)!=3:
        raise RuntimeError("Original short contact sheet lacks three pinned source Takes")
    seen=[]
    for i,(frame,tile,row,brightness) in enumerate(tiles):
        column=i%3;line=i//3
        x=SPACING+column*(THUMB[0]+SPACING)
        y=SPACING+line*(THUMB[1]+HEADER+SPACING)
        out.paste(tile,(x,y))
        draw.text((x,y+THUMB[1]+5),
                  f"{frame:03d} | {row['source_segment_id']} | {frame/24:.2f}s",
                  fill=(240,240,245))
        seen.append({
            "frame_zero":frame,"source_segment_id":row["source_segment_id"],
            "original_take_sha256":row["original_source_take_sha256"],
            "source_frame_sha256":row["frame_png_sha256"],
            "original_scene_mean_RGB_8bit":brightness,
        })
    temp=target.with_name(target.name+".partial")
    if temp.exists() or temp.is_symlink():
        raise FileExistsError("Old partial source contact sheet exists")
    out.save(temp,format="PNG")
    with Image.open(temp) as check:
        check.load()
        if check.format!="PNG" or check.size!=OUTPUT_SIZE:
            raise RuntimeError("Contact sheet PNG could not be reopened")
    temp.rename(target)
    result={
        "format":FORMAT,
        "input_source_zip_sha256":sha256(source.read_bytes()).hexdigest(),
        "contact_sheet_sha256":sha256(target.read_bytes()).hexdigest(),
        "contact_sheet_dimensions":list(OUTPUT_SIZE),
        "verified_actual_usd_source_tiles":seen,
        "native_film_frames_original":True,
        "verified_three_separate_frozen_scene_takes":True,
        "original_pixel_sha_diversity_sample":len({
            x["source_frame_sha256"] for x in seen}),
        "appearance_and_creative_quality_not_algorithmically_graded":True,
        "storyboard_is_playable_video":False,
        "representative_images_only":True,
        "light_fx_already_applied":False,
        "artistic_quality_accepted":False,
        "independent_artist_review_required":True,
    }
    proof.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return result
