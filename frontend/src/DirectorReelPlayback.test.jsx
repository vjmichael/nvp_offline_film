import React from 'react';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import DirectorReelPlayback from './DirectorReelPlayback.jsx';
const sha='a'.repeat(64),meta={fps:24,sample_rate:48000,picture_frames:48,audio_samples:96000,duration_seconds:2,reels:2,source_sha256:sha,paired_windows:true};
const reply=data=>({ok:true,json:async()=>data});
const response=(url,bad=false)=>{
  if(url.endsWith('/timeline'))return reply(meta);
  const params=new URL(url,'http://localhost').searchParams,start=Number(params.get('start_sample')),count=Number(params.get('count')),first=Math.floor(start/2000),n=Math.ceil((start%2000+count)/2000);
  const data=new Uint8Array(4);new DataView(data.buffer).setUint32(0,count,true);
  return reply({source_sha256:bad?'f'.repeat(64):sha,start_frame:first,start_sample:start,sample_count:count,audio_base64:btoa(String.fromCharCode(...data)),frames:Array.from({length:n},(_,i)=>({frame:first+i,picture_base64:'AQID'}))});
};
function fakeDevice(){
  const start=vi.fn(),stop=vi.fn(),close=vi.fn(async()=>{});
  class Context{
    sampleRate=48000;currentTime=0;destination={};
    resume=async()=>{};close=close;
    createGain(){return {gain:{value:1,setValueAtTime:vi.fn()},connect:vi.fn()};}
    decodeAudioData=async bytes=>({sampleRate:48000,numberOfChannels:2,length:new DataView(bytes).getUint32(0,true)});
    createBufferSource(){return {connect:vi.fn(),start,stop};}
  }
  vi.stubGlobal('AudioContext',Context);return {start,stop,close};
}
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('uses only paired buffers and stops all scheduled audio on explicit stop',async()=>{
  const device=fakeDevice(),fetcher=vi.fn(async url=>response(url));vi.stubGlobal('fetch',fetcher);
  render(<DirectorReelPlayback sourceBase="/working"/>);fireEvent.click(await screen.findByRole('button',{name:'Play Film'}));await screen.findByText('Playing in sync');
  expect(device.start.mock.calls.map(x=>x[0])).toEqual([.25,.75,1.25]);
  expect(fetcher.mock.calls.slice(1).every(x=>x[0].includes('/paired?'))).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Stop'}));await screen.findByText('Playback stopped.');expect(device.stop).toHaveBeenCalledTimes(3);expect(device.close).toHaveBeenCalled();
});
it('rejects a changed paired source before scheduling sound',async()=>{
  const device=fakeDevice();vi.stubGlobal('fetch',vi.fn(async url=>response(url,true)));
  render(<DirectorReelPlayback sourceBase="/working"/>);fireEvent.click(await screen.findByRole('button',{name:'Play Film'}));await screen.findByRole('alert');expect(screen.getByRole('alert').textContent).toMatch(/window changed/);expect(device.start).not.toHaveBeenCalled();expect(device.close).toHaveBeenCalled();
});
