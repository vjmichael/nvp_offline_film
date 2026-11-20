"""Fixed administrator-owned desktop hook; no creator-worker launch rights."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nvp_linux_service_recovery import systemd_hook
from backend.nvp_linux_desktop_service import desktop_service_unit


def main(args):
    if sys.platform!='linux' or os.geteuid()!=0 or len(args)!=2 or args[0] not in ('start','stop'):
        raise PermissionError('Installed desktop control hook only')
    import pwd
    kind,unit=args
    if not unit.startswith('nvp-desktop@') or not unit.endswith('.service'):
        raise PermissionError('Unexpected desktop unit')
    user=unit.removeprefix('nvp-desktop@').removesuffix('.service')
    account=pwd.getpwnam(user)
    if desktop_service_unit(account.pw_name,account.pw_uid)!=unit:
        raise PermissionError('Unexpected desktop instance')
    systemd_hook(kind,unit)


if __name__=='__main__':main(sys.argv[1:])
