import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import DataFirstAVPanel from './DataFirstAVPanel.jsx';

const pid='a'.repeat(32);
const sha='b'.repeat(64);
const take={take_id:'captured_take',take_document_sha256:sha,
  duration_tick:'70560000000',
  listeners:['/World/Camera','/World/Actor']};

afterEach(()=>{cleanup();delete window.pywebview;});

describe('DATA-AV-01 trusted desktop-native sound preview',()=>{
  it('does not invent a native sound decoder or silently require FFmpeg in ordinary browsers',()=>{
    render(<DataFirstAVPanel projectId={pid}/>);
    expect(screen.getByText(/installed NVP to use/)).toBeTruthy();
    expect(screen.getByText('Approve and audition 3D source sound').disabled)
      .toBe(true);
    expect(screen.queryByText('Start progressive long-form review…')).toBeNull();
  });

  it('lists exact frozen takes/listeners and keeps approval in the native OS',async()=>{
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:[take],
      })),
      data_av_begin:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'DENIED',
        original_modified:false,master_approved:false,
      })),
      data_av_audio_window:vi.fn(),data_av_scene_at:vi.fn(),
      data_av_stop:vi.fn(),
    };
    const original=window.AudioContext;
    window.AudioContext=class { constructor(){this.sampleRate=48000;} };
    try{
      render(<DataFirstAVPanel projectId={pid} nativeBridge={bridge}/>);
      expect(await screen.findByText('captured_take')).toBeTruthy();
      expect(screen.getByLabelText('Native spatial listener').value)
        .toBe('/World/Camera');
      fireEvent.click(screen.getByText('Approve and audition 3D source sound'));
      await waitFor(()=>expect(bridge.data_av_begin).toHaveBeenCalledWith({
        project_id:pid,take_id:'captured_take',
        take_document_sha256:sha,
        listener_path:'/World/Camera',first_sample:0,
        direction:'forward',
      }));
      expect(bridge.data_av_audio_window).not.toHaveBeenCalled();
      expect(await screen.findByText('Native audition was not approved.'))
        .toBeTruthy();
    }finally{window.AudioContext=original;}
  });

  it('fails closed when native catalog demands an FFmpeg runtime',async()=>{
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:true,takes:[take],
      })),
    };
    render(<DataFirstAVPanel projectId={pid} nativeBridge={bridge}/>);
    expect((await screen.findByRole('alert')).textContent).toMatch(
      /not verified/);
    expect(screen.getByText('Approve and audition 3D source sound').disabled)
      .toBe(true);
  });
});
