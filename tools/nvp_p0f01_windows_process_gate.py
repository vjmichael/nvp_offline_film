"""Bounded first-party installed Windows process and postmortem stage receipts.

Each stage waits for its own OS process, not the entire PowerShell
Start-Process -Wait descendant tree. On timeout reap the runner-owned test
process tree. Never change source film, real user data or worker authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

FORMAT = "nvp.p0f01.native_windows_installed_process_stage.v1"


def _record(path: Path, *, stage: str, status: str, **details: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("Refusing symlink stage-receipt path")
    record = {
        "format": FORMAT,
        "utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        **details,
    }
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        sink.flush()
        os.fsync(sink.fileno())
    print(f"NVP_P0F01_STAGE_{status.upper()}={stage}", flush=True)


def _read_diagnostics(path_text: str | None) -> None:
    if not path_text:
        return
    path = Path(path_text)
    if path.is_symlink() or not path.is_file():
        print(f"NVP_P0F01_APP_DIAGNOSTICS_MISSING={path.name}", flush=True)
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"NVP_P0F01_APP_DIAGNOSTICS_LINES={len(lines)}", flush=True)
    for line in lines[-110:]:
        print(line[:250], flush=True)


def _terminate_owned_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass


def run(
    *, stage: str, timeout_seconds: float, stage_log: Path,
    command: list[str], diagnostics: str | None = None,
) -> int:
    if not stage or not all(c.isascii() and (c.isalnum() or c in "-_") for c in stage):
        raise ValueError("Stage must be a bounded ASCII slug")
    if not 0.1 <= timeout_seconds <= 900:
        raise ValueError("Process gate timeout outside reviewed bounds")
    if not command or not command[0]:
        raise ValueError("Missing executable")
    start = time.monotonic()
    _record(stage_log, stage=stage, status="starting", executable=Path(command[0]).name,
            timeout_seconds=timeout_seconds)
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        _record(stage_log, stage=stage, status="launch_failed", error=type(exc).__name__,
                detail=str(exc)[:300])
        _read_diagnostics(diagnostics)
        return 1
    _record(stage_log, stage=stage, status="launched", pid=process.pid)
    try:
        code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _record(stage_log, stage=stage, status="timeout", pid=process.pid,
                elapsed_seconds=round(time.monotonic() - start, 3))
        _read_diagnostics(diagnostics)
        _terminate_owned_process_tree(process)
        return 2
    elapsed = round(time.monotonic() - start, 3)
    if code != 0:
        _record(stage_log, stage=stage, status="exit_failed", pid=process.pid,
                exit_code=code, elapsed_seconds=elapsed)
        _read_diagnostics(diagnostics)
        return 3
    _record(stage_log, stage=stage, status="passed", pid=process.pid,
            exit_code=code, elapsed_seconds=elapsed)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--stage-log", required=True, type=Path)
    parser.add_argument("--diagnostics")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    return run(stage=args.stage, timeout_seconds=args.timeout_seconds,
               stage_log=args.stage_log, command=command, diagnostics=args.diagnostics)


if __name__ == "__main__":
    sys.exit(main())
