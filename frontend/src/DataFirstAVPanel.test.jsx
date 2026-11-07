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

  it('selects two original emitters on one native stereo capture clock',async()=>{
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:[],
      })),
      data_av_live_catalog:vi.fn(async()=>({
        format:'nvp.data_av.live_camera_catalog.v1',status:'AVAILABLE',
        camera_timelines:[{
          scene_id:'world',scene_revision:1,
          camera_timeline_id:'real_camera',camera_timeline_revision:1,
          emitters:['/World/Actor','/World/SecondActor'],
        }],
        unapproved_capture_recovery:[{
          take_id:'Interrupted001',phase:'FAILED_UNAPPROVED',
        }],
      })),
      data_av_live_begin:vi.fn(async()=>({
        format:'nvp.data_av.live_mic_take.v1',
        status:'DENIED',output_is_original_source:true,
        flattened_soundtrack:false,
      })),
      data_av_audio_window:vi.fn(),data_av_stop:vi.fn(),
    };
    render(<DataFirstAVPanel projectId={pid} nativeBridge={bridge}/>);
    expect(await screen.findByText(/Interrupted001/)).toBeTruthy();
    const toggle=screen.getByLabelText(
      'Record two independent mono sources on one stereo input');
    fireEvent.click(toggle);
    expect(screen.getByLabelText('Second original source emitter').value)
      .toBe('/World/SecondActor');
    fireEvent.click(screen.getByText('Approve native microphone recording'));
    await waitFor(()=>expect(bridge.data_av_live_begin).toHaveBeenCalledWith(
      expect.objectContaining({
        project_id:pid,scene_id:'world',
        emitter_path:'/World/Actor',
        second_emitter_path:'/World/SecondActor',
        second_source_id:'LiveTake001.Mic2',
      })));
  });

  it('creator-approves sealed original mono recovery but never marks a new Take',async()=>{
    const record={
      format:'nvp.data_av.capture_recovery.v1',
      status:'RECOVERED_UNATTACHED_ORIGINAL_MONO',
      source_id:'RecoveredSound001',
      source_document_sha256:'c'.repeat(64),
      created_frozen_take:false,original_source_modified:false,
    };
    const catalog=vi.fn()
      .mockResolvedValueOnce({
        format:'nvp.data_av.live_camera_catalog.v1',
        status:'AVAILABLE',camera_timelines:[],
        unapproved_capture_recovery:[{
          capture_reference:'nvp-live-original-aabbccddeeff',
          take_id:'FailedTake',durable_sample_count:4000,
          phase:'DRAINED',recoverable_sealed_mono:true,
        }],
      })
      .mockResolvedValueOnce({
        format:'nvp.data_av.live_camera_catalog.v1',
        status:'AVAILABLE',camera_timelines:[],
        unapproved_capture_recovery:[],
      });
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:[],
      })),
      data_av_live_catalog:catalog,
      data_av_live_recover_original:vi.fn(async()=>record),
      data_av_audio_window:vi.fn(),data_av_stop:vi.fn(),
    };
    render(<DataFirstAVPanel projectId={pid} nativeBridge={bridge}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/FailedTake/);
    fireEvent.click(screen.getByText('Approve recovery of original sound only'));
    await waitFor(()=>expect(
      bridge.data_av_live_recover_original).toHaveBeenCalledWith({
        project_id:pid,
        capture_reference:'nvp-live-original-aabbccddeeff',
        new_source_id:'RecoveredSound001',
      }));
    expect(await screen.findByText(/No Take created/)).toBeTruthy();
    expect(screen.queryByText('FailedTake')).toBeNull();
  });

  it('picks two distinct native input endpoints with source-only ADC clock correction',async()=>{
    const bridge={
      data_av_catalog:vi.fn(async()=>({
        format:'nvp.data_av.native_session.v1',status:'AVAILABLE',
        ffmpeg_runtime_required:false,takes:[],
      })),
      data_av_live_catalog:vi.fn(async()=>({
        format:'nvp.data_av.live_camera_catalog.v1',status:'AVAILABLE',
        camera_timelines:[{
          scene_id:'world',scene_revision:1,
          camera_timeline_id:'LongCamera',camera_timeline_revision:1,
          emitters:['/World/Actor','/World/SecondActor'],
        }],
        independent_audio_inputs:[
          {device_id:4,name:'Native USB Input A',host_api:'WASAPI',max_input_channels:1},
          {device_id:7,name:'Native USB Input B',host_api:'WASAPI',max_input_channels:1},
        ],
        unapproved_capture_recovery:[],
      })),
      data_av_live_begin:vi.fn(async()=>({
        format:'nvp.data_av.live_mic_take.v1',status:'DENIED',
        output_is_original_source:true,flattened_soundtrack:false,
      })),
    };
    render(<DataFirstAVPanel projectId={pid} nativeBridge={bridge}/>);
    const toggle=await screen.findByLabelText(
      'Record two original mono sources from independent audio devices');
    fireEvent.click(toggle);
    expect(screen.getByLabelText('First independent audio capture device').value)
      .toBe('4');
    expect(screen.getByLabelText('Second independent audio capture device').value)
      .toBe('7');
    fireEvent.click(screen.getByText('Approve native microphone recording'));
    await waitFor(()=>expect(bridge.data_av_live_begin).toHaveBeenCalledWith(
      expect.objectContaining({
        independent_device_ids:[4,7],
        emitter_path:'/World/Actor',
        second_emitter_path:'/World/SecondActor',
      })));
    expect(screen.getByText(/not genlock/)).toBeTruthy();
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
