"""USD-FILM-01F native source-to-real Blender/Cycles original world Take checks.

Only a real NVP original 30s USD film source with two different world Takes,
original actor meshes, verified original PCM and source cameras. Independent
Blender render/reopen requires NVP_FILM01F_BLENDER_BIN in native CI.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from pxr import Sdf, Usd, UsdGeom
from PIL import Image

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_story_bible import StoryBible
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import FilmWorldShotPlanner
from backend.nvp_usd_film01e_world_take import OpenUSDWorldTakeCapture
from backend.nvp_usd_film01f_blender_host import (
    _snapshot_usd, ReviewedWorldTakeCyclesHost)
from backend.nvp_usd_film01f_original_audio import render_original_source_stems
from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
from tools.nvp_film01_original_30s import write_original_30s_source


class OriginalTwoShotWorldTakeSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-film01f-real-world-")
        cls.root=Path(cls.tmp.name).resolve()
        original=write_original_30s_source(
            cls.root/"original",approve_test_only=True)
        cls.pid=original["project_id"]
        cls.studio=Studio(cls.root/"original"/"short.sqlite3")
        cls.index=FilmIndex(cls.studio)
        cls.original=original
        cls.shots=(original["shots"][0],original["shots"][2])
        cls.names=("Opening","Rekindle")
        cls.ids=("FirstWorldTake","SecondWorldTake")
        world=OpenUSDWorldComposer(cls.index)
        cls.world=world.publish(
            cls.pid,"SharedOriginalWorld",
            sets=[
                {"name":name,"scene_id":"Relay30Scene",
                 "scene_revision":row["scene_revision"]}
                for name,row in zip(cls.names,cls.shots)],
            props=[],variants=[],instancers=[])
        bible=StoryBible(cls.studio)
        registry=ProductionBibleActors(cls.studio)
        original_roles=(
            ("DONUT","/World/Engineer"),
            ("BOX","/World/CrossingBox"),
            ("SPHERE","/World/PassingSphere"),
            ("SERVICE CRAFT","/World/ServiceCraft"),
        )
        cast={label:bible.create_entity(
            cls.pid,"character","ORIGINAL "+label)["id"]
            for label,_ in original_roles}
        for row in cls.shots:
            for label,path in original_roles:
                aid=cast[label]
                current=registry.actor(cls.pid,aid)
                registry.link(
                    cls.pid,aid,role="actor_prim",
                    source_family="filmindex",
                    target_id=row["take_id"],target_revision=1,
                    actor_prim_path=path,
                    expected_actor_revision=current["bible_revision"],
                    director_note="Source-authentic CI object-actor multi-shot casting")
            complete=registry.require_complete_cast(cls.pid,row["take_id"])
            if len(complete["actor_id_by_prim"])!=4:
                raise RuntimeError("Original source lacks four authentic ActorID cast links")
        planner=FilmWorldShotPlanner(cls.index)
        writer=OpenUSDWorldTakeCapture(
            cls.index,verify_creator_action=lambda event,scope:
                event=="AUTHORIZE_ORIGINAL_TEST_WORLD_TAKE" and
                scope["operation"]=="nvp.freeze.usd_film01e_world_take.v1")
        cls.take_shas=[]
        cls.original_take_shas=[]
        for i,(name,row,take_id) in enumerate(zip(
                cls.names,cls.shots,cls.ids)):
            shot_id="WorldCameraShot"+str(i)
            planner.publish(
                cls.pid,shot_id,world_id="SharedOriginalWorld",
                world_revision=1,camera_set=name,
                camera_prim="/World/Camera",
                sample_ticks=[0,5*T,9*T],
                required_sets=[name],max_loaded_sets=1)
            original_take=cls.index.read_revision(
                cls.pid,row["take_id"],1)
            cls.original_take_shas.append(original_take["document_sha256"])
            saved=writer.freeze(
                cls.pid,take_id,world_id="SharedOriginalWorld",
                world_revision=1,shot_id=shot_id,shot_revision=1,
                scene_takes=[{
                    "set":name,"take_id":row["take_id"],
                    "take_sha256":original_take["document_sha256"]}],
                creator_event="AUTHORIZE_ORIGINAL_TEST_WORLD_TAKE")
            cls.take_shas.append(saved["document_sha256"])
            if writer.verify_take(cls.pid,take_id)["canonical_actor_count"]!=4:
                raise RuntimeError("Original world Take has incomplete actor source")
        cls.cast=cast

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_independently_flattened_original_native_usd_frames(self):
        source_frames=[]
        for i,take_id in enumerate(self.ids):
            work=self.root/("source-probe-"+str(i))
            work.mkdir(exist_ok=True)
            row=_snapshot_usd(self.index,self.pid,take_id,5*T,work)
            source_frames.append(row)
            stage=Usd.Stage.Open(str(work/"source.usda"))
            self.assertEqual(
                row["source_usd_sha256"],sha_file(work/"source.usda"))
            self.assertEqual(row["original_world_sha256"],
                             self.world["document_sha256"])
            self.assertEqual(row["original_world_take_sha256"],
                             self.take_shas[i])
            self.assertEqual(len(row["actor_sources"]),4)
            self.assertEqual(row["original_pcm_source_count"],1)
            self.assertTrue(row["original_sound_not_mixed"])
            self.assertEqual(stage.GetStartTimeCode(),1.0)
            self.assertEqual(stage.GetEndTimeCode(),1.0)
            self.assertTrue(stage.GetPrimAtPath(
                row["original_camera_path"]).IsA(UsdGeom.Camera))
            donut=stage.GetPrimAtPath(
                "/World/Sets/"+self.names[i]+"/Engineer/Geometry")
            self.assertTrue(donut.IsA(UsdGeom.Mesh))
            self.assertEqual(
                len(UsdGeom.Mesh(donut).GetPointsAttr().Get()),504)
            self.assertIn(self.cast["DONUT"],
                          {actor["actor_id"] for actor in row["actor_sources"]})
            self.assertTrue(all(
                stage.GetPrimAtPath(p).IsDefined()
                for actor in row["actor_sources"]
                for p in actor["geometry_prims"]))
        self.assertNotEqual(
            source_frames[0]["original_camera_shot_sha256"],
            source_frames[1]["original_camera_shot_sha256"])
        self.assertNotEqual(
            source_frames[0]["source_usd_sha256"],
            source_frames[1]["source_usd_sha256"])
        for row,sha in zip(self.shots,self.original_take_shas):
            self.assertEqual(
                self.index.read_revision(
                    self.pid,row["take_id"],1)["document_sha256"],sha)

    def test_exact_source_timing_and_foreign_world_take_denied(self):
        with TemporaryDirectory(prefix="nvp-01f-refusals-") as temp:
            work=Path(temp)
            with self.assertRaises((RuntimeError,ValueError,PermissionError)):
                _snapshot_usd(self.index,self.pid,self.ids[0],1,work)
            with self.assertRaises((KeyError,PermissionError,RuntimeError)):
                _snapshot_usd(
                    self.index,"another-project",self.ids[0],5*T,work)
        self.assertEqual(
            self.index.read_revision(
                self.pid,self.ids[0],1)["document_sha256"],self.take_shas[0])

    def test_unchanged_original_pcm_while_world_shot_is_render_source(self):
        for i,row in enumerate(self.shots):
            source_take=self.index.read_revision(
                self.pid,row["take_id"],1)
            self.assertEqual(
                source_take["document_sha256"],self.original_take_shas[i])
            composed=self.index.read_revision(
                self.pid,self.ids[i],1)
            self.assertEqual(
                composed["data"]["world_document_sha256"],
                self.world["document_sha256"])
            self.assertGreaterEqual(
                len(composed["data"]["original_timeline_audio_sources"]),1)
            self.assertFalse(composed["data"]["final_audio_mixed"])
            self.assertFalse(composed["data"]["finished_picture_rendered"])

    def test_real_original_pcm_event_stems_keep_exact_film_time_and_wav_bytes(self):
        import wave
        for i,take in enumerate(self.ids):
            folder=self.root/("original-audio-"+str(i))
            row=render_original_source_stems(
                self.index,self.pid,take,folder)
            self.assertEqual(row["world_take_sha256"],self.take_shas[i])
            self.assertTrue(row["actual_original_pcm_readback_verified"])
            self.assertFalse(row["final_picture_sound_mux_verified"])
            stems=row["original_source_stems"]
            self.assertEqual(len(stems),1 if i==0 else 2)
            for item in stems:
                path=folder/item["wave_file"]
                self.assertEqual(item["real_wav_sha256"],sha_file(path))
                self.assertFalse(item["gain_processing_applied"])
                with wave.open(str(path),"rb") as wav:
                    self.assertEqual(wav.getframerate(),48000)
                    self.assertEqual(wav.getnchannels(),1)
                    self.assertEqual(wav.getsampwidth(),2)
                    self.assertEqual(wav.getnframes(),item["sample_count"])
                    essence=sha256()
                    while True:
                        data=wav.readframes(8192)
                        if not data:
                            break
                        essence.update(data)
                    self.assertEqual(
                        essence.hexdigest(),item["original_pcm_essence_sha256"])

    def test_actual_two_original_shot_cycles_frames_and_fresh_reopen(self):
        executable=os.environ.get("NVP_FILM01F_BLENDER_BIN")
        if not executable:
            self.skipTest("Real Blender 5.2 worker supplied only in dedicated native CI")
        binary=Path(executable).resolve(strict=True)
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,check=True,timeout=30).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        with TemporaryDirectory(prefix="nvp-01f-blender-supervised-") as temp:
            supervisor=BlenderWorkerSupervisor(
                Path(temp)/"workers",
                blender_executable=binary,blender_sha256=sha_file(binary),
                blender_version=version)
            host=ReviewedWorldTakeCyclesHost(
                self.index,supervisor,
                verify_director_action=lambda event,scope:(
                    event=="AUTHORIZE_NATIVE_TWO_SHOT_TEST" and
                    scope["operation"]=="nvp.render.usd_film01f_world_take_pair.v1"
                    and len(set(scope["camera_shot_shas"]))==2))
            result=host.render_pair(
                self.pid,[
                    {"take_id":self.ids[0],"tick":5*T,
                     "job_id":"world_cut_opening"},
                    {"take_id":self.ids[1],"tick":5*T,
                     "job_id":"world_cut_rekindle"},
                ],director_event="AUTHORIZE_NATIVE_TWO_SHOT_TEST")
            self.assertEqual(
                result["state"],"RENDERED_TWO_UNAPPROVED_WORLD_SHOT_FRAMES")
            self.assertTrue(result["independent_blender_reopen_verified"])
            self.assertTrue(result["original_source_takes_unchanged"])
            self.assertFalse(result["human_photorealism_accepted"])
            self.assertFalse(result["final_audio_mix_verified"])
            destination=Path(os.environ.get(
                "NVP_FILM01F_ARTIFACT_DIR",str(Path(temp)/"artifacts"))).resolve()
            destination.mkdir(parents=True,exist_ok=True)
            png_hashes=[]
            for i,render in enumerate(result["shots"]):
                job=render["job_dir"]
                photo=job/"frame.png"
                self.assertTrue(photo.is_file())
                with Image.open(photo) as pixels:
                    self.assertEqual(pixels.size,(320,180))
                    pixels.verify()
                self.assertTrue(render["audit"]["actual_native_cycles_image"])
                self.assertTrue(render["independent_reopen_audit"][
                    "real_saved_usd_actor_objects_reopened"])
                self.assertEqual(
                    render["independent_reopen_audit"]["source_blend_sha256"],
                    sha_file(job/"scene.blend"))
                png_hashes.append(sha_file(photo))
                source_sound=render["original_audio_source_receipt"]
                self.assertTrue(source_sound["actual_original_pcm_readback_verified"])
                self.assertGreaterEqual(len(source_sound["original_source_stems"]),1)
                (destination/("cut"+str(i)+"_original_audio.json")).write_text(
                    json.dumps(source_sound,sort_keys=True,indent=2),"utf8")
                for stem in source_sound["original_source_stems"]:
                    shutil.copyfile(
                        job/"original_audio"/stem["wave_file"],
                        destination/("cut"+str(i)+"_"+stem["wave_file"]))
                for name in ("frame.png","scene.blend","source.usda",
                             "source.json","audit.json"):
                    shutil.copyfile(job/name,destination/("cut"+str(i)+"_"+name))
                shutil.copyfile(
                    render["independent_reopen_dir"]/"audit.json",
                    destination/("cut"+str(i)+"_independent_reopen.json"))
            (destination/"two_cut_proof.json").write_text(json.dumps({
                "actual_native_cycles_frames":2,
                "independent_real_blender_scene_reopens":2,
                "source_world_sha256":self.world["document_sha256"],
                "original_source_takes":self.take_shas,
                "rendered_png_sha256":png_hashes,
                "original_pcm_wav_source_stems_independently_verified":True,
                "test_only_original_pcm_not_mixed":True,
                "film_master_ready":False,
                "photorealism_approved":False,
            },indent=2,sort_keys=True),"utf8")


if __name__=="__main__":
    unittest.main()
