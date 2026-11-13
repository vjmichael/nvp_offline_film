"""P1-F real USD character import, actor-owned dialogue and source-shot proof."""
from pathlib import Path
import struct
import tempfile
import unittest

from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel, Vt

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_p1de_edit_audio import P1DEConform
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
from backend.nvp_p1f_cycles_source_admission import admit_original_frame

T=TICKS_PER_SECOND
ACTOR="ACT_OriginalLead"


def imported_character(*,omit_shape=None,external=False):
    """Make a genuine skeletal + skinned + time-varying facial USD asset."""
    layer=Sdf.Layer.CreateAnonymous("independently-authored-actor.usda")
    stage=Usd.Stage.Open(layer)
    stage.SetTimeCodesPerSecond(float(T))
    root=UsdSkel.Root.Define(stage,"/Asset")
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().CreateAttribute(
        "nvp:actorID",Sdf.ValueTypeNames.String).Set(ACTOR)
    mesh=UsdGeom.Mesh.Define(stage,"/Asset/Geometry")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-0.5,0,-0.5),Gf.Vec3f(0.5,0,-0.5),
        Gf.Vec3f(0.5,0,0.5),Gf.Vec3f(-0.5,0,0.5)]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([4]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0,1,2,3]))
    mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    skel=UsdSkel.Skeleton.Define(stage,"/Asset/Skeleton")
    skel.GetJointsAttr().Set(Vt.TokenArray(["Body","Body/Head"]))
    identities=Vt.Matrix4dArray([Gf.Matrix4d(1.),Gf.Matrix4d(1.)])
    skel.GetBindTransformsAttr().Set(identities)
    skel.GetRestTransformsAttr().Set(identities)
    skel_binding=UsdSkel.BindingAPI.Apply(skel.GetPrim())
    skel_binding.CreateAnimationSourceRel().SetTargets([
        Sdf.Path("/Asset/Animation")])
    binding=UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    binding.CreateSkeletonRel().SetTargets([Sdf.Path("/Asset/Skeleton")])
    binding.CreateJointIndicesPrimvar(False,1).Set(Vt.IntArray([0,0,1,1]))
    binding.CreateJointWeightsPrimvar(False,1).Set(Vt.FloatArray([1.,1.,1.,1.]))
    shapes=["jawOpen","lipClose","eyeBlink","browRaise"]
    if omit_shape:
        shapes.remove(omit_shape)
    targets=[]
    for i,name in enumerate(shapes):
        shape=UsdSkel.BlendShape.Define(stage,"/Asset/Face/"+name)
        shape.GetOffsetsAttr().Set(Vt.Vec3fArray([
            Gf.Vec3f(0,0,float(i+1)*0.04)]))
        shape.GetPointIndicesAttr().Set(Vt.IntArray([i%4]))
        targets.append(shape.GetPrim().GetPath())
    binding.CreateBlendShapesAttr().Set(Vt.TokenArray(shapes))
    binding.CreateBlendShapeTargetsRel().SetTargets(targets)
    animation=UsdSkel.Animation.Define(stage,"/Asset/Animation")
    animation.GetBlendShapesAttr().Set(Vt.TokenArray(shapes))
    animation.GetBlendShapeWeightsAttr().Set(
        Vt.FloatArray([0.]*len(shapes)),Usd.TimeCode(0))
    animation.GetBlendShapeWeightsAttr().Set(
        Vt.FloatArray([.8,.5,.25,.4][:len(shapes)]),Usd.TimeCode(float(T)))
    if external:
        # This intentionally taints otherwise real geometry and MUST refuse
        # admission before it can enter the FilmIndex.
        mesh.GetPrim().GetReferences().AddReference("./private.usda")
    return layer.ExportToString().encode("utf8")


class RealImportedActorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="nvp-p1f-actor-")
        self.addCleanup(tmp.cleanup)
        self.studio=Studio(Path(tmp.name)/"nvp.sqlite3")
        self.pid=self.studio.create_project("Rigged Lead","Original Take")["id"]
        self.index=FilmIndex(self.studio)
        self.assets=OpenUSDAssetRegistry(self.index)

    def approve(self,e,scope):
        return (e=="one_reviewed_character" and
                scope["operation"]=="nvp.p1f.import_rigged_usd_actor.v1" and
                scope["actor_id"]==ACTOR)

    def load(self):
        original=imported_character()
        receipt=self.assets.import_rigged_actor(
            self.pid,"original_lead_asset",original,actor_id=ACTOR,
            approve_import=self.approve,creator_event="one_reviewed_character")
        return receipt,original

    def test_import_real_mesh_skin_expressions_and_reopen(self):
        receipt,original=self.load()
        asset,layer=self.assets.open(self.pid,"original_lead_asset",1)
        self.assertEqual(asset["document_sha256"],receipt["document_sha256"])
        self.assertEqual(asset["data"]["geometry"]["point_count"],4)
        self.assertEqual(asset["data"]["geometry"]["facial_keys"],2)
        self.assertEqual(len(asset["data"]["geometry"]["face_shapes"]),4)
        self.assertEqual(
            self.index.get_blob(self.pid,asset["data"]["layer_sha256"]),
            original)
        stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
        anim=UsdSkel.Animation(stage.GetPrimAtPath("/Asset/Animation"))
        a=anim.GetBlendShapeWeightsAttr().Get(Usd.TimeCode(0))
        b=anim.GetBlendShapeWeightsAttr().Get(Usd.TimeCode(float(T)))
        self.assertNotEqual(list(a),list(b))

    def test_unapproved_or_external_or_unrigged_actor_rejected(self):
        with self.assertRaises(PermissionError):
            self.assets.import_rigged_actor(
                self.pid,"unapproved_asset",imported_character(),actor_id=ACTOR,
                approve_import=lambda *_:False,creator_event="declined")
        with self.assertRaises(ValueError):
            self.assets.import_rigged_actor(
                self.pid,"external_asset",imported_character(external=True),
                actor_id=ACTOR,approve_import=self.approve,
                creator_event="one_reviewed_character")
        with self.assertRaises(ValueError):
            self.assets.import_rigged_actor(
                self.pid,"bad_face_asset",imported_character(omit_shape="lipClose"),
                actor_id=ACTOR,approve_import=self.approve,
                creator_event="one_reviewed_character")
        for name in ("unapproved_asset","external_asset","bad_face_asset"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,name)

    def test_composed_facial_actor_in_real_source_take_shot(self):
        asset,_=self.load()
        scene=OpenUSDSceneBridge(self.index).publish(
            self.pid,"original_actor_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,2,0]},
                {"path":"/World/Camera","role":"camera","position":[0,-6,1]}
            ],curves=[],native_schemas=True,
            asset_bindings=[{"path":"/World/Actor",
                             "asset_id":"original_lead_asset","asset_revision":1}])
        original_pcm=struct.pack("<48000h",*([1200]*48000))
        audio=RecordedSoundSources(self.index).publish(
            self.pid,"actor_dialogue_source",[original_pcm])
        timeline=TemporalLedger(self.index).publish(
            self.pid,"original_actor_timeline",
            [{"event_id":"lead_speech","event_kind":"dialogue",
              "subject_id":ACTOR,"source_id":"actor_dialogue_source",
              "source_revision":1,"start_tick":0,"end_tick":T,
              "payload":{"usd_prim_path":"/World/Actor","gain":1.0}}],
            duration_tick=2*T)
        take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:True).freeze(
            self.pid,"original_rigged_take",
            scene_id="original_actor_scene",scene_revision=1,
            timeline_id="original_actor_timeline",timeline_revision=1,
            sample_ticks=[0,T],creator_event="reviewed_capture")
        edl=P1DEConform(self.index,approve_edit=lambda *_:True)
        edited=edl.publish(self.pid,"rigged_edit",[{
            "take_id":"original_rigged_take",
            "take_sha256":take["document_sha256"],
            "in_tick":0,"out_tick":T,
            "listener_path":"/World/Camera",
            "audio":[{"event_id":"lead_speech","actor_id":ACTOR,
                      "source_id":"actor_dialogue_source","source_revision":1,
                      "source_sha256":audio["document_sha256"],
                      "enabled":True,"gain":1.0}]
        }],expected_revision=0,creator_event="reviewed_edit")
        reels=P1FReelPlan(self.index)
        reels.publish(self.pid,"rigged_reel_plan",
                      edit_id="rigged_edit",edit_revision=1,
                      expected_edit_document_sha256=edited["document_sha256"])
        admission=admit_original_frame(
            self.index,self.pid,"rigged_reel_plan",0,0)
        self.assertEqual(admission["status"],"SOURCE_ADMITTED_NOT_RENDERED")
        self.assertFalse(admission["genuine_cycles_output"])
        self.assertEqual(admission["actor_geometry"]["/World/Actor"]["mesh_count"],1)
        self.assertEqual(
            admission["actor_geometry"]["/World/Actor"]["face_domains"],
            ["expression","eyes","jaw","lips"])
        self.assertEqual(self.index.read_revision(
            self.pid,"original_rigged_take")["document_sha256"],
            take["document_sha256"])
        a=edl.audio_window(self.pid,"rigged_edit",1,first_sample=0,count=1024)
        self.assertEqual(a["sample_count"],1024)
        self.assertFalse(a["source_modified"])


if __name__=="__main__":
    unittest.main()
