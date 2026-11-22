"""Installed administrator-owned systemd control hook, no arbitrary commands."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.nvp_linux_service_recovery import systemd_hook
if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Expected start/stop and fixed unit name')
    systemd_hook(sys.argv[1], sys.argv[2])
