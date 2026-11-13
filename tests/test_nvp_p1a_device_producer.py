"""P1-A checks: no physical ADC fixture, no fake kernel-acceptance claim.

These exercise original PCM integrity, source-scope binding, verified shutdown
ordering and fail-closed publication. Native Windows Job/Linux cgroup and
installed microphone testing remain separate original-OS acceptance gates.
"""
from __future__ import annotations

import array
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest.mock import patch

import pytest

from backend.nvp_device_producer_custody import SupervisedNativeDevice, scope_sha256


class ContainedFixture:
    def __init__(self, spool, scope, *, bad_checksum=False, missing_complete=False):
        self.spool = Path(spool)
        self.scope = scope
        self.bad_checksum = bad_checksum
        self.missing_complete = missing_complete
        self.pid = 71234
        self.returncode = None
        self.cgroup = self.spool / "private-cgroup-leaf"
        self.cgroup.mkdir()
        self.terminated = False
        self.closed = False

    def poll(self):
        if not (self.spool / "producer-mono.stop").exists():
            return None
        if self.returncode is None:
            pcm = self.spool / "producer-mono.pcm"
            frames = self.spool / "producer-mono.frames"
            signal = struct.pack("<hhh",12,-5,300)
            packet = struct.pack("<IqB",3,0,1)
            pcm.write_bytes(signal)
            frames.write_bytes(packet)
            if not self.missing_complete:
                note = {
                    "format":"nvp.device_producer.v1",
                    "scope_sha256":self.scope,
                    "mode":"mono","sample_rate":48000,
                    "samples":3,
                    "pcm_sha256":("0" * 64 if self.bad_checksum
                                   else sha256(signal).hexdigest()),
                    "frames_sha256":sha256(packet).hexdigest(),
                    "calibrations":[],
                }
                (self.spool / "producer-mono.complete").write_text(
                    json.dumps(note), encoding="utf8")
            self.returncode = 0
        return self.returncode

    def terminate_tree(self):
        assert self.poll() == 0
        self.terminated = True

    def close(self):
        assert self.terminated
        self.cgroup.rmdir()
        self.closed = True


@pytest.fixture()
def spool(tmp_path):
    folder = tmp_path / "nvp-live-original-1234567890abcdef"
    folder.mkdir()
    return folder


@pytest.mark.skipif(sys.platform != "linux", reason="Uses mocked Linux OS supervisor")
def test_device_pcm_only_replayed_after_original_cgroup_shutdown(spool):
    digest = scope_sha256({"project":"p","scene":"sha","native_approval":True})
    proc = ContainedFixture(spool,digest)
    def launch(command, **kwargs):
        assert command[0] == sys.executable
        assert "--device-identity" not in command
        assert kwargs["linux_cgroup_tree_required"] is True
        assert kwargs["cwd"] == spool
        (spool / "producer-mono.ready").write_text(json.dumps({
            "scope_sha256":digest,"mode":"mono","pid":proc.pid}))
        return proc
    received = []
    def callback():
        sample = yield
        while True:
            received.extend(sample.tolist())
            assert proc.closed and proc.terminated
            sample = yield
    coro = callback()
    next(coro)
    with patch("backend.nvp_device_producer_custody.launch_contained", launch):
        device = SupervisedNativeDevice(spool, mode="mono", max_samples=10,
                                        scope_digest=digest)
        device.start(coro)
        assert received == []
        device.stop()
        assert received == [12,-5,300]
        assert device.custody_receipt["scope"] == "linux-cgroup-v2"
        assert device.custody_receipt["empty_group_verified"] is True
        device.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Uses mocked Linux OS supervisor")
@pytest.mark.parametrize("missing_complete,bad_checksum",[(True,False),(False,True)])
def test_no_original_pcm_replay_without_completed_matching_worker_receipt(
        spool,missing_complete,bad_checksum):
    digest = scope_sha256({"original":"approved"})
    proc = ContainedFixture(spool,digest,bad_checksum=bad_checksum,
                            missing_complete=missing_complete)
    def launch(command, **kwargs):
        (spool / "producer-mono.ready").write_text(json.dumps({
            "scope_sha256":digest,"mode":"mono","pid":proc.pid}))
        return proc
    seen = []
    with patch("backend.nvp_device_producer_custody.launch_contained",launch):
        device = SupervisedNativeDevice(spool,mode="mono",max_samples=10,
                                        scope_digest=digest)
        device.start(lambda v:seen.append(v))
        with pytest.raises(RuntimeError):
            device.stop()
    assert proc.closed
    assert seen == []
    assert not device.custody_receipt is None


@pytest.mark.skipif(sys.platform != "linux", reason="Uses mocked Linux OS supervisor")
def test_cancel_does_not_need_fabricated_clean_pcm_receipt(spool):
    digest = scope_sha256({"original":"approved"})
    proc = ContainedFixture(spool,digest)
    def launch(command, **kwargs):
        (spool / "producer-mono.ready").write_text(json.dumps({
            "scope_sha256":digest,"mode":"mono","pid":proc.pid}))
        return proc
    # An explicit cancellation kills/reaps the supervisor before any Take.
    with patch("backend.nvp_device_producer_custody.launch_contained",launch):
        device = SupervisedNativeDevice(spool,mode="mono",max_samples=10,
                                        scope_digest=digest)
        device.start()
        # Close calls terminate_tree without a stop/complete file.
        # This fixture's terminate implementation is strict about clean stop,
        # so use a cancellation fixture that models kernel kill independently.
        def forced_kill():
            proc.terminated = True
            proc.returncode = -9
        proc.terminate_tree = forced_kill
        device.close()
        assert proc.closed
        assert device.custody_receipt["process_tree_custody_verified"]
        assert not (spool / "producer-mono.complete").exists()


def test_constructor_rejects_unauthorized_worker_paths_or_digest(tmp_path,spool):
    with pytest.raises(PermissionError):
        SupervisedNativeDevice(tmp_path,mode="mono",max_samples=5,
                               scope_digest="a"*64)
    with pytest.raises(ValueError):
        SupervisedNativeDevice(spool,mode="mono",max_samples=5,
                               scope_digest="not-a-sha")
    with pytest.raises(ValueError):
        SupervisedNativeDevice(spool,mode="port",max_samples=5,
                               scope_digest="a"*64,device_id=2,device_descriptor={})
