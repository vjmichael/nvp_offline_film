"""PROD-06E2A: pinned Cesium Man anatomical identity native acceptance.

This regression *does not apply IK*. It first completes existing 06D native
rest-frame retargeting, then separately imports the registered GLB into Blender
and verifies the creator-declared eight-joint two-leg hierarchy and rest
geometry. The original third-party GLB is never redistributed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from backend.nvp_leg_chains import LegChainIdentity
from backend.nvp_studio import Studio
from tools.nvp_prod06d_fixture import build_external_fixture

# Exact names in the upstream Khronos Cesium Man glTF skin, verified against the
# pinned source hierarchy. No fuzzy naming/auto-acceptance in the NVP product.
CESIUM_LEG_CHAINS={
    'left': {'hip':'leg_joint_L_1','knee':'leg_joint_L_2',
             'ankle':'leg_joint_L_3','toe':'leg_joint_L_5'},
    'right':{'hip':'leg_joint_R_1','knee':'leg_joint_R_2',
             'ankle':'leg_joint_R_3','toe':'leg_joint_R_5'},
}


def run_external_legchain(out,external_glb,*,blender='blender',render_preview=True):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    prior=build_external_fixture(out/'prod06d_baseline',external_glb,
                                 render_preview=render_preview,blender=blender)
    expected='passed_blender' if render_preview else 'passed_blender_audit_only'
    if prior['status']!=expected:
        return {'status':'failed','step':'prod06d_baseline','upstream_result':prior}
    studio=Studio(out/'prod06d_baseline'/'project'/'studio.sqlite')
    projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError('Unexpected project fixture count')
    pid=projects[0]['id'];scenes=studio.get_project(pid)['scenes']
    if len(scenes)!=1:raise RuntimeError('Unexpected scene fixture count')
    sid=scenes[0]['id']
    service=LegChainIdentity(studio)
    draft=service.create(pid,sid)
    if len(draft['actors'])!=1:raise RuntimeError('Expected one actual external human')
    actor=draft['actors'][0]['instance_id']
    draft=service.configure(pid,sid,actor,CESIUM_LEG_CHAINS,draft['revision'])
    inspected=service.inspect_native(pid,sid,out/'anatomy_native',executable=blender)
    if inspected['status']!='native_anatomy_inspected':
        return {'status':'failed','step':'native_legchain_inspect','inspection':inspected}
    approved=service.approve(pid,sid,inspected['revision'])
    exported=service.export(pid,sid)['leg_identity']
    anatomy=exported['native_anatomy_evidence'][actor]
    if anatomy['ik_authorized'] or exported['ik_authorized']:
        raise RuntimeError('Leg identity must not grant IK execution authority')
    report={'status':'passed_native_leg_identity_only','baseline':prior['status'],
            'blender':anatomy['blender_version'],'asset_sha256':anatomy['asset_sha256'],
            'approved_identity_sha':approved['approval_sha'],
            'retarget_dependency_sha':exported['retarget_dependency_sha'],
            'rest_lengths_m':anatomy['rest_lengths_m'],'warnings':anatomy['warnings'],
            'mapped_joints':anatomy['chains'],
            'native_snapshot_sha':anatomy['native_snapshot_sha'],'ik_applied':False}
    (out/'legchain_result.json').write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
    return report


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--external-glb',required=True)
    p.add_argument('--audit-only',action='store_true')
    p.add_argument('--blender',default='blender')
    args=p.parse_args(argv)
    result=run_external_legchain(args.out,args.external_glb,
                                  blender=args.blender,render_preview=not args.audit_only)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True),'utf8')
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['status']=='passed_native_leg_identity_only' else 1


if __name__=='__main__':raise SystemExit(main())
