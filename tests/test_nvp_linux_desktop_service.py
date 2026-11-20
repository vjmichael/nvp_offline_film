"""Production optional service contract, not graphical installation acceptance."""
from pathlib import Path
import sys, unittest
from unittest.mock import patch
from backend.nvp_linux_desktop_service import desktop_service_unit, managed_desktop_authority
from tools import nvp_linux_desktop_recovery_hook as hook
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform=='linux','Linux managed desktop')
class DesktopService(unittest.TestCase):
    def test_nonroot_fixed_instance(self):
        self.assertEqual(desktop_service_unit('creator',1000),'nvp-desktop@creator.service')
        with self.assertRaises(PermissionError):desktop_service_unit('root',0)
        with self.assertRaises(ValueError):desktop_service_unit('../creator',1000)
    def test_environment_alone_never_authorizes(self):
        import pwd
        with patch('os.geteuid',return_value=1000),patch('pwd.getpwuid',return_value=type('P',(),{'pw_name':'creator'})()),patch.dict('os.environ',{'INVOCATION_ID':'a'*32}):
            with self.assertRaises((PermissionError, OSError, ValueError)):managed_desktop_authority()
    def test_root_hook_refuses_non_desktop_and_root(self):
        with patch.object(hook.os,'geteuid',return_value=0),patch.object(hook,'systemd_hook') as call:
            for unit in ('nvp-sec06-qualification@root.service','nvp-desktop@root.service'):
                with self.assertRaises(PermissionError):hook.main(['start',unit])
            call.assert_not_called()
    def test_packaging_contract(self):
        unit=(ROOT/'packaging/linux/nvp-desktop@.service').read_text()
        for text in ('User=%i','ExecStart=/opt/nvp/NVP --linux-managed-desktop','Delegate=yes','DelegateSubgroup=nvp.host','KillMode=control-group','Restart=no','NoNewPrivileges=yes'):
            self.assertIn(text,unit)
        self.assertNotIn('[Install]',unit)
        pkg=(ROOT/'packaging/build-nvp-deb.sh').read_text()
        self.assertIn('nvp_linux_desktop_recovery_hook.py',pkg)
        self.assertIn('nvp-desktop@.service',pkg)
        self.assertNotIn('systemctl enable',pkg)
