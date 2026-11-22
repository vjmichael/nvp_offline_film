"""P1-B: owner-operated *real* microphone / independent ADC acceptance.

Not a synthetic CI pass, film Take, soundtrack, or unsupervised worker.
Run only from the installed desktop's explicit acceptance role or the reviewed
source checkout. A separate physical loopback/ear check is still required.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import statistics
import struct
import tempfile
import time

from backend.nvp_device_producer_custody import SupervisedNativeDevice, scope_sha256
from backend.nvp_independent_device_sync import (
    DeviceTimeTrack, align_devices, RATE, MAX_DURATION_S)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FRAME = struct.Struct("<IqB")
FORMAT = "nvp.p1b.physical_original_audio.v1"


def inspect_original_pcm(path, *, expected_count, expected_sha):
    """Bounded independent disk read, never a replay into FilmIndex."""
    if path.is_symlink() or path.stat().st_size != 2*expected_count:
        raise RuntimeError("Physical original PCM length or file identity changed")
    digest=sha256()
    energy=0
    peak=0
    clipped=0
    samples=0
    with path.open("rb") as fp:
        while raw := fp.read(1024*1024):
            if len(raw)%2:
                raise RuntimeError("Truncated original microphone sample")
            digest.update(raw)
            for (x,) in struct.iter_unpack("<h",raw):
                peak=max(peak,abs(x))
                energy+=x*x
                samples+=1
                if abs(x)>=32767:
                    clipped+=1
    if (samples != expected_count or digest.hexdigest()!=expected_sha or
        samples< RATE):
        raise RuntimeError("Original physical microphone PCM is unverified")
    rms=math.sqrt(energy/samples)/32768.0
    # Silence and severe clipping are NOT accepted as physical signal.
    if not .0005 <= rms <= .95 or clipped/samples > .02:
        raise RuntimeError("Physical device produced silence or clipping; source retained unapproved")
    return {"sample_count":samples, "pcm_sha256":digest.hexdigest(),
            "rms_normalized":round(rms,6),
            "peak_normalized":round(peak/32768.0,6),
            "clipped_fraction":round(clipped/samples,8),
            "signal_present":True}


def verify_adc_packets(path, device_id, expected_count, *, calibrations):
    track=DeviceTimeTrack(device_id)
    if path.is_symlink() or path.stat().st_size%FRAME.size:
        raise RuntimeError("Physical ADC frame ledger is truncated")
    with path.open("rb") as source:
        while packet:=source.read(FRAME.size):
            if len(packet)!=FRAME.size:
                raise RuntimeError("Physical source ADC metadata truncated")
            frames,adc,good=FRAME.unpack(packet)
            if good != 1:
                raise RuntimeError("Native ADC callback reported a device fault")
            track.add(frames,adc,status_ok=True)
    if track.sample_count!=expected_count:
        raise RuntimeError("Real device ADC frame totals differ from PCM bytes")
    for before,stream,after in calibrations:
        track.calibrate(before,stream,after)
    model=track.seal()
    if model["source_sample_count"]!=expected_count:
        raise RuntimeError("Original ADC source changed during verification")
    return model


def _verify_protected_original_test_root(root):
    """Windows physical PCM tests require verified native EFS inheritance.

    Hosted CI without creator keys cannot substitute for this observation.
    This checks an already-provisioned protected directory, not key recovery.
    """
    if os.name != "nt":
        return False
    if root is None:
        raise PermissionError("Physical Windows sound acceptance requires an EFS-protected --temporary-root")
    import ctypes
    kernel=ctypes.windll.kernel32
    kernel.GetFileAttributesW.argtypes=[ctypes.c_wchar_p]
    kernel.GetFileAttributesW.restype=ctypes.c_uint32
    flags=kernel.GetFileAttributesW(str(root))
    if flags == 0xFFFFFFFF or not flags & 0x00004000:
        raise PermissionError("Physical original PCM test refuses non-EFS source storage")
    return True


def explicit_original_recording(duration, ids, *, output=None):
    if not 3 <= duration <= 30:
        raise ValueError("Physical acceptance duration must be 3..30 seconds")
    if ids is not None and (len(ids)!=2 or len(set(ids))!=2):
        raise ValueError("Two distinct physical ADC endpoints required")
    from backend.nvp_native_independent_take import native_input_devices
    descriptors=[]
    if ids is not None:
        available={d["device_id"]:d for d in native_input_devices()}
        if any(i not in available for i in ids):
            raise RuntimeError("Selected native audio input disconnected or unavailable")
        descriptors=[available[i] for i in ids]
    print("Original microphone device test: local-only PCM, no Digital Take or film export.")
    print("Two input devices require a real common physical sound impulse; virtual endpoints are not certified.")
    accepted=input("Type RECORD_ORIGINAL_TEST to confirm physical OS device capture: ")
    if accepted != "RECORD_ORIGINAL_TEST":
        raise PermissionError("No explicit local operator recording consent")
    base=Path(output).resolve() if output else None
    if base is not None:
        if not base.is_dir() or base.is_symlink():
            raise PermissionError("Physical evidence root must already exist and not be a symlink")
    protected=_verify_protected_original_test_root(base)
    # Temporary bytes intentionally vanish after this acceptance test.
    # Windows tests require inherited EFS before any OS device opens.
    with tempfile.TemporaryDirectory(prefix="nvp-p1b-physical-",dir=base) as root:
        source=Path(root)/"nvp-live-original-physical12345"
        source.mkdir(mode=0o700)
        if os.name=="nt" and not _verify_protected_original_test_root(source):
            raise PermissionError("New original PCM spool did not inherit Windows EFS")
        scope={"purpose":"P1-B creator-authorized physical ADC test only",
               "started_monotonic_ns":time.monotonic_ns(),
               "device_ids":ids, "descriptors":descriptors,
               "duration_seconds":duration,"take_approved":False}
        fingerprint=scope_sha256(scope)
        devices=[]
        def mono_receiver():
            item=yield
            while True:
                item=yield
        try:
            for i in range(2 if ids is not None else 1):
                dev=SupervisedNativeDevice(
                    source,mode="port" if ids is not None else "mono",
                    channel=i,device_id=ids[i] if ids is not None else -1,
                    device_descriptor=descriptors[i] if ids is not None else None,
                    max_samples=(duration+2)*RATE,scope_digest=fingerprint)
                devices.append(dev)
                if ids is None:
                    gen=mono_receiver()
                    next(gen)
                    dev.start(gen)
                else:
                    dev.start(lambda *args:None)
            time.sleep(duration)
            # Signal *both* real devices before either is reaped, preserving
            # their original shared capture interval for clock comparison.
            for dev in devices:dev.request_stop()
            for dev in devices:dev.stop()
            outcomes=[]
            models=[]
            for i,dev in enumerate(devices):
                receipt=dev.custody_receipt
                if (receipt is None or receipt.get("process_tree_custody_verified") is not True
                    or receipt.get("empty_group_verified") is not True or
                    receipt.get("worker_exit_verified") is not True or
                    receipt.get("worker_returncode")!=0):
                    raise RuntimeError("Physical ADC process tree custody not verified")
                raw=dev._checked_data()
                quality=inspect_original_pcm(
                    dev._path(".pcm"),expected_count=raw["samples"],
                    expected_sha=raw["pcm_sha256"])
                row={"source":i,"device":descriptors[i] if ids is not None else "default_mono",
                     "quality":quality,"kernel_scope":receipt["scope"],
                     "producer_exited_cleanly":True}
                if ids is not None:
                    model=verify_adc_packets(dev._path(".frames"),ids[i],
                        raw["samples"],calibrations=dev.calibration_anchors())
                    row["adc_model"]={
                        "source_sample_count":model["source_sample_count"],
                        "measured_drift_ppm":model["measured_drift_ppm"],
                        "max_adc_residual_ns":model["max_adc_residual_ns"],
                        "clock_calibration_count":model["clock_calibration_count"],
                        "adc_anchor_count":model["adc_anchor_count"]}
                    models.append(model)
                outcomes.append(row)
            if ids is not None:
                # Shared first monotonic epoch is a derived map only. It does
                # not claim genlock or an independently measured loopback.
                aligned=align_devices(*models,
                    camera_duration_tick=(duration+3)*TICKS_PER_SECOND)
            else:
                aligned=None
            report={"format":FORMAT,"status":"REAL_DEVICE_SIGNAL_AND_CUSTODY_VERIFIED",
                    "scope_sha256":fingerprint,"hardware_genlock":False,
                    "physical_loopback_independently_verified":False,
                    "creator_approved_frozen_take":False,
                    "original_source_modified":False,
                    "efs_source_protection_observed":protected,
                    "efs_key_recovery_verified":False,
                    "devices":outcomes,
                    "derived_clock_maps":aligned["sample_maps"] if aligned else None}
            print(json.dumps(report,sort_keys=True,indent=2))
            return report
        finally:
            for dev in reversed(devices):
                try:dev.close()
                except Exception as exc:
                    print("OS custody cleanup refused: "+str(exc))
                    raise


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--duration-seconds",type=int,default=4)
    parser.add_argument("--device-ids",type=int,nargs=2)
    parser.add_argument("--temporary-root",type=Path)
    args=parser.parse_args(argv)
    explicit_original_recording(args.duration_seconds,args.device_ids,
                                output=args.temporary_root)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
