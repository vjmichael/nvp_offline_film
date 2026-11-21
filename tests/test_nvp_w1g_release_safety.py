"""W1-G strict offline wheel, upgrade and actual executable worker contracts."""
from hashlib import sha256
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest import TestCase
import zipfile

from tools.nvp_w1g_native_dependencies import FORMAT as LOCK, validate_lock
from tools.nvp_w1g_native_upgrade import SideBySideNativeUpgrade
from tools.nvp_w1g_worker_package import (
    FORMAT as WORKERS, provision_native_workers, verify_native_workers,
)


class W1GReleaseSafetyContracts(TestCase):
    def test_offline_wheel_lock_rejects_tampering_missing_license_and_egress(self):
        with TemporaryDirectory() as temp:
            directory=Path(temp)
            filename="sample_pkg-1.0-py3-none-any.whl"
            wheel=directory/filename
            with zipfile.ZipFile(wheel,"w") as z:
                z.writestr("sample_pkg-1.0.dist-info/METADATA",
                           "Metadata-Version: 2.1\nName: sample-pkg\nVersion: 1.0\n")
            lock={"format":LOCK,"platform":"windows-amd64",
                  "wheels":[{"name":"sample-pkg","version":"1.0",
                    "filename":filename,
                    "sha256":sha256(wheel.read_bytes()).hexdigest(),
                    "license_review":"creator-reviewed license receipt"}]}
            self.assertEqual(len(validate_lock(
                lock,directory,platform="windows-amd64")),1)
            (directory/filename).write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeError,"SHA"):
                validate_lock(lock,directory,platform="windows-amd64")
            with zipfile.ZipFile(wheel,"w") as z:
                z.writestr("sample_pkg-1.0.dist-info/METADATA",
                           "Metadata-Version: 2.1\nName: sample-pkg\nVersion: 1.0\n")
            lock["wheels"][0]["sha256"]=sha256(wheel.read_bytes()).hexdigest()
            lock["wheels"][0]["license_review"]=""
            with self.assertRaisesRegex(RuntimeError,"license-review"):
                validate_lock(lock,directory,platform="windows-amd64")
            lock["wheels"][0]["license_review"]="creator-reviewed license receipt"
            with self.assertRaisesRegex(RuntimeError,"platform-specific"):
                validate_lock(lock,directory,platform="linux-amd64")

    def test_upgrade_never_changes_films_and_can_rollback_original_runtime(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            install=root/"NVP"
            stage=root/"upgrades"
            incoming=root/"new-build"
            films=root/"OriginalFilms"
            for path in (install,stage,incoming,films):path.mkdir()
            (install/"NVP").write_bytes(b"old native program")
            (incoming/"NVP").write_bytes(b"new native program")
            (films/"OriginalFilm.take").write_bytes(b"untouched original")
            owner=SideBySideNativeUpgrade(
                install,stage,films,native_authorize=lambda scope:True,
                os_workers_stopped=lambda:True)
            prepared=owner.prepare(incoming)
            self.assertEqual(prepared["state"],"PREPARED")
            result=owner.activate()
            self.assertEqual(result["status"],"NATIVE_UPGRADE_ACTIVE_UNACCEPTED")
            self.assertEqual((install/"NVP").read_bytes(),b"new native program")
            self.assertEqual(owner.reconcile()["state"],"ACTIVE")
            rolled=owner.rollback()
            self.assertTrue(rolled["original_films_preserved"])
            self.assertEqual((install/"NVP").read_bytes(),b"old native program")
            self.assertEqual((films/"OriginalFilm.take").read_bytes(),b"untouched original")

    def test_upgrade_denied_without_real_os_stop_and_rejects_nsis_inplace(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            install=root/"NVP";stage=root/"upgrades"
            incoming=root/"new-build";films=root/"OriginalFilms"
            for path in (install,stage,incoming,films):path.mkdir()
            (install/"NVP").write_bytes(b"old")
            (incoming/"NVP").write_bytes(b"new")
            (films/"film").write_bytes(b"original")
            upgrade=SideBySideNativeUpgrade(
                install,stage,films,native_authorize=lambda s:True,
                os_workers_stopped=lambda:False)
            upgrade.prepare(incoming)
            with self.assertRaises(PermissionError):
                upgrade.activate()
            self.assertEqual((install/"NVP").read_bytes(),b"old")
            (install/"nvp-alpha-install.marker").write_bytes(b"nsis")
            with self.assertRaisesRegex(RuntimeError,"NSIS-owned"):
                SideBySideNativeUpgrade(
                    install,stage,films,native_authorize=lambda s:True,
                    os_workers_stopped=lambda:True)

    def test_staged_binary_provenance_and_change_detection(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            trusted=root/"reviewed";trusted.mkdir()
            bundle=root/"bundle";bundle.mkdir()
            native=trusted/"render.exe"
            exe=bytearray(150000)
            exe[:2]=b"MZ"
            struct.pack_into("<I",exe,0x3c,0x80)
            exe[0x80:0x84]=b"PE\x00\x00"
            struct.pack_into("<H",exe,0x84,0x8664)
            struct.pack_into("<H",exe,0x80+24,0x20B)
            struct.pack_into("<H",exe,0x80+24+68,3)
            native.write_bytes(exe)
            roster={"format":WORKERS,"platform":"windows-amd64",
                "workers":[{"role":"scene_render","filename":"render.exe",
                            "sha256":sha256(native.read_bytes()).hexdigest()}]}
            provision_native_workers(trusted,bundle,roster)
            self.assertEqual(verify_native_workers(
                bundle,expected_platform="windows-amd64")["roles"],
                ["scene_render"])
            installed=bundle/"_internal"/"nvp_workers"/"render.exe"
            installed.write_bytes(installed.read_bytes()+b"\x00")
            with self.assertRaisesRegex(RuntimeError,"SHA changed"):
                verify_native_workers(bundle,expected_platform="windows-amd64")
