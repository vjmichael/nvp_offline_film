"""SLATE-01: native Take and OpenUSD coverage graph, reversible slate choices."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly

T=TICKS_PER_SECOND


class SlateBranchNativeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name)
        self.studio=Studio(self.folder/"film.sqlite")
        self.pid=self.studio.create_project("Scene 01 alternate takes","Slate")["id"]
        self.index=FilmIndex(self.studio)
        self.scene=OpenUSDSceneBridge(self.index)
        self.ledger=TemporalLedger(self.index)
        self.take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="director_freezes_take")
        self.shots=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda event,scope:
            event=="director_blocks_shot")
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda event,scope:
            event=="director_chose_cut" and
            scope["operation"]=="nvp.slate.choose_branch.v1" and
            scope["final_render_approval"] is False)
        self.scene.publish(self.pid,"scene_01",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,2,-6]},
        ],curves=[{"path":"/World/Actor","samples":[
            {"tick":0,"position":[0,0,0]},
            {"tick":3*T,"position":[6,0,0]},
        ]}])
        self.index.register_revision(
            self.pid,"actor_original","performance",
            {"format":"nvp.slate.test.actor","name":"Actor"})
        for no,verb in ((1,"walk"),(2,"run"),(3,"wild laugh and exit")):
            self.ledger.publish(self.pid,"events_"+str(no),[{
                "event_id":"beat_"+str(no),"event_kind":"action",
                "subject_id":"Actor","start_tick":0,"end_tick":3*T,
                "source_id":"actor_original","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor","verb":verb},
            }],duration_tick=4*T)
            self.take.freeze(
                self.pid,"take_"+str(no),scene_id="scene_01",
                scene_revision=1,timeline_id="events_"+str(no),
                timeline_revision=1,sample_ticks=[0,T,2*T],
                creator_event="director_freezes_take")
        for letter,x in (("A",1),("B",-1)):
            self.shots.publish(
                self.pid,"coverage_"+letter,take_id="take_1",
                start_tick=T,end_tick=2*T,
                changes=[{"path":"/World/Actor","property":"translation_offset",
                          "value":[x,0,0]}],
                purpose="framing",continuity_policy="intentional_cheat",
                reason="Director chooses a better mark for camera "+letter,
                creator_event="director_blocks_shot")

    def _node(self,branch,kind,parent,fork,group,primary,take_id,start,end,
              shot_id=None,shot_revision=None,slate_shot="01A",
              camera="A",number=1,wild=False,notes=""):
        return {
            "branch_id":branch,"kind":kind,
            "parent_id":parent,"fork_tick":fork,
            "group_id":group,"primary":primary,
            "take_id":take_id,"source_start_tick":start,
            "source_end_tick":end,"shot_id":shot_id,
            "shot_revision":shot_revision,
            "slate":{
                "scene":"01","setup":"A","shot":slate_shot,
                "camera":camera,"take_number":number,
                "wild":wild,"script_revision":"script_3","notes":notes
            },
        }

    def graph_nodes(self):
        return [
            self._node("master_take_1","performance",None,None,
                       "scene_main",True,"take_1",0,4*T,
                       slate_shot="scene_master"),
            self._node("camera_A","coverage","master_take_1",T,
                       "reaction_beat",True,"take_1",T,2*T,
                       shot_id="coverage_A",shot_revision=1,
                       camera="A",slate_shot="01A"),
            self._node("camera_B","coverage","master_take_1",T,
                       "reaction_beat",False,"take_1",T,2*T,
                       shot_id="coverage_B",shot_revision=1,
                       camera="B",slate_shot="01B"),
            self._node("take_2_branch","performance","master_take_1",T,
                       "reaction_beat",False,"take_2",T,2*T,
                       number=2,slate_shot="01A",
                       notes="Alternative dialogue and delivery"),
            self._node("wild_take_3","performance","master_take_1",T,
                       "reaction_beat",False,"take_3",T,3*T,
                       number=3,wild=True,slate_shot="01W",
                       notes="Unscripted longer version"),
        ]

    def publish(self,nodes=None,graph_id="scene_01_slate"):
        return self.slate.publish_graph(
            self.pid,graph_id,scene_id="scene_01",scene_label="01",
            nodes=nodes if nodes is not None else self.graph_nodes())

    def test_graph_has_parallel_camera_views_and_distinct_frozen_performances(self):
        graph=self.publish()
        self.assertEqual(graph["kind"],"presentation")
        view=self.slate.view(self.pid,"scene_01_slate",1)
        reaction=view["parallel_groups"]["reaction_beat"]
        self.assertEqual(len(reaction),4)
        self.assertEqual(
            [n["branch_id"] for n in reaction if n["selected"]],["camera_A"])
        self.assertEqual(
            {n["take_id"] for n in reaction if n["kind"]=="coverage"},
            {"take_1"})
        self.assertEqual(
            {n["take_id"] for n in reaction if n["kind"]=="performance"},
            {"take_2","take_3"})
        wild=next(n for n in reaction if n["branch_id"]=="wild_take_3")
        self.assertTrue(wild["slate"]["wild"])
        self.assertTrue(wild["requires_cut_or_retime_decision"])
        self.assertEqual(wild["duration_delta_from_default_tick"],T)
        self.assertEqual(
            view["parallel_groups"]["scene_main"][0]["display_color"],"green")
        self.assertIn({"object_id":"scene_01_slate","revision":1},
                      self.index.direct_dependents(self.pid,"take_3",1))

    def test_choose_alternate_turns_old_green_gray_and_is_reversible(self):
        self.publish()
        chosen=self.slate.choose(
            self.pid,"scene_01_edit",graph_id="scene_01_slate",
            graph_revision=1,group_id="reaction_beat",
            branch_id="wild_take_3",editor_event="director_chose_cut")
        self.assertEqual(chosen["revision"],1)
        first=self.slate.view(
            self.pid,"scene_01_slate",1,
            edit_id="scene_01_edit",edit_revision=1,
            group_id="reaction_beat")
        self.assertEqual(
            [x["branch_id"] for x in first["parallel_groups"]["reaction_beat"]
             if x["display_color"]=="green"],["wild_take_3"])
        second=self.slate.choose(
            self.pid,"scene_01_edit",graph_id="scene_01_slate",
            graph_revision=1,group_id="reaction_beat",
            branch_id="camera_B",editor_event="director_chose_cut",
            expected_revision=1)
        self.assertNotEqual(chosen["document_sha256"],second["document_sha256"])
        latest=self.slate.view(
            self.pid,"scene_01_slate",1,
            edit_id="scene_01_edit",edit_revision=2,
            group_id="reaction_beat")
        self.assertEqual(
            [x["branch_id"] for x in latest["parallel_groups"]["reaction_beat"]
             if x["selected"]],["camera_B"])
        self.assertEqual(self.slate.view(
            self.pid,"scene_01_slate",1,
            edit_id="scene_01_edit",edit_revision=1)["selected_by_group"][
                "reaction_beat"],"wild_take_3")
        for number in (1,2,3):
            self.assertEqual(
                self.take.verify_take(self.pid,"take_"+str(number))["status"],
                "VERIFIED_FROZEN_DATA_TAKE")

    def test_restart_uses_identical_shas_and_linked_original_scene(self):
        self.publish()
        self.slate.choose(
            self.pid,"cut",graph_id="scene_01_slate",graph_revision=1,
            group_id="reaction_beat",branch_id="take_2_branch",
            editor_event="director_chose_cut")
        new=DigitalSlateBranches(
            FilmIndex(Studio(self.studio.db_path)),
            verify_editor_action=lambda *_:False)
        read=new.view(self.pid,"scene_01_slate",1,edit_id="cut",
                      edit_revision=1)
        self.assertEqual(read["selected_by_group"]["reaction_beat"],
                         "take_2_branch")
        self.assertEqual(
            read["parallel_groups"]["reaction_beat"][0]["take_document_sha256"],
            self.index.read_revision(self.pid,"take_1",1)["document_sha256"])
        self.assertFalse(read["scene_or_take_mutated"])
        self.assertFalse(read["frames_rendered"])

    def test_refuse_cross_take_coverage_cycle_fake_parent_and_two_defaults(self):
        source=self.graph_nodes()
        alien=[dict(n) for n in source]
        alien[1]={**alien[1],"take_id":"take_2"}
        with self.assertRaises(ValueError):
            self.publish(alien,"bad_camera")
        cyclic=[dict(n) for n in source]
        cyclic[3]={**cyclic[3],"parent_id":"wild_take_3"}
        with self.assertRaises(ValueError):
            self.publish(cyclic,"future_parent")
        double=[dict(n) for n in source]
        double[2]={**double[2],"primary":True}
        with self.assertRaises(ValueError):
            self.publish(double,"bad_default")
        other=self.studio.create_project("Other project","")["id"]
        with self.assertRaises(KeyError):
            self.slate.publish_graph(
                other,"alien_graph",scene_id="scene_01",
                scene_label="01",nodes=source)

    def _source_for_assembly(self):
        # A third camera coverage of a DIFFERENT original performance:
        # this is the user's Wild Take 3 -> Camera B of Take 2 case.
        self.shots.publish(
            self.pid,"take2_camera_b",take_id="take_2",
            start_tick=T,end_tick=2*T,
            changes=[{"path":"/World/Actor","property":"translation_offset",
                      "value":[-2,0,0]}],
            purpose="framing",continuity_policy="intentional_cheat",
            reason="Take 2 reverse angle has a stronger reaction",
            creator_event="director_blocks_shot")
        nodes=self.graph_nodes()
        nodes.append(self._node(
            "camera_B_take2","coverage","take_2_branch",T,
            "reaction_beat",False,"take_2",T,2*T,
            shot_id="take2_camera_b",shot_revision=1,
            camera="B",slate_shot="02B",number=2))
        self.publish(nodes)
        assembly=SlateSequenceAssembly(
            self.slate,verify_editor_action=lambda token,scope:
            token=="make_active" and
            scope["operation"]=="nvp.slate.commit_assembled_edit.v1" and
            scope["final_render_approval"] is False)
        return assembly

    def test_edit_mixed_take_sequence_and_explicit_make_active_only(self):
        assembly=self._source_for_assembly()
        wild={"segment_id":"wild_clip","branch_id":"wild_take_3",
              "source_in_tick":T,"source_out_tick":2*T}
        angle={"segment_id":"camera_b_clip","branch_id":"camera_B_take2",
               "source_in_tick":T,"source_out_tick":2*T}
        draft=assembly.preview(
            self.pid,"scene_01_slate",1,[wild],
            inspect_branch_id="camera_B_take2")
        self.assertTrue(draft["draft_uncommitted"])
        self.assertEqual(draft["inspection_only_branch_id"],"camera_B_take2")
        self.assertFalse(draft["selection_changes_active_cut"])
        self.assertEqual(draft["active_segments_by_branch"],{})
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"assembled_cut",1)
        two=assembly.edit_draft(
            [wild],operation="insert_after",
            target_segment_id="wild_clip",segment=angle)
        result=assembly.preview(
            self.pid,"scene_01_slate",1,two,
            inspect_branch_id="camera_A")
        self.assertEqual([s["branch_id"] for s in result["segments"]],
                         ["wild_take_3","camera_B_take2"])
        self.assertEqual(result["duration_tick"],2*T)
        self.assertTrue(result["segments"][1]["incoming_transition"][
            "requires_continuity_review"])
        self.assertEqual(result["segments"][1]["timeline_start_tick"],T)
        with self.assertRaises(PermissionError):
            assembly.commit(
                self.pid,"assembled_cut",graph_id="scene_01_slate",
                graph_revision=1,segments=two,editor_event="only_inspecting")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"assembled_cut",1)
        committed=assembly.commit(
            self.pid,"assembled_cut",graph_id="scene_01_slate",
            graph_revision=1,segments=two,editor_event="make_active")
        self.assertEqual(committed["revision"],1)
        active=assembly.active_view(
            self.pid,"scene_01_slate",1,
            edit_id="assembled_cut",edit_revision=1,
            inspection_branch_id="camera_A")
        active_reaction=active["parallel_groups"]["reaction_beat"]
        self.assertEqual(
            {n["branch_id"] for n in active_reaction if n["selected"]},
            {"wild_take_3","camera_B_take2"})
        self.assertTrue(next(x for x in active_reaction if
                             x["branch_id"]=="camera_A")["inspection_focus"])
        self.assertEqual(
            next(x for x in active_reaction if
                 x["branch_id"]=="camera_A")["display_color"],"gray")
        self.assertEqual(len(active["sequence"]),2)
        self.assertFalse(active["render_approved"])

    def test_copy_paste_before_move_and_trim_do_not_change_old_cut(self):
        assembly=self._source_for_assembly()
        wild={"segment_id":"wild","branch_id":"wild_take_3",
              "source_in_tick":T,"source_out_tick":3*T}
        angle={"segment_id":"angle","branch_id":"camera_B_take2",
               "source_in_tick":T,"source_out_tick":2*T}
        first=assembly.commit(
            self.pid,"film_cut",graph_id="scene_01_slate",
            graph_revision=1,segments=[wild,angle],editor_event="make_active")
        self.assertEqual(first["revision"],1)
        # Duplicate source by REFERENCE with a new segment ID, not by
        # copying actors, the underlying USD or any physical media.
        copy={**angle,"segment_id":"another_angle"}
        expanded=assembly.edit_draft(
            [wild,angle],operation="insert_before",
            target_segment_id="wild",segment=copy)
        moved=assembly.edit_draft(
            expanded,operation="move_after",
            target_segment_id="angle",new_segment_id="wild")
        trimmed=assembly.edit_draft(
            moved,operation="trim",target_segment_id="wild",
            trim_in_tick=2*T,trim_out_tick=3*T)
        self.assertEqual([s["segment_id"] for s in trimmed],
                         ["another_angle","angle","wild"])
        preview=assembly.preview(
            self.pid,"scene_01_slate",1,trimmed,
            active_edit_id="film_cut",active_edit_revision=1,
            inspect_branch_id="camera_A")
        self.assertEqual(len(preview["active_segments_by_branch"][
            "wild_take_3"]),1)
        self.assertEqual(preview["segments"][-1]["source_in_tick"],2*T)
        self.assertTrue(preview["draft_uncommitted"])
        self.assertEqual(len(assembly.open_edit(
            self.pid,"film_cut",1)["data"]["segments"]),2)
        newer=assembly.commit(
            self.pid,"film_cut",graph_id="scene_01_slate",
            graph_revision=1,segments=trimmed,editor_event="make_active",
            expected_revision=1)
        self.assertNotEqual(first["document_sha256"],newer["document_sha256"])
        self.assertEqual(
            [s["segment_id"] for s in assembly.open_edit(
                self.pid,"film_cut",1)["data"]["segments"]],
            ["wild","angle"])
        self.assertEqual(
            [s["segment_id"] for s in assembly.open_edit(
                self.pid,"film_cut",2)["data"]["segments"]],
            ["another_angle","angle","wild"])
        with self.assertRaises(Exception):
            assembly.commit(
                self.pid,"film_cut",graph_id="scene_01_slate",
                graph_revision=1,segments=[wild],editor_event="make_active",
                expected_revision=1)

    def test_sixty_takes_plus_coverage_are_not_arbitrarily_limited_to_64(self):
        nodes=self.graph_nodes()
        for n in range(60):
            nodes.append(self._node(
                "extra_take_"+str(n),"performance","master_take_1",T,
                "reaction_beat",False,"take_2" if n%2==0 else "take_3",
                T,2*T,number=n+4,wild=bool(n%2),
                slate_shot="01A",camera="B",
                notes="Slate extra version "+str(n)))
        graph=self.publish(nodes,graph_id="large_slate")
        view=self.slate.view(self.pid,"large_slate",1)
        self.assertEqual(len(view["parallel_groups"]["reaction_beat"]),64)
        self.assertEqual(graph["data"]["source_take_count"],3)
        self.assertEqual(sum(1 for item in
            view["parallel_groups"]["reaction_beat"] if item["selected"]),1)

    def test_original_mainline_remains_before_and_after_parallel_splices(self):
        assembly=self._source_for_assembly()
        # Explicit parent continuity sections stay active before and after
        # the parallel decision, instead of implying the whole scene forks.
        source=[
            {"segment_id":"original_intro","branch_id":"master_take_1",
             "source_in_tick":0,"source_out_tick":T},
            {"segment_id":"wild_insert","branch_id":"wild_take_3",
             "source_in_tick":T,"source_out_tick":2*T},
            {"segment_id":"alt_camera_B","branch_id":"camera_B_take2",
             "source_in_tick":T,"source_out_tick":2*T},
            {"segment_id":"original_outro","branch_id":"master_take_1",
             "source_in_tick":2*T,"source_out_tick":3*T},
        ]
        original_take=self.index.read_revision(self.pid,"take_1",1)
        assembly.commit(
            self.pid,"splice_full",graph_id="scene_01_slate",
            graph_revision=1,segments=source,editor_event="make_active")
        active=assembly.active_view(
            self.pid,"scene_01_slate",1,
            edit_id="splice_full",edit_revision=1)
        self.assertEqual([x["branch_id"] for x in active["sequence"]],
                         ["master_take_1","wild_take_3",
                          "camera_B_take2","master_take_1"])
        self.assertEqual([x["timeline_start_tick"] for x in active["sequence"]],
                         [0,T,2*T,3*T])
        root=active["parallel_groups"]["scene_main"][0]
        self.assertEqual(len(root["active_source_ranges"]),2)
        self.assertEqual(
            [(x["source_in_tick"],x["source_out_tick"])
             for x in root["active_source_ranges"]],
            [(0,T),(2*T,3*T)])
        self.assertEqual(
            self.index.read_revision(self.pid,"take_1",1)["document_sha256"],
            original_take["document_sha256"])
        self.assertFalse(active["render_approved"])

    def test_assembled_cut_reopens_from_filmindex_after_restart(self):
        assembly=self._source_for_assembly()
        source=[{"segment_id":"first","branch_id":"wild_take_3",
                 "source_in_tick":T,"source_out_tick":2*T},
                {"segment_id":"next","branch_id":"camera_B_take2",
                 "source_in_tick":T,"source_out_tick":2*T}]
        assembly.commit(
            self.pid,"cut",graph_id="scene_01_slate",graph_revision=1,
            segments=source,editor_event="make_active")
        studio=Studio(self.studio.db_path)
        index=FilmIndex(studio)
        recovered=SlateSequenceAssembly(
            DigitalSlateBranches(index,verify_editor_action=lambda *_:False),
            verify_editor_action=lambda *_:False)
        saved=recovered.open_edit(self.pid,"cut",1)
        self.assertEqual(len(saved["data"]["segments"]),2)
        self.assertEqual(saved["data"]["segments"][0][
            "source_take_document_sha256"],
            self.index.read_revision(self.pid,"take_3",1)["document_sha256"])
        self.assertEqual(saved["data"]["segments"][1][
            "source_take_document_sha256"],
            self.index.read_revision(self.pid,"take_2",1)["document_sha256"])
        self.assertFalse(saved["data"]["source_performance_modified"])

    def test_refuse_forged_choice_and_never_grant_master_approval(self):
        self.publish()
        with self.assertRaises(ValueError):
            self.slate.choose(
                self.pid,"bad_edit",graph_id="scene_01_slate",
                graph_revision=1,group_id="reaction_beat",
                branch_id="master_take_1",editor_event="director_chose_cut")
        with self.assertRaises(PermissionError):
            self.slate.choose(
                self.pid,"no_permission",graph_id="scene_01_slate",
                graph_revision=1,group_id="reaction_beat",
                branch_id="wild_take_3",editor_event="ai_attempts_choice")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"no_permission",1)
        okay=self.slate.choose(
            self.pid,"valid",graph_id="scene_01_slate",graph_revision=1,
            group_id="reaction_beat",branch_id="wild_take_3",
            editor_event="director_chose_cut")
        data=self.index.read_revision(self.pid,"valid",1)["data"]
        self.assertFalse(data["render_approved"])
        self.assertFalse(data["source_performances_modified"])


if __name__=="__main__":
    unittest.main()
