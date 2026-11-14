import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import NativeCameraRailPanel from './NativeCameraRailPanel.jsx';

const project='a'.repeat(32);
const take='b'.repeat(64),timeline='c'.repeat(64);
const node=t=>({tick:t,position_m:[0,0,0],target_m:[0,3,0],
  tangent_in_mps:[0,0,0],tangent_out_mps:[0,0,0],roll_deg:0,
  focal_length_mm:35,focus_distance_m:3,f_stop:5.6,
  segment_mode:'hermite',easing:'smoothstep'});
const spec={take_id:'OriginalTake',take_document_sha256:take,
  camera_timeline_id:'SourceCamera',camera_timeline_revision:1,
  camera_timeline_sha256:timeline,
  source_camera_path:'/World/CameraA',
  camera_id:'DirectorRailCam',film_start_tick:0,film_end_tick:7056000000,
  technique:'static',rail_origin_m:[0,0,0],filmback_mm:[36,20.25],
  nodes:[node(0),node(7056000000)]};
const view={format:'nvp.plan02c.camera_rail_preview.v1',
  rail_id:'DirectorRail001',expected_revision:0,
  proposal_sha256:'d'.repeat(64),take_document_sha256:take,
  camera_timeline_sha256:timeline,
  director_approved:false,native_worker_authorized:false,
  source_film_time_samples:[{film_tick:0},{film_tick:7056000000}]};
const build=()=>({
  plan02c_catalog:vi.fn(async()=>({
    format:'nvp.plan02c.canonical_camera_source_catalog.v1',
    project_id:project,original_modified:false,sources:[{
      source_take_id:'OriginalTake',camera_timeline_id:'SourceCamera',
      source_camera_path:'/World/CameraA',source_film_start_tick:'0',
      source_film_end_tick:'7056000000',
      suggested_unapproved_rail_spec:spec}]})),
  plan02c_models:vi.fn(async()=>({
    format:'nvp.plan02c.available_loopback_gguf_models.v1',
    state:'available',models:[{id:'LocalGGUF_A'}]})),
  plan02c_preview:vi.fn(async()=>view),
  plan02c_model_candidate:vi.fn(async()=>({
    format:'nvp.plan02c.unapproved_verified_source_gguf_advice.v1',
    status:'UNAPPROVED_SOURCE_CAMERA_ADVICE',
    source_take_sha256:take,rail_published:false,
    human_authorization_granted:false,original_pcm_and_take_modified:false,
    proposed_rail_spec:{...spec,technique:'dolly'},
    provider_completion_receipt:{response_sha256:'e'.repeat(64),
      provider_reported_completion_tokens:42}})),
  plan02c_publish:vi.fn(async()=>({
    format:'nvp.plan02c.director_approved_rail_receipt.v1',
    rail_document_sha256:'f'.repeat(64),revision:1,
    original_modified:false,renderer_worker_authorized:false})),
});

describe('PLAN-02-C original Film Time rails and distinct human model permission',()=>{
  it('requires review preview then separate explicit rail publish action',async()=>{
    const native=build();
    render(<NativeCameraRailPanel projectId={project} native={native}/>);
    await screen.findByText(/OriginalTake · \/World\/CameraA/);
    expect(native.plan02c_publish).not.toHaveBeenCalled();
    expect(screen.getByText('Approve this exact rail in OS dialog').disabled)
      .toBe(true);
    fireEvent.click(screen.getByText('Verify original Film Time rail'));
    await waitFor(()=>expect(native.plan02c_preview).toHaveBeenCalledOnce());
    expect(screen.getByText('Approve this exact rail in OS dialog').disabled)
      .toBe(false);
    expect(native.plan02c_publish).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Approve this exact rail in OS dialog'));
    await waitFor(()=>expect(native.plan02c_publish).toHaveBeenCalledOnce());
    const publish=native.plan02c_publish.mock.calls[0][0];
    expect(publish.preview_sha256).toBe(view.proposal_sha256);
    expect(publish.rail_spec.take_document_sha256).toBe(take);
    expect(publish.creator_approved).toBeUndefined();
  });

  it('local model output is unapproved, invalidates an old rail preview',async()=>{
    const native=build();
    render(<NativeCameraRailPanel projectId={project} native={native}/>);
    await screen.findByText(/OriginalTake · \/World\/CameraA/);
    await waitFor(()=>expect(screen.getByRole('combobox',{
      name:'Local director GGUF model'}).value).toBe('LocalGGUF_A'));
    fireEvent.click(screen.getByText('Verify original Film Time rail'));
    await waitFor(()=>expect(native.plan02c_preview).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByText(/Ask real local GGUF for unapproved advice/));
    await waitFor(()=>expect(native.plan02c_model_candidate).toHaveBeenCalledOnce());
    expect(native.plan02c_publish).not.toHaveBeenCalled();
    expect(screen.getByText('Approve this exact rail in OS dialog').disabled)
      .toBe(true);
    expect(screen.getByText(/Model response recorded:/)).toBeTruthy();
    const req=native.plan02c_model_candidate.mock.calls[0][0];
    expect(req.model_id).toBe('LocalGGUF_A');
    expect(req.rail_spec.take_document_sha256).toBe(take);
    expect(req.human_approved).toBeUndefined();
  });

  it('rejects wrong original Take source before any native publication',async()=>{
    const native=build();
    native.plan02c_catalog.mockResolvedValueOnce({
      format:'nvp.plan02c.canonical_camera_source_catalog.v1',
      project_id:'different-project',original_modified:false,
      sources:[{suggested_unapproved_rail_spec:spec}]});
    render(<NativeCameraRailPanel projectId={project} native={native}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/source catalog was not verified/);
    expect(native.plan02c_publish).not.toHaveBeenCalled();
  });
  it('clears a verified 3D rail guide after changing the approved-source proposal',async()=>{
    const native=build(),onPreviewChange=vi.fn();
    render(<NativeCameraRailPanel projectId={project} native={native}
      onPreviewChange={onPreviewChange}/>);
    await screen.findByText(/OriginalTake · \/World\/CameraA/);
    fireEvent.click(screen.getByText('Verify original Film Time rail'));
    await waitFor(()=>expect(onPreviewChange).toHaveBeenCalledWith(view));
    fireEvent.change(screen.getByRole('textbox',{name:'New director rail ID'}),{
      target:{value:'DirectorRail002'}});
    expect(onPreviewChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByText('Approve this exact rail in OS dialog').disabled)
      .toBe(true);
  });

});
