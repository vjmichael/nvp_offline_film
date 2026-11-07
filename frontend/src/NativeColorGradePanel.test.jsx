import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import NativeColorGradePanel from './NativeColorGradePanel.jsx';

const pid='a'.repeat(32);
const takeSHA='b'.repeat(64);
const gradeSHA='c'.repeat(64);
const configSHA='d'.repeat(64);
const initial={
  exposure_stops:0,contrast:1,saturation:1,
  temperature_kelvin:6500,tint_magenta_green:0,
};
const grade={
  format:'nvp.data_first.color_decision.v1',revision:1,
  take_sha256:takeSHA,document_sha256:gradeSHA,
  parameters:initial,source_modified:false,
  rendered_frames:false,flat_master_approved:false,
  ffmpeg_used:false,
};

afterEach(()=>{cleanup();delete window.pywebview;});

function environment(){
  const bridge={
    data_av_catalog:vi.fn(async()=>({
      format:'nvp.data_av.native_session.v1',
      ffmpeg_runtime_required:false,status:'AVAILABLE',
      takes:[{take_id:'SceneTake',take_document_sha256:takeSHA}],
    })),
    data_av_native_aces_policy:vi.fn(async()=>({
      format:'nvp.native_ocio.pinned_aces2_policy.v1',
      uses_ffmpeg:false,
      configuration_sha256:configSHA,
      configuration:'ocio://pinned-ACES2',
      output_view:'ACES 2.0 - SDR',
    })),
    data_av_native_aces_review:vi.fn(async()=>({
      format:'nvp.native_ocio.source_pinned_aces2_review.v1',
      status:'VERIFIED_SOURCE_UNMASTERED_ACES2_SDR_DERIVATIVE',
      take_sha256:takeSHA,grade_sha256:gradeSHA,
      film_time_tick:'7056000000',original_camera_path:'/World/Camera',
      output_mime:'image/png',
      png16_base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9rI0Wl0AAAAASUVORK5CYII=',
      width:640,height:360,bit_depth:16,
      png16_sha256:'e'.repeat(64),clipped_channels:0,
      original_modified:false,ffmpeg_used:false,
      cinema_master_approved:false,
      scene_linear_source:{source_modified:false,actual_usd_skinned_actors:1},
      processor:{configuration_sha256:configSHA},
    })),
  };
  const api=vi.fn(async()=>grade);
  const action=vi.fn(fn=>fn());
  window.pywebview={api:bridge};
  return {bridge,api,action};
}

describe('DA-06D creator-approved OpenUSD source color in ACES2',()=>{
  it('reopens immutable grade and evaluates source camera/time under native consent',async()=>{
    const {bridge,api,action}=environment();
    render(<NativeColorGradePanel
      project={{id:pid}} api={api} action={action} busy={false}/>);
    expect(await screen.findByText('SceneTake')).toBeTruthy();
    fireEvent.click(screen.getByText('Reopen prior color decision'));
    expect(await screen.findByText(/Opened original color decision revision 1/))
      .toBeTruthy();
    fireEvent.change(screen.getByLabelText('ACES original Film Time tick'),
      {target:{value:'7056000000'}});
    fireEvent.click(screen.getByText('Review verified ACES2 source color'));
    await waitFor(()=>expect(bridge.data_av_native_aces_review)
      .toHaveBeenCalledWith({
        project_id:pid,take_id:'SceneTake',take_sha256:takeSHA,
        grade_id:'Color001',grade_revision:1,grade_sha256:gradeSHA,
        film_time_tick:7056000000,expected_config_sha256:configSHA,
      }));
    expect((await screen.findByAltText(
      'Derived source-verified OpenUSD scene in ACES2 SDR review'
    )).getAttribute('src')).toMatch(/^data:image\/png;base64,/);
    expect(screen.getByText(/not an approved professional color master/i))
      .toBeTruthy();
  });

  it('does not preview unsaved creative changes or imaginary Film Time',async()=>{
    const {bridge,api,action}=environment();
    render(<NativeColorGradePanel
      project={{id:pid}} api={api} action={action} busy={false}/>);
    await screen.findByText('SceneTake');
    fireEvent.click(screen.getByText('Reopen prior color decision'));
    await screen.findByText(/Opened original color decision revision 1/);
    fireEvent.change(screen.getByLabelText('ACES original Film Time tick'),
      {target:{value:'-1'}});
    fireEvent.click(screen.getByText('Review verified ACES2 source color'));
    expect(await screen.findByText(/exact non-negative Film Time tick/))
      .toBeTruthy();
    expect(bridge.data_av_native_aces_review).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Exposure (stops)'),
      {target:{value:'.75'}});
    expect(screen.getByText('Review verified ACES2 source color').disabled)
      .toBe(true);
  });
});
