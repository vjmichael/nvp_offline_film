"""Qualification-only override for real production unit/hook. Not GUI acceptance."""
import os, sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_linux_desktop_service import managed_desktop_authority
from backend.nvp_linux_service_recovery import digest

a=managed_desktop_authority(); current=a.current()
assert os.geteuid()!=0
state=Path.home()/'.nvp-sec06-desktop-probe.json'
if state.exists():
    old=json.loads(state.read_text()); stop=a.stopped(old['invocation'],old['sha'])
    assert stop['prior_subtree_empty'] is True
    body={'invocation':current['invocation'],'sha':digest(current),'old_stop_verified':True}
else:body={'invocation':current['invocation'],'sha':digest(current),'old_stop_verified':False}
with state.with_suffix('.new').open('x') as f:
    json.dump(body,f);f.flush();os.fsync(f.fileno())
os.replace(state.with_suffix('.new'),state)
