import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmCameraSourcePanel from './FilmCameraSourcePanel.jsx';

const pid='d'.repeat(32);
const sha='a'.repeat(64);
const list={
  format:'nvp.slate08.camera_source_list.v1',project_id:pid,
  scenes:[{scene_id:'native_scene',revision:1,document_sha256:sha,
           cameras:[{path:'/World/Camera',label:'Camera'}]}],
};
const snapshot={
  format:'nvp.camera.lens_workbench.v1',project_id:pid,scene_id:'native_scene',
  scene_revision:1,scene_document_sha256:sha,source_tick:0,
  camera_path:'/World/Camera',
  markers:[{path:'/World/Actor',role:'actor',
    camera_space_xyz:[1,0,-6],hint_radius_m:0.6}],
};
const api=vi.fn(async path=>
  path.endsWith('/film/camera-scenes')?list:snapshot);
const settings={
  format:'nvp.camera.lens_workbench.v1',preset:'standard_50',
  sensor:'full_frame',focal_length_mm:50,
  sensor_width_mm:36,sensor_height_mm:20.25,
  f_stop:2.8,focus_distance_m:5,
};
const result={
  format:'nvp.camera.desktop_delivery.v1',status:'READY',
  scene_document_sha256:sha,source_tick:0,camera_path:'/World/Camera',
  lens_settings:settings,image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
  source_modified:false,frozen_take_created:false,film_master_approved:false,
};
function ticket(){
  return {format:'nvp.camera.desktop_ticket.v1',status:'QUEUED',
    ticket_id:'ticket_1',scene_document_sha256:sha,source_tick:0,
    camera_path:'/World/Camera'};
}

describe('SLATE-08B trusted desktop still IPC',()=>{
  it('the ordinary browser cannot launch a native worker',async()=>{
    render(<FilmCameraSourcePanel projectId={pid} api={api}/>);
    expect(await screen.findByText(/50 mm · 39.6° horizontal FOV/)).toBeTruthy();
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    expect(screen.queryByText('Cancel native still')).toBeNull();
  });

  it('runs via desktop ticket and accepts only exact verified source still',async()=>{
    const request=vi.fn(async()=>ticket());
    const poll=vi.fn(async()=>result);
    const bridge={request_camera_still:request,poll_camera_still:poll,
                  cancel_camera_still:vi.fn()};
    render(<FilmCameraSourcePanel projectId={pid} api={api} nativeBridge={bridge}/>);
    await screen.findByText(/50 mm · 39.6° horizontal FOV/);
    fireEvent.click(screen.getByText('Render accurate optics still'));
    await waitFor(()=>expect(request).toHaveBeenCalledOnce());
    const sent=request.mock.calls[0][0];
    expect(sent.project_id).toBe(pid);
    expect(sent.source_scene_document_sha256).toBe(sha);
    expect(sent.source_tick).toBe(0);
    expect(sent.lens_settings.focal_length_mm).toBe(50);
    await waitFor(()=>expect(poll).toHaveBeenCalledWith('ticket_1'));
    expect(await screen.findByAltText(/Native rendered camera\/lens study/))
      .toBeTruthy();
    expect(screen.getByText('Save lens preset').disabled).toBe(true);
    expect(screen.getByText('Apply to shot').disabled).toBe(true);
  });

  it('an old native PNG is never shown as the current optical setup',async()=>{
    const bridge={
      request_camera_still:vi.fn(async()=>ticket()),
      poll_camera_still:vi.fn(async()=>result),
      cancel_camera_still:vi.fn(),
    };
    const {container}=render(<FilmCameraSourcePanel
      projectId={pid} api={api} nativeBridge={bridge}/>);
    await screen.findByText(/50 mm · 39.6° horizontal FOV/);
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'portrait_85'}});
    fireEvent.click(screen.getByText('Render accurate optics still'));
    await waitFor(()=>expect(bridge.poll_camera_still).toHaveBeenCalled());
    await screen.findByText(/Previous optics preview differs/);
    expect(container.querySelector('.nvp-camera-native-image img')).toBeNull();
  });

  it('requires a second desktop action for cancellation',async()=>{
    const bridge={
      request_camera_still:vi.fn(async()=>ticket()),
      poll_camera_still:vi.fn(async()=>({status:'QUEUED'})),
      cancel_camera_still:vi.fn(async()=>({status:'CANCELLED_QUEUED'})),
    };
    render(<FilmCameraSourcePanel projectId={pid} api={api} nativeBridge={bridge}/>);
    await screen.findByText(/50 mm · 39.6° horizontal FOV/);
    fireEvent.click(screen.getByText('Render accurate optics still'));
    const cancel=await screen.findByText('Cancel native still');
    fireEvent.click(cancel);
    await waitFor(()=>expect(bridge.cancel_camera_still)
      .toHaveBeenCalledWith('ticket_1'));
    expect(await screen.findByText(/Queued render cancelled/)).toBeTruthy();
  });

  it('refuses a desktop ticket for a different scene SHA',async()=>{
    const bridge={
      request_camera_still:vi.fn(async()=>({...ticket(),
          scene_document_sha256:'f'.repeat(64)})),
      poll_camera_still:vi.fn(),cancel_camera_still:vi.fn(),
    };
    render(<FilmCameraSourcePanel projectId={pid} api={api} nativeBridge={bridge}/>);
    await screen.findByText(/50 mm · 39.6° horizontal FOV/);
    fireEvent.click(screen.getByText('Render accurate optics still'));
    expect(await screen.findByText(/Desktop did not return an exact source-scoped render ticket/))
      .toBeTruthy();
    expect(bridge.poll_camera_still).not.toHaveBeenCalled();
  });
});
