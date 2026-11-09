// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import OriginalActorDistrictCyclesReview from './OriginalActorDistrictCyclesReview.jsx';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
const project='a'.repeat(32),bindingId='OriginalDistrictFilmShot';
const original='b'.repeat(64),world='c'.repeat(64);
const job='shot02mh_123456789abc123456789abc',ticket='d'.repeat(24);
const BIND='nvp.usd_film02m_h.approved_district_original_actor_camera_binding.v1';
const TICKET='nvp.usd_film02m_h.native_render_ticket.v1';
const STATUS='nvp.usd_film02m_h.native_render_status.v1';
const IMAGE='nvp.usd_film02m_h.verified_native_cycles_picture.v1';

function host(){
  return {
    film02mh_reopen_shot_binding:vi.fn(async()=>({
      format:BIND,binding_id:bindingId,binding_document_sha256:original,
      native_source_reopened:true,source_actor_takes_unchanged:true})),
    film02mh_render_begin:vi.fn(async()=>({
      format:TICKET,state:'PENDING_FRESH_NATIVE_APPROVAL',
      binding_id:bindingId,binding_sha256:original,ticket_id:ticket,
      original_actor_takes_modified:false,director_picture_approved:false})),
    film02mh_render_poll:vi.fn(async()=>({
      format:STATUS,state:'SOURCE_VERIFIED_CYCLES_PICTURE',
      ticket_id:ticket,binding_id:bindingId,binding_sha256:original,
      job_id:job,picture_sha256:world,
      native_worker_and_independent_reopen_verified:true,
      original_actor_takes_modified:false,director_picture_approved:false})),
    film02mh_render_image:vi.fn(async()=>({
      format:IMAGE,job_id:job,
      binding_id:bindingId,binding_sha256:original,
      picture_sha256:world,world_take_sha256:'f'.repeat(64),
      district_document_sha256:'e'.repeat(64),
      native_worker_and_independent_reopen_verified:true,
      original_actor_takes_and_pcm_unchanged:true,
      director_picture_approved:false,final_film_accepted:false,
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAE='}))
  };
}

describe('02M-HR original actor/district Cycles inside actual director',()=>{
  it('requires a real reopened binding, new native approval and independently verified pixels',async()=>{
    const native=host();
    render(<OriginalActorDistrictCyclesReview projectId={project}
      nativeBridge={native} bindingId={bindingId} bindingReceipt={null}/>);
    expect(screen.getByRole('button',{
      name:'OS approve and render original actor/district Cycles frame'
    }).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen existing approved actor/district shot for render'}));
    await waitFor(()=>expect(native.film02mh_reopen_shot_binding).toHaveBeenCalledTimes(1));
    await screen.findByText(/Approved shot SHA/);
    fireEvent.click(screen.getByRole('button',{
      name:'OS approve and render original actor/district Cycles frame'}));
    await waitFor(()=>expect(native.film02mh_render_begin).toHaveBeenCalledTimes(1));
    expect(native.film02mh_render_begin.mock.calls[0][0]).toEqual({
      project_id:project,binding_id:bindingId,binding_sha256:original});
    await waitFor(()=>expect(native.film02mh_render_poll).toHaveBeenCalled());
    await screen.findByRole('img',{
      name:'Verified original actor and modular district Cycles frame'});
    expect(native.film02mh_render_image.mock.calls[0][0]).toEqual({
      project_id:project,binding_id:bindingId,
      binding_sha256:original,job_id:job});
    expect(screen.getByText(/Human image-quality review open/)).toBeTruthy();
    expect(native.film02mh_render_begin).toHaveBeenCalledTimes(1);
  });

  it('can independently reopen completed source image after app restart without launching a worker',async()=>{
    const native=host();
    render(<OriginalActorDistrictCyclesReview projectId={project}
      nativeBridge={native} bindingId={bindingId} bindingReceipt={null}/>);
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen existing approved actor/district shot for render'}));
    await screen.findByText(/Approved shot SHA/);
    fireEvent.change(screen.getByLabelText('Exact completed Cycles worker job ID'),{
      target:{value:job}});
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen independently verified saved Cycles image'}));
    await waitFor(()=>expect(native.film02mh_render_image).toHaveBeenCalledTimes(1));
    expect(native.film02mh_render_begin).not.toHaveBeenCalled();
    await screen.findByRole('img',{
      name:'Verified original actor and modular district Cycles frame'});
  });

  it('refuses a denied native operation and never displays invented pixels',async()=>{
    const native=host();
    native.film02mh_render_poll=vi.fn(async()=>({
      format:STATUS,state:'NATIVE_DENIED_OR_REQUIRES_NEW_APPROVAL',
      ticket_id:ticket,binding_id:bindingId,binding_sha256:original,
      original_actor_takes_modified:false,director_picture_approved:false}));
    render(<OriginalActorDistrictCyclesReview projectId={project}
      nativeBridge={native} bindingId={bindingId} bindingReceipt={null}/>);
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen existing approved actor/district shot for render'}));
    await screen.findByText(/Approved shot SHA/);
    fireEvent.click(screen.getByRole('button',{
      name:'OS approve and render original actor/district Cycles frame'}));
    await screen.findByText(/Historical source approval cannot authorize a new worker/);
    expect(native.film02mh_render_image).not.toHaveBeenCalled();
    expect(screen.queryByRole('img',{
      name:'Verified original actor and modular district Cycles frame'})).toBeNull();
  });

  it('fails closed if worker image does not match source-bound receipt',async()=>{
    const native=host();
    native.film02mh_render_image=vi.fn(async()=>({
      format:IMAGE,binding_id:bindingId,binding_sha256:'0'.repeat(64),
      job_id:job,picture_sha256:world,
      native_worker_and_independent_reopen_verified:true,
      original_actor_takes_and_pcm_unchanged:true,
      director_picture_approved:false,final_film_accepted:false,
      image_data_url:'data:image/png;base64,aGVsbG8='}));
    render(<OriginalActorDistrictCyclesReview projectId={project}
      nativeBridge={native} bindingId={bindingId} bindingReceipt={null}/>);
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen existing approved actor/district shot for render'}));
    await screen.findByText(/Approved shot SHA/);
    fireEvent.change(screen.getByLabelText('Exact completed Cycles worker job ID'),{
      target:{value:job}});
    fireEvent.click(screen.getByRole('button',{
      name:'Reopen independently verified saved Cycles image'}));
    await screen.findByRole('alert');
    expect(screen.queryByRole('img',{
      name:'Verified original actor and modular district Cycles frame'})).toBeNull();
    expect(native.film02mh_render_begin).not.toHaveBeenCalled();
  });
});
