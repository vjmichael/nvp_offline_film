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
      takes:[{take_id:'SceneTake',take_document_sha256:takeSHA,
        source_cameras:['/World/Camera']}],
    })),
    data_av_native_aces_policy:vi.fn(async()=>({
      format:'nvp.native_ocio.pinned_aces2_policy.v1',
      uses_ffmpeg:false,
      configuration_sha256:configSHA,
      configuration:'ocio://pinned-ACES2',
      output_view:'ACES 2.0 - SDR',
    })),
    data_av_export_native_aces_package:vi.fn(async()=>({
      format:'nvp.native_ocio.approved_source_png16_package.v1',
      status:'UNMASTERED_ACES2_PNG16_AUDIO_PACKAGE',
      take_sha256:takeSHA,color_grade_sha256:gradeSHA,
      color_pipeline:'ocio_aces2_scene_linear_png16_unmastered',
      pixel_bit_depth:16,ffmpeg_used:false,
      original_modified:false,master_approved:false,
      directory:'C:/Approved/ACESPresentation001',
      manifest_sha256:'f'.repeat(64),
    })),
    data_av_export_native_acescg_exr:vi.fn(async()=>({
      format:'nvp.native_ocio.approved_acescg_exr32_package.v1',
      status:'UNMASTERED_SOURCE_ACESCG_EXR32_PCM_PACKAGE',
      take_sha256:takeSHA,color_grade_sha256:gradeSHA,
      color_pipeline:'ocio_scene_linear_acescg_exr32_unmastered',
      picture_format:'exr',pixel_bit_depth:32,
      ffmpeg_used:false,original_modified:false,master_approved:false,
      directory:'C:/Approved/ACEScgScene001',
      manifest_sha256:'f'.repeat(64),
    })),
    data_av_cinema_readiness:vi.fn(async()=>({
      format:'nvp.native_data_first.cinema_preflight.v1',
      status:'NO_CINEMA_OR_HDR_MASTER_AUTHORIZED',
      target:'SMPTE_2K_FLAT_24',
      source_take_sha256:takeSHA,
      source_integrity_verified:true,
      authenticated_approved_source_derivative:true,
      authenticated_native_presentation_sha256:'e'.repeat(64),
      dcp_delivered:false,hdr10_master_approved:false,
      source_original_modified:false,ffmpeg_used:false,
      required_master_color_and_delivery_capabilities:[
        'native_SMPTE_2K_XYZ_12bit_JPEG2000_encoder',
        'theater_server_and_projector_ingest_acceptance',
      ],
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

  it('uses native OS picker for a separate RGB16 ACES2 and PCM output',async()=>{
    const {bridge,api,action}=environment();
    render(<NativeColorGradePanel
      project={{id:pid}} api={api} action={action} busy={false}/>);
    await screen.findByText('SceneTake');
    fireEvent.click(screen.getByText('Reopen prior color decision'));
    await screen.findByText(/Opened original color decision revision 1/);
    expect(screen.getByLabelText('Native ACES output source camera').value)
      .toBe('/World/Camera');
    fireEvent.click(screen.getByText(
      'Approve ACES2 16-bit picture and PCM package'));
    await waitFor(()=>expect(
      bridge.data_av_export_native_aces_package).toHaveBeenCalledWith({
        project_id:pid,take_id:'SceneTake',
        take_document_sha256:takeSHA,
        presentation_id:'ACESPresentation001',
        listener_path:'/World/Camera',
        fps_num:24,fps_den:1,
        aces_color_grade:{
          grade_id:'Color001',revision:1,
          document_sha256:gradeSHA,config_sha256:configSHA,
        },
      }));
    expect(await screen.findByText(/Saved a new immutable derived package/))
      .toBeTruthy();
    expect(screen.getByText(/not a cinema master/i)).toBeTruthy();
  });

  it('exports separately approved original ACEScg FLOAT32 EXR+PCM source',async()=>{
    const {bridge,api,action}=environment();
    render(<NativeColorGradePanel
      project={{id:pid}} api={api} action={action} busy={false}/>);
    await screen.findByText('SceneTake');
    fireEvent.click(screen.getByText('Reopen prior color decision'));
    await screen.findByText(/Opened original color decision revision 1/);
    fireEvent.click(screen.getByText(
      'Approve source-linear OpenEXR and PCM package'));
    await waitFor(()=>expect(
      bridge.data_av_export_native_acescg_exr).toHaveBeenCalledWith({
        project_id:pid,take_id:'SceneTake',
        take_document_sha256:takeSHA,
        presentation_id:'ACEScgScene001',
        listener_path:'/World/Camera',
        fps_num:24,fps_den:1,
        linear_exr_grade:{
          grade_id:'Color001',revision:1,
          document_sha256:gradeSHA,config_sha256:configSHA,
        },
      }));
    expect(await screen.findByText(/Verified new ACEScg EXR32 package/))
      .toBeTruthy();
  });

  it('never advertises source-only cinema readiness as an approved DCP',async()=>{
    const {bridge,api,action}=environment();
    render(<NativeColorGradePanel
      project={{id:pid}} api={api} action={action} busy={false}/>);
    await screen.findByText('SceneTake');
    fireEvent.click(screen.getByText('Inspect cinema/HDR readiness'));
    await waitFor(()=>expect(
      bridge.data_av_cinema_readiness).toHaveBeenCalledWith({
        project_id:pid,take_id:'SceneTake',
        take_document_sha256:takeSHA,
        target:'SMPTE_2K_FLAT_24',
      }));
    expect(await screen.findByText(
      /not an approved cinema or HDR master/)).toBeTruthy();
    expect(screen.getByText(/JPEG2000 encoder/)).toBeTruthy();
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
    fireEvent.change(screen.getByLabelText(/^Exposure \(stops\):/),
      {target:{value:'.75'}});
    expect(screen.getByText('Review verified ACES2 source color').disabled)
      .toBe(true);
  });
});
