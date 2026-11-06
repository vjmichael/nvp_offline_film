"""PROD06E2C2 explicit plantar markers, floor hash and native audit contracts."""
import copy
import tempfile
import unittest
from pathlib import Path
from backend.nvp_plantar import (
    PlantarContactPlan, validate_plantar_config, analyze_plantar_observation,
    PLANTAR_NATIVE_AUDIT, PLANTAR_FIXTURE_PROBE)
from backend.nvp_studio import Studio
from backend.nvp_production_scene import digest

def package():
    return {
        "take":{"shots":[{"start_frame":1,"stop_frame":5}]},
        "foot_lock":{"approval_sha":"f"*64,"actors":[{
            "instance_id":"a","config":{
                "left":{"contact_windows":[[1,2]]},
                "right":{"contact_windows":[[3,4]]}
            }}]},
        "leg_identity":{"approval_sha":"b"*64,"actors":[{"instance_id":"a","asset_sha256":"c"*64}]}
    }

def config():
    return {"surface":{"object_name":"NVP_FLOOR","geometry_sha256":"d"*64},
            "actors":{"a":{
                "left":{"mesh_name":"CharacterMesh","markers":{"heel":1,"ball":2,"toe":3},
                         "contact_roles":["heel","ball","toe"]},
                "right":{"mesh_name":"CharacterMesh","markers":{"heel":11,"ball":12,"toe":13},
                          "contact_roles":["heel","toe"]},
                "max_penetration_m":.002,"max_gap_m":.02,"max_slide_m":.01}}}

def native_report():
    row=[]
    for frame in (1,2,3,4):
        sides={}
        for side,x in (("left",-.15),("right",.15)):
            sides[side]={role:[x+i*.02,.04+frame*.001,.004] for i,role in enumerate(("heel","ball","toe"))}
        row.append({"frame":frame,"sides":sides})
    return {"format":"nvp.plantar.native_observation.v1",
            "plantar_approval_sha":"e"*64,"foot_lock_sha":"f"*64,
            "floor":{"geometry_sha256":"d"*64,"top_z_m":0.0,
                     "bounds_xy_m":[-1,1,-1,1]},
            "actors":{"a":{"asset_sha256":"c"*64,"frames":[1,2,3,4],
                           "observations":row}}}

def approved_package():
    return {**package(),"plantar":{"approval_sha":"e"*64,"plan":config()}}

class MarkerValidation(unittest.TestCase):
    def test_explicit_heel_ball_toe_mapping(self):
        outcome=validate_plantar_config(config(),package()["foot_lock"]["actors"])
        self.assertEqual(outcome["surface"]["object_name"],"NVP_FLOOR")
        self.assertEqual(outcome["actors"]["a"]["left"]["markers"]["toe"],3)

    def test_reject_foreign_mesh_forged_floor_invalid_source_and_duplicate_marker(self):
        for name in ("bad_sha","wrong_floor","missing_toe","shared_vertex","negative_vertex",
                     "extra_actor","missing_side","nan_gap","unknown_contact","bad_mesh"):
            item=config();actor=item["actors"]["a"]
            if name=="bad_sha":item["surface"]["geometry_sha256"]="0"*7
            if name=="wrong_floor":item["surface"]["object_name"]="Invented Floor"
            if name=="missing_toe":del actor["left"]["markers"]["toe"]
            if name=="shared_vertex":actor["right"]["markers"]["heel"]=1
            if name=="negative_vertex":actor["left"]["markers"]["heel"]=-1
            if name=="extra_actor":item["actors"]["foreign"]=actor
            if name=="missing_side":del actor["right"]
            if name=="nan_gap":actor["max_gap_m"]=float("nan")
            if name=="unknown_contact":actor["left"]["contact_roles"]=["head"]
            if name=="bad_mesh":actor["left"]["mesh_name"]=""
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_plantar_config(item,package()["foot_lock"]["actors"])

    def test_stale_approval_and_revision_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio=Studio(Path(tmp)/"s.sqlite");pid=studio.create_project("T","Test")["id"]
            pkg=package()
            class Service(PlantarContactPlan):
                def _context(self,p,s):
                    if (p,s)!=(pid,"scene"):raise KeyError("Foreign scene")
                    return pkg,digest([pkg["foot_lock"],pkg["leg_identity"],pkg["take"]])
            svc=Service(studio)
            row=svc.create(pid,"scene")
            with self.assertRaises(RuntimeError):svc.approve(pid,"scene",row["revision"])
            row=svc.configure(pid,"scene",config(),row["revision"])
            with self.assertRaises(RuntimeError):svc.configure(pid,"scene",config(),0)
            row=svc.approve(pid,"scene",row["revision"])
            self.assertEqual(row["status"],"approved")
            self.assertFalse(svc.export(pid,"scene")["plantar"]["physical_contact_verified"])
            recovered=Service(Studio(studio.db_path))
            self.assertEqual(recovered.read(pid,"scene")["approval_sha"],row["approval_sha"])
            pkg["foot_lock"]["approval_sha"]="0"*64
            self.assertTrue(recovered.read(pid,"scene")["stale"])
            with self.assertRaises(RuntimeError):recovered.export(pid,"scene")
            with self.assertRaises(KeyError):recovered.read(pid,"different")

class NativeAuditTests(unittest.TestCase):
    def test_measures_actual_floor_and_contact_flags(self):
        result=analyze_plantar_observation(native_report(),approved_package())
        self.assertEqual(result["format"],"nvp.plantar.floor_contact_audit.v1")
        self.assertTrue(result["contact_meets_configured_tolerances"])
        self.assertFalse(result["anatomical_sole_certified"])
        self.assertAlmostEqual(result["actors"]["a"]["left"]["heel"]["min_clearance_m"],.004)

    def test_penetration_is_reported_not_silently_fixed(self):
        raw=native_report()
        for item in raw["actors"]["a"]["observations"]:
            item["sides"]["left"]["heel"][2]=-.008
        checked=analyze_plantar_observation(raw,approved_package())
        self.assertFalse(checked["contact_meets_configured_tolerances"])
        self.assertAlmostEqual(checked["actors"]["a"]["left"]["heel"]["min_clearance_m"],-.008)
        self.assertFalse(checked["actors"]["a"]["left"]["heel"]["contact_meets_tolerances"])

    def test_floor_and_asset_tamper_out_of_bounds_or_incomplete_samples_fail(self):
        for change in ("floor_sha","approval","asset","bad_x","nan","missing_frame","missing_role","wrong_frame"):
            obs=native_report()
            if change=="floor_sha":obs["floor"]["geometry_sha256"]="0"*64
            if change=="approval":obs["plantar_approval_sha"]="0"*64
            if change=="asset":obs["actors"]["a"]["asset_sha256"]="0"*64
            if change=="bad_x":obs["actors"]["a"]["observations"][0]["sides"]["left"]["heel"][0]=1e9
            if change=="nan":obs["actors"]["a"]["observations"][0]["sides"]["left"]["heel"][1]=float("nan")
            if change=="missing_frame":obs["actors"]["a"]["observations"].pop()
            if change=="missing_role":del obs["actors"]["a"]["observations"][0]["sides"]["left"]["toe"]
            if change=="wrong_frame":obs["actors"]["a"]["observations"][0]["frame"]=20
            with self.subTest(change=change),self.assertRaises(ValueError):
                analyze_plantar_observation(obs,approved_package())

    def test_native_scripts_are_parseable_and_do_not_edit_rig(self):
        compile(PLANTAR_NATIVE_AUDIT,"plantar-native-audit","exec")
        compile(PLANTAR_FIXTURE_PROBE,"plantar-fixture-proposal","exec")
        self.assertIn("ev.to_mesh()",PLANTAR_NATIVE_AUDIT)
        for script in (PLANTAR_NATIVE_AUDIT,PLANTAR_FIXTURE_PROBE):
            self.assertNotIn("keyframe_insert(",script)
            self.assertNotIn("bpy.ops.wm.save_as_mainfile",script)

if __name__=="__main__":unittest.main()
