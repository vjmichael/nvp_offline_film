import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmCameraSourcePanel from './FilmCameraSourcePanel.jsx';

const pid='a'.repeat(32);
const source={
  scene_id:'studio_set',revision:1,document_sha256:'b'.repeat(64),
  cameras:[{path:'/World/Camera',label:'Camera'}],
};
const snapshot={
  format:'nvp.camera.lens_workbench.v1',
  project_id:pid,scene_id:'studio_set',scene_revision:1,
  scene_document_sha256:'b'.repeat(64),source_tick:0,
  camera_path:'/World/Camera',
  markers:[{path:'/World/Actor',role:'actor',
            camera_space_xyz:[1,0,-8],hint_radius_m:0.6}],
  frozen_take_created:false,
};
const list={format:'nvp.slate08.camera_source_list.v1',project_id:pid,
  scenes:[source],usd_loaded:false,worker_started:false};

describe('SLATE-08 main UI read-only real scene camera',()=>{
  it('loads one source pose then performs lens reframing without network or Take write',async()=>{
    const api=vi.fn(async path=>path.endsWith('/film/camera-scenes')
      ?list:snapshot);
    const {container}=render(<FilmCameraSourcePanel
      projectId={pid} api={api}/>);
    expect(await screen.findByText(/50 mm · 39.6° horizontal FOV/)).toBeTruthy();
    await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'wide_24'}});
    expect(screen.getByText(/24 mm · 73.7° horizontal FOV/)).toBeTruthy();
    expect(api).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    expect(screen.getByText('Save lens preset').disabled).toBe(true);
    expect(screen.getByText('Apply to shot').disabled).toBe(true);
    expect(container.querySelector('img')).toBeNull();
  });

  it('does not invent native cameras when no source has been authored',async()=>{
    const api=vi.fn(async()=>({...list,scenes:[]}));
    render(<FilmCameraSourcePanel projectId={pid} api={api}/>);
    expect(await screen.findByText(/No native OpenUSD camera source/)).toBeTruthy();
    expect(screen.queryByLabelText('Virtual Camera Workbench')).toBeNull();
  });

  it('rejects a stale source SHA before ever publishing a lens snapshot',async()=>{
    const api=vi.fn(async path=>path.endsWith('/film/camera-scenes')
      ?list:{...snapshot,scene_document_sha256:'f'.repeat(64)});
    render(<FilmCameraSourcePanel projectId={pid} api={api}/>);
    expect((await screen.findByRole('alert')).textContent).toMatch(/no longer matches/);
  });
});
