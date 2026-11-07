import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup}
  from '@testing-library/react';

vi.mock('./NativeTextureGPUReference.js',()=>({
  runGPUTextureReference:vi.fn(),
  runGPUSourceTextureReference:vi.fn(async(packet)=>({
    format:'nvp.wo2.native_source_cpu_gpu_texture_comparison.v1',
    source_texture_sha256:packet.sha256,
    source_preview_sha256:packet.preview_sha256,
    passed:true,actual_gpu_readback:true,max_channel_error:0,
    physical_display_calibrated:false,
    full_usd_material_parity_proven:false,
  })),
}));
import DataFirstAVPanel from './DataFirstAVPanel.jsx';

afterEach(cleanup);
const project='a'.repeat(32);
const sha='b'.repeat(64);
const preview='c'.repeat(64);

describe('WO2 installed-only GPU source acceptance',()=>{
  it('exposes the probe only from authenticated native desktop IPC',async()=>{
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',
        ffmpeg_runtime_required:false,status:'AVAILABLE',takes:[],
      })),
      wo2_gpu_texture_probe:vi.fn(async()=>({
        format:'nvp.wo2.installed_texture_probe.v1',
        status:'READY',source_modified:false,
        texture:{format:'nvp.original.usd_texture_png.v1',
          sha256:sha,preview_sha256:preview},
      })),
    };
    render(<DataFirstAVPanel projectId={project} nativeBridge={bridge}/>);
    const button=screen.getByText('Run installed original PNG GPU comparison');
    fireEvent.click(button);
    expect(await screen.findByText(/WO2 installed source GPU texel comparison PASSED/))
      .toBeTruthy();
    expect(bridge.wo2_gpu_texture_probe).toHaveBeenCalledTimes(1);
  });

  it('never fabricates installed GPU acceptance in an ordinary browser',()=>{
    render(<DataFirstAVPanel projectId={project}/>);
    expect(screen.queryByText(
      'Run installed original PNG GPU comparison')).toBeNull();
  });
});
