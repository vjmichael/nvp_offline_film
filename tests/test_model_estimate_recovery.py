"""B3: strict CLI estimate provenance, lifecycle admission and advisory recovery."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from backend.nvp_guarded_model_lifecycle import StrictEstimatedCpuModelManager
from backend.nvp_model_consent import NativeModelConsent
from backend.nvp_model_estimates import (TrustedLmsEstimator,EstimateStore,CpuEstimateReceipt,
                                         operation_from_estimate,parse_cpu_estimate)
from backend.nvp_model_recovery import LocalModelObserver
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def sample(available=24000):
    return ResourceSnapshot(1,32768,available,0,())


def estimate_output(key="local/model"):
    return (f"Model: {key}\nEstimated GPU Memory: 0.00 GB\n"
            "Estimated Total Memory: 3.5 GB\n"
            "Estimate: This model may be loaded based on resource guardrails settings.\n")


def fake_receipt(*,key="local/model",context=4096,age=0):
    # A trusted estimate reader would sign this local CPU-only result.
    args=("load","--estimate-only",key,"--context-length",str(context),
          "--gpu","off","--host","127.0.0.1:1234")
    return CpuEstimateReceipt(
        model_key=key,context_length=context,estimated_total_mib=3584,
        estimated_gpu_mib=0,conservative_ram_mb=5504,
        captured_at=time.time()-age,cli_sha256="1"*64,output_sha256="2"*64,
        cli_args=args)


class Handle:
    def __init__(self,ident):
        self.ident=ident
        self.model_key="local/model"
        self.instance_reference="real-provider-reference-original"
        self.unloads=0
    def get_info(self):
        return {"identifier":self.ident,"modelKey":self.model_key,
                "instanceReference":self.instance_reference}
    def unload(self):
        self.unloads+=1


class Llm:
    def __init__(self):
        self.calls=[]
        self.handle=None
    def load_new_instance(self,key,ident,*,config):
        self.calls.append((key,ident,config))
        self.handle=Handle(ident)
        return self.handle


class Client:
    def __init__(self):
        self.llm=Llm()


class EstimateContracts(unittest.TestCase):
    def test_exact_cpu_estimate_and_conservative_headroom(self):
        result=parse_cpu_estimate(estimate_output(),model_key="local/model")
        self.assertEqual(result,{"estimated_total_mib":3584,
            "estimated_gpu_mib":0,"conservative_ram_mb":5504})

    def test_fail_closed_on_gpu_key_duplicates_and_terminal_noise(self):
        with self.assertRaises(ValueError):
            parse_cpu_estimate(estimate_output().replace("0.00 GB","1.00 GB"),
                model_key="local/model")
        with self.assertRaises(ValueError):
            parse_cpu_estimate(estimate_output(),model_key="other/model")
        with self.assertRaises(ValueError):
            parse_cpu_estimate(estimate_output()+"Estimated Total Memory: 1 GB\n",
                model_key="local/model")
        with self.assertRaises(ValueError):
            parse_cpu_estimate("\x1b[31m"+estimate_output(),model_key="local/model")
        with self.assertRaises(ValueError):
            parse_cpu_estimate(estimate_output("ok/model"),model_key="../bad")

    def test_sha_pinned_cli_exact_flags_no_shell_and_no_model_load(self):
        with TemporaryDirectory() as root:
            binary=Path(root)/"lms-native"
            binary.write_bytes(b"Trusted fake CLI executable")
            binary_sha=hashlib.sha256(binary.read_bytes()).hexdigest()
            calls=[]
            def run(argv,**kw):
                calls.append((argv,kw))
                return subprocess.CompletedProcess(argv,0,estimate_output())
            estimator=TrustedLmsEstimator(executable=binary,
                executable_sha256=binary_sha,port=1234,runner=run)
            receipt=estimator.capture("local/model",4096)
            self.assertEqual(receipt.cli_sha256,binary_sha)
            self.assertEqual(receipt.model_key,"local/model")
            self.assertEqual(receipt.conservative_ram_mb,5504)
            self.assertEqual(calls[0][0][1:],
                ["load","--estimate-only","local/model","--context-length","4096",
                 "--gpu","off","--host","127.0.0.1:1234"])
            self.assertIs(calls[0][1]["shell"],False)
            binary.write_bytes(b"tampered")
            with self.assertRaises(RuntimeError):
                estimator.capture("local/model",4096)

    def test_invalid_cli_binary_and_failed_estimate_rejected(self):
        with TemporaryDirectory() as root:
            binary=Path(root)/"lms.cmd"
            binary.write_bytes(b"echo unsafe")
            sha=hashlib.sha256(binary.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                TrustedLmsEstimator(executable=binary,executable_sha256=sha)
            binary=Path(root)/"lms-native"
            binary.write_bytes(b"native")
            sha=hashlib.sha256(binary.read_bytes()).hexdigest()
            fail=lambda argv,**kw:subprocess.CompletedProcess(argv,1,"")
            estimator=TrustedLmsEstimator(executable=binary,
                executable_sha256=sha,runner=fail)
            with self.assertRaises(RuntimeError):
                estimator.capture("local/model",4096)

    def test_proof_rejects_missing_modified_stale_and_wrong_model(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            store=EstimateStore(ledger)
            receipt=fake_receipt()
            op=operation_from_estimate("task_one",receipt)
            with self.assertRaises(PermissionError):
                store.verify(op)
            self.assertEqual(store.record("task_one",receipt),op.estimate_sha256)
            self.assertEqual(store.verify(op).digest,receipt.digest)
            with self.assertRaises(RuntimeError):
                store.verify(op,now=receipt.captured_at+301)
            with self.assertRaises(PermissionError):
                store.verify(operation_from_estimate("task_one",
                    fake_receipt(key="different/model")))
            with ledger._db() as db:
                db.execute("UPDATE model_estimate_receipts SET receipt_json=? WHERE task_id=?",
                    ("{}", "task_one"))
            with self.assertRaises(RuntimeError):
                store.verify(op)

    def test_sha_only_untrusted_operation_not_allowed(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            client=Client()
            manager=StrictEstimatedCpuModelManager(ledger,
                approval_check=lambda *_:True,client=client,estimates=EstimateStore(ledger))
            op=operation_from_estimate("task",fake_receipt())
            with self.assertRaises(PermissionError):
                manager.enqueue(op,approval_id="approved")
            self.assertIsNone(ledger.get_task("task"))


class LifecycleAndRestartContracts(unittest.TestCase):
    def manager(self,root,*,available=24000):
        ledger=TaskLedger(root,sampler=lambda:sample(available))
        store=EstimateStore(ledger)
        client=Client()
        manager=StrictEstimatedCpuModelManager(ledger,
            approval_check=lambda approval,digest,doc:approval=="creator_approved",
            client=client,estimates=store)
        return ledger,store,client,manager

    def test_full_cpu_only_owned_load_and_same_handle_release(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            receipt=fake_receipt()
            manager.enqueue_estimated("task_one",receipt,approval_id="creator_approved")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            result=manager.load_next()
            self.assertEqual(result["state"],"ACTIVE")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)
            self.assertEqual(client.llm.calls[0][2]["gpu"]["ratio"],0)
            self.assertEqual(client.llm.calls[0][2]["contextLength"],4096)
            self.assertIsNone(ledger.get_task("task_one")["completed_fraction"])
            manager.release("task_one")
            self.assertEqual(client.llm.handle.unloads,1)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)


    def test_reused_provider_identifier_cannot_authorize_foreign_unload(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            loaded=manager.load_next()
            client.llm.handle.instance_reference="different-instance-same-name"
            with self.assertRaises(RuntimeError):
                manager.release(loaded["task_id"])
            self.assertEqual(client.llm.handle.unloads,0)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)

    def test_native_consent_is_hash_bound_revocable_and_expires(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            store=EstimateStore(ledger)
            receipt=fake_receipt()
            op=operation_from_estimate("task_one",receipt)
            consent=NativeModelConsent(ledger)
            approval=consent.issue_from_trusted_ui(op,duration_s=30)
            client=Client()
            manager=StrictEstimatedCpuModelManager(ledger,
                approval_check=consent.check,client=client,estimates=store)
            manager.enqueue_estimated("task_one",receipt,approval_id=approval)
            self.assertTrue(consent.check(approval,
                hashlib.sha256(json.dumps(op.__dict__,sort_keys=True,
                  separators=(",",":")).encode()).hexdigest(),op.__dict__))
            # A change of model, context, estimate, task or hash cannot
            # borrow another creator-approved model-load permission.
            foreign=dict(op.__dict__);foreign["model_key"]="foreign/model"
            self.assertFalse(consent.check(approval,"a"*64,foreign))
            consent.revoke_from_trusted_ui(approval)
            with self.assertRaises(PermissionError):
                manager.load_next()
            self.assertEqual(client.llm.calls,[])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            with self.assertRaises(KeyError):
                consent.revoke_from_trusted_ui(approval)

    def test_native_consent_is_persistent_across_manager_restarts(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            receipt=fake_receipt()
            op=operation_from_estimate("task_one",receipt)
            creator=NativeModelConsent(ledger)
            approval=creator.issue_from_trusted_ui(op,duration_s=30)
            reopened=NativeModelConsent(TaskLedger(root,sampler=sample))
            digest=hashlib.sha256(json.dumps(op.__dict__,sort_keys=True,
                    separators=(",",":")).encode()).hexdigest()
            self.assertTrue(reopened.check(approval,digest,dict(op.__dict__)))
            reopened.revoke_from_trusted_ui(approval)
            self.assertFalse(creator.check(approval,digest,dict(op.__dict__)))

    def test_wrong_model_key_blocks_acceptance_and_keeps_reservation(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            client.llm.load_new_instance=lambda key,ident,*,config:Handle(ident)
            # This fake deliberately reports a foreign key despite the same
            # instance identifier; real producer must not accept that model.
            def wrong(key,ident,*,config):
                handle=Handle(ident)
                handle.model_key="foreign/model"
                client.llm.handle=handle
                return handle
            client.llm.load_new_instance=wrong
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            with self.assertRaises(RuntimeError):
                manager.load_next()
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)
            self.assertEqual(client.llm.handle.unloads,0)

    def test_estimate_expiry_before_claim_never_loads(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            manager.enqueue_estimated("task_one",fake_receipt(),
                                      approval_id="creator_approved")
            with ledger._db() as db:
                doc=db.execute("SELECT receipt_json FROM model_estimate_receipts").fetchone()[0]
                parsed=json.loads(doc)
                parsed["captured_at"]-=400
                # Repair SHA too to prove freshness is checked independently
                # of tamper detection. The trusted local runtime owns DB.
                new=json.dumps(parsed,sort_keys=True,separators=(",",":"))
                digest=hashlib.sha256(new.encode()).hexdigest()
                db.execute("""UPDATE model_estimate_receipts
                    SET receipt_json=?,digest=? WHERE task_id=?""",(new,digest,"task_one"))
            with self.assertRaises((RuntimeError,PermissionError)):
                manager.load_next()
            self.assertEqual(client.llm.calls,[])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_unsafe_memory_blocks_before_provider(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root,available=6500)
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            blocked=manager.load_next()
            self.assertEqual(blocked["state"],"QUEUED")
            self.assertEqual(client.llm.calls,[])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_restart_observation_present_does_not_unload_or_free(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            loaded=manager.load_next()
            instance=loaded["instance_id"]
            provider={"models":[{"key":"local/model",
                       "loaded_instances":[{"id":instance}]}]}
            observer=LocalModelObserver(TaskLedger(root,sampler=sample),
                                        reader=lambda url:json.dumps(provider).encode())
            reports=observer.observe()
            self.assertEqual(reports[0]["observation"],"PRESENT_UNVERIFIED")
            self.assertFalse(reports[0]["auto_unload"])
            self.assertFalse(reports[0]["cleanup_proven"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)
            self.assertEqual(client.llm.handle.unloads,0)
            self.assertEqual(len(observer.history("task_one")),1)

    def test_missing_remote_is_not_certified_cleanup(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            manager.load_next()
            observer=LocalModelObserver(ledger,
                reader=lambda url:b'{"models":[{"key":"local/model","loaded_instances":[]}]}')
            report=observer.observe()[0]
            self.assertEqual(report["observation"],"NOT_OBSERVED")
            self.assertFalse(report["reservation_released"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)

    def test_provider_unreachable_or_conflicted_never_releases(self):
        with TemporaryDirectory() as root:
            ledger,store,client,manager=self.manager(root)
            manager.enqueue_estimated("task_one",fake_receipt(),approval_id="creator_approved")
            loaded=manager.load_next()
            def disconnected(url):
                raise OSError("Connection refused")
            observer=LocalModelObserver(ledger,reader=disconnected)
            self.assertEqual(observer.observe()[0]["observation"],"PROVIDER_UNAVAILABLE")
            ident=loaded["instance_id"]
            wrong={"models":[{"key":"foreign/model","loaded_instances":[{"id":ident}]}]}
            conflict=LocalModelObserver(ledger,reader=lambda url:json.dumps(wrong).encode())
            self.assertEqual(conflict.observe()[0]["observation"],"IDENTITY_CONFLICT")
            self.assertEqual(client.llm.handle.unloads,0)
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],5504)

    def test_observer_rejects_malformed_or_duplicate_instances_without_false_absence(self):
        self.assertRaises(ValueError,LocalModelObserver._instances,b'{}')
        duplicated={"models":[{"key":"a","loaded_instances":[{"id":"nvp-abc"}]},
                              {"key":"b","loaded_instances":[{"id":"nvp-abc"}]}]}
        self.assertRaises(ValueError,LocalModelObserver._instances,duplicated)


if __name__=="__main__":
    unittest.main()
