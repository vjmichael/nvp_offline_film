import React,{useCallback,useEffect,useRef,useState} from 'react';
import './director-av-monitor.css';

/** G09-C source film player, audio-clock master; source film never overwritten. */
const RATE=48000;
const FPS=24;
const AUDIO_CHUNK=24000;
const FRAMES_CHUNK=12;
const MAX_STORED_FRAMES=96;
async function get(url,signal){
  const response=await fetch(url,{
    signal,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Cache-Control':'no-store'}});
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw Error(typeof error.detail==='string'?error.detail:
      'The original film could not be played at this moment.');
  }
  return response;
}
const format=n=>{
  const safe=Math.max(0,Number(n||0));
  return Math.floor(safe/60)+':'+String(Math.floor(safe%60)).padStart(2,'0')+
    '.'+String(Math.floor((safe%1)*10));
};
export default function DirectorAVMonitor({movie,editRevision,onPositionChange}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/av';
  const [timeline,setTimeline]=useState(null);
  const [position,setPosition]=useState(0);
  const [image,setImage]=useState('');
  const [playing,setPlaying]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [muted,setMuted]=useState(false);
  const player=useRef(null);
  const frameCache=useRef(new Map());
  const positionRef=useRef(0);
  const session=useRef(0);
  const autoPosition=useRef(onPositionChange);
  const output=useRef(null);
  autoPosition.current=onPositionChange;

  const endPlayback=useCallback((message='')=>{
    const p=player.current;
    player.current=null;
    session.current++;
    if(p){
      p.abort.abort();
      for(const node of p.nodes){try{node.stop()}catch(_){}}
      p.nodes.clear();
      p.ctx.close().catch(()=>{});
      if(p.frameTimer)window.cancelAnimationFrame(p.frameTimer);
      if(p.feedTimer)window.clearInterval(p.feedTimer);
    }
    setPlaying(false);
    setBusy(false);
    if(message)setNotice(message);
  },[]);

  useEffect(()=>{
    endPlayback();
    let live=true;const abort=new AbortController();
    setTimeline(null);setImage('');setPosition(0);
    positionRef.current=0;frameCache.current.clear();
    setNotice('');setError('');
    if(!editRevision)return()=>{live=false;abort.abort()};
    get(base+'/timeline?revision='+editRevision,abort.signal)
      .then(r=>r.json()).then(data=>{
        if(live)setTimeline(data);
      }).catch(e=>{if(live&&e.name!=='AbortError')setError(e.message)});
    return()=>{live=false;abort.abort();endPlayback()};
  },[base,editRevision]);

  const queryFrames=async(p,first,epoch)=>{
    if(first>=timeline.picture_frames||p.aborted||p.abort.signal.aborted)return;
    if(p.frameRequests.has(first))return p.frameRequests.get(first);
    const count=Math.min(FRAMES_CHUNK,timeline.picture_frames-first);
    const request=(async()=>{
      const url=base+'/frames?revision='+editRevision+
        '&start_frame='+first+'&count='+count;
      const payload=await (await get(url,p.abort.signal)).json();
      if(payload.edit_sha256!==timeline.edit_sha256 ||
          payload.look_sha256!==timeline.look_sha256 ||
          payload.actor_sha256!==timeline.actor_sha256 ||
          epoch!==session.current)throw Error(
            'The edited movie changed while playing. Reopen it to continue.');
      for(const frame of payload.frames){
        if(!Number.isInteger(frame.frame)||typeof frame.picture_base64!=='string')
          throw Error('The picture source was incomplete');
        frameCache.current.set(frame.frame,
          'data:image/jpeg;base64,'+frame.picture_base64);
      }
      // Keep a bounded handful of independently evaluated frames.
      const minimum=first-FPS*2;
      for(const frame of frameCache.current.keys())
        if(frame<minimum)frameCache.current.delete(frame);
      while(frameCache.current.size>MAX_STORED_FRAMES)
        frameCache.current.delete(frameCache.current.keys().next().value);
    })().finally(()=>p.frameRequests.delete(first));
    p.frameRequests.set(first,request);
    return request;
  };

  const querySound=async(p,epoch)=>{
    if(p.nextSample>=timeline.audio_samples||p.aborted)return;
    const sample=p.nextSample;
    const count=Math.min(AUDIO_CHUNK,timeline.audio_samples-sample);
    const url=base+'/sound?revision='+editRevision+
      '&start_sample='+sample+'&count='+count;
    const response=await get(url,p.abort.signal);
    const start=Number(response.headers.get('X-NVP-Audio-Start-Sample'));
    const samples=Number(response.headers.get('X-NVP-Audio-Samples'));
    if(start!==sample||samples!==count)throw Error(
      'The original sound was not aligned to the picture.');
    const raw=await response.arrayBuffer();
    if(epoch!==session.current||p.abort.signal.aborted)return;
    const decoded=await p.ctx.decodeAudioData(raw);
    if(epoch!==session.current||p.abort.signal.aborted)return;
    if(decoded.sampleRate!==RATE||decoded.numberOfChannels!==2||
       decoded.length!==count)throw Error(
         'The sound device did not preserve the 48kHz film clock.');
    if(p.nextAt<p.ctx.currentTime+.025){
      throw Error('Playback needs to rebuffer before continuing in sync.');
    }
    const node=p.ctx.createBufferSource();
    node.buffer=decoded;node.connect(p.gain);
    node.onended=()=>p.nodes.delete(node);
    node.start(p.nextAt);
    p.nodes.add(node);
    p.nextAt+=count/RATE;
    p.nextSample+=count;
  };

  async function start(){
    if(!timeline||busy||player.current)return;
    setBusy(true);setError('');setNotice('Preparing your film and sound…');
    const epoch=++session.current;
    const abort=new AbortController();
    let context=null;
    try{
      const Context=window.AudioContext||window.webkitAudioContext;
      if(!Context)throw Error('Synchronized audio playback is unavailable on this device.');
      context=new Context({sampleRate:RATE,latencyHint:'playback'});
      if(context.sampleRate!==RATE)throw Error(
        'The audio device could not establish the source sound rate.');
      await context.resume();
      const initial=Math.floor(positionRef.current*RATE);
      // Seek from the director's exact source sample, not the previous
      // half-second chunk: otherwise sound and picture would jump backwards.
      const startSample=initial;
      const startFrame=Math.floor(startSample/RATE*FPS);
      const gain=context.createGain();
      gain.gain.value=muted?0:1;gain.connect(context.destination);
      const p={ctx:context,gain,abort,nodes:new Set(),nextSample:startSample,
        nextAt:context.currentTime+.75,
        clockAt:context.currentTime+.75,
        clockSample:startSample,
        aborted:false,frameRequests:new Map(),
        frameTimer:0,feedTimer:0,feeding:false};
      player.current=p;
      await Promise.all([
        queryFrames(p,Math.floor(startFrame/FRAMES_CHUNK)*FRAMES_CHUNK,epoch),
        queryFrames(p,Math.floor(startFrame/FRAMES_CHUNK)*FRAMES_CHUNK+
          FRAMES_CHUNK,epoch)
      ]);
      if(epoch!==session.current)return;
      // Source-picture prebuffering can be expensive. Establish the
      // audio master clock only AFTER the first source images are ready.
      p.nextAt=p.ctx.currentTime+.75;
      p.clockAt=p.nextAt;
      await querySound(p,epoch);
      if(epoch!==session.current)return;
      if(p.nextSample<timeline.audio_samples)await querySound(p,epoch);
      if(epoch!==session.current)return;
      setBusy(false);setPlaying(true);setNotice('');
      const paint=()=>{
        if(epoch!==session.current||!player.current)return;
        const soundSeconds=Math.max(0,p.ctx.currentTime-p.clockAt);
        const at=(p.clockSample/RATE)+soundSeconds;
        const next=Math.min(timeline.duration_seconds,at);
        positionRef.current=next;setPosition(next);
        autoPosition.current?.(next);
        const frame=Math.min(timeline.picture_frames-1,Math.floor(next*FPS));
        if(frame>=0){
          const picture=frameCache.current.get(frame);
          if(picture)setImage(picture);
          else if(next<timeline.duration_seconds-.15){
            endPlayback('Playback paused because a picture was not ready. '+
              'Resume to continue in sync.');
            return;
          }
        }
        if(next>=timeline.duration_seconds-.001){
          endPlayback('Finished playing. Your source film remains unchanged.');
          return;
        }
        p.frameTimer=window.requestAnimationFrame(paint);
      };
      p.frameTimer=window.requestAnimationFrame(paint);
      p.feedTimer=window.setInterval(async()=>{
        if(epoch!==session.current||!player.current||p.feeding)return;
        p.feeding=true;
        try{
          // Keep one second of both video and sound ready, but do not
          // request an unbounded stream or hold more than 96 pictures.
          while(p.nextSample<timeline.audio_samples&&
                p.nextAt-p.ctx.currentTime<1.15){
            await querySound(p,epoch);
          }
          const current=Math.floor(positionRef.current*FPS);
          const nearest=Math.floor(current/FRAMES_CHUNK)*FRAMES_CHUNK;
          for(let i=0;i<3;i++){
            const frame=nearest+i*FRAMES_CHUNK;
            if(frame<timeline.picture_frames){
              await queryFrames(p,frame,epoch);
            }
          }
        }catch(e){
          if(epoch===session.current&&e.name!=='AbortError'){
            setError(e.message);
            endPlayback('Playback stopped to keep picture and sound synchronized.');
          }
        }finally{p.feeding=false}
      },160);
    }catch(e){
      if(epoch===session.current){
        setError(e.message);
        endPlayback('Your film is safe. The player can be restarted.');
      }else if(context){context.close().catch(()=>{})}
    }
  }

  function seek(value){
    if(player.current)endPlayback('Playback paused at your chosen film moment.');
    const at=Math.min(timeline?.duration_seconds||0,
      Math.max(0,Number(value)||0));
    positionRef.current=at;setPosition(at);
    autoPosition.current?.(at);
    const still=frameCache.current.get(Math.floor(at*FPS));
    if(still)setImage(still);
  }

  useEffect(()=>{
    const p=player.current;
    if(p)p.gain.gain.setValueAtTime(muted?0:1,p.ctx.currentTime);
  },[muted]);
  return <section className="director-av-monitor"
    aria-label="Play edited film with picture and sound">
    <div className="director-av-header">
      <div><h3>Play Film With Sound</h3>
        <p className="film-muted">See your original performances, selected
          camera views and approved sound together. Nothing here changes your
          recordings or saved edit.</p></div>
      <span className="director-av-status">{playing?'Playing in sync':
        busy?'Preparing film':'Ready to preview'}</span>
    </div>
    {error&&<div className="director-av-error" role="alert">{error}</div>}
    {notice&&<div className="director-av-notice" role="status">{notice}</div>}
    <div className="director-av-picture">
      {image?<img alt="Picture from the selected original 3D film performances"
        src={image}/>:
        <div className="director-av-placeholder">
          {timeline?'Press Play to see and hear your film.':
            'Choose an edited scene to watch the film.'}
        </div>}
    </div>
    {timeline&&<div className="director-av-transport">
      <div className="director-av-actions">
        <button className="film-primary" disabled={busy}
          onClick={playing?()=>endPlayback('Paused at your film moment.'):start}>
          {playing?'Pause Film':busy?'Preparing…':'Play Film'}</button>
        <button className="film-secondary" disabled={!playing&&!busy}
          onClick={()=>endPlayback('Film playback stopped.')}>Stop</button>
        <label className="director-av-mute">
          <input type="checkbox" checked={muted}
            onChange={e=>setMuted(e.target.checked)}/> Mute
        </label>
        <span>{format(position)} / {format(timeline.duration_seconds)}</span>
      </div>
      <label className="director-av-scrubber">Film position
        <input type="range" min={0} max={timeline.duration_seconds}
          step={1/RATE} value={position}
          onChange={e=>seek(e.target.value)}/>
      </label>
      <p className="film-hint">Picture and original-source sound follow the same
        film clock. This is an editing playback; cinema mastering and
        feature-length playback are later production work.</p>
    </div>}
  </section>;
}
