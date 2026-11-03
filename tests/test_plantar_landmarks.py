"""Anatomical-reviewed foot attachment is distinct from vertex contact math."""
import copy
import tempfile
import unittest
from pathlib import Path
from backend.nvp_plantar_landmarks import (
    FootAnatomyAttachment,validate_landmarks,analyze_imported_landmarks)
from backend.nvp_plantar_anatomy_blender import ANATOMY_ATTACHMENT_NATIVE
from backend.nvp_production_scene import digest
from backend.nvp_studio import Studio

ROLES=("heel_pad","mt1_pad","mt5_pad","hallux_pad")

def package():
    return {"leg_identity":{"approval_sha":"a"*64,
                            "actors":[{"instance_id":"human","asset_sha256":"b"*64}]},
            "plantar":{"approval_sha":"c"*64},
            "foot_lock":{"approval_sha":"d"*64},
            "plantar_correction":{"approval_sha":"e"*64}}

def annotation():
    return {
        "evidence":{"origin":"independently_reviewed_annotation",
                    "reference_id":"independent-foot-study-001",
                    "reference_sha256":"f"*64,
                    "license_id":"creator-owned-review-only",
                    "annotator_id":"rig-artist",
                    "reviewer_id":"anatomy-auditor",
                    "method":"manual_mesh_landmark_review"},
        "actors":{"human":{
            "left":{"mesh_name":"human_mesh","vertex_indices":dict(zip(ROLES,(1,2,3,4)))},
            "right":{"mesh_name":"human_mesh","vertex_indices":dict(zip(ROLES,(11,12,13,14)))}}
        }}

def native(approved):
    locations={
        "heel_pad":[0.,-.08,0.],
        "mt1_pad":[-.045,.13,0.],
        "mt5_pad":[.045,.13,0.],
        "hallux_pad":[-.02,.235,0.]}
    sides={}
    for side,x in (("left",-.16),("right",.16)):
        sides[side]={
            "ankle_world_m":[x,0,.12],
            "toe_joint_world_m":[x,.18,.12],
            "points":{key:{"position_world_m":[v[0]+x,v[1],v[2]],
                           "normal_world":[0,0,-1]} for key,v in locations.items()}}
    return {"format":"nvp.foot.attachment.observation.v1",
            "annotation_sha":digest(approved),
            "leg_identity_sha":"a"*64,"correction_sha":"e"*64,
            "actors":{"human":{"asset_sha256":"b"*64,"sides":sides}}}


class AuthoringContract(unittest.TestCase):
    def test_all_four_plantar_landmarks_explicit_bilateral_and_independent(self):
        valid=validate_landmarks(annotation(),package())
        self.assertEqual(valid["format"],"nvp.foot.attachment.v1")
        self.assertEqual(valid["actors"]["human"]["right"]["vertex_indices"]["mt5_pad"],13)
        self.assertEqual(valid["evidence"]["annotator_id"],"rig-artist")

    def test_refuse_auto_guess_and_ambiguous_or_unauthorized_landmarks(self):
        for fault in ("auto","self_review","no_ref","wrong_method","missing_pad",
                      "side_swap","duplicate_foot","foreign_actor","bad_mesh","float_vertex"):
            p=annotation()
            if fault=="auto":p["evidence"]["origin"]="algorithmic_fixture"
            if fault=="self_review":p["evidence"]["reviewer_id"]="rig-artist"
            if fault=="no_ref":p["evidence"]["reference_sha256"]="?"
            if fault=="wrong_method":p["evidence"]["method"]="text_guess"
            if fault=="missing_pad":del p["actors"]["human"]["left"]["vertex_indices"]["mt1_pad"]
            if fault=="side_swap":p["actors"]["human"]["right"]=p["actors"]["human"]["left"]
            if fault=="duplicate_foot":p["actors"]["human"]["right"]["vertex_indices"]["hallux_pad"]=3
            if fault=="foreign_actor":p["actors"]["other"]=p["actors"]["human"]
            if fault=="bad_mesh":p["actors"]["human"]["left"]["mesh_name"]=""
            if fault=="float_vertex":p["actors"]["human"]["left"]["vertex_indices"]["heel_pad"]=1.0
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                validate_landmarks(p,package())

    def test_independent_import_rejects_dorsal_and_mixed_up_anatomy(self):
        a=validate_landmarks(annotation(),package())
        correct=analyze_imported_landmarks(native(a),a,package())
        self.assertTrue(correct["attached_geometry_valid"])
        self.assertFalse(correct["clinical_anatomy_certified"])
        for fault in ("sha","dorsal","heel_front","zero_foot_breadth","unknown_asset",
                      "nonfinite","duplicate_side"):
            r=native(a)
            s=r["actors"]["human"]["sides"]["left"]
            if fault=="sha":r["annotation_sha"]="0"*64
            if fault=="dorsal":s["points"]["heel_pad"]["normal_world"]=[0.,0.,1.]
            if fault=="heel_front":s["points"]["heel_pad"]["position_world_m"][1]=.30
            if fault=="zero_foot_breadth":
                s["points"]["mt5_pad"]["position_world_m"]=s["points"]["mt1_pad"]["position_world_m"][:]
            if fault=="unknown_asset":r["actors"]["human"]["asset_sha256"]="0"*64
            if fault=="nonfinite":s["points"]["hallux_pad"]["position_world_m"][1]=float("nan")
            if fault=="duplicate_side":del r["actors"]["human"]["sides"]["right"]
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                analyze_imported_landmarks(r,a,package())

    def test_durable_attachment_requires_native_evidence_and_rejects_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio=Studio(Path(tmp)/"review.sqlite")
            pid=studio.create_project("Anatomy audit","original")["id"]
            pkg=package()
            class InContext(FootAnatomyAttachment):
                def _context(self,p,s):
                    if p!=pid or s!="scene":raise KeyError("Foreign film/scene")
                    return pkg,digest([pkg["plantar_correction"],pkg["leg_identity"],pkg["plantar"]])
            svc=InContext(studio)
            x=svc.create(pid,"scene")
            with self.assertRaises(RuntimeError):
                svc.approve_attachment(pid,"scene",x["revision"])
            x=svc.configure(pid,"scene",annotation(),x["revision"])
            with self.assertRaises(RuntimeError):
                svc.approve_attachment(pid,"scene",x["revision"])
            n=native(x["attachment"])
            x=svc.attest_imported_geometry(pid,"scene",n,x["revision"])
            self.assertTrue(x["geometry_observed"])
            x=svc.approve_attachment(pid,"scene",x["revision"])
            exported=svc.export(pid,"scene")["anatomy_attachment"]
            self.assertFalse(exported["clinical_anatomy_certified"])
            recovered=InContext(Studio(studio.db_path))
            self.assertEqual(recovered.read(pid,"scene")["receipt_sha"],x["receipt_sha"])
            pkg["plantar_correction"]["approval_sha"]="changed"
            self.assertTrue(recovered.read(pid,"scene")["stale"])
            with self.assertRaises(RuntimeError):recovered.export(pid,"scene")
            with self.assertRaises(KeyError):recovered.read(pid,"other")

    def test_native_script_observes_actual_deformed_mesh_without_editing(self):
        compile(ANATOMY_ATTACHMENT_NATIVE,"native_anatomy","exec")
        self.assertIn("ev.to_mesh()",ANATOMY_ATTACHMENT_NATIVE)
        self.assertIn("rig.pose.bones",ANATOMY_ATTACHMENT_NATIVE)
        self.assertNotIn("keyframe_insert(",ANATOMY_ATTACHMENT_NATIVE)
        self.assertNotIn("bpy.ops.wm.save_as_mainfile",ANATOMY_ATTACHMENT_NATIVE)

if __name__=="__main__":unittest.main()
