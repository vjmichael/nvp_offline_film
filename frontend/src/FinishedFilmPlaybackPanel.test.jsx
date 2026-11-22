// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,cleanup,fireEvent,waitFor} from '@testing-library/react';
import FinishedFilmPlaybackPanel,{
  checkFinishedFrame,checkFinishedWindow,
  requireAheadOfAudioClock,requireContinuousPicture
} from './FinishedFilmPlaybackPanel.jsx';

const FORMAT='nvp.wo5.finished_dcp_pcm24_picture_review.v1';
const pid='a'.repeat(32),fid='OriginalFilmFeature01';
const packet=n=>({
  format:FORMAT,status:'DECODED_PUBLISHED_FINAL_FRAME',
  frame_index:n,picture_24fps_film_time_tick:n*294000000,
  audio_start_sample:n*2000,audio_samples:2000,
  picture_and_sound_from_final_published_mxf:true,
  picture_width:128,picture_height:72,
  picture_png_base64:'AQID',
  stereo_pcm16_base64:'AQID',
  production_accepted:false,
});
afterEach(()=>{cleanup();delete window.pywebview;vi.restoreAllMocks();});

describe('WO5 finished published picture/mastered sound playback',()=>{
  it('never schedules already-expired audio or counts hidden skipped frames as watched',()=>{
    expect(requireAheadOfAudioClock(10.2,10.05)).toBe(10.2);
    expect(()=>requireAheadOfAudioClock(10.2,10.21))
      .toThrow(/missed its exact presentation deadline/);
    expect(()=>requireAheadOfAudioClock(10.2,10.198))
      .toThrow(/missed its exact presentation deadline/);
    expect(requireContinuousPicture(23,24)).toBe(24);
    expect(()=>requireContinuousPicture(24,23)).toThrow(/skipped a required presentation frame/);
    expect(()=>requireContinuousPicture(23,25))
      .toThrow(/skipped a required presentation frame/);
  });
  it('accepts only ordered bounded final-MXF batches within the same reel',()=>{
    const first={...packet(2),reel_index:0};
    const second={...packet(3),reel_index:0};
    const batch={format:FORMAT,status:'DECODED_PUBLISHED_FINAL_WINDOW',
      start_frame:2,frame_count:2,reel_index:0,
      frames:[first,second],no_reel_crossing:true,production_accepted:false};
    expect(checkFinishedWindow(batch,2).map(x=>x.frame_index)).toEqual([2,3]);
    expect(()=>checkFinishedWindow({...batch,frames:[second,first]},2))
      .toThrow(/receipt rejected/);
    expect(()=>checkFinishedWindow({...batch,
      frames:[first,{...second,reel_index:1}]},2))
      .toThrow(/unapproved reel/);
    expect(()=>checkFinishedWindow({...batch,frame_count:5},2))
      .toThrow(/omitted a complete/);
    expect(()=>checkFinishedWindow({...batch,production_accepted:true},2))
      .toThrow(/omitted a complete/);
  });

  it('rejects stale audio indices, missing picture, forged production approval',()=>{
    expect(checkFinishedFrame(packet(12),12).frame_index).toBe(12);
    for(const forged of [
      {...packet(12),frame_index:11},
      {...packet(12),picture_24fps_film_time_tick:11*294000000},
      {...packet(12),audio_start_sample:11*2000},
      {...packet(12),audio_samples:1999},
      {...packet(12),picture_and_sound_from_final_published_mxf:false},
      {...packet(12),picture_width:4096},
      {...packet(12),picture_png_base64:'<script>'},
      {...packet(12),production_accepted:true}
    ])expect(()=>checkFinishedFrame(forged,12)).toThrow(/receipt rejected/);
  });

  it('never uses a browser fallback or a source-Take audition as finished film',()=>{
    render(<FinishedFilmPlaybackPanel projectId={pid} featureId={fid}/>);
    expect(screen.getByRole('button',{
      name:'Play Finished Film'}).disabled)
      .toBe(true);
    expect(screen.getByText(/Finished-film viewing is not yet available/))
      .toBeTruthy();
  });

  it('explains missing installed codec bundle and leaves real play disabled',async()=>{
    const native={
      wo5_film_capabilities:vi.fn(async()=>({
        format:FORMAT,native_finished_mxf_decode_configured:false})),
      wo5_film_begin:vi.fn(),wo5_film_frame:vi.fn(),
      wo5_film_stop:vi.fn()
    };
    render(<FinishedFilmPlaybackPanel projectId={pid}
      featureId={fid} nativeBridge={native}/>);
    await waitFor(()=>expect(native.wo5_film_capabilities).toHaveBeenCalled());
    expect(screen.getByRole('button',{
      name:'Play Finished Film'}).disabled)
      .toBe(true);
    expect(native.wo5_film_begin).not.toHaveBeenCalled();
  });

  it('stopping during native consent fences a late approved session',async()=>{
    let resolveBegin;
    const native={
      wo5_film_capabilities:vi.fn(async()=>({format:FORMAT,native_finished_mxf_decode_configured:true})),
      wo5_film_begin:vi.fn(()=>new Promise(resolve=>{resolveBegin=resolve;})),
      wo5_film_frame:vi.fn(),wo5_film_window:vi.fn(),wo5_film_stop:vi.fn(async()=>({status:'STOPPED'}))
    };
    const old=window.AudioContext;
    window.AudioContext=class {state='running';resume(){return Promise.resolve();}close(){return Promise.resolve();}};
    try{
      render(<FinishedFilmPlaybackPanel projectId={pid} featureId={fid} nativeBridge={native}/>);
      const play=screen.getByRole('button',{name:'Play Finished Film'});
      await waitFor(()=>expect(play.disabled).toBe(false));
      fireEvent.click(play);
      await waitFor(()=>expect(native.wo5_film_begin).toHaveBeenCalledTimes(1));
      expect(play.disabled).toBe(true);
      fireEvent.click(screen.getByRole('button',{name:'Stop'}));
      resolveBegin({session_id:'late-ticket',status:'FINISHED_DCP_READONLY_READY'});
      await waitFor(()=>expect(native.wo5_film_stop).toHaveBeenCalledWith('late-ticket'));
      expect(native.wo5_film_frame).not.toHaveBeenCalled();
      expect(native.wo5_film_window).not.toHaveBeenCalled();
    }finally{window.AudioContext=old;}
  });

  it('stopping while the audio device activates revokes the admitted session',async()=>{
    let activate;
    const native={
      wo5_film_capabilities:vi.fn(async()=>({format:FORMAT,native_finished_mxf_decode_configured:true})),
      wo5_film_begin:vi.fn(async()=>({format:FORMAT,status:'FINISHED_DCP_READONLY_READY',session_id:'admitted-ticket',
        native_picture_and_sound_from_published_mxf:true,production_accepted:false,
        fps:24,sound_rate:48000,sound_samples_per_frame:2000,frame_count:24})),
      wo5_film_frame:vi.fn(),wo5_film_window:vi.fn(),wo5_film_stop:vi.fn(async()=>({status:'STOPPED'}))
    };
    const analyser=vi.fn();
    const old=window.AudioContext;
    window.AudioContext=class {state='running';resume(){return new Promise(resolve=>{activate=resolve;});}close(){return Promise.resolve();}createAnalyser(){return analyser();}};
    try{
      render(<FinishedFilmPlaybackPanel projectId={pid} featureId={fid} nativeBridge={native}/>);
      const play=screen.getByRole('button',{name:'Play Finished Film'});
      await waitFor(()=>expect(play.disabled).toBe(false));
      fireEvent.click(play);
      await waitFor(()=>expect(native.wo5_film_begin).toHaveBeenCalledTimes(1));
      fireEvent.click(screen.getByRole('button',{name:'Stop'}));
      activate();
      await waitFor(()=>expect(native.wo5_film_stop).toHaveBeenCalledWith('admitted-ticket'));
      expect(analyser).not.toHaveBeenCalled();
      expect(native.wo5_film_window).not.toHaveBeenCalled();
    }finally{window.AudioContext=old;}
  });

  it('native OS denied playback is not a fake film presentation',async()=>{
    const native={
      wo5_film_capabilities:vi.fn(async()=>({
        format:FORMAT,native_finished_mxf_decode_configured:true})),
      wo5_film_begin:vi.fn(async()=>({
        format:FORMAT,status:'DENIED'})),
      wo5_film_frame:vi.fn(),wo5_film_stop:vi.fn()
    };
    const audio=window.AudioContext;
    window.AudioContext=class {
      state='running';
      resume(){return Promise.resolve();}
      close(){return Promise.resolve();}
    };
    try{
      render(<FinishedFilmPlaybackPanel projectId={pid}
        featureId={fid} nativeBridge={native}/>);
      await waitFor(()=>expect(screen.getByRole('button',{
        name:'Play Finished Film'}).disabled)
        .toBe(false));
      fireEvent.click(screen.getByRole('button',{
        name:'Play Finished Film'}));
      await waitFor(()=>expect(native.wo5_film_begin)
        .toHaveBeenCalledWith(pid,fid));
      await waitFor(()=>expect(screen.getByText(/Permission declined/)).toBeTruthy());
      expect(native.wo5_film_frame).not.toHaveBeenCalled();
    }finally{window.AudioContext=audio;}
  });
});
