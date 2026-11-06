"""Create an offline approved, frame-accurate two-camera shot for native CI audits."""
from pathlib import Path
import argparse
import json

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence, run_shot_acceptance


def fixture(root, *, render_preview=True):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    studio=Studio(root/'film.sqlite3')
    pid=studio.create_project('NVP-PROD-05 native take fixture','Two-cut actor movement test')['id']
    sid=studio.save_screenplay(pid,'INT. FILM SET - DAY\n\nMARA\nThe key is here.\n',0)['scenes'][0]['id']
    prod=ProductionScene(studio)
    prod.create_asset(pid,{'name':'MARA','category':'character',
                           'dimensions':[.4,.4,1.68]})
    stage=prod.stage_scene(pid,sid,[8,6,3])
    stage=prod.solve_scene(pid,sid,stage['plan_revision'])
    prod.approve_scene(pid,sid,stage['plan_revision'])
    actor=next(i for i in prod.export_manifest(pid,sid)['instances'] if i['name']=='MARA')
    bc=BlockingCamera(studio)
    mark=bc.add_mark(pid,sid,actor['instance_id'],
                     [actor['pose']['x']+.5,actor['pose']['y']],start_s=.8,end_s=3.)
    cam_a=bc.solve_shot(pid,sid,[actor['instance_id']],lens_mm=50)
    cam_b=bc.solve_shot(pid,sid,[actor['instance_id']],lens_mm=35)
    line=bc.dialogue(pid,sid)['dialogue'][0]
    bc.set_dialogue_duration(pid,sid,line['id'],.8)
    seq=ShotSequence(studio)
    state=seq.create(pid,sid)
    state=seq.add_shot(pid,sid,cam_a['id'],60,'single',state['revision'])
    state=seq.add_shot(pid,sid,cam_b['id'],60,'reaction',state['revision'])
    state=seq.place_cue(pid,sid,line['id'],5,state['revision'])
    assert not state['review']['errors'], state['review']
    if state['review']['warnings']:
        state=seq.acknowledge(pid,sid,[w['code'] for w in state['review']['warnings']],state['revision'])
    state=seq.approve(pid,sid,state['revision'])
    report=run_shot_acceptance(seq,pid,sid,root/'take',render_preview=render_preview)
    (root/'take_result.json').write_text(json.dumps(report,indent=2),'utf8')
    assert report['status'] == ('passed_blender' if render_preview else 'passed_blender_audit_only'), report
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(fixture(args.out,render_preview=not args.audit_only),indent=2))


if __name__=='__main__':main()
