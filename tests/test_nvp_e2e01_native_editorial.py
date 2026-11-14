"""NVP-E2E-01A: real native editorial acceptance through Studio + FilmIndex.

This is a first integrated alpha *technical* gate, not an assertion that the
desktop UI or approved AUDIO-01J/K movie delivery chain is complete.

Creates two real ProRes/PCM24 MOV source clips, imports their exact bytes into
FilmIndex, commits a source-dependent edit, renders a 24-frame cut from the
indexed sources with genuine FFmpeg, commits derived media, restarts the studio,
independently rehashes all media, and rejects corrupted output.

FFmpeg in this test is a technical test driver, not NVP's authorized/contained
production render worker. A separate gate must exercise that worker.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex


def required_binary(name):
    binary=shutil.which(name)
    if not binary:
        raise RuntimeError("NVP-E2E-01 requires actual native executable: "+name)
    return binary


def checked(argv, *, timeout=180):
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=timeout,check=False)
    if result.returncode:
        raise RuntimeError("Real native editorial command failed: "+
                           result.stderr.decode("utf-8","replace")[-2000:])
    return result.stdout


def make_source(ffmpeg,dest,frequency):
    checked([ffmpeg,"-nostdin","-hide_banner","-v","error","-xerror","-y",
        "-f","lavfi","-i","testsrc2=size=160x90:rate=24:duration=1",
        "-f","lavfi","-i",f"sine=frequency={frequency}:sample_rate=48000:duration=1",
        "-map","0:v:0","-map","1:a:0",
        "-c:v","prores_ks","-profile:v","3","-pix_fmt","yuv422p10le",
        "-r","24","-c:a","pcm_s24le","-ar","48000","-ac","2",
        "-frames:v","24","-f","mov",str(dest)])


def probe(ffprobe,path):
    out=checked([ffprobe,"-v","error","-show_streams","-count_frames",
                 "-of","json",str(path)])
    streams=json.loads(out)["streams"]
    video=[s for s in streams if s.get("codec_type")=="video"]
    audio=[s for s in streams if s.get("codec_type")=="audio"]
    if len(video)!=1 or len(audio)!=1:
        raise RuntimeError("Editorial result must have exactly one video and one audio stream")
    v,a=video[0],audio[0]
    if (v.get("codec_name")!="prores" or
        a.get("codec_name")!="pcm_s24le" or
        a.get("sample_rate")!="48000" or
        a.get("channels")!=2 or
        v.get("avg_frame_rate")!="24/1"):
        raise RuntimeError("Editorial result has incompatible ProRes/PCM24 media")
    return {"frames":int(v["nb_read_frames"]),
            "duration":float(v["duration"]),
            "audio_duration":float(a["duration"])}


def render_edit(ffmpeg,sources,output):
    """Render two 12-frame selections from exact indexed source blobs."""
    filter_graph=(
        "[0:v:0]trim=start_frame=0:end_frame=12,setpts=PTS-STARTPTS[v0];"
        "[0:a:0]atrim=duration=0.5,asetpts=PTS-STARTPTS[a0];"
        "[1:v:0]trim=start_frame=12:end_frame=24,setpts=PTS-STARTPTS[v1];"
        "[1:a:0]atrim=start=0.5:end=1.0,asetpts=PTS-STARTPTS[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    checked([ffmpeg,"-nostdin","-hide_banner","-v","error","-xerror","-y",
             "-i",sources[0],"-i",sources[1],
             "-filter_complex",filter_graph,
             "-map","[v]","-map","[a]",
             "-c:v","prores_ks","-profile:v","3","-pix_fmt","yuv422p10le",
             "-r","24","-c:a","pcm_s24le","-ar","48000","-ac","2",
             "-f","mov",str(output)],timeout=300)


class NativeEditorialE2E(unittest.TestCase):
    def test_import_edit_render_restart_rehash_and_reject_tamper(self):
        ffmpeg=required_binary("ffmpeg")
        ffprobe=required_binary("ffprobe")
        with tempfile.TemporaryDirectory(prefix="nvp-e2e01-") as temp:
            root=Path(temp)
            database=root/"studio.sqlite3"
            studio=Studio(database)
            project=studio.create_project(
                "E2E-01 Real Two Shot Film","Import edit render restart")
            pid=project["id"]
            script="INT. EDIT SUITE - DAY\\n\\nA short NVP alpha acceptance film."
            saved=studio.save_screenplay(pid,script,expected_revision=0)
            self.assertEqual(saved["revision"],1)
            self.assertEqual(len(saved["scenes"]),1)
            index=FilmIndex(studio)
            self.assertEqual(len(studio.list_projects()),1)

            indexed=[]
            source_ids=["source_a","source_b"]
            for i,(asset_id,freq) in enumerate(zip(source_ids,(330,660))):
                mov=root/f"source{i}.mov"
                make_source(ffmpeg,mov,freq)
                source_proof=probe(ffprobe,mov)
                self.assertEqual(source_proof["frames"],24)
                media=index.put_media_file(pid,mov,"video/quicktime")
                doc=index.register_revision(pid,asset_id,"asset",{
                    "format":"nvp.e2e01.import.v1",
                    "source_sha256":media["sha256"],
                    "source_frames":24,
                    "codec":"prores_pcm24"
                },expected_revision=0,dependencies=[])
                self.assertEqual(index.read_revision(pid,asset_id,1)["data"]["source_sha256"],media["sha256"])
                indexed.append(index.verify_media_file(
                    pid,media["sha256"],"video/quicktime"))
                mov.unlink()

            edit=index.register_revision(pid,"edit01","edit",{
                "format":"nvp.e2e01.technical_edit.v1",
                "fps":24,"frames":24,
                "selections":[
                    {"source_id":"source_a","start_frame":0,"frames":12},
                    {"source_id":"source_b","start_frame":12,"frames":12}
                ],
                "creator_approved_final_master":False
            },expected_revision=0,dependencies=[
                {"object_id":"source_a","revision":1,"role":"asset"},
                {"object_id":"source_b","revision":1,"role":"asset"}
            ])
            self.assertEqual(len(edit["dependencies"]),2)
            output=root/"preview.mov"
            render_edit(ffmpeg,[entry["path"] for entry in indexed],output)
            av=probe(ffprobe,output)
            self.assertEqual(av["frames"],24)
            self.assertAlmostEqual(av["duration"],1.0,delta=0.05)
            self.assertAlmostEqual(av["audio_duration"],1.0,delta=0.05)
            delivered=index.put_media_file(pid,output,"video/quicktime")
            exported=index.register_revision(pid,"preview01","presentation",{
                "format":"nvp.e2e01.technical_preview.v1",
                "movie_sha256":delivered["sha256"],
                "frames":24,
                "source_edit_sha256":edit["document_sha256"],
                "approved_final_master":False,"dcp_delivered":False
            },expected_revision=0,dependencies=[
                {"object_id":"edit01","revision":1,"role":"timeline"}])
            output.unlink()

            # A new Studio and FilmIndex instance is the essential durability gate.
            del index,studio
            reopened=Studio(database)
            reopened_index=FilmIndex(reopened)
            self.assertEqual(reopened.get_project(pid)["title"],
                             "E2E-01 Real Two Shot Film")
            self.assertEqual(reopened.get_project(pid)["screenplay"],script)
            self.assertEqual(reopened.get_project(pid)["revision"],1)
            with self.assertRaises(RuntimeError):
                reopened.save_screenplay(pid,"stale overwrite",expected_revision=0)
            after_edit=reopened_index.read_revision(pid,"edit01",1)
            after_export=reopened_index.read_revision(pid,"preview01",1)
            self.assertEqual(after_export["document_sha256"],
                             exported["document_sha256"])
            self.assertEqual(after_edit["document_sha256"],
                             edit["document_sha256"])
            self.assertEqual(after_export["dependencies"][0]["object_id"],"edit01")
            for asset_id,media in zip(source_ids,indexed):
                self.assertEqual(
                    reopened_index.read_revision(pid,asset_id,1)["data"]["source_sha256"],
                    media["sha256"])
                reopened_index.verify_media_file(pid,media["sha256"],"video/quicktime")
            final=reopened_index.verify_media_file(
                pid,delivered["sha256"],"video/quicktime")
            self.assertEqual(probe(ffprobe,final["path"])["frames"],24)
            self.assertFalse(after_export["data"]["approved_final_master"])
            self.assertFalse(after_export["data"]["dcp_delivered"])
            with self.assertRaises(RuntimeError):
                reopened_index.register_revision(pid,"preview01",
                    "presentation",{"format":"nvp.e2e01.illegal_replay.v1"},
                    expected_revision=0,dependencies=[])
            # Deliberately change actual content-addressed stored media.
            with open(final["path"],"r+b") as media_file:
                media_file.seek(4096)
                original=media_file.read(1)
                media_file.seek(4096)
                media_file.write(bytes([original[0]^0x01]))
                media_file.flush()
            with self.assertRaisesRegex(RuntimeError,"integrity"):
                reopened_index.verify_media_file(
                    pid,delivered["sha256"],"video/quicktime")


if __name__=="__main__":
    unittest.main()
