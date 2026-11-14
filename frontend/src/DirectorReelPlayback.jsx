import React,{useCallback,useEffect,useRef,useState} from 'react';
import './director-reel-playback.css';

/** G09-F verified completed AVI reels, one global film/audio clock. */
const RATE=48000, FPS=24, AUDIO_BLOCK=24000, FRAME_BLOCK=12;
const MAX_FRAMES=96;
async function get(url,signal){
  const r=await fetch(url,{credentials:'same-origin',signal,
    headers:{'x-nvp-director':'1','Cache-Control':'no-store'}});
  if(!r.ok){
    const e=await r.json().catch(()=>({}));
    throw Error(typeof e.detail==='string'?e.detail:
      'The finished reel could not be verified for playback.');
  }
  return r;
}
const clock=s=>{
  const t=Math.max(0,Number(s)||0),h=Math.floor(t/3600),
    m=Math.floor(t/60)%60,sec=Math.floor(t%60);
  return (h?h+':':'')+(h?String(m).padStart(2,'0'):m)+
    ':'+String(sec).padStart(2,'0');
};

export default function DirectorReelPlayback({sourceBase,title='Watch Finished Film'}){
  const [info,setInfo]=useState(null);
  const [playing,setPlaying]=useState(false);
  const [preparing,setPreparing]=useState(false);
  const [position,setPosition]=useState(0);
  const [picture,setPicture]=useState('');
  const [muted,setMuted]=useState(false);
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  const run=useRef(null),epoch=useRef(0),
    current=useRef(0),cache=useRef(new Map());

  const stop=useCallback((message='')=>{
    const p=run.current;
    run.current=null;epoch.current++;
    if(p){
      p.abort.abort();
      if(p.timer)cancelAnimationFrame(p.timer);
      if(p.feeder)clearInterval(p.feeder);
      for(const src of p.nodes){try{src.stop()}catch(_){}}
      p.nodes.clear();
      p.ctx.close().catch(()=>{});
    }
    setPlaying(false);setPreparing(false);
    if(message)setNotice(message);
  },[]);

  useEffect(()=>{
    stop();current.current=0;setPosition(0);setPicture('');cache.current.clear();
    setError('');setNotice('');setInfo(null);
    const c=new AbortController();let active=true;
    get(sourceBase+'/timeline',c.signal)
      .then(r=>r.json()).then(meta=>{
        if(!active)return;
        if(meta.fps!==24||meta.sample_rate!==48000||
           !meta.source_sha256||meta.audio_samples!==meta.picture_frames*2000)
          throw Error('Finished film has no consistent picture/audio clock');
        setInfo(meta);
      }).catch(e=>{
        if(active&&e.name!=='AbortError')setError(e.message);
      });
    return()=>{active=false;c.abort();stop()};
  },[sourceBase]);

  const loadFrames=async(p,first,token)=>{
    if(first>=info.picture_frames||first<0)return;
    if(p.frameRequests.has(first))return p.frameRequests.get(first);
    // Requests never encode an arbitrary host file path.
    const promise=(async()=>{
      const count=Math.min(FRAME_BLOCK,info.picture_frames-first);
      const r=await get(sourceBase+'/frames?start_frame='+first+
        '&count='+count,p.abort.signal);
      const data=await r.json();
      if(token!==epoch.current)return;
      if(data.source_sha256!==info.source_sha256||
         data.start_frame!==first||data.frames?.length!==count)
        throw Error('The film changed after its picture source was verified.');
      for(const frame of data.frames){
        if(!Number.isInteger(frame.frame)||typeof frame.picture_base64!=='string')
          throw Error('One original finished frame is missing');
        cache.current.set(frame.frame,
          'data:image/jpeg;base64,'+frame.picture_base64);
      }
      const oldest=Math.max(0,Math.floor(current.current*FPS)-24);
      for(const key of cache.current.keys())
        if(key<oldest)cache.current.delete(key);
      while(cache.current.size>MAX_FRAMES)
        cache.current.delete(cache.current.keys().next().value);
    })().finally(()=>p.frameRequests.delete(first));
    p.frameRequests.set(first,promise);
    return promise;
  };

  const loadSound=async(p,token)=>{
    if(p.nextSample>=info.audio_samples)return;
    const start=p.nextSample;
    const count=Math.min(AUDIO_BLOCK,info.audio_samples-start);
    const response=await get(sourceBase+'/sound?start_sample='+start+
      '&count='+count,p.abort.signal);
    const startHeader=Number(response.headers.get('X-NVP-Audio-Start-Sample'));
    const countHeader=Number(response.headers.get('X-NVP-Audio-Samples'));
    const sourceSHA=response.headers.get('X-NVP-Source-SHA256');
    if(startHeader!==start||countHeader!==count||sourceSHA!==info.source_sha256)
      throw Error('A film reel lost its original global sound position.');
    const data=await response.arrayBuffer();
    if(token!==epoch.current)return;
    const buffer=await p.ctx.decodeAudioData(data);
    if(token!==epoch.current)return;
    if(buffer.sampleRate!==RATE||buffer.numberOfChannels!==2||
       buffer.length!==count)throw Error(
         'The sound device did not preserve the film sample rate.');
    if(p.at<p.ctx.currentTime+.025)
      throw Error('Playback could not maintain synchronization; resume when ready.');
    const src=p.ctx.createBufferSource();
    src.buffer=buffer;src.connect(p.gain);
    src.onended=()=>p.nodes.delete(src);
    src.start(p.at);
    p.nodes.add(src);
    p.at+=count/RATE;p.nextSample+=count;
  };

  async function play(){
    if(!info||playing||preparing||run.current)return;
    setError('');setNotice('Opening verified picture and sound…');
    setPreparing(true);
    const id=++epoch.current;
    let ctx=null;
    try{
      const Context=window.AudioContext||window.webkitAudioContext;
      if(!Context)throw Error('This device does not support synchronized sound.');
      ctx=new Context({sampleRate:RATE,latencyHint:'playback'});
      if(ctx.sampleRate!==RATE)throw Error(
        'The playback device did not select the original film sample clock.');
      await ctx.resume();
      const first=Math.max(0,Math.min(info.audio_samples-1,
        Math.floor(current.current*RATE)));
      const gain=ctx.createGain();
      gain.gain.value=muted?0:1;gain.connect(ctx.destination);
      const p={ctx,gain,abort:new AbortController(),
        frameRequests:new Map(),nodes:new Set(),
        nextSample:first,clockSample:first,
        at:0,clockAt:0,timer:0,feeder:0,feeding:false};
      run.current=p;
      const frame=Math.floor(first/2000);
      const block=Math.floor(frame/FRAME_BLOCK)*FRAME_BLOCK;
      await Promise.all([loadFrames(p,block,id),
        loadFrames(p,block+FRAME_BLOCK,id),
        loadFrames(p,block+FRAME_BLOCK*2,id)]);
      if(id!==epoch.current)return;
      p.at=ctx.currentTime+.85;p.clockAt=p.at;
      for(let i=0;i<3&&p.nextSample<info.audio_samples;i++)
        await loadSound(p,id);
      if(id!==epoch.current)return;
      setPreparing(false);setPlaying(true);setNotice('');
      const draw=()=>{
        if(id!==epoch.current||run.current!==p)return;
        const delta=Math.max(0,p.ctx.currentTime-p.clockAt);
        const seconds=Math.min(info.duration_seconds,
          (p.clockSample/RATE)+delta);
        current.current=seconds;setPosition(seconds);
        const wanted=Math.min(info.picture_frames-1,Math.floor(seconds*FPS));
        const ready=cache.current.get(wanted);
        if(ready)setPicture(ready);
        else if(seconds<info.duration_seconds-.12){
          stop('Playback paused because a verified picture was not ready.');
          return;
        }
        if(seconds>=info.duration_seconds-.002){
          stop('The finished film has ended.');
          return;
        }
        p.timer=requestAnimationFrame(draw);
      };
      p.timer=requestAnimationFrame(draw);
      p.feeder=setInterval(async()=>{
        if(id!==epoch.current||run.current!==p||p.feeding)return;
        p.feeding=true;
        try{
          while(p.nextSample<info.audio_samples &&
                p.at-p.ctx.currentTime<1.25)
            await loadSound(p,id);
          const frame=Math.floor(current.current*FPS);
          const start=Math.floor(frame/FRAME_BLOCK)*FRAME_BLOCK;
          await Promise.all(
            Array.from({length:4},(_,i)=>start+i*FRAME_BLOCK)
              .filter(index=>index<info.picture_frames)
              .map(index=>loadFrames(p,index,id)));
        }catch(e){
          if(id===epoch.current&&e.name!=='AbortError'){
            setError(e.message);
            stop('Playback paused rather than allowing picture and sound to drift.');
          }
        }finally{p.feeding=false}
      },150);
    }catch(e){
      if(id===epoch.current){
        setError(e.message);
        stop('The finished film remains unchanged.');
      }else if(ctx){ctx.close().catch(()=>{})}
    }
  }

  function seek(value){
    stop('Playback paused at the selected film moment.');
    const seconds=Math.max(0,Math.min(info?.duration_seconds||0,
      Number(value)||0));
    current.current=seconds;setPosition(seconds);
    const still=cache.current.get(Math.floor(seconds*FPS));
    if(still)setPicture(still);
  }
  useEffect(()=>{
    if(run.current)
      run.current.gain.gain.setValueAtTime(
        muted?0:1,run.current.ctx.currentTime);
  },[muted]);

  return <section className="director-reel-player"
    aria-label="Watch completed original-source film reels">
    <div className="director-reel-header">
      <h4>{title}</h4>
      <span>{playing?'Playing in sync':
        preparing?'Preparing original picture and sound':
        info?'Film ready to watch':'Opening verified film…'}</span>
    </div>
    {error&&<p role="alert" className="director-reel-error">{error}</p>}
    {notice&&<p role="status" className="director-reel-notice">{notice}</p>}
    <div className="director-reel-picture">
      {picture?<img src={picture}
        alt="Actual picture frame from the verified finished film"/>:
        <p>{info?'Press Play Film to start watching.':
          'The verified film will appear here.'}</p>}
    </div>
    {info&&<div className="director-reel-controls">
      <div className="director-reel-actions">
        <button className="film-primary" disabled={preparing}
          onClick={playing?()=>stop('Paused. Resume at the same film moment.'):play}>
          {playing?'Pause Film':preparing?'Opening…':'Play Film'}
        </button>
        <button className="film-secondary" disabled={!playing&&!preparing}
          onClick={()=>stop('Playback stopped.')}>Stop</button>
        <label><input type="checkbox" checked={muted}
          onChange={e=>setMuted(e.target.checked)}/> Mute</label>
        <span>{clock(position)} / {clock(info.duration_seconds)}</span>
      </div>
      <label className="director-reel-seek">Film position
        <input type="range" min="0" max={info.duration_seconds}
          step={1/RATE} value={position}
          onChange={e=>seek(e.target.value)}/>
      </label>
      <p className="film-hint">{info.reels} independently checked
        reels form one original film clock. This is the first continuous
        film player; uninterrupted feature-length physical device playback
        has not yet passed installed-app acceptance.</p>
    </div>}
  </section>;
}
