"""Pinned Cesium Man: audit candidate sole regions after *real* Blender IK.

An external CC-BY glTF sample is required. No asset bytes are redistributed.
This milestone deliberately does not call a set of weighted vertices a sole.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from backend.nvp_foot_contact import FootLockPlan
from backend.nvp_foot_sole import run_native_sole_region
from backend.nvp_studio import Studio
from tools.nvp_prod06e2b_fixture import run_fixture


def run_fixture_sole(out,source,*,blender='blender',audit_only=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    predecessor=run_fixture(out/'prod06e2b',source,blender=blender,audit_only=audit_only)
    if predecessor['status']!='passed_native_ankle_lock_only':
        return {'status':'failed','step':'upstream_native_ik','result':predecessor}
    db=out/'prod06e2b'/'prod06e2a'/'prod06d_baseline'/'project'/'studio.sqlite'
    blend=out/'prod06e2b'/'native_footlock'/'ankle_locked.blend'
    if not db.is_file() or not blend.is_file():
        return {'status':'failed','step':'source_missing','db':str(db),'blend':str(blend)}
    studio=Studio(db);projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError('Unexpected pinned project count')
    pid=projects[0]['id'];scenes=studio.get_project(pid)['scenes']
    if len(scenes)!=1:raise RuntimeError('Unexpected pinned scene count')
    service=FootLockPlan(studio)
    result=run_native_sole_region(service,pid,scenes[0]['id'],blend,
                                  out/'native_sole_regions',blender=blender)
    if result['status']=='passed_candidate_region_survey_only':
        report=result['report']
        actor=next(iter(report['actors']))
        result={'status':result['status'],'stage':'nvp.prod06e2c.sole_candidate.v1',
                'blender':predecessor['blender_version'],
                'actor_regions':report['actors'][actor],
                'report_sha':report['report_sha'],
                'physical_sole_contact_verified':False,
                'source_ankle_ik_passed':True}
    (out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--external-glb',required=True)
    p.add_argument('--blender',default='blender')
    p.add_argument('--audit-only',action='store_true')
    args=p.parse_args(argv)
    r=run_fixture_sole(args.out,args.external_glb,blender=args.blender,audit_only=args.audit_only)
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r.get('status')=='passed_candidate_region_survey_only' else 1
if __name__=='__main__':raise SystemExit(main())
