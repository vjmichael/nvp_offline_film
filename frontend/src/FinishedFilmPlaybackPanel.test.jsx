// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,cleanup,fireEvent,waitFor} from '@testing-library/react';
import FinishedFilmPlaybackPanel,{
  checkFinishedFrame,requireAheadOfAudioClock,requireContinuousPicture
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
    expect(()=>requireContinuousPicture(23,25))
      .toThrow(/skipped a required presentation frame/);
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
      name:'Request native permission and play finished DCP'}).disabled)
      .toBe(true);
    expect(screen.getByText(/Verified installed CineCert\/OpenJPEG decoder bundle/))
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
      name:'Request native permission and play finished DCP'}).disabled)
      .toBe(true);
    expect(native.wo5_film_begin).not.toHaveBeenCalled();
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
    window.AudioContext=class {};
    try{
      render(<FinishedFilmPlaybackPanel projectId={pid}
        featureId={fid} nativeBridge={native}/>);
      await waitFor(()=>expect(screen.getByRole('button',{
        name:'Request native permission and play finished DCP'}).disabled)
        .toBe(false));
      fireEvent.click(screen.getByRole('button',{
        name:'Request native permission and play finished DCP'}));
      await waitFor(()=>expect(native.wo5_film_begin)
        .toHaveBeenCalledWith(pid,fid));
      expect(screen.getByText(/State: DENIED/)).toBeTruthy();
      expect(native.wo5_film_frame).not.toHaveBeenCalled();
    }finally{window.AudioContext=audio;}
  });
});
