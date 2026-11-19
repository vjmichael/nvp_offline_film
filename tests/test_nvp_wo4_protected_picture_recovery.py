"""Genuine Windows protected picture-reel checkpoint/reopen pilot.

Uses generated source fixtures and actual pinned codecs. No claim of an
installed host, full-length film, sound delivery, or DCI certification.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_nvp_wo3_native_delivery as fixture_module
from backend.nvp_wo3_native_codecs import ProtectedCodecAuthority,ApprovedCodecBinary,ROLES
from backend.nvp_wo4_mastering_decision import register_mastering_decision
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_production_journal import SingletonSupervisor
from backend.nvp_wo4_feature_journal import FeatureJournal,ASSEMBLY_FORMAT
from backend.nvp_wo5_original_short import inspect_indexed_reel,inspect_original_single_reel_readiness
from backend.nvp_wo5_original_feature import inspect_indexed_feature,inspect_original_feature_readiness
from backend.nvp_wo5_codec_binding import pinned_codec_pair
from backend.nvp_wo5_finished_playback import FinishedFilmPlayer
import base64
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_wo3_independent_essence import decode_full_multireel_candidate,decode_full_dcp_candidate
import ctypes
from backend.nvp_production_supervisor import ProductionSupervisor
from backend.nvp_wo4_pcm_stream import _hash_stream


@unittest.skipUnless(os.environ.get("NVP_WO3_FIXTURE_MANIFEST_PIN"),"Reviewed native CI fixture required")
class NativePictureCheckpointRecovery(unittest.TestCase):
    def test_real_picture_checkpoint_reopens_and_finishes(self):
        f=fixture_module.WO3OriginalCinemaAuthoring(
            "test_real_smpte_package_metadata_is_written_and_reopened")
        f.setUp()
        self.addCleanup(f.doCleanups)
        root=Path(f.tmp.name).resolve()
        require_efs_stage(root)
        self.assertTrue(ctypes.windll.advapi32.EncryptFileW(str(f.index.studio.db_path)))
        journal=FeatureJournal(root/"production")
        bundle=Path(os.environ["NVP_WO3_FIXTURE_BUNDLE"])
        runtime=Path(os.environ["NVP_WO3_FIXTURE_ROOT"])
        manifest=json.loads((bundle/"nvp-codec-manifest.json").read_text("ascii"))
        def factory(pid,check):
            self.assertEqual(pid,f.pid)
            seen=set()
            def approve(scope):
                identity=(scope["job_id"],scope.get("invocation_id"))
                if scope["project_id"]!=pid or identity in seen:
                    return False
                seen.add(identity)
                return True
            host=ProtectedCodecAuthority(bundle,manifest,
                manifest_sha256=os.environ["NVP_WO3_FIXTURE_MANIFEST_PIN"],
                runtime=runtime,project_id=pid,authorize_stage=approve,
                authorize_execution=approve,check_cancel=check)
            products=("OpenJPEG-opj_compress","ASDCP-asdcp_wrap","ASDCP-asdcp_info")
            return tuple(ApprovedCodecBinary(bundle/manifest["tools"][ROLES[p]]["filename"],
                         sha256=manifest["tools"][ROLES[p]]["sha256"],product=p,authority=host)
                         for p in products)
        pictures=[]
        sources=[]
        for n in (32,1024,2048):
            raw=n.to_bytes(2,"big")*3*(1998*1080)
            source=root/f"source-{n}.xyz12"
            source.write_bytes(raw)
            sources.append(str(source))
            pictures.append({"format":"nvp.wo4.xyz12_master_candidate.v1",
               "original_take_sha256":f.sha,"xyz12":raw,"xyz12_sha256":sha256(raw).hexdigest(),
               "profile":"2K_FLAT_24","width":1998,"height":1080,
               "source_modified":False,"production_picture_accepted":False})
        pcm=b"\0"*(6000*2*3)
        sound=master_pcm24_candidate(pcm,source_sha256=sha256(pcm).hexdigest(),
            original_take_sha256=f.sha,cinema_frames=3,channel_layout="stereo",creator_approved=True)
        decision=register_mastering_decision(f.index,f.pid,take_id="FrozenFixture",take_revision=1,
            take_sha256=f.sha,picture=pictures[0],ordered_pictures=pictures,sound=sound,
            qc=evaluate_master_candidates(pictures[0],sound),
            decision_id="NativeProductionDecision",approve=lambda _:True)
        self.assertEqual(decision["status"],"MASTERING_DECISION_RECORDED")
        enc,wrap,info=factory(f.pid,lambda:False)
        uid=journal.submit_reel(f.index,f.pid,mastering_decision_id="NativeProductionDecision",
            frame_sources=sources,openjpeg=enc,wrapper=wrap,info=info,approve=lambda _:True)["job_id"]
        with SingletonSupervisor(journal.root):
            runner=ProductionSupervisor(journal,resolve_project=lambda _:f.index,codec_factory=factory)
            self.assertEqual(runner.run_one()["status"],"PICTURE_FRAME_CHECKPOINTED")
        first=journal.status(uid)["segments"][0]["verified_sha256"]
        self.assertTrue(first)
        reopened=FeatureJournal(journal.root)
        with SingletonSupervisor(reopened.root):
            recovered=reopened.cinema_reconcile()
            self.assertEqual(recovered["jobs"][0]["reused_verified_frames"],1)
            runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
            self.assertEqual(runner.run_one()["position"],1)
            self.assertEqual(runner.run_one()["position"],2)
            result=runner.run_one()
            self.assertEqual(result["status"],"FILE_BACKED_PICTURE_MXF_READY")
            self.assertEqual(reopened.cinema_reconcile()["jobs"][0]["status"],"RECONCILED")
        snap=reopened.status(uid)
        self.assertEqual(snap["state"],"OUTPUT_READY")
        self.assertEqual(snap["verified_segments"],3)
        self.assertEqual(snap["segments"][0]["verified_sha256"],first)
        self.assertEqual(len({s["verified_sha256"] for s in snap["segments"]}),3)
        self.assertEqual(_hash_stream(Path(result["path"])),(result["sha256"],result["bytes"]))
        for source,picture in zip(sources,pictures):
            self.assertEqual(_hash_stream(Path(source))[0],picture["xyz12_sha256"])
        # Reopened picture job is now attached to a separately approved
        # encrypted PCM master and exported to its durable DCP/FilmIndex.
        exports=root/"exports-supervised";exports.mkdir()
        pcm_path=root/"master-a.pcm";pcm_path.write_bytes(pcm)
        wav=stream_master_pcm24_candidate(pcm_path,source_sha256=sha256(pcm).hexdigest(),
            original_take_sha256=f.sha,cinema_frames=3,channel_layout="stereo",
            output_root=exports,approve=lambda _:True)
        self.assertEqual(reopened.attach_delivery(f.index,uid,sound_candidate=wav,
            output_root=exports,title="Native source reel A",approve=lambda _:True)["status"],"SOUND_PENDING")
        for expected in ("FILE_BACKED_SOUND_MXF_READY","PUBLISHED_PENDING_INDEX","STRUCTURAL_DCP_FILMINDEX_RECORDED"):
            reopened=FeatureJournal(journal.root)
            with SingletonSupervisor(reopened.root):
                reopened.reconcile_after_restart()
                reopened.cinema_reconcile()
                reopened.delivery_reconcile()
                runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
                state=runner.run_one()
                self.assertEqual(state["status"],expected,state)
        second=OpenUSDTakeCapture(f.index,verify_creator_action=lambda event,scope:
            event=="approved" and scope["operation"]=="nvp.freeze.usd_temporal_take.v1").freeze(
            f.pid,"FrozenFixtureB",scene_id="CinemaScene",scene_revision=1,
            timeline_id="CinemaEvents",timeline_revision=1,
            sample_ticks=[0,TICKS_PER_SECOND],creator_event="approved")
        origin=second["document_sha256"]
        self.assertNotEqual(origin,f.sha)
        new_pictures=[]
        new_paths=[]
        for n in (256,1200,3500):
            raw=n.to_bytes(2,"big")*3*(1998*1080)
            path=root/f"source-b-{n}.xyz12";path.write_bytes(raw)
            new_paths.append(str(path))
            new_pictures.append({**pictures[0],"xyz12":raw,
                "xyz12_sha256":sha256(raw).hexdigest(),"original_take_sha256":origin})
        pcm_b=b"\x01\x00\x00\x04\x00\x00"*6000
        sound_b=master_pcm24_candidate(pcm_b,source_sha256=sha256(pcm_b).hexdigest(),
            original_take_sha256=origin,cinema_frames=3,channel_layout="stereo",creator_approved=True)
        self.assertEqual(register_mastering_decision(f.index,f.pid,take_id="FrozenFixtureB",take_revision=1,
            take_sha256=origin,picture=new_pictures[0],ordered_pictures=new_pictures,sound=sound_b,
            qc=evaluate_master_candidates(new_pictures[0],sound_b),decision_id="NativeProductionDecisionB",
            approve=lambda _:True)["status"],"MASTERING_DECISION_RECORDED")
        enc,wrap,info=factory(f.pid,lambda:False)
        uid_b=reopened.submit_reel(f.index,f.pid,mastering_decision_id="NativeProductionDecisionB",
            frame_sources=new_paths,openjpeg=enc,wrapper=wrap,info=info,approve=lambda _:True)["job_id"]
        with SingletonSupervisor(reopened.root):
            runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
            for i in range(3):
                self.assertEqual(runner.run_one()["status"],"PICTURE_FRAME_CHECKPOINTED")
            self.assertEqual(runner.run_one()["status"],"FILE_BACKED_PICTURE_MXF_READY")
        pcm_path_b=root/"master-b.pcm";pcm_path_b.write_bytes(pcm_b)
        wav_b=stream_master_pcm24_candidate(pcm_path_b,source_sha256=sha256(pcm_b).hexdigest(),
            original_take_sha256=origin,cinema_frames=3,channel_layout="stereo",
            output_root=exports,approve=lambda _:True)
        reopened.attach_delivery(f.index,uid_b,sound_candidate=wav_b,output_root=exports,
            title="Native source reel B",approve=lambda _:True)
        with SingletonSupervisor(reopened.root):
            runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
            for expected in ("FILE_BACKED_SOUND_MXF_READY","PUBLISHED_PENDING_INDEX","STRUCTURAL_DCP_FILMINDEX_RECORDED"):
                self.assertEqual(runner.run_one()["status"],expected)
        dep=[]
        ledgers=[]
        for job_id in (uid,uid_b):
            d=reopened.delivery(job_id);r=reopened.reel(job_id)
            dep.append({"object_id":"WO3DCP_"+d["cpl_uuid"].replace("-",""),
                        "revision":1,"role":"presentation"})
            ledgers.append({"picture_uuid":r["picture_uuid"],"sound_uuid":d["sound_uuid"],
                "frames":3,"ordered_codestream_sha256":[x["verified_sha256"] for x in reopened.status(job_id)["segments"]],
                "pcm_sha256":d["master_pcm_sha256"]})
        f.index.register_revision(f.pid,"NativeApprovedFeature","edit",
            {"format":ASSEMBLY_FORMAT,"ordered_reel_job_ids":[uid,uid_b],
             "start_tick":0,"end_tick":6*(TICKS_PER_SECOND//24)},
            expected_revision=0,dependencies=dep)
        fid=reopened.submit_feature(f.index,f.pid,assembly_id="NativeApprovedFeature",
            assembly_revision=1,ordered_job_ids=[uid,uid_b],title="Native feature pilot",
            profile="2K_FLAT_24",output_root=exports,approve=lambda _:True)["feature_id"]
        with SingletonSupervisor(reopened.root):
            runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
            published=runner.run_one()
            self.assertEqual(published["status"],"FEATURE_PUBLISHED_PENDING_INDEX",published)
        reopened=FeatureJournal(journal.root)
        with SingletonSupervisor(reopened.root):
            self.assertEqual(reopened.reconcile_features()["jobs"][0]["state"],"PUBLISHED_PENDING_INDEX")
            runner=ProductionSupervisor(reopened,resolve_project=lambda _:f.index,codec_factory=factory)
            self.assertEqual(runner.run_one()["status"],"MULTIREEL_FEATURE_FILMINDEX_RECORDED")
        check=lambda:False
        authority=factory(f.pid,check)[0].authority
        unwrap,decoder=pinned_codec_pair(bundle,manifest,authority.pin,authority=authority,
                                        project_id=f.pid,check_cancel=check)
        with self.assertRaises(PermissionError):
            pinned_codec_pair(bundle,manifest,authority.pin,authority=authority,
                              project_id="other-project",check_cancel=check)
        with self.assertRaises(PermissionError):
            pinned_codec_pair(bundle,manifest,authority.pin,authority=authority,
                              project_id=f.pid,check_cancel=lambda:False)
        for job in (uid,uid_b):
            receipt=inspect_indexed_reel(f.index,reopened,f.pid,job)
            self.assertEqual(receipt["status"],"INDEXED_REEL_SOURCE_CUSTODY_VERIFIED")
            self.assertEqual(receipt["frame_count"],3)
            self.assertFalse(receipt["production_acceptance"])
            self.assertNotIn(str(root),str(receipt))
            # Real short playback admission must not be confused with the
            # specific one-second varied-frame creative proof threshold.
            with self.assertRaises(ValueError):
                inspect_original_single_reel_readiness(f.index,reopened,f.pid,job)
        film=inspect_indexed_feature(f.index,reopened,f.pid,fid)
        self.assertEqual(film["status"],"INDEXED_FEATURE_SOURCE_CUSTODY_VERIFIED")
        self.assertEqual(film["frame_count"],6)
        self.assertFalse(film["pilot_variation_checked"])
        self.assertFalse(film["production_acceptance"])
        self.assertNotIn(str(root),str(film))
        with self.assertRaises(ValueError):
            inspect_original_feature_readiness(f.index,reopened,f.pid,fid)
        print("WO5_PROTECTED_INDEXED_REEL_AND_FEATURE_DECODER_ADMISSION_PASS",flush=True)
        first_d=reopened.delivery(uid)
        single=decode_full_dcp_candidate(exports/("DCP_"+first_d["cpl_uuid"]),
            unwrap=unwrap,decoder=decoder,expected_frames=3,
            expected_picture_codestream_sha256=ledgers[0]["ordered_codestream_sha256"],
            expected_sound_pcm_sha256=ledgers[0]["pcm_sha256"])
        self.assertTrue(single["pcm24_48000_sample_exact"])
        full=decode_full_multireel_candidate(published["destination"],unwrap=unwrap,decoder=decoder,
            expected_reels=ledgers)
        self.assertEqual(full["frames_decoded"],6)
        self.assertEqual(reopened.feature(fid)["state"],"INDEXED")
        self.assertEqual(len({h for r in full["reels"] for h in r["decoded_frame_sha256"]}),6)
        self.assertTrue(all(r["pcm24_48000_sample_exact"] for r in full["reels"]))
        self.assertFalse(full["production_dcp_accepted"])
        def playback_factory(pid,cancel):
            host=factory(pid,cancel)[0].authority
            return pinned_codec_pair(bundle,manifest,host.pin,authority=host,project_id=pid,check_cancel=cancel)
        approved=[False]
        revoked=[False]
        player=FinishedFilmPlayer(f.index,reopened,codec_factory=playback_factory,
            native_window=lambda:True,ask_native=lambda scope:approved[0],host_revoked=lambda:revoked[0])
        self.addCleanup(player.close)
        self.assertEqual(player.begin(f.pid,fid)["status"],"DENIED")
        approved[0]=True
        opened=player.begin(f.pid,fid)
        self.assertEqual(opened["frame_count"],6)
        self.assertFalse(opened["continuous_real_time_playback_verified"])
        ticket=opened["session_id"]
        with self.assertRaises(PermissionError):
            player.begin(f.pid,fid)
        with self.assertRaises(PermissionError):
            player.frame("wrong-ticket",0)
        with self.assertRaises(ValueError):
            player.frame(ticket,6)
        first=player.window(ticket,0,2)
        tail=player.window(ticket,2,4)
        self.assertEqual(tail["frame_count"],1)
        # Active reel input handle denies external writes; preview is not a
        # plaintext scratch proxy or a mutable stat-only source binding.
        with self.assertRaises((OSError,PermissionError)):
            with (Path(published["destination"])/"picture_0000.mxf").open("r+b"):
                pass
        second=player.window(ticket,3,3)
        selected=first["frames"]+tail["frames"]+second["frames"]
        self.assertEqual([x["frame_index"] for x in selected],list(range(6)))
        self.assertEqual([x["audio_start_sample"] for x in selected],[2000*i for i in range(6)])
        self.assertEqual([x["decoded_xyz12_sha256"] for x in selected],
                         [h for reel in full["reels"] for h in reel["decoded_frame_sha256"]])
        self.assertEqual([x["source_pcm24_sha256"] for x in selected],
                         [sha256(pcm[i*12000:(i+1)*12000]).hexdigest() for i in range(3)]+
                         [sha256(pcm_b[i*12000:(i+1)*12000]).hexdigest() for i in range(3)])
        self.assertTrue(all(base64.b64decode(x["picture_png_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
                            and len(base64.b64decode(x["stereo_pcm16_base64"]))==8000 for x in selected))
        seek=player.frame(ticket,1)
        self.assertEqual(seek["decoded_xyz12_sha256"],selected[1]["decoded_xyz12_sha256"])
        self.assertEqual(player.stop(ticket)["status"],"STOPPED")
        self.assertIsNone(player._active)
        self.assertIsNone(player._pcm_cache)
        with self.assertRaises(PermissionError):
            player.frame(ticket,0)
        single_review=player.begin(f.pid,uid,single_reel=True)
        single_frame=player.frame(single_review["session_id"],2)
        self.assertEqual(single_frame["decoded_xyz12_sha256"],selected[2]["decoded_xyz12_sha256"])
        revoked[0]=True
        with self.assertRaises(PermissionError):
            player.frame(single_review["session_id"],0)
        player.close()
        self.assertIsNone(player._active)
        print("WO5_PROTECTED_FINISHED_AV_PLAYBACK_PASS",{"frames":6,"reels":2,
              "nonzero_range_seek":True,"pcm24_per_frame_sha_exact":True,
              "independent_xyz12_matches":True,"single_reel":True,"native_write_denial":True,
              "not_continuous_realtime_or_installed_playback":True},flush=True)
        print("WO4_PROTECTED_FEATURE_RESTART_PILOT",{"reels":2,"unique_decoded_frames":6,
            "first_checkpoint_reused":True,"full_pcm_exact":True,"indexed":True,
            "production_dcp_accepted":False},flush=True)


        # PERF-03F-R6-R1: retain the original two-reel independent decode and
        # playback tests above. Add two separately authorized, native-encoded
        # reels from the same approved Takes to verify an ordered hierarchy
        # with two finite leaves. This deliberately repeats source material;
        # it is a short protected fixture, not a throughput/creative proof.
        from backend.nvp_production_host import NativeProductionHost
        events=[]
        def resolve_project(pid):
            if pid!=f.pid:
                raise PermissionError("Native hierarchy fixture project mismatch")
            return f.index
        def creator_action(event,scope):
            events.append((event,scope.get("operation")))
            return event=="approved" and scope.get("project_id")==f.pid
        def open_host():
            return NativeProductionHost(journal.root,resolve_project=resolve_project,
                codec_factory=factory,verify_creator_action=creator_action)
        native=open_host()
        extra=[]
        for decision_id,paths,audio in (
            ("NativeProductionDecision",sources,wav),
            ("NativeProductionDecisionB",new_paths,wav_b),
        ):
            j=native.submit_reel(f.pid,creator_event="approved",
                mastering_decision_id=decision_id,frame_sources=paths)["job_id"]
            extra.append(j)
            with native.service_session() as runner:
                for position in range(3):
                    part=runner.run_one()
                    self.assertEqual(part["status"],"PICTURE_FRAME_CHECKPOINTED",part)
                    self.assertEqual(part["position"],position)
                self.assertEqual(runner.run_one()["status"],"FILE_BACKED_PICTURE_MXF_READY")
            sound_attachment=native.attach_delivery(f.pid,j,creator_event="approved",
                sound_candidate=audio,output_root=exports,title="Hierarchy source reel")
            self.assertEqual(sound_attachment["status"],"SOUND_PENDING")
            with native.service_session() as runner:
                for expected in ("FILE_BACKED_SOUND_MXF_READY","PUBLISHED_PENDING_INDEX","STRUCTURAL_DCP_FILMINDEX_RECORDED"):
                    self.assertEqual(runner.run_one()["status"],expected)
        all_jobs=[uid,uid_b,*extra]
        extra_deps=[{"object_id":"WO3DCP_"+native.journal.delivery(j)["cpl_uuid"].replace("-",""),
                     "revision":1,"role":"presentation"} for j in extra]
        f.index.register_revision(f.pid,"NativeApprovedFeatureSecond","edit",
            {"format":ASSEMBLY_FORMAT,"ordered_reel_job_ids":extra,"start_tick":0,
             "end_tick":6*(TICKS_PER_SECOND//24)},expected_revision=0,dependencies=extra_deps)
        def exact_ref(oid):
            record=f.index.read_revision(f.pid,oid,1)
            return {"object_id":oid,"revision":1,"sha256":record["document_sha256"]}
        group=native.register_feature_sections(f.pid,"NativeFeatureHierarchy",
            [exact_ref("NativeApprovedFeature"),exact_ref("NativeApprovedFeatureSecond")],creator_event="approved")
        self.assertEqual(group["revision"],1)
        source=exact_ref("NativeFeatureHierarchy")
        denied=native.register_feature_export_assembly(f.pid,"HierarchyDenied",source,
            creator_event="denied",profile="2K_FLAT_24")
        self.assertEqual(denied,{"status":"DENIED"})
        self.assertEqual(f.index.history(f.pid,"HierarchyDenied"),[])
        native.register_feature_export_assembly(f.pid,"HierarchyExport",source,
            creator_event="approved",profile="2K_FLAT_24")
        derived=f.index.read_revision(f.pid,"HierarchyExport",1)["data"]
        self.assertEqual(derived["ordered_reel_job_ids"],all_jobs)
        self.assertEqual(derived["hierarchical_reel_receipt_sha256"],
            [native.journal.delivery(j)["filmindex_sha256"] for j in all_jobs])
        args=dict(assembly_id="HierarchyExport",assembly_revision=1,
            ordered_job_ids=all_jobs,title="Native hierarchy pilot",profile="2K_FLAT_24",output_root=exports)
        self.assertEqual(native.submit_feature(f.pid,creator_event="denied",**args)["status"],"DENIED")
        hierarchical=native.submit_feature(f.pid,creator_event="approved",**args)
        self.assertEqual(hierarchical["total_frames"],12)
        hierarchy_id=hierarchical["feature_id"]
        with native.service_session() as runner:
            output=runner.run_one()
            self.assertEqual(output["status"],"FEATURE_PUBLISHED_PENDING_INDEX",output)
        native=open_host()
        with native.service_session() as runner:
            self.assertEqual(runner.run_one()["status"],"MULTIREEL_FEATURE_FILMINDEX_RECORDED")
        self.assertEqual(native.journal.feature(hierarchy_id)["state"],"INDEXED")
        report=inspect_indexed_feature(f.index,native.journal,f.pid,hierarchy_id)
        self.assertEqual(report["frame_count"],12)
        self.assertFalse(report["production_acceptance"])
        all_ledgers=[]
        for j in all_jobs:
            d=native.journal.delivery(j);r=native.journal.reel(j)
            all_ledgers.append({"picture_uuid":r["picture_uuid"],"sound_uuid":d["sound_uuid"],"frames":3,
                "ordered_codestream_sha256":[x["verified_sha256"] for x in native.journal.status(j)["segments"]],
                "pcm_sha256":d["master_pcm_sha256"]})
        check=lambda:False
        decoder_authority=factory(f.pid,check)[0].authority
        unwrap,decoder=pinned_codec_pair(bundle,manifest,decoder_authority.pin,authority=decoder_authority,
            project_id=f.pid,check_cancel=check)
        result=decode_full_multireel_candidate(output["destination"],unwrap=unwrap,decoder=decoder,
            expected_reels=all_ledgers)
        self.assertEqual(result["frames_decoded"],12)
        self.assertEqual(sum(r["cinema_rate_constraints"]["frames_audited"] for r in result["reels"]),12)
        self.assertTrue(all(r["cinema_rate_constraints"]["declared_structure_and_rate_bounds_verified"] for r in result["reels"]))
        self.assertTrue(all(reel["pcm24_48000_sample_exact"] for reel in result["reels"]))
        # Match the previously independently decoded source content and order.
        decoded=[h for reel in result["reels"] for h in reel["decoded_frame_sha256"]]
        expected=[h for reel in full["reels"] for h in reel["decoded_frame_sha256"]]
        self.assertEqual(decoded,expected+expected)
        self.assertFalse(result["production_dcp_accepted"])
        for path,picture in [*zip(sources,pictures),*zip(new_paths,new_pictures)]:
            self.assertEqual(_hash_stream(Path(path))[0],picture["xyz12_sha256"])
        self.assertIn(("approved","nvp.wo4.approve_finite_hierarchical_export_assembly.v1"),events)
        print("NVP_PERF03F_R6_NATIVE_HIERARCHY_PILOT",{
            "reels":4,"independently_decoded_frames":12,"distinct_original_source_frames":6,
            "repeated_source_performance_intentional":True,"indexed_after_reopen":True,
            "exact_pcm":True,"production_dcp_accepted":False},flush=True)


if __name__=="__main__":
    unittest.main()
