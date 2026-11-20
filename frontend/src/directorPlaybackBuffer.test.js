import {describe,it,expect} from 'vitest';
import {appendPictures,pairedRequest,adaptiveSeconds,MAX_FRAMES,MAX_PICTURE_BYTES} from './directorPlaybackBuffer.js';
const frames=(first,count,raw='AQID')=>Array.from({length:count},(_,i)=>({frame:first+i,picture_base64:raw}));
describe('protected paired playback buffer',()=>{
  it('keeps an exact unaligned sample and ends at a bounded frame boundary',()=>{
    expect(pairedRequest(179999,360000)).toEqual({first:89,count:22001,frames:12});
    expect(pairedRequest(359999,360000)).toEqual({first:179,count:1,frames:1});
    expect(pairedRequest(0,360000)).toEqual({first:0,count:24000,frames:12});
  });
  it('adapts latency but keeps the time horizon bounded',()=>{
    expect(adaptiveSeconds(null,.01).seconds).toBe(1.25);
    expect(adaptiveSeconds(null,5).seconds).toBe(3);
    expect(adaptiveSeconds(.5,.1).average).toBeCloseTo(.4);
  });
  it('rejects wrong frames and never evicts unplayed pictures',()=>{
    const cache=new Map();appendPictures(cache,frames(0,MAX_FRAMES),0,MAX_FRAMES,0);
    expect(()=>appendPictures(cache,frames(MAX_FRAMES,1),MAX_FRAMES,1,0)).toThrow(/full/);
    expect(cache.has(0)).toBe(true);expect(cache.size).toBe(MAX_FRAMES);
    appendPictures(cache,frames(MAX_FRAMES,1),MAX_FRAMES,1,1);expect(cache.has(0)).toBe(false);
    expect(()=>appendPictures(cache,frames(100,2),99,2,1)).toThrow(/missing/);
  });
  it('enforces the byte budget even when frame count is small',()=>{
    const cache=new Map(),raw='A'.repeat(Math.floor(MAX_PICTURE_BYTES/8));
    appendPictures(cache,frames(0,3,raw),0,3,0);
    expect(()=>appendPictures(cache,frames(3,1,raw),3,1,0)).toThrow(/full/);
    expect(cache.size).toBe(3);
  });
});
