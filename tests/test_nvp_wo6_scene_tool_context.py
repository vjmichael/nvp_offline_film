"""WO6-03 actual native OpenUSD/source-sound and tool preflight contracts.

Use a REAL OpenUSD scene, source event ledger and frozen Digital Take;
do not mock native visual or PCM evidence. The only short sound block is
original test fixture PCM. This is not final mastered film playback.
"""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_ai_read_host import NativeAiReadHost, TrustedReadScope
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_wo6_scene_context import (
    FORMAT as CONTEXT_FORMAT,assemble_film_crew_context)
from backend.nvp_wo6_tool_readiness import (
    TrustedToolInventory,TrustedNativeToolPin,preflight_tool_inventory)

T=TICKS_PER_SECOND


class NativeSceneCrewContext(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="nvp-wo6-context-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.studio=Studio(self.root/"studio.sqlite3")
        p=self.studio.create_project("Original film","Director authored")
        p=self.studio.save_screenplay(
            p["id"],"INT. ENGINEERING BAY - NIGHT\n\nADA\nThe relay is alive.",
            p["revision"])
        self.pid=p["id"]
        self.script_revision=p["revision"]
        self.script_scene=p["scenes"][0]["id"]
        self.index=FilmIndex(self.studio)
        self.actor_scene=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,3,-8]},
            {"path":"/World/Light","role":"light","position":[2,2,5]},
        ]
        self.curves=[
            {"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[10,0,0]},
            ]},
            {"path":"/World/Camera","samples":[
                {"tick":0,"position":[0,3,-8]},
                {"tick":2*T,"position":[2,3,-8]},
            ]},
        ]
        self.scene=OpenUSDSceneBridge(self.index).publish(
            self.pid,"OriginalScene",prims=self.actor_scene,
            curves=self.curves,native_schemas=True)
        self.sound=RecordedSoundSources(self.index).publish(
            self.pid,"RecordedActorVoice",[b"\x34\x12"*256])
        self.temporal=TemporalLedger(self.index).publish(
            self.pid,"OriginalActions",[
                {"event_id":"Walking","event_kind":"action",
                 "subject_id":"Actor","start_tick":0,"end_tick":2*T,
                 "source_id":"OriginalScene","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Actor","action":"walk"}},
                {"event_id":"Voice","event_kind":"dialogue",
                 "subject_id":"Actor","start_tick":T,"end_tick":2*T,
                 "source_id":"RecordedActorVoice","source_revision":1,
                 "payload":{"line_id":"line001"}},
                {"event_id":"CameraMove","event_kind":"camera",
                 "subject_id":"DirectorCamera","start_tick":0,"end_tick":2*T,
                 "source_id":"OriginalScene","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Camera"}},
            ],duration_tick=3*T)
        self.take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="CI_CREATOR_APPROVED" and
                scope["scene_id"]=="OriginalScene").freeze(
            self.pid,"OriginalTake",scene_id="OriginalScene",
            scene_revision=1,timeline_id="OriginalActions",
            timeline_revision=1,sample_ticks=[0,T,2*T],
            creator_event="CI_CREATOR_APPROVED")

    def context(self,**changes):
        kwargs=dict(source_revision=self.script_revision,
                    screenplay_scene_id=self.script_scene)
        kwargs.update(changes)
        return assemble_film_crew_context(
            self.index,self.pid,"OriginalTake",1,T,**kwargs)

    def test_real_usd_actor_camera_light_motion_and_original_voice_are_grounded(self):
        result=self.context()
        self.assertEqual(result["format"],CONTEXT_FORMAT)
        self.assertEqual(result["source_take"]["document_sha256"],
                         self.take["document_sha256"])
        self.assertTrue(result["source_take"]["independently_reopened"])
        items={i["prim_path"]:i for i in result["visible_scene_prims"]}
        self.assertEqual(set(items),{
            "/World/Actor","/World/Camera","/World/Light"})
        self.assertAlmostEqual(items["/World/Actor"][
            "world_translation"][0],5.0,places=5)
        self.assertAlmostEqual(items["/World/Camera"][
            "world_translation"][0],1.0,places=5)
        self.assertEqual(items["/World/Camera"]["native_schema"]["schema"],
                         "UsdGeom.Camera")
        self.assertEqual(items["/World/Light"]["native_schema"]["schema"],
                         "UsdLux.SphereLight")
        self.assertEqual({e["event_id"] for e in result["active_events"]},
                         {"Walking","Voice","CameraMove"})
        self.assertEqual(result["sound_events"][0]["source_id"],
                         "RecordedActorVoice")
        self.assertTrue(result["sound_events"][0][
            "recorded_sound_pcm_verified"])
        self.assertEqual(result["sound_events"][0]["sample_count"],256)
        self.assertFalse(result["sound_events"][0][
            "mastered_final_audio_verified"])
        self.assertEqual(result["screenplay_scene_context"][
            "source_revision"],self.script_revision)
        self.assertEqual(result["scene_prim_count_omitted"],0)
        self.assertFalse(result["historical_take_not_current_scene"])
        self.assertFalse(result["visual_frames_rendered"])
        self.assertFalse(result["mastered_soundtrack_replayed"])
        self.assertFalse(result["human_artist_approval"])
        self.assertFalse(result["side_effects_performed"])
        import json
        copy=dict(result);actual=copy.pop("context_sha256")
        self.assertEqual(actual,hashlib.sha256(json.dumps(
            copy,sort_keys=True,separators=(",",":"),
            ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest())

    def test_context_exposes_truncated_prims_events_and_missing_screenplay(self):
        result=self.context(source_revision=None,screenplay_scene_id=None,
                            max_prims=1,max_events=1)
        self.assertEqual(result["scene_prim_count_omitted"],2)
        self.assertTrue(result["active_events_truncated"])
        self.assertIsNone(result["screenplay_scene_context"])
        self.assertTrue(result["no_unlisted_actors_or_sound_assumed"])

    def test_historical_frozen_take_still_valid_after_current_scene_revision(self):
        OpenUSDSceneBridge(self.index).publish(
            self.pid,"OriginalScene",prims=self.actor_scene,
            curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[20,0,0]}]}],
            native_schemas=True,expected_revision=1)
        old=self.context()
        self.assertTrue(old["historical_take_not_current_scene"])
        self.assertEqual(old["source_heads"][0]["head_revision_observed"],2)
        self.assertEqual(old["source_heads"][0]["revision"],1)
        self.assertEqual(old["source_take"]["document_sha256"],
                         self.take["document_sha256"])

    def test_invalid_time_stale_script_and_other_project_refused(self):
        with self.assertRaises(ValueError):
            assemble_film_crew_context(
                self.index,self.pid,"OriginalTake",1,3*T)
        with self.assertRaises(ValueError):
            self.context(max_prims=65)
        with self.assertRaises(ValueError):
            self.context(source_revision=None)
        self.studio.save_screenplay(
            self.pid,"INT. ENGINEERING BAY - DAY\n\nADA\nChange.",
            self.script_revision)
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.context()
        with self.assertRaises(KeyError):
            assemble_film_crew_context(
                self.index,self.studio.create_project("Other","")["id"],
                "OriginalTake",1,T)

    def test_temporal_source_tamper_refused_and_no_worker_actions(self):
        with self.studio._connection() as db:
            db.execute("""UPDATE nvp_temporal_events SET payload_json=?
                WHERE project_id=? AND timeline_id=? AND event_id=?""",
                ('{"forged":true}',self.pid,"OriginalActions","Voice"))
        with self.assertRaises(RuntimeError):
            self.context()

    def test_trusted_read_host_rechecks_per_turn_authority_and_rejects_tool_injection(self):
        allowed={"can":True}
        seen=[]
        def approve(scope,cap,digest,req):
            seen.append((scope,cap,digest,req))
            return allowed["can"]
        host=NativeAiReadHost(self.studio,authorize_read=approve)
        request={
            "capability_id":"nvp.film.read_scene_crew_context.v1",
            "project_id":self.pid,
            "take_id":"OriginalTake","take_revision":1,"tick":T,
            "source_revision":self.script_revision,
            "screenplay_scene_id":self.script_scene,
        }
        ids={c["id"] for c in host.catalog()["capabilities"]}
        self.assertIn("nvp.film.read_scene_crew_context.v1",ids)
        self.assertNotIn("nvp.tools.inspect_host_pinned.v1",ids)
        receipt=host.execute_read(
            TrustedReadScope("filmmaker",self.pid,"turn1"),request)
        self.assertEqual(receipt["format"],"nvp.ai.read_receipt.v1")
        self.assertEqual(receipt["result"]["native_tool_readiness"]["status"],
            "HOST_HAS_NOT_PINNED_NATIVE_TOOL_INSTALLATIONS")
        self.assertFalse(receipt["authority_granted_to_model"])
        self.assertFalse(receipt["creator_approval_granted"])
        self.assertEqual(len(seen),1)
        allowed["can"]=False
        with self.assertRaises(PermissionError):
            host.execute_read(
                TrustedReadScope("filmmaker",self.pid,"turn2"),request)
        allowed["can"]=True
        with self.assertRaises(PermissionError):
            host.execute_read(
                TrustedReadScope("filmmaker",self.pid,"turn3"),
                {**request,"project_id":"other"})
        with self.assertRaises(ValueError):
            host.execute_read(
                TrustedReadScope("filmmaker",self.pid,"turn4"),
                {**request,"tool_path":"C:/untrusted/opj.exe"})


class TrustedInstalledToolPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="nvp-wo6-tools-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        (self.root/"codecs").mkdir()
        (self.root/"licenses").mkdir()
        self.bin=self.root/"codecs"/"native_tool.exe"
        self.notice=self.root/"licenses"/"LICENSE.txt"
        self.bin.write_bytes(b"nativecodec-test")
        self.notice.write_text("BSD-style unit test license\n")
        self.pin=TrustedNativeToolPin(
            "nvp.codec.test","codecs/native_tool.exe",
            hashlib.sha256(self.bin.read_bytes()).hexdigest(),
            "licenses/LICENSE.txt",
            hashlib.sha256(self.notice.read_bytes()).hexdigest(),
            "test-only-version")
        self.inv=TrustedToolInventory(self.root,(self.pin,))

    def test_rechecks_actual_binary_and_license_without_executing(self):
        good=preflight_tool_inventory(self.inv)
        self.assertTrue(good["all_pins_verified"])
        self.assertEqual(good["tools"][0]["status"],
                         "SHA_AND_LICENSE_VERIFIED_NOT_EXECUTED")
        self.assertFalse(good["runtime_execution_verified"])
        self.assertFalse(good["operation_authorization_granted"])
        self.assertFalse(good["tools"][0]["file_paths_disclosed_to_model"])
        self.bin.write_bytes(b"changed")
        bad=preflight_tool_inventory(self.inv)
        self.assertEqual(bad["tools"][0]["status"],"BINARY_SHA_MISMATCH")
        self.bin.unlink()
        missing=preflight_tool_inventory(self.inv)
        self.assertEqual(missing["tools"][0]["status"],"MISSING")
        self.bin.write_bytes(b"nativecodec-test")
        self.notice.unlink()
        self.assertEqual(preflight_tool_inventory(self.inv)["tools"][0][
            "status"],"LICENSE_MISSING")

    def test_symlink_and_model_path_injection_refused(self):
        with self.assertRaises(ValueError):
            TrustedNativeToolPin(
                "nvp.codec.bad","../outside","0"*64,
                "licenses/LICENSE.txt","0"*64,"x")
        with self.assertRaises(ValueError):
            TrustedNativeToolPin(
                "nvp.ffmpeg.codec","codecs/native_tool.exe","0"*64,
                "licenses/LICENSE.txt","0"*64,"x")
        alt=self.root/"codecs"/"actual.exe"
        self.bin.rename(alt)
        try:
            self.bin.symlink_to(alt)
        except OSError:
            # Unprivileged Windows may not permit symlink creation.
            return
        with self.assertRaises(PermissionError):
            preflight_tool_inventory(self.inv)

    def test_native_host_only_inventory_probes_with_current_authority(self):
        studio=Studio(self.root/"film.sqlite3")
        pid=studio.create_project("Movie","")["id"]
        host=NativeAiReadHost(
            studio,authorize_read=lambda *_:True,
            trusted_tool_inventory=self.inv)
        self.assertIn(
            "nvp.tools.inspect_host_pinned.v1",
            {c["id"] for c in host.catalog()["capabilities"]})
        scope=TrustedReadScope("creator",pid,"turn1")
        req={"capability_id":"nvp.tools.inspect_host_pinned.v1",
             "project_id":pid}
        got=host.execute_read(scope,req)
        self.assertTrue(got["result"]["all_pins_verified"])
        self.assertFalse(got["authority_granted_to_model"])
        with self.assertRaises(ValueError):
            host.execute_read(scope,{**req,"executable":"../../override.exe"})
        with self.assertRaises(PermissionError):
            host.execute_read(scope,{**req,"project_id":"different"})
        with self.assertRaises(TypeError):
            NativeAiReadHost(
                studio,authorize_read=lambda *_:True,
                trusted_tool_inventory={"root":str(self.root)})


if __name__=="__main__":
    unittest.main()
