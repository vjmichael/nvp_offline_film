// A bounded in-memory buffer for one active playback epoch. No disk cache.
export const MAX_FRAMES=96, MAX_PICTURE_BYTES=32*1024*1024;
export const FRAME_PREFIX='data:image/jpeg;base64,';
export function appendPictures(cache, frames, first, count, oldest){
  if(!Array.isArray(frames)||frames.length!==count)throw Error('The film lost a verified picture window.');
  const staged=new Map();
  for(const [i,frame] of frames.entries()){
    if(frame.frame!==first+i||typeof frame.picture_base64!=='string'||!frame.picture_base64.length||frame.picture_base64.length>12*1024*1024)
      throw Error('One original finished frame is missing or too large');
    staged.set(frame.frame,FRAME_PREFIX+frame.picture_base64);
  }
  // Drop only consumed pictures, never evict an unplayed picture to make room.
  for(const key of cache.keys())if(key<oldest)cache.delete(key);
  let bytes=0,entries=0;
  for(const [key,value] of cache)if(!staged.has(key)){bytes+=2*value.length;entries++;}
  for(const value of staged.values()){bytes+=2*value.length;entries++;}
  if(bytes>MAX_PICTURE_BYTES||entries>MAX_FRAMES)throw Error('Playback picture buffer is full; resume when ready.');
  for(const [key,value] of staged)cache.set(key,value);
}
export function pairedRequest(sample,total){
  const count=Math.min(24000-sample%2000,total-sample);
  return {first:Math.floor(sample/2000),count,frames:Math.ceil((sample%2000+count)/2000)};
}
export function adaptiveSeconds(previous,elapsed){
  const average=previous===null?elapsed:previous*.75+elapsed*.25;
  return {average,seconds:Math.min(3,Math.max(1.25,.75+4*average))};
}
