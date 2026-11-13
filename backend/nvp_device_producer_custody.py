"""P1-A trusted-host device producer: actual ADC acquisition is in an OS child.

A complete PCM receipt is necessary but never sufficient: the host must close
the *original* Windows Job Object / Linux guardian+cgroup and independently
observe the empty process tree before replaying any original sample into the
source-only Take pipeline. Never construct custody from a remembered PID.
"""
from __future__ import annotations

import array
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import struct
import sys
import time

from backend.nvp_worker_containment import launch_contained

RATE = 48000
MAX_SAMPLES = RATE * 600
CHUNK = 1024 * 1024
FRAME = struct.Struct("<IqB")


def scope_sha256(scope):
    return sha256(json.dumps(scope, sort_keys=True, separators=(",",":"),
                             allow_nan=False).encode("utf8")).hexdigest()


class SupervisedNativeDevice:
    """One child-owned native microphone endpoint, not a desktop ADC adapter.

    Device selection and spool paths come exclusively from trusted Python code;
    browser/model requests may never supply executable names, directories,
    cgroup paths, process IDs, authentication or worker arguments.
    """
    uses_worker_clock = True

    def __init__(self, spool, *, mode, max_samples, scope_digest,
                 device_id=-1, device_descriptor=None, channel=0):
        if Path(spool).is_symlink():
            raise PermissionError("Symlinked recording spool refused")
        self.spool = Path(spool).resolve(strict=True)
        if (not self.spool.name.startswith("nvp-live-original-") or
            not self.spool.is_dir() or
            self.spool.is_symlink()):
            raise PermissionError("Only an authorized original capture spool can launch a device")
        if mode not in ("mono","port") or type(max_samples) is not int or not 0 < max_samples <= MAX_SAMPLES:
            raise ValueError("Invalid native recording mode or duration")
        if (type(scope_digest) is not str or len(scope_digest) != 64 or
            any(ch not in "0123456789abcdef" for ch in scope_digest)):
            raise ValueError("Authorized original source digest required")
        if mode == "port":
            if (type(channel) is not int or channel not in (0,1) or
                type(device_id) is not int or device_id < 0 or
                type(device_descriptor) is not dict or
                device_descriptor.get("device_id") != device_id):
                raise ValueError("Trusted independent native endpoint required")
            self.identity = scope_sha256(device_descriptor)
        else:
            self.identity = ""
        self.prefix = "producer-mono" if mode == "mono" else "producer-" + str(channel)
        self.mode, self.max_samples, self.scope_digest = mode, max_samples, scope_digest
        self.device_id = device_id
        self._process = None
        self._log = None
        self._callback = None
        self._started = False
        self._stopped = False
        self._calibrations = ()
        self._custody_receipt = None

    def _path(self, suffix):
        return self.spool / (self.prefix + suffix)

    def _note(self, suffix):
        path = self._path(suffix)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024:
            raise RuntimeError("Untrusted original device-producer evidence")
        return json.loads(path.read_text("utf8"))

    def start(self, callback=None):
        if self._started:
            raise RuntimeError("Original device producer is one use")
        self._started = True
        if callback is not None:
            self._callback = callback
        # A frozen PyInstaller desktop cannot execute a .py source file by
        # passing its path to NVP.exe. Launch the SAME verified installed PE
        # with an internal worker role; the native host still owns its Job.
        if getattr(sys, "frozen", False):
            executable = Path(sys.executable)
            if executable.is_symlink() or not executable.is_file():
                raise RuntimeError("Installed original producer executable absent")
            command = [str(executable), "--device-producer-worker"]
        else:
            executable = Path(__file__).resolve().parent.parent / "tools" / "nvp_native_device_producer_worker.py"
            if executable.is_symlink() or not executable.is_file():
                raise RuntimeError("Reviewed original device worker not provisioned")
            command = [sys.executable, str(executable)]
        command += ["--directory", str(self.spool),
            "--prefix", self.prefix, "--mode", self.mode,
            "--max-samples", str(self.max_samples), "--scope", self.scope_digest,
        ]
        if self.mode == "port":
            command += ["--device-id", str(self.device_id),
                        "--device-identity", self.identity]
        try:
            self._log = self._path(".log").open("xb")
            # Linux is explicitly strict: old process-group/PDEATHSIG-only
            # containment is not an acceptable substitute for cgroup v2.
            self._process = launch_contained(
                command, cwd=self.spool, stdout=self._log, stderr=self._log,
                memory_mb=512, linux_cgroup_tree_required=True,
                linux_write_spool=self.spool)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self._path(".ready").exists():
                    ready = self._note(".ready")
                    if (ready.get("scope_sha256") != self.scope_digest or
                        ready.get("mode") != self.mode or
                        type(ready.get("pid")) is not int or
                        ready["pid"] != self._process.pid or
                        self._process.poll() is not None):
                        raise RuntimeError("Original device producer failed launch attestation")
                    return
                if self._process.poll() is not None:
                    raise RuntimeError("Original device producer exited before opening ADC")
                time.sleep(0.02)
            raise TimeoutError("Original device producer did not open ADC within startup deadline")
        except BaseException:
            self.close()
            raise

    def _shutdown(self):
        process = self._process
        if process is None:
            return
        # Even a normally exited direct child can have detached descendants.
        # Terminate/verify the *original* supervisor, never a PID scan.
        process.terminate_tree()
        if os.name == "nt":
            import win32job
            job = process._job
            if job is None:
                raise RuntimeError("Original Windows Job Object was lost")
            deadline = time.monotonic() + 5
            while True:
                info = win32job.QueryInformationJobObject(
                    job, win32job.JobObjectBasicAccountingInformation)
                if info["ActiveProcesses"] == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Device producer Windows Job retains active descendants")
                time.sleep(0.02)
            scope = "windows-job-object"
        elif sys.platform == "linux":
            if not hasattr(process, "cgroup"):
                raise RuntimeError("Linux device worker lacks delegated cgroup custody")
            scope = "linux-cgroup-v2"
        else:
            raise RuntimeError("Unsupported device producer process custody")
        if process.returncode is None:
            raise RuntimeError("Device producer direct-child exit was not reaped")
        process.close()
        if scope == "linux-cgroup-v2" and Path(process.cgroup).exists():
            raise RuntimeError("Device producer cgroup was not removed after guardian shutdown")
        self._custody_receipt = {
            "scope":scope, "process_tree_custody_verified":True,
            "empty_group_verified":True, "worker_exit_verified":True,
            "worker_returncode":process.returncode,
        }
        self._process = None
        if self._log is not None:
            self._log.close()
            self._log = None

    def _checked_data(self):
        data = self._note(".complete")
        if (type(data) is not dict or
            set(data) != {"format","scope_sha256","mode","sample_rate","samples",
                          "pcm_sha256","frames_sha256","calibrations"} or
            data["format"] != "nvp.device_producer.v1" or
            data["scope_sha256"] != self.scope_digest or
            data["mode"] != self.mode or data["sample_rate"] != RATE or
            type(data["samples"]) is not int or
            not 0 < data["samples"] <= self.max_samples or
            type(data["calibrations"]) is not list or len(data["calibrations"]) > 4096):
            raise RuntimeError("Invalid device producer original PCM receipt")
        if self.mode == "mono" and data["calibrations"]:
            raise RuntimeError("Unexpected device clock in mono original PCM receipt")
        if self.mode == "port":
            for sample in data["calibrations"]:
                if (type(sample) is not list or len(sample) != 3 or
                    any(type(x) is not int or x < 0 for x in sample) or
                    sample[2] < sample[0] or sample[2]-sample[0] > 2_000_000):
                    raise RuntimeError("Bad worker-bracketed physical device clock")
        for suffix, length_limit, expected in (
            (".pcm",data["samples"]*2,data["pcm_sha256"]),
            (".frames",16 * 1024 * 1024,data["frames_sha256"])):
            path = self._path(suffix)
            if (path.is_symlink() or not path.is_file() or
                path.stat().st_size > length_limit or
                (suffix == ".pcm" and path.stat().st_size != length_limit) or
                type(expected) is not str or len(expected) != 64):
                raise RuntimeError("Device producer original output is invalid")
            digest = sha256()
            with path.open("rb") as fp:
                while block := fp.read(CHUNK):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise RuntimeError("Original PCM or timing packet digest changed")
        return data

    def _replay(self, data):
        total = 0
        pcm_digest = sha256()
        frame_digest = sha256()
        with self._path(".pcm").open("rb") as pcm, self._path(".frames").open("rb") as frames:
            while packet := frames.read(FRAME.size):
                frame_digest.update(packet)
                if len(packet) != FRAME.size:
                    raise RuntimeError("Partial independent ADC frame record")
                count, adc, good = FRAME.unpack(packet)
                if not 0 < count <= RATE or good != 1:
                    raise RuntimeError("Invalid verified device packet")
                raw = pcm.read(count * 2)
                if len(raw) != count * 2:
                    raise RuntimeError("Truncated original producer signal")
                pcm_digest.update(raw)
                total += count
                if total > data["samples"]:
                    raise RuntimeError("Device packet count exceeds approved original source")
                if self.mode == "mono":
                    samples = array.array("h")
                    samples.frombytes(raw)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    self._callback.send(samples)
                else:
                    self._callback(raw, count, adc, True)
            if (pcm.read(1) or total != data["samples"] or
                pcm_digest.hexdigest() != data["pcm_sha256"] or
                frame_digest.hexdigest() != data["frames_sha256"]):
                # Already-enqueued samples are not approved. The parent
                # refuses freeze and preserves the unapproved journal.
                raise RuntimeError("Device packet ledger and original PCM differ")
        self._calibrations = tuple(tuple(s) for s in data["calibrations"])

    def request_stop(self):
        if not self._started or self._process is None:
            return
        marker = self._path(".stop")
        if not marker.exists():
            with marker.open("xb"):
                pass

    def stop(self):
        if not self._started or self._stopped:
            return
        self._stopped = True
        if self._process is None:
            raise RuntimeError("No verified original device producer exists")
        # Cooperative stop first lets producer flush and fsync every PCM byte.
        self.request_stop()
        deadline = time.monotonic() + 10
        while self._process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        completed = self._process.poll() == 0
        self._shutdown()
        if (not completed or self._custody_receipt is None or
            self._custody_receipt["worker_returncode"] != 0):
            raise RuntimeError("Device producer did not exit cleanly under kernel custody")
        data = self._checked_data()
        if self._callback is not None:
            self._replay(data)

    def calibration_anchors(self):
        if self.mode != "port" or not self._custody_receipt:
            raise RuntimeError("Independent device has no verified worker-clock evidence")
        return self._calibrations

    @property
    def custody_receipt(self):
        return dict(self._custody_receipt) if self._custody_receipt else None

    def close(self):
        if self._process is not None:
            self._shutdown()
        if self._log is not None:
            self._log.close()
            self._log = None
