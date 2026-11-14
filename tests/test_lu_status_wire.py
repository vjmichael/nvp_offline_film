"""B5: native Lu status-only authorization, replay and real AF_UNIX pair."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest

from backend.nvp_lu_alpha_contract import LuRuntimeView
from backend.nvp_lu_status_wire import (
    REQUEST,RESPONSE,StatusGrant,StatusHostProof,canonical,parse,
    request,unwrap,verify_reply,wrap,
)
from backend.nvp_lu_status_socket import LuStatusClient,read_frame,send_frame
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def sample():
    return ResourceSnapshot(1,32768,23000,0,())


def grant():
    return StatusGrant("film_project","a"*32,b"k"*32,int(time.time()*1000)+30000)


def idle():
    return {"modelRef":None,"sessionId":None,"generationId":None,
            "phase":"Idle","pid":None}


class B5AuthenticatedStatusTests(unittest.TestCase):
    def test_readonly_authorized_request_and_exact_response(self):
        with tempfile.TemporaryDirectory() as root:
            g=grant();gate=StatusHostProof(TaskLedger(root,sampler=sample),g)
            req=request(g)
            parsed=gate.accept(req)
            self.assertEqual(parsed["operation"],"status")
            reply=gate.respond(parsed,idle())
            self.assertEqual(verify_reply(g,req,reply),idle())

    def test_mutations_wrong_scope_foreign_host_and_model_control_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            g=grant();gate=StatusHostProof(TaskLedger(root,sampler=sample),g)
            source=request(g)
            data=unwrap(g.key,REQUEST,source)
            for changes in (
                {"operation":"load"},{"operation":"unload"},
                {"operation":"generate"},{"operation":"cancel"},
                {"project":"other_project"},{"epoch":"b"*32},
                {"v":2},{"id":"short"},
            ):
                changed=dict(data);changed.update(changes)
                with self.subTest(changes=changes):
                    with self.assertRaises(PermissionError):
                        gate.accept(wrap(g.key,REQUEST,changed))
            foreign=StatusGrant(g.project,g.epoch,b"X"*32,g.expires_ms)
            with self.assertRaises(PermissionError):
                gate.accept(request(foreign))
            altered=bytearray(source);altered[-6]=ord("z")
            with self.assertRaises((PermissionError,ValueError)):
                gate.accept(bytes(altered))

    def test_nonce_replay_and_durable_revocation(self):
        with tempfile.TemporaryDirectory() as root:
            g=grant();ledger=TaskLedger(root,sampler=sample)
            gate=StatusHostProof(ledger,g);raw=request(g)
            gate.accept(raw)
            reopened=StatusHostProof(TaskLedger(root,sampler=sample),g)
            with self.assertRaises(PermissionError):
                reopened.accept(raw)
            reopened.revoke()
            with self.assertRaises(PermissionError):
                gate.accept(request(g))
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_expiry_future_request_and_invalid_scope(self):
        with tempfile.TemporaryDirectory() as root:
            g=grant();gate=StatusHostProof(TaskLedger(root,sampler=sample),g)
            with self.assertRaises(PermissionError):
                request(g,now_ms=g.expires_ms+1)
            raw=request(g)
            with self.assertRaises(PermissionError):
                gate.accept(raw,now_ms=int(time.time()*1000)+6000)

    def test_wrong_correlated_response_never_becomes_status(self):
        with tempfile.TemporaryDirectory() as root:
            g=grant();gate=StatusHostProof(TaskLedger(root,sampler=sample),g)
            req=request(g)
            checked=gate.accept(req)
            good=unwrap(g.key,RESPONSE,gate.respond(checked,idle()))
            for change in ({"id":"b"*32},{"epoch":"b"*32},
                           {"project":"other_project"},{"operation":"unload"},
                           {"v":2}):
                changed=dict(good);changed.update(change)
                with self.subTest(change=change):
                    with self.assertRaises(PermissionError):
                        verify_reply(g,req,wrap(g.key,RESPONSE,changed))
            with self.assertRaises(ValueError):
                gate.respond(checked,{"modelRef":None,"sessionId":None,
                                      "generationId":None,"phase":"Ready","pid":None})

    def test_duplicate_noncanonical_and_oversize_frame_rejected(self):
        with self.assertRaises(ValueError):
            parse(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            parse(b'{"b":2, "a":1}')
        with self.assertRaises(ValueError):
            parse(b"x"*8193)
        with self.assertRaises(ValueError):
            canonical({"oversized":"x"*9000})

    def test_real_local_socket_status_read_only(self):
        if not hasattr(socket,"AF_UNIX"):
            self.skipTest("System AF_UNIX unavailable")
        with tempfile.TemporaryDirectory(prefix="nvb5-") as root:
            ep=Path(root)/"lu.sock"
            if len(str(ep))>=99:
                self.skipTest("OS temp path too long for AF_UNIX")
            ledger=TaskLedger(Path(root)/"ledger",sampler=sample)
            g=grant();gate=StatusHostProof(ledger,g)
            failures=[]
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.settimeout(5)
                server.bind(str(ep))
                server.listen(1)
                def serve():
                    try:
                        conn,_=server.accept()
                        with conn:
                            conn.settimeout(4)
                            original=read_frame(conn)
                            checked=gate.accept(original)
                            send_frame(conn,gate.respond(checked,idle()))
                    except Exception as exc:
                        failures.append(str(exc))
                t=threading.Thread(target=serve,daemon=True)
                t.start()
                client=LuStatusClient(ep,g)
                result=client.fetch_status()
                t.join(timeout=5)
                self.assertEqual(failures,[])
                self.assertFalse(t.is_alive())
                self.assertEqual(result,idle())
                # Even an authenticated Lu status response is not proof NVP
                # owns the model or is authorized to load/unload it.
                self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            try:ep.unlink()
            except FileNotFoundError:pass

    def test_status_observation_never_reserves_or_releases_lu_memory(self):
        if not hasattr(socket,"AF_UNIX"):
            self.skipTest("System AF_UNIX unavailable")
        with tempfile.TemporaryDirectory(prefix="nvb5-") as root:
            ep=Path(root)/"status.sock"
            if len(str(ep))>=99:
                self.skipTest("OS temp path too long")
            ledger=TaskLedger(Path(root)/"ledger",sampler=sample)
            g=grant();gate=StatusHostProof(ledger,g)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.settimeout(5)
                server.bind(str(ep));server.listen(1)
                def serve():
                    conn,_=server.accept()
                    with conn:
                        conn.settimeout(4)
                        data=gate.accept(read_frame(conn))
                        send_frame(conn,gate.respond(data,idle()))
                t=threading.Thread(target=serve,daemon=True);t.start()
                observer=LuStatusClient(ep,g).make_passive_observer(ledger)
                report=observer.observe()
                t.join(timeout=5)
                self.assertFalse(t.is_alive())
                self.assertFalse(report["model_loading_authorized"])
                self.assertFalse(report["model_unloading_authorized"])
                self.assertFalse(report["nvp_owned"])
                self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            try:ep.unlink()
            except FileNotFoundError:pass


if __name__=="__main__":
    unittest.main()
