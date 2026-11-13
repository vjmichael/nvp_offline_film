"""P1-B acceptance contracts only: mocked test waveforms are never hardware evidence."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import struct
from unittest.mock import patch

import pytest

from tools.nvp_p1b_physical_device_acceptance import (
    inspect_original_pcm, verify_adc_packets, explicit_original_recording)


def test_rejects_unverified_silence_and_clipping(tmp_path):
    pcm=tmp_path/"original.pcm"
    for value in (0,32767):
        raw=struct.pack("<h",value)*48000
        pcm.write_bytes(raw)
        with pytest.raises(RuntimeError,match="silence or clipping"):
            inspect_original_pcm(pcm,expected_count=48000,
                                 expected_sha=sha256(raw).hexdigest())


def test_rejects_changed_original_source_digest_and_truncation(tmp_path):
    pcm=tmp_path/"original.pcm"
    raw=struct.pack("<h",1500)*48000
    pcm.write_bytes(raw)
    good=inspect_original_pcm(pcm,expected_count=48000,
                              expected_sha=sha256(raw).hexdigest())
    assert good["sample_count"]==48000
    assert good["signal_present"] is True
    with pytest.raises(RuntimeError):
        inspect_original_pcm(pcm,expected_count=48000,expected_sha="0"*64)
    pcm.write_bytes(raw[:-2])
    with pytest.raises(RuntimeError):
        inspect_original_pcm(pcm,expected_count=48000,
                             expected_sha=sha256(raw).hexdigest())


def test_physical_device_acceptance_denied_without_owner_authorization():
    with patch("builtins.input",return_value="DENY"):
        with pytest.raises(PermissionError,match="operator"):
            explicit_original_recording(4,None)


def test_two_independent_physical_devices_reject_identical_endpoints():
    with pytest.raises(ValueError,match="distinct"):
        explicit_original_recording(4,[1,1])


def test_real_adc_requires_actual_clock_evidence(tmp_path):
    frame=tmp_path/"recorded.frames"
    # Genuine 48-kHz ADC callbacks advance by 10 ms for 480 samples.
    # Missing calibration (not a fabricated discontinuity) is this gate.
    frame.write_bytes(b"".join(
        struct.pack("<IqB",480,i*10_000_000,1) for i in range(100)))
    with pytest.raises(RuntimeError,match="insufficient clock evidence"):
        verify_adc_packets(frame,1,48000,calibrations=[])


def test_frozen_package_worker_uses_pinned_desktop_exe_not_source_py(tmp_path):
    spool=tmp_path/"nvp-live-original-1234567890abcd"
    spool.mkdir()
    binary=tmp_path/"NVP.exe"
    binary.write_bytes(b"PE SOURCE CONTRACT ONLY")
    class Fake:
        @staticmethod
        def launch(command, **kwargs):
            assert command[:2]==[str(binary),"--device-producer-worker"]
            assert "nvp_native_device_producer_worker.py" not in " ".join(command)
            assert kwargs["linux_cgroup_tree_required"] is True
            raise RuntimeError("expected no actual hardware")
    from backend.nvp_device_producer_custody import SupervisedNativeDevice
    from unittest.mock import patch as patcher
    with patcher("sys.frozen",True,create=True),patcher("sys.executable",str(binary)):
        with patcher("backend.nvp_device_producer_custody.launch_contained",
                     side_effect=Fake.launch):
            dev=SupervisedNativeDevice(spool,mode="mono",max_samples=48000,
                                       scope_digest="a"*64)
            with pytest.raises(RuntimeError,match="expected no actual hardware"):
                dev.start()
    assert not (spool/"producer-mono.complete").exists()
