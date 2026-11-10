// @vitest-environment jsdom
import React from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import CameraRailsDirector from './CameraRailsDirector.jsx';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
const PID='a'.repeat(32),T=7056000000;
const BANK='b'.repeat(64),TAKE='c'.repeat(64);
const PREVIEW='d'.repeat(64),LAYER='e'.repeat(64);
const GUIDANCE='f'.repeat(64),DID='a'.repeat(24);
const AID='b'.repeat(24),SOURCE='c'.repeat(64);
const BANKNAME='NativeOriginalBank';

function native(){
  let latest=null,version=1;
  const actor={actor_id:'SourceActorOne',
    source_prim:'/World/Sets/Street/Actor',
    center_world_m:[0,0,1],
    bounds_world_m:[[-.5,-.5,0],[.5,.5,2]],
    frame:{state:'PARTLY_IN_FRAME',coverage:.15,
      bounds_uv:[.1,.2,.5,.8],center_uv:[.3,.5]}};
  const native={
    camfx01_catalog:vi.fn(async()=>({
      format:'nvp.cam_fx01.trusted_director_rail_catalog.v1',
      project_id:PID,camera_banks:[{
        bank_id:BANKNAME,revision:1,document_sha256:BANK,
        world_take_id:'FrozenTake',world_take_sha256:TAKE,
        duration_ticks:2*T,cameras:[{
          camera_id:'VerifiedCamera',position_m:[0,-8,3],
          focal_length_mm:35,focus_distance_m:8}]}],
      rails:[],native_worker_started:false,
      frozen_actor_takes_modified:false})),
    camfx01_preview:vi.fn(async r=>({
      format:'nvp.cam_fx01.verified_director_rail_proposal.v1',
      expected_revision:r.expected_revision,proposal_sha256:PREVIEW,
      rail_layer_sha256:LAYER,
      world_take_sha256:TAKE,camera_bank_sha256:BANK,
      film_time_samples:[{film_tick:0},{film_tick:T},{film_tick:2*T}],
      native_blender_workers_started:0,
      original_actor_takes_and_pcm_unchanged:true,
      director_creative_approval_granted:false})),
    camfx02_publish:vi.fn(),
    camfx02_reopen:vi.fn(async r=>({
      format:'nvp.cam_fx02.trusted_native_director_rail_reopen.v1',
      rail_id:r.rail_id,revision:r.revision,
      layer_sha256:LAYER,native_stronger_layer_verified:true,
      frozen_actor_takes_and_pcm_unchanged:true,
      native_camera_path:'/World/NVPDirectorRails/'+r.rail_id,
      native_reopened_sample_count:50})),
    camfx02_sample:vi.fn(async r=>({
      format:'nvp.cam_fx02.native_rail_film_tick_pose.v1',
      rail_id:r.rail_id,revision:r.revision,rail_layer_sha256:LAYER,
      film_tick:r.film_tick,source_actor_pcm_changed:false,
      native_worker_started:false,
      native_layer_sample_authored_and_read_back:true,
      host_exact_film_time_interpolated:false,
      sample:{position_m:[0,-8,3],target_m:[0,0,1],
        focal_length_mm:35,focus_distance_m:8,f_stop:5.6}})),
    camfx03_scene_guidance:vi.fn(async r=>({
      format:'nvp.cam_fx03.source_grounded_actor_framing_and_occlusion.v1',
      project_id:PID,camera_bank_sha256:BANK,
      world_take_sha256:TAKE,
      source_actor_takes_and_pcm_unchanged:true,
      native_scene_reviewed:true,guidance_sha256:GUIDANCE,
      approved_district_sha256:null,native_actor_count:1,
      source_guided_frames:[0,T,2*T].map(t=>({
        film_tick:t,original_actor_views:[actor],
        selected_actor_center_ray:{
          state:r.actor_id?'NO_HIT_IN_REVIEWED_CENTER_RAY':'NO_TARGET',
          reviewed_original_district_triangles:0,
          excluded_nonmesh_shapes:0,hit_source_prim:null,
          full_image_visibility_proven:false}
      }))})),
    camfx03_draft_catalog:vi.fn(async()=>({
      format:'nvp.cam_fx03.original_camera_draft_catalog.v1',
      project_id:PID,drafts:latest?[{draft_id:DID,rail_id:'OriginalCameraRail',
        version,state:'DRAFT'}]:[],model_attempts:[],
      native_worker_authorized:false})),
    camfx03_draft_create:vi.fn(async r=>{
      latest={...r.rail_spec};
      return {
        format:'nvp.cam_fx03.durable_original_camera_rail_draft.v1',
        project_id:PID,draft_id:DID,rail_id:'OriginalCameraRail',
        base_revision:0,version,state:'DRAFT',
        rail_spec:latest,proposal_sha256:PREVIEW,stronger_usd_sha256:LAYER,
        source_world_take_sha256:TAKE,undo_depth:0,
        source_actor_takes_and_pcm_changed:false};}),
    camfx03_draft_save:vi.fn(async r=>{
      latest={...r.rail_spec};version++;
      return {
        format:'nvp.cam_fx03.durable_original_camera_rail_draft.v1',
        project_id:PID,draft_id:DID,rail_id:'OriginalCameraRail',
        base_revision:0,version,state:'DRAFT',
        rail_spec:latest,proposal_sha256:PREVIEW,stronger_usd_sha256:LAYER,
        source_world_take_sha256:TAKE,undo_depth:1,
        source_actor_takes_and_pcm_changed:false};}),
    camfx03_draft_reopen:vi.fn(async()=>({
      format:'nvp.cam_fx03.durable_original_camera_rail_draft.v1',
      project_id:PID,draft_id:DID,rail_id:'OriginalCameraRail',
      base_revision:0,version,state:'DRAFT',rail_spec:latest,
      proposal_sha256:PREVIEW,stronger_usd_sha256:LAYER,
      source_world_take_sha256:TAKE,undo_depth:1,
      source_actor_takes_and_pcm_changed:false})),
    camfx03_draft_undo:vi.fn(),camfx03_draft_discard:vi.fn(),
    camfx03_draft_publish:vi.fn(async()=>({
      format:'nvp.cam_fx03.durable_published_director_rail.v1',
      rail_receipt:{revision:1,document_sha256:SOURCE,
        source_usd_layer_sha256:LAYER,
        original_actor_takes_and_pcm_unchanged:true},
      draft:{
        format:'nvp.cam_fx03.durable_original_camera_rail_draft.v1',
        project_id:PID,draft_id:DID,rail_id:'OriginalCameraRail',
        base_revision:0,version,state:'PUBLISHED',rail_spec:latest,
        proposal_sha256:PREVIEW,stronger_usd_sha256:LAYER,
        source_world_take_sha256:TAKE,undo_depth:1,
        source_actor_takes_and_pcm_changed:false},
      actor_pcm_modified:false,native_worker_authorized:false})),
    camfx03_draft_recover_publish:vi.fn(),
    camfx04_start_candidate:vi.fn(async()=>({
      format:'nvp.cam_fx04.durable_unapproved_model_camera_proposal.v1',
      project_id:PID,draft_id:DID,attempt_id:AID,
      state:'GENERATING',director_approval_granted:false,
      native_worker_authorized:false})),
    camfx04_candidate_status:vi.fn(async()=>({
      format:'nvp.cam_fx04.durable_unapproved_model_camera_proposal.v1',
      project_id:PID,draft_id:DID,attempt_id:AID,
      state:'DRAFT_UPDATED_UNAPPROVED',
      director_approval_granted:false,native_worker_authorized:false,
      draft:{
        format:'nvp.cam_fx03.durable_original_camera_rail_draft.v1',
        project_id:PID,draft_id:DID,rail_id:'OriginalCameraRail',
        base_revision:0,version:version+1,state:'DRAFT',
        rail_spec:{...latest,technique:'crane'},
        proposal_sha256:PREVIEW,stronger_usd_sha256:LAYER,
        source_world_take_sha256:TAKE,undo_depth:1,proposed_by:'model',
        source_actor_takes_and_pcm_changed:false}})),
    camfx04_cancel_candidate:vi.fn(),
    wo6_local_models:vi.fn(async()=>({
      state:'available',models:[{id:'LocalGGUFForCamera'}]}))
  };
  return native;
}

async function createSourceDraft(bridge){
  fireEvent.click(screen.getByRole('button',{
    name:'Create editable camera rail handles from technique'}));
  await screen.findByLabelText('Rail key 2 tick');
  fireEvent.click(screen.getByRole('button',{
    name:'Create source-bound durable camera-rail draft'}));
  await screen.findByText(/Camera path durably committed as an UNAPPROVED SQLite draft/);
}

describe('CAM-FX-03/04 installed director native source/AI recovery',()=>{
  it('uses actual ActorID source guidance for projected 3D handles and never calls a fake renderer',async()=>{
    const host=native();
    render(<CameraRailsDirector projectId={PID} nativeBridge={host}/>);
    await screen.findByRole('option',{name:'NativeOriginalBank · revision 1'});
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Create editable camera rail handles from technique'}));
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}));
    await screen.findByRole('region',{
      name:'Verified original ActorID scene and ray guidance'});
    expect(screen.getAllByText(/ActorID SourceActorOne/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Full frame visibility never certified by one ray/).length).toBe(3);
    expect(screen.getByRole('img',{
      name:'Editable 3D projected original camera rail and source ActorID bounds'})).toBeTruthy();
    expect(host.camfx03_scene_guidance.mock.calls[0][0].actor_id).toBe(null);
    fireEvent.change(screen.getByLabelText('Original native ActorID framing target'),{
      target:{value:'SourceActorOne'}});
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}));
    await waitFor(()=>expect(host.camfx03_scene_guidance).toHaveBeenCalledTimes(2));
    expect(host.camfx03_scene_guidance.mock.calls[1][0].actor_id).toBe('SourceActorOne');
    expect(host.camfx02_publish).not.toHaveBeenCalled();
  });

  it('persists edits in SQLite after source-draft creation and invalidates old approval',async()=>{
    const host=native();
    render(<CameraRailsDirector projectId={PID} nativeBridge={host}/>);
    await screen.findByRole('option',{name:'NativeOriginalBank · revision 1'});
    await createSourceDraft(host);
    fireEvent.change(screen.getByLabelText('Rail key 1 focus_distance_m'),{
      target:{value:'4'}});
    await waitFor(()=>expect(host.camfx03_draft_save).toHaveBeenCalled(),{
      timeout:2800});
    expect(host.camfx03_draft_save.mock.calls[0][0]).toMatchObject({
      project_id:PID,draft_id:DID,version:1});
    expect(host.camfx03_draft_save.mock.calls[0][0].rail_spec.nodes[1]
      .focus_distance_m).toBe(4);
    expect(host.camfx03_draft_publish).not.toHaveBeenCalled();
  });

  it('saves an untrusted GGUF suggestion as editable draft, never auto publishes its camera layer',async()=>{
    const host=native();
    render(<CameraRailsDirector projectId={PID} nativeBridge={host}/>);
    await screen.findByRole('option',{name:'NativeOriginalBank · revision 1'});
    await createSourceDraft(host);
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Read actual original USD ActorID framing and bounded occlusion'}));
    await screen.findByRole('region',{
      name:'Verified original ActorID scene and ray guidance'});
    await screen.findByRole('option',{name:'LocalGGUFForCamera'});
    fireEvent.change(screen.getByLabelText('Native original camera model direction'),{
      target:{value:'Suggest a source-linked crane shot'}});
    fireEvent.click(screen.getByRole('button',{
      name:'Suggest and save unapproved source-grounded AI camera rail'}));
    await waitFor(()=>expect(host.camfx04_start_candidate).toHaveBeenCalledTimes(1));
    expect(host.camfx04_start_candidate.mock.calls[0][0]).toMatchObject({
      project_id:PID,draft_id:DID,version:1,
      model_id:'LocalGGUFForCamera'});
    await waitFor(()=>expect(host.camfx04_candidate_status).toHaveBeenCalled(),{
      timeout:2500});
    await screen.findByText(/Local model suggestion saved as editable UNAPPROVED rail version/);
    expect(host.camfx03_draft_publish).not.toHaveBeenCalled();
    expect(host.camfx02_publish).not.toHaveBeenCalled();
  });
});
