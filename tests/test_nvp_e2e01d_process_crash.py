"""NVP-E2E-01D: actual host-process death at coordinator persistence boundaries.

The child process is terminated by os._exit, NOT a Python exception. Parent
opens the durable SQLite journal after the child is dead. Native B13/B14/J
workers are mocked only at staging (before process creation); this explicitly
tests coordinator crash atomicity, not an actual OS-contained render worker.
"""
from __future__ import annotations
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EXIT=93


def _child_b13(root):
    from backend.nvp_studio import Studio
    from backend.nvp_digital_capture import DigitalCapture
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import ResourceSnapshot
    from backend.nvp_b13_native_reimport import NativeB13ImportHost
    from backend.nvp_b14_native_conform import NativeB14ConformHost
    from backend.nvp_e2e01b_native_editorial import NativeEditorialChain
    studio=Studio(root/"studio.sqlite3")
    project=studio.create_project("E2E-D subprocess crash","")
    (root/"pid.txt").write_text(project["id"])
    capture=DigitalCapture(studio)
    ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        1,32768,25000,0,()))
    b13=NativeB13ImportHost(capture,ledger,root/"b13",
                            verify_creator_action=lambda *_:True)
    b14=NativeB14ConformHost(capture,ledger,root/"b14",
                             verify_creator_action=lambda *_:True)
    chain=NativeEditorialChain(capture,ledger,b13,b14)
    package=root/"package"
    package.mkdir()
    input_=root/"incoming.otio"
    input_.write_text("crash-only test, never genuine NLE input")
    with patch.object(b13,"stage_and_approve",side_effect=lambda *_a,**_kw:os._exit(EXIT)):
        chain.stage_edit(project["id"],"source",package,input_,object(),
                         edit_id="edit_alpha",presentation_id="conform_alpha",
                         destination_dir=root/"output")
    raise AssertionError("os._exit not reached")


def _child_b14(root):
    from backend.nvp_studio import Studio
    from backend.nvp_digital_capture import DigitalCapture
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import ResourceSnapshot
    from backend.nvp_b13_native_reimport import NativeB13ImportHost
    from backend.nvp_b14_native_conform import NativeB14ConformHost
    from backend.nvp_e2e01b_native_editorial import NativeEditorialChain
    studio=Studio(root/"studio.sqlite3")
    project=studio.create_project("E2E-D conform crash","")
    (root/"pid.txt").write_text(project["id"])
    capture=DigitalCapture(studio)
    ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        1,32768,25000,0,()))
    b13=NativeB13ImportHost(capture,ledger,root/"b13",
                            verify_creator_action=lambda *_:True)
    b14=NativeB14ConformHost(capture,ledger,root/"b14",
                             verify_creator_action=lambda *_:True)
    chain=NativeEditorialChain(capture,ledger,b13,b14)
    package=root/"package"
    package.mkdir()
    input_=root/"incoming.otio"
    input_.write_text("crash-only input")
    with patch.object(b13,"stage_and_approve",
                      return_value={"state":"QUEUED","job_id":"editjob_fixture"}):
        t=chain.stage_edit(project["id"],"source",package,input_,object(),
            edit_id="edit_alpha",presentation_id="conform_alpha",
            destination_dir=root/"output")
    capture.index.register_revision(project["id"],"edit_alpha","edit",
                                    {"format":"unit.handoff"})
    proof={"status":"VERIFIED_EDITED_OTIO_REVISION","edit_id":"edit_alpha",
           "revision":1,"picture_approved":False,"audio_included":False}
    with patch.object(b13,"verify_completed",return_value=proof):
        with patch.object(b14,"stage_and_approve",
                          side_effect=lambda *_a,**_kw:os._exit(EXIT)):
            chain.stage_conform(t["chain_id"],object())
    raise AssertionError("os._exit not reached")


def _child_av(root,mode="av"):
    from backend.nvp_studio import Studio
    from backend.nvp_digital_capture import DigitalCapture
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import ResourceSnapshot
    from backend.nvp_audio01i_native_host import NativeAudio01IHost
    from backend.nvp_audio01j_native_host import NativeAudio01JHost
    from backend.nvp_audio01k_native_host import NativeAudio01KHost
    from backend.nvp_e2e01c_finishing import NativeFinishingHandoff
    studio=Studio(root/"studio.sqlite3")
    project=studio.create_project("E2E-D AV crash","")
    pid=project["id"]
    (root/"pid.txt").write_text(pid)
    capture=DigitalCapture(studio)
    ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        1,32768,25000,0,()))
    creator=lambda *_:True
    audio=NativeAudio01IHost(capture,ledger,root/"audio",
              verify_creator_action=creator,strict_linux_tree=False)
    av=NativeAudio01JHost(capture,ledger,root/"av",
              verify_creator_action=creator,audio_host=audio,
              strict_linux_tree=False)
    dist=NativeAudio01KHost(capture,ledger,
              av_host=av,verify_creator_action=creator)
    chain=NativeFinishingHandoff(capture,ledger,audio,av,dist)
    lock=capture.index.register_revision(pid,"picture_lock","presentation",
         {"format":"unit","picture_locked":True,"director_approved":True})
    capture.index.register_revision(pid,"approved_audio","audio",
         {"format":"unit","director_approved":True})
    (root/"picture").mkdir()
    (root/"approved_audio_dir").mkdir()
    def checked_lock(_capture,project_id,lock_id):
        if project_id!=pid or lock_id!="picture_lock":
            raise PermissionError("Wrong picture lock")
        return capture.index.read_revision(pid,lock_id,1),None
    with patch("backend.nvp_e2e01c_finishing.validate_picture_lock",
               side_effect=checked_lock),patch.object(
               audio,"verify_delivery",return_value={"status":"VERIFIED"}):
        chain.register(pid,"picture_lock","approved_audio",
          movie_dir=root/"picture",audio_dir=root/"approved_audio_dir",
          final_dir=root/"final_av",export_id="approved_movie",
          distribution_id="mezzanine",distribution_dir=root/"distribution")
        if mode=="av":
            with patch.object(av,"stage",side_effect=lambda *_a,**_kw:os._exit(EXIT)):
                chain.stage_final_av(pid,"approved_movie","native_creator_event")
        else:
            with patch.object(av,"stage",return_value={
                    "state":"QUEUED","job_id":"avjob_fixture",
                    "export_id":"approved_movie"}):
                chain.stage_final_av(pid,"approved_movie","native_creator_event")
            capture.index.register_revision(pid,"approved_movie","master",{
                "format":"nvp.audio01j.final_av_master.v1",
                "final_master":True,"dcp_delivered":False,
                "picture_lock_id":"picture_lock",
                "audio_delivery_id":"approved_audio"})
            with patch.object(ledger,"get_task",return_value={
                    "state":"SUCCEEDED","reserved":0}),patch.object(
                    av,"verify_published",return_value={
                    "status":"VERIFIED_FINAL_AV_MASTER"}):
                chain.verify_final_av(pid,"approved_movie")
                with patch.object(dist,"publish",
                       side_effect=lambda *_a,**_kw:os._exit(EXIT)):
                    chain.publish_mezzanine(
                        pid,"approved_movie","distribution_creator_event")
    raise AssertionError("os._exit not reached")


def _child_reserved_worker(root):
    from backend.nvp_studio import Studio
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
    studio=Studio(root/"studio.sqlite3")
    project=studio.create_project("E2E-D held RAM after host death","")
    (root/"pid.txt").write_text(project["id"])
    ledger=TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        1,32768,25000,0,()))
    admitted=ledger.admit(AdmissionRequest(
        "owned_native_worker","compositing","Crash-injected reserved worker",1024))
    if not admitted["admitted"]:
        raise RuntimeError("Test did not reserve RAM before process death")
    os._exit(EXIT)


def child(case,root):
    {"b13":_child_b13,"b14":_child_b14,"av":_child_av,
     "distribution":lambda p:_child_av(p,mode="distribution"),
     "reservation":_child_reserved_worker}[case](root)


def _reopen_coord(root,case,pid):
    """Instantiate new Studio, ledger, native hosts and coordinator post-crash."""
    from backend.nvp_studio import Studio
    from backend.nvp_digital_capture import DigitalCapture
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import ResourceSnapshot
    studio=Studio(root/"studio.sqlite3")
    capture=DigitalCapture(studio)
    ledger=TaskLedger(root/"ledger",sampler=lambda:
        ResourceSnapshot(1,32768,25000,0,()))
    creator=lambda *_:False  # recovery does not spend new creator permission
    if case in ("b13","b14"):
        from backend.nvp_b13_native_reimport import NativeB13ImportHost
        from backend.nvp_b14_native_conform import NativeB14ConformHost
        from backend.nvp_e2e01b_native_editorial import NativeEditorialChain
        b13=NativeB13ImportHost(capture,ledger,root/"b13",
                                verify_creator_action=creator)
        b14=NativeB14ConformHost(capture,ledger,root/"b14",
                                verify_creator_action=creator)
        coordinator=NativeEditorialChain(capture,ledger,b13,b14)
        with ledger._db() as db:
            chain_id=db.execute("""SELECT chain_id FROM native_e2e01b_chains
                WHERE project_id=?""",(pid,)).fetchone()[0]
        return coordinator.reopen(chain_id)
    from backend.nvp_audio01i_native_host import NativeAudio01IHost
    from backend.nvp_audio01j_native_host import NativeAudio01JHost
    from backend.nvp_audio01k_native_host import NativeAudio01KHost
    from backend.nvp_e2e01c_finishing import NativeFinishingHandoff
    audio=NativeAudio01IHost(capture,ledger,root/"audio",
            verify_creator_action=creator,strict_linux_tree=False)
    av=NativeAudio01JHost(capture,ledger,root/"av",
            verify_creator_action=creator,audio_host=audio,
            strict_linux_tree=False)
    dist=NativeAudio01KHost(capture,ledger,av_host=av,
            verify_creator_action=creator)
    coordinator=NativeFinishingHandoff(capture,ledger,audio,av,dist)
    return coordinator.reopen(pid,"approved_movie")


class ProcessDeathRecovery(unittest.TestCase):
    def _crash(self,case):
        with tempfile.TemporaryDirectory(prefix="nvp-e2e01d-") as path:
            root=Path(path)
            repo_root = Path(__file__).resolve().parents[1]
            # A script executed by filename puts tests/ (not the repository root)
            # on sys.path. Give crash-injected children the same backend import
            # path regardless of pytest, unittest, or runner environment.
            child_env = os.environ.copy()
            child_env["PYTHONPATH"] = os.pathsep.join(filter(None, (
                str(repo_root), child_env.get("PYTHONPATH", ""))))
            result=subprocess.run(
                [sys.executable,str(Path(__file__).resolve()),"--child",case,str(root)],
                cwd=repo_root,env=child_env,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=False)
            self.assertEqual(result.returncode,EXIT,result.stderr.decode("utf8","replace"))
            pid=(root/"pid.txt").read_text()
            with closing(sqlite3.connect(root/"ledger"/"task_activity.sqlite3")) as db:
                if case=="reservation":
                    row=db.execute("""SELECT state,reserved,ram_mb FROM tasks
                        WHERE id='owned_native_worker'""").fetchone()
                    self.assertEqual(row,("ACTIVE",1,1024))
                    # A new process cannot infer an OS termination witness.
                    from backend.nvp_resource_ledger import TaskLedger
                    from backend.nvp_resource_guard import ResourceSnapshot
                    opened=TaskLedger(root/"ledger",sampler=lambda:
                        ResourceSnapshot(1,32768,25000,0,()))
                    record=opened.get_task("owned_native_worker")
                    self.assertEqual((record["state"],record["reserved"]),
                                     ("ACTIVE",1))
                    self.assertEqual(opened.snapshot()["reservations"]["ram_mb"],1024)
                elif case in ("b13","b14"):
                    row=db.execute("""SELECT state,import_job,conform_job
                        FROM native_e2e01b_chains WHERE project_id=?""",(pid,)).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row[0],"IMPORT_STAGING_UNCERTAIN" if case=="b13"
                                     else "CONFORM_STAGING_UNCERTAIN")
                    if case=="b13":
                        self.assertTrue(row[1].startswith("pending_editorial_"))
                    else:
                        self.assertIsNone(row[2])
                else:
                    row=db.execute("""SELECT state,av_job,distribution_sha
                        FROM native_e2e01c_handoffs WHERE project_id=?""",(pid,)).fetchone()
                    if case=="av":
                        self.assertEqual(row[0],"AV_STAGING_UNCERTAIN")
                        self.assertIsNone(row[1])
                    else:
                        self.assertEqual(row[0],"DISTRIBUTION_UNCERTAIN")
                        self.assertEqual(row[1],"avjob_fixture")
                    self.assertIsNone(row[2])
                # Never synthesize a success or release another producer's
                # RAM from an unknown worker state.
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE state='SUCCEEDED'").fetchone()[0],0)
            if case!="reservation":
                recovered=_reopen_coord(root,case,pid)
                self.assertEqual(recovered["state"],{
                    "b13":"IMPORT_STAGING_UNCERTAIN",
                    "b14":"CONFORM_STAGING_UNCERTAIN",
                    "av":"AV_STAGING_UNCERTAIN",
                    "distribution":"DISTRIBUTION_UNCERTAIN"}[case])
                self.assertTrue(recovered["requires_native_reconciliation"])
                self.assertFalse(recovered.get("recovered_without_relaunch",False))
            with closing(sqlite3.connect(root/"studio.sqlite3")) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM projects WHERE id=?",(pid,)).fetchone()[0],1)
                film_table=db.execute("""SELECT name FROM sqlite_master
                    WHERE type='table' AND name='film_objects'""").fetchone()
                if film_table is None:
                    # A resource-only crash must not need to initialize the
                    # FilmIndex just to assert that no film was published.
                    self.assertEqual(case,"reservation")
                else:
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM film_objects WHERE project_id=? AND kind='master'",
                        (pid,)).fetchone()[0],1 if case=="distribution" else 0)

    def test_b13_staging_abrupt_process_death(self):
        self._crash("b13")

    def test_b14_staging_abrupt_process_death(self):
        self._crash("b14")

    def test_final_av_staging_abrupt_process_death(self):
        self._crash("av")

    def test_distribution_publication_abrupt_process_death(self):
        self._crash("distribution")

    def test_active_native_ram_reservation_survives_host_process_death(self):
        self._crash("reservation")


if __name__=="__main__":
    if len(sys.argv)==4 and sys.argv[1]=="--child":
        child(sys.argv[2],Path(sys.argv[3]))
    else:
        unittest.main()
