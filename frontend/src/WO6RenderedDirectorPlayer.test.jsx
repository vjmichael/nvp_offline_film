// @vitest-environment jsdom
import React from 'react';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import WO6RenderedDirectorPlayer from './WO6RenderedDirectorPlayer.jsx';

const pid='a'.repeat(32);
const sha='b'.repeat(64);
const CAT='nvp.wo6_07e.original_source_review_catalog.v1';
const KIND='nvp.wo6_07f.actual_rendered_frame_pcm_window.v1';
const edit={edit_id:'real_source_cut',edit_revision:1,edit_sha256:sha,
            duration_tick:String(294000000*24),segment_count:2};
const catalog={format:CAT,project_id:pid,native_worker_authorized:false,
               edits:[edit],timelines:[]};
let rafHandlers=[],audioInstances=[],audioStarts=[];
let priorImage,priorAudio,priorRAF,priorCancel,priorAtob;

function packet(request){
  return {
    format:KIND,project_id:pid,edit_sha256:sha,
    first_frame_zero:request.first_frame,count:request.count,
    source_audio_rate:48000,
    actual_audio_sample_count:request.count*2000,
    real_original_usd_pixels_rendered:true,
    native_worker_authorized:false,source_modified:false,
    film_delivered:false,
    source_audio_wav_data_url:'data:audio/wav;base64,AAAA',
    images:Array.from({length:request.count},(_,i)=>({
      output_frame_zero:request.first_frame+i,
      output_film_time_tick:String((request.first_frame+i)*294000000),
      source_take_id:'original_frozen_take',
      source_segment_id:request.first_frame+i>=12?'cut_b':'cut_a',
      actual_rasterized_triangles:12,
      frame_png_sha256:'c'.repeat(64),
      frame_image_data_url:'data:image/png;base64,AAAB',
    })),
  };
}
function makeHost(){
  return {wo6_07e_source_review_catalog:vi.fn(async()=>catalog),
    wo6_07f_rendered_av_window:vi.fn(async req=>packet(req))};
}
function advance(time){
  const audio=audioInstances.at(-1);
  audio.currentTime=time;
  const handlers=rafHandlers.splice(0);
  for(const fn of handlers)fn();
}
beforeEach(()=>{
  rafHandlers=[];audioInstances=[];audioStarts=[];
  priorImage=globalThis.Image;
  priorAudio=window.AudioContext;
  priorRAF=globalThis.requestAnimationFrame;
  priorCancel=globalThis.cancelAnimationFrame;
  priorAtob=globalThis.atob;
  class Img {
    set src(v){this._src=v}
    async decode(){return true}
  }
  globalThis.Image=Img;
  globalThis.requestAnimationFrame=(fn)=>{rafHandlers.push(fn);return rafHandlers.length};
  globalThis.cancelAnimationFrame=()=>{};
  globalThis.atob=()=>String.fromCharCode(0,0,0,0);
  window.AudioContext=class {
    constructor(){this.currentTime=0;this.destination={};audioInstances.push(this)}
    async resume(){}
    async close(){}
    async decodeAudioData(){return {numberOfChannels:1,duration:6/24}}
    createBufferSource(){
      return {buffer:null,connect:()=>{},disconnect:()=>{},
        start:(t)=>audioStarts.push(t),stop:()=>{}};
    }
  };
});
afterEach(()=>{
  cleanup();delete window.pywebview;
  globalThis.Image=priorImage;window.AudioContext=priorAudio;
  globalThis.requestAnimationFrame=priorRAF;globalThis.cancelAnimationFrame=priorCancel;
  globalThis.atob=priorAtob;
  vi.restoreAllMocks();
});

describe('WO6-07F actual pixel + source audio-clock director preview',()=>{
  it('requires user click, prebuffers native real frames, schedules exact sound windows and displays exact frame from device time',async()=>{
    const host=makeHost();window.pywebview={api:host};
    const {container}=render(<WO6RenderedDirectorPlayer projectId={pid}/>);
    await screen.findByText(/real_source_cut/);
    expect(host.wo6_07f_rendered_av_window).not.toHaveBeenCalled();
    expect(audioStarts).toHaveLength(0);
    fireEvent.click(screen.getByText('Pre-render first two A/V windows'));
    await waitFor(()=>expect(host.wo6_07f_rendered_av_window).toHaveBeenCalledTimes(2));
    await screen.findByText(/Playback: ready/);
    expect(host.wo6_07f_rendered_av_window).toHaveBeenNthCalledWith(1,{
      project_id:pid,edit_id:'real_source_cut',edit_revision:1,
      edit_sha256:sha,first_frame:0,count:6,camera_path:null,
      sound_timeline_id:null,sound_timeline_revision:null,
      sound_timeline_sha256:null,
    });
    expect(audioStarts).toHaveLength(0);
    expect(container.querySelector('img')).toBeNull();
    fireEvent.click(screen.getByText('Play with audio clock'));
    await waitFor(()=>expect(audioStarts).toHaveLength(2));
    expect(audioStarts[0]).toBeCloseTo(0.3);
    expect(audioStarts[1]).toBeCloseTo(0.55);
    await act(async()=>advance(0.31));
    expect(screen.getByText(/Frames presented by preview clock: 1/)).toBeTruthy();
    expect(container.querySelector('img')?.getAttribute('src'))
      .toBe('data:image/png;base64,AAAB');
    expect(screen.getByText(/Full 24fps sustained acceptance: not certified/)).toBeTruthy();
    expect(host.wo6_07f_rendered_av_window.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
  it('stops and reports audio-clock underflow instead of silently dropping original frames',async()=>{
    const host=makeHost();window.pywebview={api:host};
    render(<WO6RenderedDirectorPlayer projectId={pid}/>);
    await screen.findByText(/real_source_cut/);
    fireEvent.click(screen.getByText('Pre-render first two A/V windows'));
    await screen.findByText(/Playback: ready/);
    fireEvent.click(screen.getByText('Play with audio clock'));
    await waitFor(()=>expect(audioStarts).toHaveLength(2));
    await act(async()=>advance(.31));
    await act(async()=>advance(.56)); // jumps >one frame from audio clock
    expect(await screen.findByText(/Presentation clock missed/)).toBeTruthy();
    expect(screen.getByText(/Playback: underrun/)).toBeTruthy();
    expect(screen.getByText(/Frames presented by preview clock: 1/)).toBeTruthy();
  });
  it('denies fake source packets and never autostarts audio',async()=>{
    const host=makeHost();
    host.wo6_07f_rendered_av_window=vi.fn(async req=>({
      ...packet(req),real_original_usd_pixels_rendered:false,
    }));
    window.pywebview={api:host};
    render(<WO6RenderedDirectorPlayer projectId={pid}/>);
    await screen.findByText(/real_source_cut/);
    fireEvent.click(screen.getByText('Pre-render first two A/V windows'));
    expect(await screen.findByText(/Native rendered picture\/PCM count/)).toBeTruthy();
    expect(audioStarts).toHaveLength(0);
    expect(screen.getByText(/Playback: error/)).toBeTruthy();
  });
  it('denies starting when the installed native WebView2 bridge is missing',async()=>{
    render(<WO6RenderedDirectorPlayer projectId={pid}/>);
    expect(await screen.findByText(/source catalog unavailable/)).toBeTruthy();
    expect(screen.getByText('Play with audio clock').disabled).toBe(true);
  });
});
