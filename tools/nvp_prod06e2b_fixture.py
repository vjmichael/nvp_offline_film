"""PROD-06E2B1 native stage survey on pinned real Cesium Man.

Runs the existing 06E2A actual external character baseline, then opens the
retargeted Blender scene to survey posed limb world geometry. Neither the
fixture nor its report creates an IK animation or authorizes contacts.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from backend.nvp_leg_chains import LegChainIdentity
from backend.nvp_staged_pose import survey_native_staged_pose
from backend.nvp_studio import Studio
from tools.nvp_prod06e2_fixture import run_external_legchain


def run_staged_pose_fixture(out,source,*,blender='blender',audit_only=False):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    upstream=run_external_legchain(out/'baseline_06e2a',source,
            blender=blender,render_preview=not audit_only)
    if upstream.get('status')!='passed_native_leg_identity_only':
        return {'status':'failed','step':'anatomical_identity','result':upstream}
    project=out/'baseline_06e2a'/'prod06d_baseline'/'project'/'studio.sqlite'
    stage=out/'baseline_06e2a'/'prod06d_baseline'/'native'/'retarget.blend'
    if not project.is_file() or not stage.is_file():
        return {'status':'failed','step':'staged_baseline_missing','db':str(project),'blend':str(stage)}
    studio=Studio(project)
    projects=studio.list_projects()
    if len(projects)!=1:raise RuntimeError('Native fixture must contain one project')
    pid=projects[0]['id']
    scenes=studio.get_project(pid)['scenes']
    if len(scenes)!=1:raise RuntimeError('Native fixture must contain one scene')
    sid=scenes[0]['id']
    service=LegChainIdentity(studio)
    result=survey_native_staged_pose(service,pid,sid,stage,out/'native_staged_pose',
                                     blender=blender)
    if result['status']!='passed_staged_pose_observation_only':
        return {'status':'failed','step':'native_pose_survey','result':result}
    measurements=result['result']
    actor=next(iter(measurements['actors']))
    series=measurements['actors'][actor]
    summary={
        'status':'passed_staged_pose_observation_only',
        'baseline':'passed_native_leg_identity_only',
        'blender':measurements['blender_version'],
        'actor':actor,
        'frames':[x['frame'] for x in series],
        'staged_lengths_m':{
            side:{key:round(series[0]['legs'][side][key],9)
                  for key in ('upper_m','lower_m','ankle_to_toe_m')}
            for side in ('left','right')},
        'scale_observed':series[0]['rig_world_scale'],
        'source_sha':measurements['source_sha'],
        'leg_approval_sha':measurements['leg_approval_sha'],
        'ik_applied':False,
        'note':'Real Blender staged pose survey only; neither physical foot contact nor IK is verified'
    }
    (out/'result.json').write_text(json.dumps(summary,indent=2,sort_keys=True),'utf8')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--external-glb',required=True)
    p.add_argument('--blender',default='blender')
    p.add_argument('--audit-only',action='store_true')
    a=p.parse_args(argv)
    result=run_staged_pose_fixture(a.out,a.external_glb,blender=a.blender,
                                  audit_only=a.audit_only)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['status']=='passed_staged_pose_observation_only' else 1
if __name__=='__main__':raise SystemExit(main())
