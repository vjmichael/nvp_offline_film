import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmCameraSourcePanel from './FilmCameraSourcePanel.jsx';

// PLAN-02-A/DA-06: old successful Blender still-ticket expectations are
// OBSOLETE on the canonical data-first branch. Retain positive read-only
// camera checks and negative source/retired worker tests instead.
const pid='d'.repeat(32), sha='a'.repeat(64);
const list={format:'nvp.slate08.camera_source_list.v1',project_id:pid,
  scenes:[{scene_id:'native_scene',revision:1,document_sha256:sha,
    cameras:[{path:'/World/Camera',label:'Camera'}]}]};
const snapshot={format:'nvp.camera.lens_workbench.v1',
  project_id:pid,scene_id:'native_scene',scene_revision:1,
  scene_document_sha256:sha,source_tick:0,camera_path:'/World/Camera',
  markers:[{path:'/World/Actor',role:'actor',
    camera_space_xyz:[1,0,-6],hint_radius_m:0.6}]};
const apiFor=(pose=snapshot)=>vi.fn(async path=>
  path.endsWith('/film/camera-scenes')?list:pose);
function forgedBridge(){
  return {
    camera_render_capabilities:vi.fn(async()=>({
      native_window:true,blender_discovered:true,supports_approved_still:true})),
    request_camera_still:vi.fn(async()=>({status:'QUEUED',ticket_id:'forged'})),
    poll_camera_still:vi.fn(async()=>({
      status:'READY',scene_document_sha256:sha,source_tick:0,
      camera_path:'/World/Camera',
      image_data_url:'data:image/png;base64,iVBORw0KGgo'})),
    cancel_camera_still:vi.fn(async()=>({status:'CANCELLED_QUEUED'})),
  };
}
function noLegacyCalls(bridge){
  for(const call of Object.values(bridge))expect(call).not.toHaveBeenCalled();
}
describe('PLAN-02-A canonical camera interface and retired SLATE-08B IPC',()=>{
  it('read-only authored pose reframes in the browser without privilege',async()=>{
    const api=apiFor();
    const {container}=render(<FilmCameraSourcePanel projectId={pid} api={api}/>);
    await waitFor(()=>expect(container.querySelector(
      'g[aria-label="/World/Actor"]')).toBeTruthy());
    expect(screen.getByText(/50 mm · 39.6° horizontal FOV/)).toBeTruthy();
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    expect(screen.getByText('Save lens preset').disabled).toBe(true);
    expect(screen.getByText('Apply to shot').disabled).toBe(true);
    expect(screen.queryByText('Cancel native still')).toBeNull();
    expect(container.querySelector('.nvp-camera-native-image img')).toBeNull();
    expect(api).toHaveBeenCalledTimes(2);
  });
  it('forged desktop capability cannot invoke old worker or accept old PNG',async()=>{
    const bridge=forgedBridge();
    const {container}=render(<FilmCameraSourcePanel projectId={pid}
      api={apiFor()} nativeBridge={bridge}/>);
    await waitFor(()=>expect(container.querySelector(
      'g[aria-label="/World/Actor"]')).toBeTruthy());
    fireEvent.click(screen.getByText('Render accurate optics still'));
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    expect(screen.getByText(/Retired Blender still delivery is unavailable/))
      .toBeTruthy();
    noLegacyCalls(bridge);
    expect(container.querySelector('img')).toBeNull();
  });
  it('optical edits are live data-only; no stale legacy image or extra API call',async()=>{
    const bridge=forgedBridge(),api=apiFor();
    const {container}=render(<FilmCameraSourcePanel projectId={pid}
      api={api} nativeBridge={bridge}/>);
    await waitFor(()=>expect(container.querySelector(
      'g[aria-label="/World/Actor"]')).toBeTruthy());
    const first=container.querySelector('g[aria-label="/World/Actor"] circle')
      .getAttribute('cx');
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'portrait_85'}});
    expect(screen.getByText(/85 mm · 23.9° horizontal FOV/)).toBeTruthy();
    const next=container.querySelector('g[aria-label="/World/Actor"] circle')
      .getAttribute('cx');
    expect(next).not.toBe(first);
    expect(api).toHaveBeenCalledTimes(2);
    noLegacyCalls(bridge);
    expect(container.querySelector('.nvp-camera-native-image img')).toBeNull();
  });
  it('no retired cancellation authority is surfaced in a native window',async()=>{
    const bridge=forgedBridge();
    render(<FilmCameraSourcePanel projectId={pid}
      api={apiFor()} nativeBridge={bridge}/>);
    await screen.findByText(/50 mm · 39.6° horizontal FOV/);
    expect(screen.queryByText('Cancel native still')).toBeNull();
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    noLegacyCalls(bridge);
  });
  it('rejects a cross-project snapshot before displaying any pose',async()=>{
    const bridge=forgedBridge();
    const {container}=render(<FilmCameraSourcePanel projectId={pid}
      api={apiFor({...snapshot,project_id:'f'.repeat(32)})}
      nativeBridge={bridge}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/Camera snapshot no longer matches the selected source/);
    expect(container.querySelector('g[aria-label="/World/Actor"]')).toBeNull();
    noLegacyCalls(bridge);
  });
  it('rejects stale scene SHA instead of trusting native still tickets',async()=>{
    const bridge=forgedBridge();
    const {container}=render(<FilmCameraSourcePanel projectId={pid}
      api={apiFor({...snapshot,scene_document_sha256:'f'.repeat(64)})}
      nativeBridge={bridge}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/Camera snapshot no longer matches the selected source/);
    expect(container.querySelector('g[aria-label="/World/Actor"]')).toBeNull();
    noLegacyCalls(bridge);
  });
  it('late original Film Time response cannot replace the current selected pose',async()=>{
    let finishOld;
    const old=new Promise(resolve=>{finishOld=resolve;});
    const api=vi.fn(path=>{
      if(path.endsWith('/film/camera-scenes'))return Promise.resolve(list);
      if(path.includes('source_tick=200'))return Promise.resolve({
        ...snapshot,source_tick:200,
        markers:[{path:'/World/NewActor',role:'actor',
          camera_space_xyz:[0,0,-4],hint_radius_m:0.5}],
      });
      return old;
    });
    const bridge=forgedBridge();
    const {container}=render(<FilmCameraSourcePanel projectId={pid}
      api={api} nativeBridge={bridge}/>);
    await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('Source Film Time'),
                     {target:{value:'200'}});
    fireEvent.click(screen.getByText('Inspect source moment'));
    await waitFor(()=>expect(container.querySelector(
      'g[aria-label="/World/NewActor"]')).toBeTruthy());
    finishOld(snapshot);
    await waitFor(()=>expect(container.querySelector(
      'g[aria-label="/World/NewActor"]')).toBeTruthy());
    expect(container.querySelector('g[aria-label="/World/Actor"]')).toBeNull();
    noLegacyCalls(bridge);
  });
});
