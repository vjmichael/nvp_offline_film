// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import DataFirstViewpointEditor from './DataFirstViewpointEditor.jsx';

vi.mock('./SourceUSDViewport.jsx',()=>({
  default:({snapshot,orbit})=><div aria-label="Source USD viewport test">
    {snapshot?'Verified camera '+snapshot.camera_id:'Pending source'}
    {orbit?' orbit':' fixed'}
  </div>,
}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});

const original='a'.repeat(64),bankHash='b'.repeat(64);
const camera=id=>({
  camera_id:id,setup:'Director',framing:id==='Wide'?'wide':'OTS',
  position_m:[0,0,10],rotation_euler_deg:[0,0,0],
  focal_length_mm:35,focus_distance_m:10,clip_range_m:[.01,10000],
  move_keys:[],camera_ray_exclusions:[],
});
function catalog(edits=[]){
  return {
    format:'nvp.usd_film01r.original_world_viewpoint_catalog.v1',
    project_id:'project1',
    original_world_takes:[{world_take_id:'SourceTake',original_take_sha256:'d'.repeat(64)}],
    camera_banks:[{camera_bank_id:'OriginalBank',revision:1,
      document_sha256:bankHash,original_world_take_id:'SourceTake',
      original_performance_sha256:original,
      cameras:[camera('Wide'),camera('OTS')]}],
    edits,
  };
}
function source(cameraId,frame){
  return {
    format:'nvp.usd_film01r.source_3d_lofi_viewpoint.v1',
    project_id:'project1',camera_bank_id:'OriginalBank',
    camera_bank_revision:1,camera_bank_sha256:bankHash,
    original_performance_sha256:original,
    camera_id:cameraId,frame,native_blender_workers_started:0,
    objects:[],camera_world_matrix_rows:[],
    preview_is_source_derived_not_final_cycles_image:true,
  };
}
function buildApi(current){
  return vi.fn(async(path,method,payload)=>{
    if(path.endsWith('/film/data-first-viewpoints'))
      return current();
    if(path.includes('/preview?')){
      const qs=new URLSearchParams(path.split('?')[1]);
      return source(qs.get('camera_id'),Number(qs.get('frame')));
    }
    if(path==='/system/shot-batch-estimate'){
      return {format:'nvp.film01s.read_only_batch_capacity_preview.v1',
        shots_per_batch:payload.shots_per_batch||2,
        safe_parallel_workers:{hifi:{safe_workers:1}},
        render_jobs_started:0};
    }
    throw Error('Unexpected API operation: '+path);
  });
}
describe('01R editable source-first virtual film',()=>{
  it('scrubs one frozen scene and makes a camera cut without rendering nine rolls',async()=>{
    const api=buildApi(()=>catalog());
    render(<DataFirstViewpointEditor projectId="project1" api={api}/>);
    expect(await screen.findByRole('button',{name:'Shot 1 using Wide'})).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Film frame scrubber'),
      {target:{value:'360'}});
    fireEvent.click(screen.getByRole('button',{name:'Split at playhead'}));
    expect(await screen.findByRole('button',{name:'Shot 2 using Wide'})).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Virtual viewpoint'),
      {target:{value:'OTS'}});
    fireEvent.click(screen.getByRole('button',
      {name:'Use selected camera for this shot'}));
    expect(screen.getByRole('button',{name:'Shot 2 using OTS'})).toBeTruthy();
    expect(screen.getByText(/2 cuts cover exactly 720 frames/)).toBeTruthy();
    expect(screen.getByText(/original performance, or soundtrack/)).toBeTruthy();
    const last=api.mock.calls.filter(call=>call[0].includes('/preview?')).at(-1);
    expect(last[0]).toContain('frame=360');
    expect(api.mock.calls.every(call=>call[1]!=='POST')).toBe(true);
  });

  it('denies browser-only source edits and native render authority',async()=>{
    const api=buildApi(()=>catalog());
    render(<DataFirstViewpointEditor projectId="project1" api={api}/>);
    await screen.findByRole('button',{name:'Shot 1 using Wide'});
    expect(screen.getByRole('button',
      {name:'Native approve & save edit'}).disabled).toBe(true);
    expect(screen.getByRole('button',
      {name:'Native approve next 8 selected frames'}).disabled).toBe(true);
    expect(screen.getByText(/Browser source inspection only/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Estimate batches'}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith(
      '/system/shot-batch-estimate','POST',expect.anything()));
    expect(screen.getByText(/Adaptive batch estimate/)).toBeTruthy();
  });

  it('saves exact source EDL only through native OS-confirmed bridge',async()=>{
    let saved=null;
    const api=buildApi(()=>catalog(saved?[saved]:[]));
    const native={
      film01r_create_bank:vi.fn(),film01r_revise_bank:vi.fn(),
      film01r_save_edit:vi.fn(async payload=>{
        expect(payload.project_id).toBe('project1');
        expect(payload.camera_bank_id).toBe('OriginalBank');
        expect(payload.expected_revision).toBe(0);
        expect(payload.cuts[0].edit_out_frame).toBe(720);
        saved={edit_id:payload.edit_id,revision:1,
          document_sha256:'e'.repeat(64),camera_bank_id:'OriginalBank',
          camera_bank_revision:1,original_performance_sha256:original,
          cuts:payload.cuts};
        return {format:'nvp.film01r.authenticated_source_edit_saved.v1',
          edit_id:payload.edit_id,revision:1,document_sha256:'e'.repeat(64),
          original_performance_modified:false,native_render_jobs_started:0};
      }),
      film01r_render_next:vi.fn(async()=>({
        format:'nvp.film01r.native_selected_frame_ticket.v1',
        state:'QUEUED_FOR_RESOURCES',reason:'Available RAM below reserve'})),
      film01r_render_poll:vi.fn(),
    };
    render(<DataFirstViewpointEditor projectId="project1" api={api}
      nativeBridge={native}/>);
    await screen.findByRole('button',{name:'Shot 1 using Wide'});
    fireEvent.click(screen.getByRole('button',
      {name:'Native approve & save edit'}));
    await waitFor(()=>expect(native.film01r_save_edit).toHaveBeenCalledTimes(1));
    await screen.findByText(/Source edit saved/);
    fireEvent.change(screen.getByLabelText('Original film render quality'),
      {target:{value:'final_720p'}});
    fireEvent.change(screen.getByLabelText('Director shots per batch'),
      {target:{value:'6'}});
    fireEvent.click(screen.getByRole('button',
      {name:'Native approve next 8 selected frames'}));
    await waitFor(()=>expect(native.film01r_render_next).toHaveBeenCalledTimes(1));
    expect(native.film01r_render_next.mock.calls[0][0]).toMatchObject({
      project_id:'project1',revision:1,render_quality:'final_720p',
      shots_per_batch:6});
    expect(screen.getByText(/QUEUED_FOR_RESOURCES/)).toBeTruthy();
    expect(screen.queryByText(/Independently checked frames/)).toBe(null);
  });
});
