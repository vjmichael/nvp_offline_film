"""Host-only admission gate for the optional systemd-managed Linux desktop.

No browser or environment variable alone grants service authority. A matching
root-issued start record and actual delegated cgroup membership are required.
A normal desktop launch never assumes or fabricates that authority.
"""
from __future__ import annotations
import os
import sys


def desktop_service_unit(username, uid):
    from backend.nvp_linux_service_recovery import _unit
    if type(uid) is not int or uid <= 0:
        raise PermissionError('NVP managed desktop must run as a non-root user')
    return _unit('nvp-desktop@'+username+'.service')


def managed_desktop_authority():
    if sys.platform != 'linux':
        raise PermissionError('Managed Linux desktop only supported on Linux')
    import pwd
    from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority
    from backend.nvp_worker_linux_cgroup import current_delegated_parent
    uid=os.geteuid()
    unit=desktop_service_unit(pwd.getpwuid(uid).pw_name, uid)
    authority=SystemdRecoveryAuthority(unit)
    start=authority.current()
    if str(current_delegated_parent()) != start['scope']:
        raise PermissionError('Managed desktop lacks its original delegation')
    return authority
