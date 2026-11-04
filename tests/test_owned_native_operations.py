"""STACK-02C3B2 immutable operation and owned CPU model lifecycle contracts."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.nvp_approved_tasks import ApprovedTaskBindings
from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor
from backend.nvp_owned_models import OwnedCpuModelManager,OwnedCpuModelOperation,create_local_owned_cpu_manager
from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def measured():
    return ResourceSnapshot(1,32768,24000,0,())


class FakeHandle:
    def __init__(self,identifier):
        self.identifier=identifier
        self.unloads=0
        self.fail_unload=False

    def get_info(self):
        return {"identifier":self.identifier}

    def unload(self):
        self.unloads+=1
        if self.fail_unload:
            raise OSError("Provider response interrupted")


class FakeLLM:
    def __init__(self):
        self.calls=[]
        self.handle=None
        self.foreign_identity=False
        self.fail_after_submit=False

    def load_new_instance(self,model_key,identifier,*,config):
        self.calls.append((model_key,identifier,config))
        if self.fail_after_submit:
            raise OSError("Provider connection dropped")
        self.handle=FakeHandle("external_model" if self.foreign_identity else identifier)
        return self.handle


class FakeClient:
    def __init__(self):
        self.llm=FakeLLM()


class ApprovedBindingTests(unittest.TestCase):
    def test_exact_approval_only_and_atomic_enqueue(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            accepted=[]
            check=lambda a,d,s: accepted.append((a,d,s)) or a=="scene_approved"
            binder=ApprovedTaskBindings(ledger,approval_check=check)
            request=AdmissionRequest("job_one","blender","Test scene",1024)
            document={"task_id":"job_one","kind":"blender","scene":"a"}
            with self.assertRaises(PermissionError):
                binder.enqueue(request,owner_key="source_one",lane="interactive",
                               approval_id="unapproved",document=document)
            self.assertIsNone(ledger.get_task("job_one"))
            saved=binder.enqueue(request,owner_key="source_one",lane="interactive",
                                 approval_id="scene_approved",document=document)
            self.assertEqual(saved["spec_sha256"],hashlib.sha256(
                b'{"kind":"blender","scene":"a","task_id":"job_one"}').hexdigest())
            self.assertIsNone(binder.claim_next(owner_key="wrong_owner"))
            claimed=binder.claim_next(owner_key="source_one")
            self.assertTrue(claimed["admitted"])
            self.assertEqual(binder.verified_spec("job_one",owner_key="source_one"),document)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],1024)

    def test_revocation_and_tampering_fail_closed(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            decision={"allowed":True}
            binder=ApprovedTaskBindings(ledger,approval_check=lambda a,d,s:decision["allowed"])
            spec={"task_id":"job","kind":"blender","source":"approved"}
            binder.enqueue(AdmissionRequest("job","blender","T",2048),
                owner_key="blender_host",lane="standard",approval_id="approval_one",document=spec)
            decision["allowed"]=False
            with self.assertRaises(PermissionError):
                binder.claim_next(owner_key="blender_host")
            # A revocation caught before admission must not strand memory.
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            self.assertEqual(ledger.get_task("job")["state"],"QUEUED")
            decision["allowed"]=True
            self.assertTrue(binder.claim_next(owner_key="blender_host")["admitted"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],2048)
            with ledger._db() as db:
                db.execute("UPDATE authorized_task_specs SET spec_json=? WHERE task_id=?",
                           ('{"kind":"blender","task_id":"job","source":"tampered"}',"job"))
            with self.assertRaises(RuntimeError):
                binder.verified_spec("job",owner_key="blender_host")

    def test_bindings_survive_restart_without_unapproved_launch(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            binder=ApprovedTaskBindings(ledger,approval_check=lambda *_:True)
            document={"task_id":"restart_job","kind":"encoding","approved":True}
            binder.enqueue(AdmissionRequest("restart_job","encoding","Export",1024),
                owner_key="encoder",lane="standard",approval_id="approval",document=document)
            reopened=ApprovedTaskBindings(TaskLedger(root,sampler=measured),
                                           approval_check=lambda *_:True)
            self.assertTrue(reopened.claim_next(owner_key="encoder")["admitted"])
            self.assertEqual(reopened.verified_spec("restart_job",owner_key="encoder"),document)


class OwnedModelTests(unittest.TestCase):
    def operation(self,key="cpu_model_one"):
        return OwnedCpuModelOperation(key,"local/qwen-small",4096,4096,"a"*64)

    def test_explicit_approval_and_exact_new_instance_unload(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            client=FakeClient()
            checks=[]
            def approve(approval_id,digest,operation):
                checks.append((approval_id,digest))
                return approval_id=="creator_approved" and operation["estimate_sha256"]=="a"*64
            manager=OwnedCpuModelManager(ledger,approval_check=approve,client=client)
            with self.assertRaises(PermissionError):
                manager.enqueue(self.operation(),approval_id="unapproved")
            self.assertEqual(client.llm.calls,[])
            manager.enqueue(self.operation(),approval_id="creator_approved")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            result=manager.load_next()
            self.assertTrue(result["managed_by_nvp"])
            self.assertTrue(result["instance_id"].startswith("nvp-"))
            self.assertEqual(len(client.llm.calls),1)
            self.assertEqual(client.llm.calls[0][2]["gpu"]["ratio"],0.0)
            self.assertEqual(client.llm.calls[0][2]["contextLength"],4096)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],4096)
            self.assertIsNone(ledger.get_task(result["task_id"])["completed_fraction"])
            done=manager.release(result["task_id"])
            self.assertEqual(done["state"],"UNLOADED")
            self.assertEqual(client.llm.handle.unloads,1)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            with self.assertRaises(PermissionError):
                manager.release(result["task_id"])
            self.assertGreaterEqual(len(checks),3)

    def test_foreign_identity_never_unloads_and_does_not_free_ram(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            client=FakeClient()
            client.llm.foreign_identity=True
            manager=OwnedCpuModelManager(ledger,approval_check=lambda *_:True,client=client)
            manager.enqueue(self.operation(),approval_id="creator")
            with self.assertRaises(RuntimeError):
                manager.load_next()
            self.assertEqual(client.llm.handle.unloads,0)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],4096)
            self.assertEqual(manager.durable_attempts()[0]["state"],"UNVERIFIED")
            with self.assertRaises(PermissionError):
                manager.release("cpu_model_one")

    def test_lost_provider_ack_retains_cpu_reservation(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            client=FakeClient()
            client.llm.fail_after_submit=True
            manager=OwnedCpuModelManager(ledger,approval_check=lambda *_:True,client=client)
            manager.enqueue(self.operation(),approval_id="creator")
            with self.assertRaises(OSError):
                manager.load_next()
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],4096)
            self.assertEqual(manager.durable_attempts()[0]["state"],"UNVERIFIED")

    def test_unload_failure_and_restart_cannot_touch_foreign_model(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            client=FakeClient()
            manager=OwnedCpuModelManager(ledger,approval_check=lambda *_:True,client=client)
            manager.enqueue(self.operation(),approval_id="creator")
            loaded=manager.load_next()
            client.llm.handle.fail_unload=True
            with self.assertRaises(OSError):
                manager.release(loaded["task_id"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],4096)
            restarted=OwnedCpuModelManager(TaskLedger(root,sampler=measured),
                approval_check=lambda *_:True,client=FakeClient())
            with self.assertRaises(PermissionError):
                restarted.release(loaded["task_id"])
            self.assertEqual(restarted.durable_attempts()[0]["state"],"LOADED")


    def test_official_sdk_factory_is_numeric_loopback_only(self):
        import sys
        from types import SimpleNamespace
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=measured)
            with self.assertRaises(ValueError):
                create_local_owned_cpu_manager(ledger,approval_check=lambda *_:True,port=443)
            seen=[]
            def make_client(host):
                seen.append(host)
                return FakeClient()
            with patch.dict(sys.modules,{"lmstudio":SimpleNamespace(Client=make_client)}):
                instance=create_local_owned_cpu_manager(
                    ledger,approval_check=lambda *_:True,port=1234)
                self.assertIsInstance(instance,OwnedCpuModelManager)
            self.assertEqual(seen,["127.0.0.1:1234"])

    def test_memory_refusal_never_invokes_sdk(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=lambda:ResourceSnapshot(1,32768,6000,0,()))
            client=FakeClient()
            manager=OwnedCpuModelManager(ledger,approval_check=lambda *_:True,client=client)
            manager.enqueue(self.operation(),approval_id="creator")
            response=manager.load_next()
            self.assertFalse(response["admitted"])
            self.assertEqual(client.llm.calls,[])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)


class NativeBlenderDispatchTests(unittest.TestCase):
    def test_approved_dispatch_uses_existing_supervisor_and_verifies_output(self):
        with TemporaryDirectory() as root:
            executable=Path(root)/"blender_fake.exe"
            executable.write_bytes(b"Fake worker; patched so no process is launched")
            workspace=Path(root)/"jobs"
            ledger=TaskLedger(Path(root)/"ledger",sampler=measured)
            worker=BlenderWorkerSupervisor(workspace,
                blender_executable=executable,
                blender_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                blender_version="Blender Test",activity_ledger=ledger)
            check=lambda approval,digest,doc:approval=="scene_approved"
            dispatcher=ApprovedBlenderDispatcher(worker,ledger,approval_check=check)
            operation=BlenderOperation(job_id="approved_scene",script="trusted.py",
                script_sha256="a"*64,inputs={},outputs={},arguments={},
                memory_limit_mb=2048)
            dispatcher.enqueue(operation,approval_id="scene_approved")
            verified={"state":"SUCCEEDED","error":None,"id":"approved_scene"}
            with patch.object(worker,"_run_worker",return_value=verified) as execute, \
                 patch.object(worker,"inspect",return_value=verified), \
                 patch.object(worker,"verify_completed",return_value=verified) as audit:
                dispatcher.run_next()
                execute.assert_called_once()
                audit.assert_called_once_with("approved_scene")
            self.assertEqual(ledger.get_task(worker._activity_id("approved_scene"))["state"],"SUCCEEDED")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_worker_failure_without_cleanup_proof_retains_reservation(self):
        with TemporaryDirectory() as root:
            executable=Path(root)/"b";executable.write_bytes(b"test")
            ledger=TaskLedger(Path(root)/"ledger",sampler=measured)
            worker=BlenderWorkerSupervisor(Path(root)/"work",
                blender_executable=executable,
                blender_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                blender_version="Blender Test",activity_ledger=ledger)
            dispatcher=ApprovedBlenderDispatcher(worker,ledger,approval_check=lambda *_:True)
            op=BlenderOperation(job_id="broken_scene",script="trusted.py",
                script_sha256="a"*64,inputs={},outputs={},arguments={},memory_limit_mb=2048)
            dispatcher.enqueue(op,approval_id="creator")
            failed={"state":"FAILED","error":"OS containment cleanup unproven: guardian unavailable"}
            with patch.object(worker,"_run_worker",return_value=failed), \
                 patch.object(worker,"inspect",return_value=failed):
                with self.assertRaises(RuntimeError):
                    dispatcher.run_next()
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],2048)


if __name__=="__main__":
    unittest.main()
