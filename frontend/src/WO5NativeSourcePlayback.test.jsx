// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react';
import DataFirstAVPanel from './DataFirstAVPanel.jsx';

const project='a'.repeat(32);
const shaA='b'.repeat(64),shaB='c'.repeat(64);
const sources=[
 {take_id:'OtherFrozenTake',take_document_sha256:shaA,
  duration_tick:'70560000000',listeners:['/World/Camera']},
 {take_id:'ApprovedWO5SourceTake',take_document_sha256:shaB,
  duration_tick:'70560000000',listeners:['/World/Camera']}
];
afterEach(()=>{cleanup();delete window.pywebview;vi.restoreAllMocks();});

describe('WO5 selected original source native A/V viewer',()=>{
  it('really targets the exact approved Take ID and 48-kHz source sample',async()=>{
    const native={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:sources
      })),
      data_av_begin:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'DENIED',
        original_modified:false,master_approved:false
      })),
      data_av_audio_window:vi.fn(),data_av_scene_at:vi.fn(),
      data_av_stop:vi.fn()
    };
    const before=window.AudioContext;
    window.AudioContext=class {constructor(){this.sampleRate=48000;}};
    try{
      render(<DataFirstAVPanel projectId={project}
        nativeBridge={native} initialTakeId="ApprovedWO5SourceTake"
        initialSourceSample={2000}/>);
      await waitFor(()=>expect(screen.getByLabelText(
        'Native frozen Digital Take').value).toBe('ApprovedWO5SourceTake'));
      expect(screen.getByLabelText('Native source sample seek').value).toBe('2000');
      fireEvent.click(screen.getByText('Approve and audition 3D source sound'));
      await waitFor(()=>expect(native.data_av_begin).toHaveBeenCalledWith({
        project_id:project,take_id:'ApprovedWO5SourceTake',
        take_document_sha256:shaB,listener_path:'/World/Camera',
        first_sample:2000,direction:'forward'
      }));
      expect(native.data_av_audio_window).not.toHaveBeenCalled();
    }finally{
      window.AudioContext=before;
    }
  });

  it('never fabricates a missing approved Take when native catalog differs',async()=>{
    const native={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:[sources[0]]
      })),
      data_av_begin:vi.fn(),data_av_audio_window:vi.fn(),
      data_av_scene_at:vi.fn(),data_av_stop:vi.fn()
    };
    render(<DataFirstAVPanel projectId={project}
      nativeBridge={native} initialTakeId="ApprovedWO5SourceTake"
      initialSourceSample={2000}/>);
    await waitFor(()=>expect(screen.getByLabelText(
      'Native frozen Digital Take').value).toBe(''));
    expect(screen.getByText(/exact approved original Take is missing/)).toBeTruthy();
    expect(native.data_av_begin).not.toHaveBeenCalled();
  });
});
