"""SYSTEM-READY-01 real host inventory and guarded package-repair contracts.

Tests do not install packages. They exercise read-only detection, allowlist,
approval refusal and the exact fixed OS-manager argv using subprocess mocks.
"""
from unittest import TestCase,mock
import tempfile
from pathlib import Path
from backend import nvp_system_packages as p

class PackagesTests(TestCase):
    def test_missing_linux_packages_get_no_implicit_install(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(p.sys,"platform","linux"), \
             mock.patch.object(p,"_installed_binaries",return_value=(False,False)), \
             mock.patch.object(p,"_linux_gui",return_value=False), \
             mock.patch.object(p,"_manager",return_value=("apt+polkit","/usr/bin/pkexec")), \
             mock.patch.object(p.subprocess,"run") as launch:
            result=p.inventory(studio_path=Path(tmp))
            self.assertEqual(result["format"],p.FORMAT)
            self.assertEqual(result["status"],"ACTION_NEEDED")
            self.assertFalse(result["auto_install"])
            self.assertEqual(result["components"][0]["status"],"missing")
            self.assertEqual(result["components"][0]["repair"],"ffmpeg")
            self.assertEqual(result["components"][1]["repair"],"linux_webkit")
            launch.assert_not_called()

    def test_refuse_arbitrary_package_names_without_os_confirmation(self):
        with mock.patch.object(p.subprocess,"run") as launch:
            for bad in ("curl","python","../ffmpeg","apt-get","",None):
                with self.subTest(bad=bad):
                    with self.assertRaises(ValueError):
                        p.repair(bad,confirm=lambda _msg:True)
            launch.assert_not_called()

    def test_explicit_native_decline_prevents_any_package_launch(self):
        snapshot={"components":[{"repair":"ffmpeg",
                                  "name":"FFmpeg and FFprobe",
                                  "status":"missing"}]}
        with mock.patch.object(p,"inventory",return_value=snapshot), \
             mock.patch.object(p.subprocess,"run") as launch:
            refused=p.repair("ffmpeg",confirm=lambda _:False)
            self.assertEqual(refused["status"],"DECLINED")
            launch.assert_not_called()

    def test_fixed_debian_linux_repair_no_shell_no_arbitrary_package(self):
        snapshot={"components":[
            {"repair":"ffmpeg","name":"FFmpeg and FFprobe","status":"missing"},
        ]}
        updated={"components":[
            {"id":"video_tools","status":"ready","repair":None},
        ]}
        fake=mock.Mock(returncode=0)
        with mock.patch.object(p,"inventory",side_effect=[snapshot,updated]), \
             mock.patch.object(p,"_manager",return_value=("apt+polkit","/usr/bin/pkexec")), \
             mock.patch.object(p.subprocess,"run",return_value=fake) as run, \
             mock.patch.object(Path,"is_symlink",return_value=False):
            outcome=p.repair("ffmpeg",confirm=lambda text:True)
            self.assertEqual(outcome["status"],"INSTALLED")
            args,kwargs=run.call_args
            self.assertEqual(args[0],[
                "/usr/bin/pkexec","/usr/bin/apt-get",
                "install","-y","ffmpeg",
            ])
            self.assertFalse(kwargs["shell"])
            self.assertLessEqual(kwargs["timeout"],600)
            self.assertFalse(outcome["source_media_modified"])
