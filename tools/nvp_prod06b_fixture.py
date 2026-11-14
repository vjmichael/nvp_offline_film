"""Repeatable real-Blender acceptance fixture for approved weighted skinning.

Run after Blender 5.2+ has been installed on the host CI runner.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from backend.nvp_skinning import SkinnedPerformance, run_skin_acceptance
from tests.test_skinning import make_fixture


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True)
    ap.add_argument('--audit-only',action='store_true')
    args=ap.parse_args(argv)
    output=Path(args.out).resolve()
    output.mkdir(parents=True,exist_ok=True)
    studio,pid,sid,actor=make_fixture(output)
    skin=SkinnedPerformance(studio)
    session=skin.create(pid,sid)
    session=skin.calibrate(pid,sid,actor,'arm_left',[10,0,0],[0,0,0],session['revision'])
    skin.approve(pid,sid,session['revision'])
    result=run_skin_acceptance(skin,pid,sid,output/'native',render_preview=not args.audit_only)
    (output/'result.json').write_text(json.dumps(result,indent=2),'utf8')
    expected='passed_blender_audit_only' if args.audit_only else 'passed_blender'
    if result['status']!=expected:
        print(json.dumps(result,indent=2))
        raise SystemExit(1)
    print(json.dumps({'status':result['status'],'checks':result['checks'],'blend':result['blend'],
                      'audit':result['audit'],'preview':result['preview']},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
