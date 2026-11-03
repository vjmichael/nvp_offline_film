"""PROD-06E2B: external licensed humanoid ankle-lock native acceptance.

Combines approved 06D real retarget, 06E2A independently observed anatomy,
then 06E2B artist-authored contact/IK bake on *another copy* of the real stage.
The fixture tests ankle marker locks, NOT a physically simulated sole or gait.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nvp_foot_contact import FootLockPlan
from backend.nvp_foot_blender import run_footlock_acceptance
from backend.nvp_studio import Studio
from tools.nvp_prod06e2_fixture import run_external_legchain


def fixture_actor_settings():
    # Explicit left/right pole offsets, distinct locked windows and deliberate
    # 2-cm inward ankle target: motion MUST be measurable in the native rig.
    return {
        'left': {'contact_windows':[[1,12]],'pole_offset_actor_m':[0,.4,0],
                 'anchor_pull_to_hip_m':.02},
        'right':{'contact_windows':[[13,25]],'pole_offset_actor_m':[0,.4,0],
                 'anchor_pull_to_hip_m':.02},
        'max_ankle_correction_m':.08,
        'max_ankle_slide_m':.012
    }


def run_fixture(out,source,*,blender='blender',audit_only=False):
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    predecessor=run_external_legchain(out/'prod06e2a',Path(source),
                                      blender=blender,render_preview=not audit_only)
    if predecessor['status']!='passed_native_leg_identity_only':
        return {'status':'failed','step':'prod06e2a','details':predecessor}
    base=out/'prod06e2a'/'prod06d_baseline'
    studio=Studio(base/'project'/'studio.sqlite')
    projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError('Unexpected project count')
    pid=projects[0]['id']
    scenes=studio.get_project(pid)['scenes']
    if len(scenes)!=1:raise RuntimeError('Unexpected scene count')
    sid=scenes[0]['id']
    contact=FootLockPlan(studio)
    p=contact.create(pid,sid)
    if len(p['actors'])!=1:raise RuntimeError('Expected exactly one mapped real human')
    actor=p['actors'][0]['instance_id']
    p=contact.configure(pid,sid,actor,fixture_actor_settings(),p['revision'])
    p=contact.approve(pid,sid,p['revision'])
    result=run_footlock_acceptance(contact,pid,sid,out/'native_footlock',
                                   executable=blender,render_preview=False,
                                   baseline_blend=base/'native'/'retarget.blend')
    result['source_anatomy_approval_sha']=predecessor['approved_identity_sha']
    result['source_asset_sha256']=predecessor['asset_sha256']
    result['stage']='nvp.prod06e2b.ankle_lock.v1'
    (out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--external-glb',required=True)
    parser.add_argument('--blender',default='blender')
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args(argv)
    result=run_fixture(args.out,args.external_glb,blender=args.blender,audit_only=args.audit_only)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result.get('status')=='passed_native_ankle_lock_only' else 1


if __name__=='__main__':raise SystemExit(main())
