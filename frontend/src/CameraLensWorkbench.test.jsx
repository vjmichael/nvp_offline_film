import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import CameraLensWorkbench from './CameraLensWorkbench';

const snapshot={
  format:'nvp.camera.lens_workbench.v1',
  project_id:'e'.repeat(32),scene_id:'scene_original',scene_revision:1,
  scene_document_sha256:'a'.repeat(64),source_tick:12345,
  camera_path:'/World/Camera',
  markers:[
    {path:'/World/Actor',role:'actor',camera_space_xyz:[1,0,-5],
     hint_radius_m:0.6},
    {path:'/World/Prop',role:'prop',camera_space_xyz:[-1,1,-8],
     hint_radius_m:0.4},
  ],
  frozen_take_created:false,
};

describe('CAM-01 pre-Take interactive spherical lens study',()=>{
  it('updates the focal framing immediately without saving or rendering a Take',()=>{
    const renderStill=vi.fn(),save=vi.fn(),apply=vi.fn();
    const {container}=render(<CameraLensWorkbench
      sceneSnapshot={snapshot}
      onRequestRenderedPreview={renderStill}
      onSavePreset={save}
      onApplyToShot={apply}/>);
    expect(screen.getByText(/50 mm · 39.6° horizontal FOV/)).toBeTruthy();
    const actor=container.querySelector('g[aria-label="/World/Actor"] circle');
    const firstX=Number(actor.getAttribute('cx'));
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'wide_24'}});
    expect(screen.getByText(/24 mm · 73.7° horizontal FOV/)).toBeTruthy();
    const wideX=Number(container.querySelector(
      'g[aria-label="/World/Actor"] circle').getAttribute('cx'));
    expect(Math.abs(wideX-500)).toBeLessThan(Math.abs(firstX-500));
    expect(renderStill).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
    expect(container.querySelector('[data-preview-mode="live-projection"]')).toBeTruthy();
  });

  it('focus and f-stop change quick optical hints independently of source scene',()=>{
    const {container}=render(<CameraLensWorkbench sceneSnapshot={snapshot}/>);
    const circle=()=>container.querySelector(
      'g[aria-label="/World/Actor"] circle');
    const before=circle().getAttribute('style');
    fireEvent.change(screen.getByLabelText('Aperture'),
                     {target:{value:'1.4'}});
    fireEvent.change(screen.getByLabelText('Focus distance'),
                     {target:{value:'20'}});
    const after=circle().getAttribute('style');
    expect(after).not.toEqual(before);
    expect(screen.getByText(/Aperture · f\/1.4/)).toBeTruthy();
    expect(screen.getByText(/Focus · 20.0 m/)).toBeTruthy();
  });

  it('requests exact-scene optical render without auto-freezing and supports director decisions',()=>{
    const renderStill=vi.fn(),save=vi.fn(),apply=vi.fn();
    render(<CameraLensWorkbench sceneSnapshot={snapshot}
      onRequestRenderedPreview={renderStill}
      onSavePreset={save} onApplyToShot={apply}/>);
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'portrait_85'}});
    fireEvent.change(screen.getByLabelText('Sensor / filmback'),
                     {target:{value:'super_35'}});
    fireEvent.click(screen.getByText('Render accurate optics still'));
    const payload=renderStill.mock.calls[0][0];
    expect(payload.source_scene_id).toBe('scene_original');
    expect(payload.source_scene_revision).toBe(1);
    expect(payload.source_scene_document_sha256).toBe('a'.repeat(64));
    expect(payload.source_tick).toBe(12345);
    expect(payload.camera_path).toBe('/World/Camera');
    expect(payload.lens_settings.focal_length_mm).toBe(85);
    expect(payload.lens_settings.sensor_width_mm).toBe(24.89);
    expect(payload.lens_settings.lens_effect_stack).toEqual([]);
    expect(payload.frozen_take_created).toBe(false);
    expect(payload.source_modified).toBe(false);
    expect(save).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Save lens preset'));
    expect(save).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByText('Apply to shot'));
    expect(apply).toHaveBeenCalledOnce();
  });

  it('prevents native rendering when source camera snapshot has not been provided',()=>{
    const renderStill=vi.fn();
    render(<CameraLensWorkbench onRequestRenderedPreview={renderStill}/>);
    expect(screen.getByText(/Choose an authored camera/)).toBeTruthy();
    expect(screen.getByText('Render accurate optics still').disabled).toBe(true);
    expect(screen.getByText('Save lens preset').disabled).toBe(true);
    expect(screen.getByText('Apply to shot').disabled).toBe(true);
  });

  it('only displays native optics PNG matching source SHA and current lens settings',()=>{
    const full={
      format:'nvp.camera.lens_workbench.v1',
      preset:'standard_50',sensor:'full_frame',
      focal_length_mm:50,sensor_width_mm:36,sensor_height_mm:20.25,
      f_stop:2.8,focus_distance_m:5,
    };
    const result={
      status:'READY',source_tick:12345,camera_path:'/World/Camera',
      scene_document_sha256:'a'.repeat(64),lens_settings:full,
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
    };
    const {container}=render(<CameraLensWorkbench
      sceneSnapshot={snapshot} renderResult={result}/>);
    expect(screen.getByAltText(/Native rendered camera\/lens study/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Lens preset'),
                     {target:{value:'portrait_85'}});
    expect(container.querySelector('.nvp-camera-native-image img')).toBeNull();
    expect(screen.getByText(/Previous optics preview differs/)).toBeTruthy();
  });

  it('does not treat an authorized queue as a completed camera preview',()=>{
    const {container}=render(<CameraLensWorkbench
      sceneSnapshot={snapshot} renderResult={{status:'QUEUED'}}/>);
    expect(screen.getByText(/Higher-quality optics preview queued/)).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/instant diagram is an approximation/)).toBeTruthy();
  });
});
