import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,waitFor,fireEvent} from '@testing-library/react';
import NativeOriginalCapturePanel from './NativeOriginalCapturePanel.jsx';

const pid='a'.repeat(32),sha='b'.repeat(64),planSha='c'.repeat(64);
const timeline={
  timeline_id:'CameraSource',revision:1,document_sha256:planSha,
  scene_id:'World001',scene_revision:1,scene_document_sha256:sha,
  duration_tick:'7056000000',
  emitter_paths:['/World/Actor','/World/Listener']};
function bridge(){
  return {
    data_av_capture_catalog:vi.fn(async()=>({
      format:'nvp.data_av.original_capture_catalog.v1',
      project_id:pid,timelines:[timeline]})),
    data_av_capture_begin:vi.fn(async request=>({
      format:'nvp.data_av.native_capture_session.v1',
      status:'RECORDING',take_id:request.take_id,
      scene_document_sha256:sha})),
    data_av_capture_finish:vi.fn(async()=>({
      format:'nvp.data_av.native_capture_session.v1',
      status:'FROZEN_ORIGINAL_LIVE_TAKE',
      take_id:'OriginalMicTake001',take_document_sha256:'f'.repeat(64),
      picture_frames_generated:false})),
    data_av_capture_cancel:vi.fn(async()=>({status:'CANCELLED'})),
    data_av_capture_devices:vi.fn(async()=>({
      format:'nvp.data_av.native_capture_session.v1',
      input_devices:[{device_id:10,name:'Mic A',host_api:'Native'},
                     {device_id:11,name:'Mic B',host_api:'Native'}]})),
  };
}
describe('PLAN-02-B trusted original PCM control',()=>{
  it('does not send browser approval; start and freeze are separate human operations',async()=>{
    const native=bridge(),onCompleted=vi.fn();
    render(<NativeOriginalCapturePanel projectId={pid} native={native}
      onCompleted={onCompleted}/>);
    await screen.findByText(/CameraSource · revision 1/);
    // Catalog option can render before the emitter-selection effect settles.
    // Wait for the creator action to become admissible, not just for its label.
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Start original recording (OS approval)'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Start original recording (OS approval)'}));
    await waitFor(()=>expect(native.data_av_capture_begin).toHaveBeenCalledOnce());
    const req=native.data_av_capture_begin.mock.calls[0][0];
    expect(req.project_id).toBe(pid);
    expect(req.scene_document_sha256).toBe(sha);
    expect(req.camera_timeline_document_sha256).toBe(planSha);
    expect(req.emitter_path).toBe('/World/Actor');
    expect(req.creator_approved).toBeUndefined();
    fireEvent.click(await screen.findByText('Stop and request Take freeze'));
    await waitFor(()=>expect(native.data_av_capture_finish).toHaveBeenCalledOnce());
    expect(onCompleted).toHaveBeenCalledOnce();
    expect(screen.getByText(/Frozen original Take/)).toBeTruthy();
  });
  it('refuses cross-project source catalog and never starts native capture',async()=>{
    const native=bridge();
    native.data_av_capture_catalog.mockResolvedValueOnce({
      format:'nvp.data_av.original_capture_catalog.v1',
      project_id:'d'.repeat(32),timelines:[timeline]});
    render(<NativeOriginalCapturePanel projectId={pid} native={native}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/source identity mismatch/);
    expect(screen.getByText('Start original recording (OS approval)').disabled)
      .toBe(true);
    expect(native.data_av_capture_begin).not.toHaveBeenCalled();
  });
  it('explicit cancellation does not request Take freeze',async()=>{
    const native=bridge();
    render(<NativeOriginalCapturePanel projectId={pid} native={native}/>);
    await screen.findByText(/CameraSource · revision 1/);
    // Catalog option can render before the emitter-selection effect settles.
    // Wait for the creator action to become admissible, not just for its label.
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Start original recording (OS approval)'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Start original recording (OS approval)'}));
    await screen.findByText(/Recording original PCM/);
    fireEvent.click(screen.getByText('Cancel without freezing'));
    await screen.findByText(/Recording stopped without freezing/);
    expect(native.data_av_capture_finish).not.toHaveBeenCalled();
    expect(native.data_av_capture_cancel).toHaveBeenCalledOnce();
  });
});
