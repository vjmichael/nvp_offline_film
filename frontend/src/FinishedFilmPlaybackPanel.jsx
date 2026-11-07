import React,{useEffect,useRef,useState} from 'react';

const FORMAT='nvp.wo5.finished_dcp_pcm24_picture_review.v1';
const FPS=24, RATE=48000, SAMPLES=2000;
const BUFFER=16, PREROLL=8, AHEAD=0.75;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

export function requireAheadOfAudioClock(plannedStart,currentTime){
  // WebAudio starts late nodes immediately. That would pair picture frame N
  // with sound heard at N+1. Never silently accept an already-expired cue.
  if(!Number.isFinite(plannedStart)||!Number.isFinite(currentTime)||
     plannedStart<currentTime+0.005)
    throw Error('Finished-film audio missed its exact presentation deadline');
  return plannedStart;
}
export function requireContinuousPicture(lastPainted,nextFrame){
  // rAF can be throttled when the window is hidden. An unseen skipped
  // picture cannot be counted as a complete film review.
  if(!Number.isInteger(lastPainted)||!Number.isInteger(nextFrame)||
     nextFrame>lastPainted+1)
    throw Error('Finished-film picture skipped a required presentation frame');
  return nextFrame;
}

export function checkFinishedFrame(packet,expected){
  if(!packet||packet.format!==FORMAT||
     packet.status!=='DECODED_PUBLISHED_FINAL_FRAME'||
     packet.frame_index!==expected||
     packet.picture_24fps_film_time_tick!==expected*294000000||
     packet.audio_start_sample!==expected*SAMPLES||
     packet.audio_samples!==SAMPLES||
     !packet.picture_and_sound_from_final_published_mxf||
     packet.production_accepted!==false||
     !Number.isInteger(packet.picture_width)||
     !Number.isInteger(packet.picture_height)||
     packet.picture_width<1||packet.picture_height<1||
     packet.picture_width>1024||packet.picture_height>1024||
     typeof packet.picture_png_base64!=='string'||
     packet.picture_png_base64.length>4*1024*1024||
     typeof packet.stereo_pcm16_base64!=='string'||
     packet.stereo_pcm16_base64.length>16000||
     !/^[A-Za-z0-9+/]+={0,2}$/.test(packet.picture_png_base64)||
     !/^[A-Za-z0-9+/]+={0,2}$/.test(packet.stereo_pcm16_base64)){
    throw Error('Finished DCP frame/audio receipt rejected; playback stopped.');
  }
  return packet;
}

function sampleChannels(base64){
  const binary=atob(base64);
  if(binary.length!==SAMPLES*4)
    throw Error('Native decoded final PCM16 audio window is incomplete');
  const left=new Float32Array(SAMPLES),right=new Float32Array(SAMPLES);
  const bytes=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
  const view=new DataView(bytes.buffer);
  for(let i=0;i<SAMPLES;i++){
    left[i]=view.getInt16(4*i,true)/32768;
    right[i]=view.getInt16(4*i+2,true)/32768;
  }
  return [left,right];
}
async function decodedPicture(base64){
  const img=new Image();
  img.src='data:image/png;base64,'+base64;
  if(img.decode)await img.decode();
  else await new Promise((resolve,reject)=>{
    img.onload=resolve;img.onerror=()=>reject(Error('Real DCP screen frame unavailable'));
  });
  return img;
}

export default function FinishedFilmPlaybackPanel({projectId,featureId,nativeBridge=null}){
  const [native,setNative]=useState(nativeBridge);
  const [capability,setCapability]=useState(null);
  const [status,setStatus]=useState('NOT_STARTED');
  const [error,setError]=useState('');
  const [note,setNote]=useState('');
  const [info,setInfo]=useState(null);
  const [seek,setSeek]=useState('0');
  const [position,setPosition]=useState(0);
  const [playing,setPlaying]=useState(false);
  const canvas=useRef(null);
  const ref=useRef({generation:0,active:false});

  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    const discover=()=>{
      const bridge=window.pywebview?.api;
      if(bridge && ['wo5_film_capabilities','wo5_film_begin',
                    'wo5_film_frame','wo5_film_stop'].every(
                      key=>typeof bridge[key]==='function'))setNative(bridge);
    };
    discover();
    window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[nativeBridge]);

  useEffect(()=>{
    let live=true;
    setCapability(null);
    if(native&&projectId&&
       typeof native.wo5_film_capabilities==='function'){
      Promise.resolve(native.wo5_film_capabilities()).then(c=>{
        if(live&&c?.format===FORMAT)setCapability(c);
      }).catch(e=>{if(live)setError(e.message);});
    }
    return ()=>{live=false;};
  },[native,projectId]);

  const stop=async(silent=false)=>{
    const r=ref.current;
    r.generation++;
    r.active=false;
    if(r.animation!=null)cancelAnimationFrame(r.animation);
    for(const node of r.scheduled||[]){
      try{node.stop();}catch{}
      try{node.disconnect();}catch{}
    }
    r.scheduled=[];
    if(r.context){try{await r.context.close();}catch{}}
    if(r.ticket&&r.native){
      try{await r.native.wo5_film_stop(r.ticket);}catch(e){
        if(!silent)setError('Playback stopped locally; native grant cleanup failed: '+e.message);
      }
    }
    ref.current={generation:r.generation,active:false};
    if(!silent){setPlaying(false);setStatus('STOPPED');}
  };

  useEffect(()=>()=>{void stop(true);},[featureId,projectId,native]);

  async function begin(){
    if(!native||!featureId||playing)return;
    setError('');setNote('');
    let start=Number(seek);
    if(!Number.isSafeInteger(start)||start<0||
       (info&&start>=info.frame_count)){
      setError('Select an exact finished-film frame inside the indexed feature.');return;
    }
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio){setError('A real WebView2 WebAudio device is required for synchronized film review.');return;}
    await stop(true);
    const current=ref.current;
    const gen=current.generation;
    setStatus('APPROVING_NATIVE_READ');
    let session=null,ctx=null;
    try{
      session=await native.wo5_film_begin(projectId,featureId);
      if(session?.status==='DENIED'){setStatus('DENIED');return;}
      if(!session||session.format!==FORMAT||
         session.status!=='FINISHED_DCP_READONLY_READY'||
         session.native_picture_and_sound_from_published_mxf!==true||
         session.production_accepted!==false||
         session.fps!==FPS||session.sound_rate!==RATE||
         session.sound_samples_per_frame!==SAMPLES||
         !Number.isInteger(session.frame_count)||
         session.frame_count<1||!session.session_id)
        throw Error('Native completed-film session receipt is invalid');
      if(start>=session.frame_count)throw Error('Seek beyond finished film duration');
      ctx=new Audio({sampleRate:RATE});
      await ctx.resume();
      const c={
        generation:gen,active:true,native,
        ticket:session.session_id,context:ctx,
        first:start,requested:start,loaded:new Map(),scheduled:[],
        started:false,anchor:0,nextSchedule:start,
        displayed:start-1,animation:null,lastFrame:session.frame_count-1,
      };
      ref.current=c;
      setInfo(session);setPlaying(true);
      setPosition(start);setStatus('BUFFERING_NATIVE_FINISHED_ESSENCE');
      const remain=()=>ref.current===c && c.active && c.generation===gen;
      function schedule(){
        if(!remain())return;
        if(!c.started){
          const preroll=Math.min(PREROLL,session.frame_count-c.first);
          if(c.loaded.size<preroll)return;
          c.started=true;
          c.anchor=ctx.currentTime+0.17;
          setStatus('PLAYING_FINAL_MXF_AUDIO_CLOCK');
        }
        while(c.loaded.has(c.nextSchedule) &&
              c.anchor+(c.nextSchedule-c.first)/FPS<
                ctx.currentTime+AHEAD){
          const item=c.loaded.get(c.nextSchedule);
          if(item.scheduled)break;
          const clip=ctx.createBuffer(2,SAMPLES,RATE);
          clip.getChannelData(0).set(item.audio[0]);
          clip.getChannelData(1).set(item.audio[1]);
          const node=ctx.createBufferSource();
          node.buffer=clip;
          node.connect(ctx.destination);
          node.start(requireAheadOfAudioClock(
            c.anchor+(c.nextSchedule-c.first)/FPS,ctx.currentTime));
          c.scheduled.push(node);
          item.scheduled=true;
          c.nextSchedule++;
        }
      }
      function tick(){
        if(!remain())return;
        try{schedule();}catch(e){
          setError(e.message);
          setStatus('FAILED_AUDIO_CLOCK_NOT_REVIEWED');
          void stop(true);setPlaying(false);return;
        }
        if(c.started){
          const elapsed=ctx.currentTime-c.anchor;
          if(elapsed>=0){
            const frame=c.first+Math.floor(elapsed*FPS);
            if(frame>c.lastFrame){
              if(c.displayed!==c.lastFrame || c.nextSchedule!==c.lastFrame+1){
                setError('Final film ended with missing presented picture or audio.');
                setStatus('FAILED_INCOMPLETE_FILM_NOT_REVIEWED');
                void stop(true);setPlaying(false);return;
              }
              setStatus('FINISHED_PLAYBACK_REACHED_END_NOT_CREATIVE_APPROVAL');
              setNote('Decoded final picture/audio reached the last presentation frame. This does not certify that a person watched and heard it.');
              void stop(true);
              setPlaying(false);
              return;
            }
            const packet=c.loaded.get(frame);
            if(!packet||!packet.scheduled){
              setError('Playback underrun: final DCP picture and/or mastered sound was not ready at the audio clock. No frames skipped; seek back and restart.');
              setStatus('FAILED_UNDERRUN_NOT_REVIEWED');
              void stop(true);
              setPlaying(false);
              return;
            }
            if(frame!==c.displayed){
              try{requireContinuousPicture(c.displayed,frame);}
              catch(e){
                setError(e.message);
                setStatus('FAILED_SKIPPED_PICTURE_NOT_REVIEWED');
                void stop(true);setPlaying(false);return;
              }
              const target=canvas.current;
              const paint=target?.getContext('2d');
              if(target&&paint){
                if(target.width!==packet.width)target.width=packet.width;
                if(target.height!==packet.height)target.height=packet.height;
                paint.drawImage(packet.image,0,0,target.width,target.height);
              }
              c.displayed=frame;
              setPosition(frame);
              // No full-film frames retained: only a short real-time window.
              for(const n of c.loaded.keys()){
                if(n<frame-1)c.loaded.delete(n);
              }
            }
          }
        }
        c.animation=requestAnimationFrame(tick);
      }
      async function pump(){
        while(remain()&&c.requested<=c.lastFrame){
          if(c.loaded.size>=BUFFER){
            await sleep(12);continue;
          }
          const n=c.requested;
          const frame=checkFinishedFrame(
            await native.wo5_film_frame(c.ticket,n),n);
          if(!remain())return;
          const image=await decodedPicture(frame.picture_png_base64);
          const audio=sampleChannels(frame.stereo_pcm16_base64);
          if(!remain())return;
          c.loaded.set(n,{image,audio,scheduled:false,
                          width:frame.picture_width,
                          height:frame.picture_height});
          c.requested++;
          schedule();
        }
      }
      c.animation=requestAnimationFrame(tick);
      void pump().catch(e=>{
        if(remain()){
          setError('Native finished film decode stopped: '+e.message);
          setStatus('FAILED_NATIVE_DECODE_NOT_REVIEWED');
          void stop(true);setPlaying(false);
        }
      });
    }catch(e){
      if(ctx){try{await ctx.close();}catch{}}
      if(session?.session_id){
        try{await native.wo5_film_stop(session.session_id);}catch{}
      }
      setStatus('UNAVAILABLE');setError(e.message);setPlaying(false);
    }
  }

  return <section className="card" aria-label="Finished film picture and sound review">
    <h3>Finished film · actual published picture and mastered sound</h3>
    <p className="fineprint">
      This player reads native decoded picture and PCM24 **from the final DCP's
      picture/sound MXF tracks**, not from the original USD Take viewer.
      It uses the actual 24fps picture Film Time and 48kHz mastered audio
      as one WebAudio clock, including across cuts and reel boundaries.
      Original DCP bytes remain untouched.
    </p>
    {error&&<p role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    {!capability?.native_finished_mxf_decode_configured&&
      <p role="status">Verified installed CineCert/OpenJPEG decoder bundle
      has not been configured for the trusted desktop host. Finished
      DCP playback cannot start; no FFmpeg or synthetic fallback.</p>}
    <p aria-label="Finished film playback state">State: {status}</p>
    <canvas ref={canvas} width={512} height={270} role="img"
      aria-label="Decoded finished DCP picture at its audio-clock Film Time"
      style={{width:'100%',height:'auto',background:'#090b12',aspectRatio:'16/9'}}/>
    <p className="fineprint">Output frame: {position} ·
      {info ? (position/24).toFixed(3)+' / '+(info.frame_count/24).toFixed(3)+' seconds'
        : 'Waiting for a verified native film'}
      · 48kHz stereo monitoring downmix (not calibrated cinema surround)</p>
    <label>Seek to exact 24fps finished-film frame
      <input aria-label="Finished film frame seek"
        type="number" min={0} step={1}
        max={Math.max(0,(info?.frame_count||1)-1)}
        disabled={playing} value={seek} onChange={e=>setSeek(e.target.value)}/>
    </label>
    <div className="actions">
      <button disabled={!native||playing||!featureId||
        !capability?.native_finished_mxf_decode_configured}
        onClick={begin}>Request native permission and play finished DCP</button>
      <button disabled={!playing} className="secondary"
        onClick={()=>void stop()}>Stop final film playback</button>
    </div>
    <p className="fineprint">Native decode is bounded by a 16-frame
      picture+audio buffer. If a decoder misses the audio clock, playback
      fails closed instead of silently skipping a shot or reporting success.
      Picture is an uncalibrated XYZ-to-sRGB review PNG; the original
      multi-channel 24-bit DCP sound is preserved. SMPTE DCP Bv2.1,
      cinema projector ingest and the director's creative judgment
      remain independent acceptance requirements.</p>
  </section>;
}
