// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import CameraRailsDirector from './CameraRailsDirector.jsx';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
const T=7056000000,PID='a'.repeat(32),BANK='b'.repeat(64);
const TAKE='c'.repeat(64),LAYER='d'.repeat(64),PROPOSAL='e'.repeat(64);
const BIND='f'.repeat(64);

function bridge(){
  const bank={
    bank_id:'ShotCameraBank',revision:1,
    document_sha256:BANK,
    world_take_id:'FrozenWorldTake',
    world_take_sha256:TAKE,duration_ticks:2*T,
    cameras:[{
      camera_id:'RailCam',position_m:[1,-8,3],
      focal_length_mm:35,focus_distance_m:8}]
  };
  let railRecord=null;
  const native={
    camfx01_catalog:vi.fn(async()=>({
      format:'nvp.cam_fx01.trusted_director_rail_catalog.v1',
      project_id:PID,camera_banks:[bank],
      rails:railRecord?[{rail_id:'OriginalCameraRail',revision:1,
        document_sha256:BIND,technique:'dolly'}]:[],
      frozen_actor_takes_modified:false,
      native_worker_started:false})),
    camfx01_preview:vi.fn(async r=>({
      format:'nvp.cam_fx01.verified_director_rail_proposal.v1',
      expected_revision:r.expected_revision,
      world_take_sha256:TAKE,camera_bank_sha256:BANK,
      proposal_sha256:PROPOSAL,rail_layer_sha256:LAYER,
      native_blender_workers_started:0,
      original_actor_takes_and_pcm_unchanged:true,
      director_creative_approval_granted:false,
      film_time_samples:[{film_tick:0},{film_tick:T},{film_tick:2*T}]})),
    camfx02_publish:vi.fn(async r=>{
      railRecord=r;
      return {
        revision:r.expected_revision+1,
        document_sha256:BIND,source_usd_layer_sha256:LAYER,
        original_actor_takes_and_pcm_unchanged:true,
        director_picture_approved:false};
    }),
    camfx02_reopen:vi.fn(async r=>({
      format:'nvp.cam_fx02.trusted_native_director_rail_reopen.v1',
      rail_id:r.rail_id,revision:r.revision,
      layer_sha256:LAYER,
      native_stronger_layer_verified:true,
      frozen_actor_takes_and_pcm_unchanged:true,
      native_camera_path:'/World/NVPDirectorRails/'+r.rail_id,
      native_reopened_sample_count:50,
      rail_spec:railRecord?.rail_spec
    })),
    camfx02_sample:vi.fn(async r=>({
      format:'nvp.cam_fx02.native_rail_film_tick_pose.v1',
      rail_id:r.rail_id,revision:r.revision,
      rail_layer_sha256:LAYER,film_tick:r.film_tick,
      native_worker_started:false,source_actor_pcm_changed:false,
      sample:{position_m:[1,0,3],target_m:[1,8,3],
        focal_length_mm:35,focus_distance_m:8,f_stop:5.6}
    }))
  };
  return native;
}

describe('CAM-FX installed original camera-rail director',()=>{
  it('proposes a real source bank, director-edits handles and grants only a separately confirmed camera-layer revision',async()=>{
    const native=bridge();
    render(<CameraRailsDirector projectId={PID} nativeBridge={native}/>);
    await screen.findByRole('option',{name:'ShotCameraBank · revision 1'});
    await waitFor(()=>expect(screen.getByLabelText(
      'Rail source camera').value).toBe('RailCam'));
    fireEvent.click(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}));
    await screen.findByLabelText('Rail key 2 focal_length_mm');
    fireEvent.change(screen.getByLabelText('Rail key 2 focal_length_mm'),{
      target:{value:'48'}});
    fireEvent.change(screen.getByLabelText('Rail key 1 position_m X'),{
      target:{value:'2.4'}});
    fireEvent.click(screen.getByRole('button',{
      name:'Preview exact-time stronger camera USD layer'}));
    await waitFor(()=>expect(native.camfx01_preview).toHaveBeenCalledTimes(1));
    const proposed=native.camfx01_preview.mock.calls[0][0];
    expect(proposed.project_id).toBe(PID);
    expect(proposed.rail_spec.nodes[2].focal_length_mm).toBe(48);
    expect(proposed.rail_spec.nodes[1].position_m[0]).toBe(2.4);
    expect(proposed.rail_spec.camera_bank_revision).toBe(1);
    expect(proposed.rail_spec.film_end_tick).toBe(2*T);
    expect(native.camfx02_publish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{
      name:'OS approve exact director-editable camera rail revision'}));
    await waitFor(()=>expect(native.camfx02_publish).toHaveBeenCalledTimes(1));
    expect(native.camfx02_publish.mock.calls[0][0]).toMatchObject({
      project_id:PID,rail_id:'OriginalCameraRail',expected_revision:0,
      preview_sha256:PROPOSAL});
    await screen.findByText(/Native camera source revision 1 committed/);
    expect(native.camfx02_reopen).toHaveBeenCalledWith({
      project_id:PID,rail_id:'OriginalCameraRail',revision:1});
    expect(screen.getByText(/Actual stronger OpenUSD camera/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Camera rail sample tick'),{
      target:{value:String(T)}});
    fireEvent.click(screen.getByRole('button',{
      name:'Read exact original-time native camera pose'}));
    await waitFor(()=>expect(native.camfx02_sample).toHaveBeenCalledWith({
      project_id:PID,rail_id:'OriginalCameraRail',revision:1,film_tick:T}));
  });

  it('inserts, moves, retimes, removes and undoes unapproved exact-time handles',async()=>{
    const native=bridge();
    render(<CameraRailsDirector projectId={PID} nativeBridge={native}/>);
    await screen.findByRole('option',{name:'ShotCameraBank · revision 1'});
    fireEvent.click(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}));
    await screen.findByLabelText('Rail key 2 tick');
    expect(screen.queryByLabelText('Rail key 3 tick')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Insert handle after 1'}));
    await screen.findByLabelText('Rail key 3 tick');
    const middle=screen.getByLabelText('Rail key 1 tick');
    expect(Number(middle.value)).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText('Rail key 1 position_m Z'),{
      target:{value:'4.8'}});
    expect(Number(screen.getByLabelText('Rail key 1 position_m Z').value)).toBe(4.8);
    fireEvent.click(screen.getByRole('button',{
      name:'Undo last unapproved camera-rail handle edit'}));
    expect(Number(screen.getByLabelText('Rail key 1 position_m Z').value)).not.toBe(4.8);
    fireEvent.click(screen.getByRole('button',{name:'Remove handle 2'}));
    expect(screen.queryByLabelText('Rail key 3 tick')).toBeNull();
    expect(native.camfx02_publish).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{
      name:'OS approve exact director-editable camera rail revision'}).disabled).toBe(true);
  });

  it('invalidates approval preview if the director changes any handle afterward',async()=>{
    const native=bridge();
    render(<CameraRailsDirector projectId={PID} nativeBridge={native}/>);
    await screen.findByRole('option',{name:'ShotCameraBank · revision 1'});
    fireEvent.click(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}));
    await screen.findByLabelText('Rail key 1 focus_distance_m');
    fireEvent.click(screen.getByRole('button',{
      name:'Preview exact-time stronger camera USD layer'}));
    await screen.findByText(/Director rail preview SHA/);
    expect(screen.getByRole('button',{
      name:'OS approve exact director-editable camera rail revision'}).disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('Rail key 1 focus_distance_m'),{
      target:{value:'5'}});
    expect(screen.getByRole('button',{
      name:'OS approve exact director-editable camera rail revision'}).disabled).toBe(true);
    expect(native.camfx02_publish).not.toHaveBeenCalled();
  });

  it('rejects mismatched model/browser native preview and will never publish',async()=>{
    const native=bridge();
    native.camfx01_preview=vi.fn(async()=>({
      format:'nvp.cam_fx01.verified_director_rail_proposal.v1',
      proposal_sha256:PROPOSAL,
      camera_bank_sha256:'0'.repeat(64),
      world_take_sha256:TAKE,
      director_creative_approval_granted:false,
      original_actor_takes_and_pcm_unchanged:true}));
    render(<CameraRailsDirector projectId={PID} nativeBridge={native}/>);
    await screen.findByRole('option',{name:'ShotCameraBank · revision 1'});
    fireEvent.click(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}));
    await screen.findByLabelText('Rail key 0 tick');
    fireEvent.click(screen.getByRole('button',{
      name:'Preview exact-time stronger camera USD layer'}));
    await screen.findByRole('alert');
    expect(native.camfx02_publish).not.toHaveBeenCalled();
  });

  it('never enables a browser-only rail writer or unapproved worker',()=>{
    const {container}=render(<CameraRailsDirector projectId={PID}
      nativeBridge={null}/>);
    expect(container.textContent).toBe('');
  });
});
