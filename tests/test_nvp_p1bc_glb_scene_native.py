"""P1-B/C genuine imported binary GLB -> original USD bones/skin/voice/Cycles source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from pxr import Sdf,Usd,UsdGeom,UsdSkel,UsdShade

from backend.nvp_character_assets import CharacterAssets
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_int02_cycles_renderer import static_composed_usd
from backend.nvp_int02_usd_materials import source_preview_materials
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_skinning import evaluate_skin
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_p1bc_actor_registry import ActorDirectory, ActorDialogueDirector
from backend.nvp_p1bc_glb_character import ImportedCharacterSources
from backend.nvp_p1bc_scene_cast import NativeActorSceneCasting
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND

T=TICKS_PER_SECOND


def original_rigged_glb():
    """A structurally genuine GLB2: original triangle, 3 bones and PBR."""
    raw=bytearray()
    views=[]
    accessors=[]
    def source(data,kind,ctype,count):
        offset=len(raw)
        raw.extend(data)
        while len(raw)%4:raw.append(0)
        view=len(views)
        views.append({"buffer":0,"byteOffset":offset,"byteLength":len(data)})
        i=len(accessors)
        accessors.append({"bufferView":view,"componentType":ctype,
                          "count":count,"type":kind})
        return i
    # Original glTF Y-up vertex positions yield a horizontal Z-up
    # triangle in NVP for actual overhead-camera Cycles visibility.
    pos=source(struct.pack("<9f",0,0,0, 1,0,0, 0,0,-1),"VEC3",5126,3)
    joints=source(bytes([1,0,0,0]*3),"VEC4",5121,3)
    weights=source(struct.pack("<12f",*([1.0,0.0,0.0,0.0]*3)),
                   "VEC4",5126,3)
    jaw=source(struct.pack("<9f",0,.2,0, 0,0,0, 0,0,0),
               "VEC3",5126,3)
    doc={"asset":{"version":"2.0"},
         "buffers":[{"byteLength":len(raw)}],
         "bufferViews":views,"accessors":accessors,
         "nodes":[{"name":"Root","children":[1,2]},
                  {"name":"FaceJaw"},{"name":"Shoulder"},
                  {"name":"Original Body","skin":0,"mesh":0}],
         "skins":[{"joints":[0,1,2]}],
         "meshes":[{"primitives":[{
             "attributes":{"POSITION":pos,"JOINTS_0":joints,
                           "WEIGHTS_0":weights},
             "targets":[{"POSITION":jaw}],
             "material":0,"mode":4
         }],"extras":{"targetNames":["jaw_open"]}}],
         "materials":[{
             "name":"Original GLB PBR",
             "pbrMetallicRoughness":{
                 "baseColorFactor":[0.85,0.16,0.08,1.0],
                 "metallicFactor":0.0,
                 "roughnessFactor":0.4,
             },
             "alphaMode":"OPAQUE",
         }],
         "scenes":[{"nodes":[0,3]}],"scene":0}
    header=json.dumps(doc,separators=(",",":")).encode()
    header+=b" "*(-len(header)%4)
    body=struct.pack("<II",len(header),0x4e4f534a)+header
    body+=struct.pack("<II",len(raw),0x004e4942)+bytes(raw)
    return b"glTF"+struct.pack("<II",2,len(body)+12)+body


class OriginalImportedGLBAndActing(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory(prefix="nvp-actual-glb-")
        self.addCleanup(tmp.cleanup)
        self.studio=Studio(Path(tmp.name)/"filming.sqlite3")
        self.project=self.studio.create_project("Original GLB film","")["id"]
        self.index=FilmIndex(self.studio)
        self.actors=ActorDirectory(
            self.index,verify_director_action=lambda event,scope:
            event=="creator_yes" and scope["operation"]=="nvp.p1bc.register_actor.v1")
        self.actors.register(self.project,"ActorLead",display_name="Lead",
                             creator_event="creator_yes")
        self.registered=CharacterAssets(self.studio).register(
            self.project,original_rigged_glb(),"creator_owned")
        self.director=NativeActorSceneCasting(
            self.index,verify_director_action=lambda event,scope:
            event=="creator_yes" and
            scope["operation"]=="nvp.p1bc.native_actor_scene_cast.v1")
        self.cast=[{"actor_id":"ActorLead",
                    "character_asset_id":self.registered["asset_id"],
                    "position":[0.0,0.0,0.0],
                    "motion_joint":"Bone001","travel":0.4,
                    "face_target":"jaw_open","face_strength":0.5}]
        self.source=self.director.publish(
            self.project,"SourceHumanScene",cast=self.cast,
            camera_height=8.0,creator_event="creator_yes")
        self.scene=OpenUSDSceneBridge(self.index)

    def _make_take(self):
        audio=RecordedSoundSources(self.index).publish(
            self.project,"OriginalSpeech",[struct.pack("<h",1200)*48000])
        event=TemporalLedger(self.index).publish(
            self.project,"HumanSpeechTimeline",[{
                "event_id":"OriginalLine","event_kind":"dialogue",
                "subject_id":"ActorLead","start_tick":0,"end_tick":T,
                "source_id":"OriginalSpeech","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor001","gain":1.0}
            }],duration_tick=2*T)
        take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda action,scope:
            action=="creator_yes" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1").freeze(
                self.project,"SourceHumanTake",scene_id="SourceHumanScene",
                scene_revision=1,timeline_id="HumanSpeechTimeline",
                timeline_revision=1,sample_ticks=[0,T],
                creator_event="creator_yes")
        return take

    def test_real_glb_vertices_joint_deformation_and_source_pbr(self):
        rec,stage=self.scene.open(self.project,"SourceHumanScene",1)
        path="/World/Actor001/Rig/CharacterMesh"
        prim=stage.GetPrimAtPath(path)
        self.assertTrue(prim.IsA(UsdGeom.Mesh))
        self.assertTrue(prim.HasAPI(UsdSkel.BindingAPI))
        self.assertEqual(prim.GetAttribute("nvp:sourceGLBSHA256").Get(),
                         self.registered["sha256"])
        shape=UsdGeom.Mesh(prim)
        self.assertEqual(len(shape.GetPointsAttr().Get()),3)
        bound,relation=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        self.assertTrue(bound)
        surfaces=source_preview_materials(stage,T//2)
        self.assertEqual(len(surfaces),1)
        self.assertAlmostEqual(surfaces[0]["linear_diffuse_rgb"][0],.85,places=5)
        self.assertAlmostEqual(surfaces[0]["roughness"],.4,places=5)
        origin=evaluate_skin(stage,prim,"/World/Actor001",0)
        mid=evaluate_skin(stage,prim,"/World/Actor001",T//2)
        self.assertTrue(mid["skinning_evaluated"])
        self.assertTrue(mid["facial_deformation_evaluated"])
        self.assertEqual(mid["source_facial_shapes"][0]["name"],"jaw_open")
        self.assertAlmostEqual(mid["source_facial_shapes"][0]["weight"],.25)
        self.assertAlmostEqual(mid["deformed_points"][0][2]-
                               origin["deformed_points"][0][2],.05,places=4)
        self.assertAlmostEqual(mid["deformed_points"][0][0]-
                               origin["deformed_points"][0][0],.2,places=4)
        source=rec["data"]["imported_characters"][0]
        self.assertEqual(source["original_glb_sha256"],self.registered["sha256"])
        self.assertIn({"object_id":self.registered["asset_id"],
                       "revision":1,"role":"asset"},rec["dependencies"])

    def test_frozen_original_dialogue_and_rig_survive_restart(self):
        take=self._make_take()
        attestor=ActorDialogueDirector(
            self.index,verify_director_action=lambda event,scope:
            event=="creator_yes" and
            scope["operation"]=="nvp.p1bc.bind_original_dialogue.v1")
        line=attestor.bind(
            self.project,"ActorLeadOriginalLine",
            actor_id="ActorLead",take_id="SourceHumanTake",
            event_id="OriginalLine",creator_event="creator_yes")
        act=attestor.at(self.project,"ActorLeadOriginalLine",1,T//2)
        self.assertTrue(act["dialogue_active"])
        self.assertTrue(act["native_skin_deformation_evaluated"])
        self.assertTrue(act["native_facial_deformation_evaluated"])
        self.assertEqual(act["original_glb_face_targets"][0]["name"],"jaw_open")
        self.assertAlmostEqual(
            act["original_glb_face_targets"][0]["weight"],.25)
        self.assertEqual(act["source_skin_vertex_count"],3)
        self.assertFalse(act["voice_synthesized"])
        self.assertEqual(OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:False
            ).verify_take(self.project,"SourceHumanTake")["status"],
            "VERIFIED_FROZEN_DATA_TAKE")
        reopened=FilmIndex(Studio(self.studio.db_path))
        fresh=ActorDialogueDirector(
            reopened,verify_director_action=lambda *_:False).at(
            self.project,"ActorLeadOriginalLine",1,T//2)
        self.assertEqual(fresh,act)
        self.assertEqual(
            reopened.read_revision(self.project,"SourceHumanTake",1
                )["data"]["imported_characters"],
            self.index.read_revision(self.project,"SourceHumanScene",1
                )["data"]["imported_characters"])

    def test_exact_usd_skin_baked_for_genuine_cycles_not_reanimated(self):
        take=self._make_take()
        kwargs=dict(project_id=self.project,take_id="SourceHumanTake",
                    take_sha=take["document_sha256"],
                    camera_path="/World/Camera")
        source0,optics,mats=static_composed_usd(self.index,tick=0,**kwargs)
        source1,_,_=static_composed_usd(self.index,tick=T//2,**kwargs)
        self.assertNotEqual(hashlib.sha256(source0).digest(),
                            hashlib.sha256(source1).digest())
        self.assertEqual(len(mats),1)
        self.assertAlmostEqual(optics["camera_focal_length_mm"],50.0,places=3)
        def baked(usd):
            layer=Sdf.Layer.CreateAnonymous()
            self.assertTrue(layer.ImportFromString(usd.decode()))
            stage=Usd.Stage.Open(layer)
            mesh=stage.GetPrimAtPath("/World/Actor001/Rig/CharacterMesh")
            self.assertTrue(mesh.IsA(UsdGeom.Mesh))
            self.assertFalse(mesh.GetProperty("skel:skeleton"))
            return [list(p) for p in UsdGeom.Mesh(mesh).GetPointsAttr().Get()]
        a,b=baked(source0),baked(source1)
        self.assertEqual(len(a),3)
        self.assertAlmostEqual(b[0][0]-a[0][0],.2,places=4)
        self.assertAlmostEqual(b[0][2]-a[0][2],.05,places=4)

    def test_refused_duplicate_foreign_or_tampered_glb_never_cast(self):
        before=self.index.read_revision(self.project,"SourceHumanScene",1)
        with self.assertRaises(ValueError):
            self.director.publish(
                self.project,"DuplicateHuman",cast=self.cast+self.cast,
                creator_event="creator_yes")
        other=self.studio.create_project("Foreign", "")["id"]
        with self.assertRaises(KeyError):
            self.director.publish(other,"ForeignHuman",cast=self.cast,
                                  creator_event="creator_yes")
        refusal=NativeActorSceneCasting(
            self.index,verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            refusal.publish(self.project,"NotApproved",cast=self.cast,
                            creator_event="no")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.project,"NotApproved",1)
        expected=self.registered["sha256"]
        blob=CharacterAssets(self.studio).root/(expected+".glb")
        blob.write_bytes(b"tampered original")
        with self.assertRaises(RuntimeError):
            ImportedCharacterSources(self.index).rig(
                self.project,self.registered["asset_id"],1,path="/World/Actor001")
        self.assertEqual(
            self.index.read_revision(self.project,"SourceHumanScene",1
                )["document_sha256"],before["document_sha256"])


if __name__=="__main__":
    unittest.main()
