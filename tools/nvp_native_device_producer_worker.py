"""P1-A: original microphone producer, executed only as a contained OS child.

No FilmIndex writes, creator approval, fallback recorder, network, shell, or
device acquisition in the desktop process. A parent-held Job/cgroup owns this
process; a complete file is *not* a process-custody receipt.
"""
from __future__ import annotations

import argparse
import array
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import struct
import sys
import threading
import time

RATE = 48000
MAX_SECONDS = 600
MAX_CHUNK = 1024 * 1024
MAX_QUEUE = 24
FRAME = struct.Struct("<IqB")


def atomic_note(path, data):
    raw = json.dumps(data, sort_keys=True, separators=(",",":"), allow_nan=False).encode("utf8")
    if len(raw) > 512 * 1024:
        raise RuntimeError("Device-producer receipt exceeds bound")
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def verified_directory(raw):
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise PermissionError("Host-owned recording directory required")
    if not path.name.startswith("nvp-live-original-"):
        raise PermissionError("Not a native original source spool")
    return path


class Recorder:
    def __init__(self, directory, prefix, mode, max_samples, device_id, device_identity):
        self.directory = directory
        self.prefix = prefix
        self.mode = mode
        self.max_samples = max_samples
        self.device_id = device_id
        self.device_identity = device_identity
        self.pcm = directory / (prefix + ".pcm")
        self.frames = directory / (prefix + ".frames")
        self.samples = 0
        self.raw_sha = sha256()
        self.frames_sha = sha256()
        self.queue = queue.Queue(maxsize=MAX_QUEUE)
        self.error = None
        self.calibrations = []
        self.writer = threading.Thread(target=self.write, name="NVP original producer disk", daemon=True)
        self.device = None

    def enqueue(self, raw, frames, adc=0, good=True):
        if self.error is not None:
            return
        if (type(raw) is not bytes or type(frames) is not int or
            not 0 < frames <= RATE or len(raw) != frames * 2 or
            len(raw) > MAX_CHUNK or not good or
            type(adc) is not int or adc < 0):
            self.error = RuntimeError("Invalid original device callback, timing or overflow")
            return
        try:
            self.queue.put_nowait((raw, frames, adc))
        except queue.Full:
            self.error = RuntimeError("Original PCM callback queue overran disk")

    def mono_callback(self):
        samples = yield
        while True:
            if not isinstance(samples, array.array) or samples.typecode != "h":
                self.error = RuntimeError("Miniaudio callback is not signed PCM16")
            else:
                raw = samples.tobytes()
                if sys.byteorder != "little":
                    samples.byteswap()
                    raw = samples.tobytes()
                if raw:
                    self.enqueue(raw, len(samples))
            samples = yield

    def port_callback(self, data, frames, timing, status):
        value = timing.inputBufferAdcTime
        if (type(value) not in (int,float) or not 0 < value < float("inf")):
            self.error = RuntimeError("PortAudio ADC timing unavailable")
            return
        self.enqueue(bytes(data), int(frames), round(value * 1_000_000_000), not bool(status))

    def write(self):
        try:
            with self.pcm.open("xb") as out, self.frames.open("xb") as frame_out:
                while True:
                    entry = self.queue.get()
                    if entry is None:
                        break
                    raw, count, adc = entry
                    self.samples += count
                    if self.samples > self.max_samples:
                        raise RuntimeError("Original device source exceeded approved sample bound")
                    frame = FRAME.pack(count, adc, 1)
                    out.write(raw)
                    frame_out.write(frame)
                    self.raw_sha.update(raw)
                    self.frames_sha.update(frame)
                out.flush()
                os.fsync(out.fileno())
                frame_out.flush()
                os.fsync(frame_out.fileno())
        except BaseException as exc:
            self.error = exc

    def open_device(self):
        if self.mode == "mono":
            import miniaudio
            self.device = miniaudio.CaptureDevice(
                input_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1, sample_rate=RATE, buffersize_msec=40,
                app_name="NVP Original Sound Capture")
            callback = self.mono_callback()
            next(callback)
            self.device.start(callback)
        else:
            import sounddevice as sd
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            if (self.device_id < 0 or self.device_id >= len(devices) or
                int(devices[self.device_id]["max_input_channels"]) < 1):
                raise RuntimeError("Original device endpoint disconnected")
            selected = devices[self.device_id]
            descriptor = {
                "device_id": self.device_id,
                "name": str(selected["name"])[:160],
                "host_api": str(hostapis[int(selected["hostapi"])]["name"])[:80],
                "max_input_channels": int(selected["max_input_channels"]),
            }
            actual = sha256(json.dumps(descriptor, sort_keys=True,
                separators=(",",":")).encode("utf8")).hexdigest()
            if actual != self.device_identity:
                raise RuntimeError("Original input endpoint identity changed")
            self.device = sd.RawInputStream(
                samplerate=RATE, channels=1, dtype="int16",
                device=self.device_id, blocksize=0, latency="low",
                callback=self.port_callback)
            self.device.start()

    def run(self, scope):
        self.writer.start()
        try:
            self.open_device()
            atomic_note(self.directory / (self.prefix + ".ready"),
                {"scope_sha256":scope, "mode":self.mode, "pid":os.getpid()})
            started = time.monotonic()
            next_sample = started
            while True:
                if self.error is not None:
                    raise RuntimeError("Original device producer failed") from self.error
                if (self.directory / (self.prefix + ".stop")).exists():
                    break
                now = time.monotonic()
                if now - started > MAX_SECONDS:
                    raise TimeoutError("Original recording exceeded bounded session")
                if self.mode == "port" and now >= next_sample:
                    before = time.perf_counter_ns()
                    stream = round(float(self.device.time) * 1_000_000_000)
                    after = time.perf_counter_ns()
                    if stream < 0 or len(self.calibrations) >= 4096:
                        raise RuntimeError("Invalid independent device calibration")
                    self.calibrations.append([before,stream,after])
                    next_sample = now + 0.20
                time.sleep(0.02)
            self.device.stop()
            self.device.close()
            self.device = None
            self.queue.put(None, timeout=5)
            self.writer.join(timeout=10)
            if self.writer.is_alive() or self.error is not None or self.samples < 1:
                raise RuntimeError("Original PCM producer failed durable shutdown") from self.error
            atomic_note(self.directory / (self.prefix + ".complete"), {
                "format":"nvp.device_producer.v1",
                "scope_sha256":scope, "mode":self.mode,
                "sample_rate":RATE, "samples":self.samples,
                "pcm_sha256":self.raw_sha.hexdigest(),
                "frames_sha256":self.frames_sha.hexdigest(),
                "calibrations":self.calibrations,
            })
            return 0
        finally:
            if self.device is not None:
                try:
                    self.device.stop()
                finally:
                    self.device.close()
            if self.writer.is_alive():
                try:
                    self.queue.put(None, timeout=1)
                except queue.Full:
                    pass
                self.writer.join(timeout=2)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--prefix", choices=("producer-mono","producer-0","producer-1"), required=True)
    parser.add_argument("--mode", choices=("mono","port"), required=True)
    parser.add_argument("--max-samples", type=int, required=True)
    parser.add_argument("--device-id", type=int, default=-1)
    parser.add_argument("--device-identity", default="")
    parser.add_argument("--scope", required=True)
    args = parser.parse_args(argv)
    directory = verified_directory(args.directory)
    if not 0 < args.max_samples <= RATE * MAX_SECONDS:
        raise ValueError("Invalid authorized sample bound")
    if (len(args.scope) != 64 or any(c not in "0123456789abcdef" for c in args.scope)):
        raise ValueError("Invalid approved source scope digest")
    if args.mode == "port" and (not 0 <= args.device_id <= 4096 or
        len(args.device_identity) != 64):
        raise ValueError("PortAudio endpoint identity required")
    return Recorder(directory,args.prefix,args.mode,args.max_samples,
                    args.device_id,args.device_identity).run(args.scope)


if __name__ == "__main__":
    sys.exit(main())
