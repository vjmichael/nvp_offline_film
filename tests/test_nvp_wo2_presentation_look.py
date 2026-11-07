"""WO2 A–E: production presentation decisions never mutate source films."""
import copy
import unittest

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_wo2_presentation_look import (
    OriginalSceneLook,default_look,propose_look,validate_look)


class WO2PresentationLookAuthority(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.source=self.scene.open(self.pid,"scene_reusable",1)[0]
        self.sha=self.source["document_sha256"]
        self.looks=OriginalSceneLook(self.index)
        self.roles=self.source["data"]["prim_roles"]

    def test_approved_versions_link_to_exact_usd_source_and_do_not_edit_takes(self):
        original=default_look()
        original["materials"]["/World/Actor"]={
            "opacity":.8,"transmission":.6,"ior":1.45,"thickness_m":.02}
        original["textures"]["transforms"]["/World/Actor"]={
            "normal":{"repeat":[2.,2.],"offset":[.1,.0],
                      "rotation_deg":30.}}
        source_before=self.scene.open(self.pid,"scene_reusable",1)[0]
        proposal=propose_look("dramatic",self.roles)
        self.assertFalse(proposal["creator_approved"])
        self.assertFalse(proposal["persisted"])
        denied=self.looks.publish(
            self.pid,"DirectorLook001",
            scene_id="scene_reusable",scene_revision=1,
            scene_sha256=self.sha,look=original,
            approve=lambda scope:False)
        self.assertEqual(denied["status"],"DENIED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DirectorLook001")
        accepted=self.looks.publish(
            self.pid,"DirectorLook001",
            scene_id="scene_reusable",scene_revision=1,
            scene_sha256=self.sha,look=original,
            approve=lambda scope:
                scope["look"]["materials"]["/World/Actor"]["ior"]==1.45)
        self.assertEqual(accepted["revision"],1)
        reopened=self.looks.open(self.pid,"DirectorLook001",1,
                                 scene_sha256=self.sha)
        self.assertEqual(reopened["look"],validate_look(original,self.roles))
        with self.assertRaises(PermissionError):
            self.looks.open(self.pid,"DirectorLook001",1,
                            scene_sha256="0"*64)
        next_look=copy.deepcopy(original)
        next_look["camera"]["exposure_ev"]=1.5
        follow=self.looks.publish(
            self.pid,"DirectorLook001",
            scene_id="scene_reusable",scene_revision=1,
            scene_sha256=self.sha,look=next_look,
            expected_revision=1,approve=lambda _:True)
        self.assertEqual(follow["revision"],2)
        self.assertEqual(
            self.looks.open(self.pid,"DirectorLook001",1,
                            scene_sha256=self.sha)["look"],original)
        self.assertEqual(self.scene.open(
            self.pid,"scene_reusable",1)[0]["document_sha256"],
            source_before["document_sha256"])

    def test_ai_receives_verified_scene_facts_but_never_inherits_grants(self):
        brief=self.looks.assistant_scene_brief(
            self.pid,scene_id="scene_reusable",scene_revision=1,
            scene_sha256=self.sha)
        self.assertEqual(brief["scene_sha256"],self.sha)
        self.assertEqual(len(brief["material_sources"]),3)
        self.assertFalse(brief["source_mutation_permitted"])
        proposal=self.looks.validate_assistant_proposal(
            self.pid,scene_id="scene_reusable",scene_revision=1,
            scene_sha256=self.sha,look=propose_look(
                "dramatic",self.roles)["look"],
            rationale="Lower ambient and place attention on the actor")
        self.assertEqual(proposal["changed_areas"],["lighting","camera"])
        self.assertFalse(proposal["creator_approved"])
        self.assertFalse(proposal["persisted"])
        self.assertFalse(proposal["may_execute_native_tools"])
        self.assertFalse(proposal["may_author_shader_code"])
        with self.assertRaises(ValueError):
            self.looks.validate_assistant_proposal(
                self.pid,scene_id="scene_reusable",scene_revision=1,
                scene_sha256=self.sha,look=default_look(),
                rationale="malformed\\x00instruction")
        with self.assertRaises(PermissionError):
            self.looks.assistant_scene_brief(
                self.pid,scene_id="scene_reusable",scene_revision=1,
                scene_sha256="0"*64)

    def test_invalid_source_paths_and_arbitrary_look_properties_fail_closed(self):
        bad=default_look()
        bad["materials"]["/Other/Intruder"]={
            "opacity":.5,"transmission":1.,"ior":1.5,"thickness_m":.1}
        with self.assertRaises(ValueError):
            validate_look(bad,self.roles)
        bad=default_look()
        bad["environment"]["preset"]="https://unauthorized.example/hdr"
        with self.assertRaises(ValueError):
            validate_look(bad,self.roles)
        bad=default_look()
        bad["camera"]["exposure_ev"]=float("nan")
        with self.assertRaises(ValueError):
            validate_look(bad,self.roles)
        bad=default_look()
        bad["textures"]["transforms"]["/World/Actor"]={
            "arbitrary_shader":{"repeat":[1,1],"offset":[0,0],
                                "rotation_deg":0}}
        with self.assertRaises(ValueError):
            validate_look(bad,self.roles)
        with self.assertRaises(ValueError):
            propose_look("model says run remote code",self.roles)
        with self.assertRaises(PermissionError):
            self.looks.publish(
                self.pid,"OtherLook001",
                scene_id="scene_reusable",scene_revision=1,
                scene_sha256="0"*64,look=default_look(),
                approve=lambda _:True)


if __name__=="__main__":
    unittest.main()
