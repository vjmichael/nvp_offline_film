import React,{useEffect,useRef,useState} from 'react';

// DATA-AV-01: there is no MP4, frame sequence or HTTP audio endpoint.
// The authenticated desktop bridge returns <=4096 PCM samples at a time
// from a frozen, exact-SHA OpenUSD Digital Take. Web Audio sends temporary
// samples to the OS device. No complete soundtrack is ever materialized.
const FORMAT='nvp.data_av.native_session.v1';
const WINDOW=2048;
const RATE=48000;
const TICKS_PER_SAMPLE=147000;

function decodedStereo(base64,count){
  const binary=atob(base64);
  if(binary.length!==count*4)throw Error('Unbounded or incomplete native PCM response');
  const buffer=new ArrayBuffer(binary.length);
  const bytes=new Uint8Array(buffer);
  for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
  const view=new DataView(buffer);
  const left=new Float32Array(count),right=new Float32Array(count);
  for(let i=0;i<count;i++){
    left[i]=view.getInt16(i*4,true)/32768;
    right[i]=view.getInt16(i*4+2,true)/32768;
  }
  return [left,right];
}

export default function DataFirstAVPanel({projectId,nativeBridge=null}){
  const [native,setNative]=useState(nativeBridge);
  const [takes,setTakes]=useState([]);
  const [takeId,setTakeId]=useState('');
  const [listener,setListener]=useState('');
  const [sourceSample,setSourceSample]=useState('0');
  const [playing,setPlaying]=useState(false);
  const [error,setError]=useState('');
  const [note,setNote]=useState('');
  const [scene,setScene]=useState(null);
  const [direction,setDirection]=useState('forward');
  const controller=useRef({ticket:null,context:null,scheduled:[],
    generation:0,cursor:0,last:0,first:0,nextAudioAt:0,
    working:false,active:false,stopping:false});
  const item=takes.find(x=>x.take_id===takeId);

  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    const discover=()=>{
      const api=window.pywebview?.api;
      if(api&&['data_av_catalog','data_av_begin','data_av_audio_window',
               'data_av_scene_at','data_av_stop'].every(k=>
               typeof api[k]==='function'))setNative(api);
    };
    discover();
    window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[nativeBridge]);

  useEffect(()=>{
    if(!native||!projectId)return;
    let live=true;
    setError('');setTakes([]);setTakeId('');setListener('');setScene(null);
    Promise.resolve(native.data_av_catalog(projectId)).then(result=>{
      if(!live)return;
      if(result?.format!==FORMAT||result.status!=='AVAILABLE'||
         result.ffmpeg_runtime_required!==false||!Array.isArray(result.takes))
        throw Error('Native film data inventory is not verified');
      setTakes(result.takes);
      setTakeId(result.takes[0]?.take_id||'');
    }).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[native,projectId]);

  useEffect(()=>{
    setListener(item?.listeners?.[0]||'');
  },[takeId,takes]);

  async function stop(){
    const st=controller.current;
    st.generation++;
    st.active=false;st.working=false;
    for(const node of st.scheduled){
      try{node.stop();}catch{}
      try{node.disconnect();}catch{}
    }
    st.scheduled=[];
    if(st.context){
      const ctx=st.context;
      st.context=null;
      try{await ctx.close();}catch{}
    }
    const ticket=st.ticket;
    st.ticket=null;
    setPlaying(false);setScene(null);
    if(ticket&&native){
      try{await native.data_av_stop(ticket);}
      catch(e){setNote('Preview stopped locally; native permission may need restart cleanup.');}
    }
  }

  useEffect(()=>()=>{ // cleanup must revoke on tab/scene switch
    const st=controller.current;
    st.generation++;
    st.active=false;
    for(const node of st.scheduled)try{node.stop();}catch{}
    st.scheduled=[];
    if(st.context)Promise.resolve(st.context.close()).catch(()=>{});
    if(st.ticket&&native)Promise.resolve(
      native.data_av_stop(st.ticket)).catch(()=>{});
    st.ticket=null;st.context=null;
  },[native,projectId]);

  async function inspect(ticket,sample){
    if(!native||!ticket)return;
    try{
      const response=await native.data_av_scene_at(
        ticket,sample*TICKS_PER_SAMPLE);
      if(response?.format!==FORMAT||response.status!=='SCENE_READY'||
         response.original_modified!==false||
         response.master_approved!==false)return;
      if(controller.current.ticket===ticket)setScene(response);
    }catch(e){
      setNote('Scene view could not be refreshed; audio source remains immutable.');
    }
  }

  async function queueAudio(gen){
    const st=controller.current;
    if(!st.active||!st.context||!st.ticket||st.generation!==gen||
       st.working)return;
    st.working=true;
    try{
      // Maximum ~0.45s of ahead-of-time audio; no feature-long memory
      // buffer, persistent soundtrack, codec stream or frame clock.
      for(let i=0;i<7&&st.active&&st.generation===gen;i++){
        const ahead=st.nextAudioAt-st.context.currentTime;
        if(ahead>0.45)break;
        const reverse=direction==='reverse';
        const first=reverse?Math.max(st.first,st.cursor-WINDOW):st.cursor;
        const count=reverse?st.cursor-first:Math.min(WINDOW,st.last-first);
        if(count<=0){
          st.active=false;
          setPlaying(false);
          setNote('Reached the end of this creator-approved Film Time interval.');
          break;
        }
        const response=await native.data_av_audio_window(st.ticket,first,count);
        if(!st.active||st.generation!==gen)return;
        if(response?.format!=='nvp.data_av.native_scene_window.v1'||
           response.status!=='READY'||response.session_id!==st.ticket||
           response.take_document_sha256!==item.take_document_sha256||
           response.sample_rate!==RATE||response.channels!==2||
           response.sample_count!==count||response.first_sample!==first||
           response.source_modified!==false||
           response.film_master_approved!==false||
           response.frame_based_playback!==false)
          throw Error('Native window source/clock verification failed');
        const [left,right]=decodedStereo(response.pcm_base64,count);
        const clip=st.context.createBuffer(2,count,RATE);
        const l=clip.getChannelData(0),r=clip.getChannelData(1);
        for(let k=0;k<count;k++){
          const read=reverse?count-1-k:k;
          l[k]=left[read];r[k]=right[read];
        }
        const node=st.context.createBufferSource();
        node.buffer=clip;
        node.connect(st.context.destination);
        node.start(Math.max(st.context.currentTime+0.025,st.nextAudioAt));
        st.scheduled.push(node);
        node.onended=()=>{const k=st.scheduled.indexOf(node);
          if(k>=0)st.scheduled.splice(k,1);};
        st.nextAudioAt=Math.max(
          st.context.currentTime+0.025,st.nextAudioAt)+count/RATE;
        st.cursor=reverse?first:first+count;
        if(i===0)inspect(st.ticket,reverse?first:st.cursor-1);
        setSourceSample(String(st.cursor));
      }
    }catch(e){
      if(st.generation===gen){
        setError(e.message);setPlaying(false);st.active=false;
        for(const node of st.scheduled)try{node.stop();}catch{}
        st.scheduled=[];
      }
    }finally{
      st.working=false;
    }
  }

  async function begin(){
    if(!native||!item||!listener||playing)return;
    setError('');setNote('');
    const first=Number(sourceSample);
    if(!Number.isSafeInteger(first)||first<0){
      setError('Enter a valid nonnegative sample position.');return;
    }
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio){setError('Native WebView audio device support unavailable.');return;}
    await stop();
    try{
      const reply=await native.data_av_begin({
        project_id:projectId,take_id:item.take_id,
        take_document_sha256:item.take_document_sha256,
        listener_path:listener,first_sample:first,direction,
      });
      if(reply?.status==='DENIED'){setNote('Native audition was not approved.');return;}
      if(reply?.format!==FORMAT||reply.status!=='READY'||
         reply.ffmpeg_runtime_required!==false||
         reply.take_document_sha256!==item.take_document_sha256||
         reply.listener_path!==listener||
         reply.direction!==direction||
         !Number.isSafeInteger(reply.approved_first_sample)||
         !Number.isSafeInteger(reply.last_sample_exclusive))
        throw Error('Native Digital Take approval was not source-bound');
      const st=controller.current;
      st.ticket=reply.session_id;st.first=reply.approved_first_sample;
      st.last=reply.last_sample_exclusive;
      st.cursor=first;
      st.context=new Audio({sampleRate:RATE});
      await st.context.resume();
      st.generation++;
      st.nextAudioAt=st.context.currentTime+0.08;
      st.active=true;setPlaying(true);
      queueAudio(st.generation);
    }catch(e){setError(e.message);await stop();}
  }

  useEffect(()=>{
    if(!playing)return;
    const interval=setInterval(()=>queueAudio(controller.current.generation),45);
    return ()=>clearInterval(interval);
  },[playing,native,direction,item]);

  return <section className="card" aria-label="Data-first native A/V preview">
    <h2>Native Film Time & 3D sound</h2>
    <p className="fineprint">Audition immutable OpenUSD Digital Takes directly.
      Sound is evaluated from time-addressed source signals and scene positions.
      No FFmpeg, BWF bounce, MP4 proxy, full-film RAM load, or approved final
      2D presentation is involved.</p>
    {!native&&<p role="status">Open this workspace in installed NVP to use
      native audio permission and the OS sound device.</p>}
    {error&&<p role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    <label>Frozen Digital Take
      <select aria-label="Native frozen Digital Take" value={takeId}
        disabled={playing} onChange={e=>setTakeId(e.target.value)}>
        {!takes.length&&<option value="">No frozen Digital Takes in this project</option>}
        {takes.map(x=><option key={x.take_id} value={x.take_id}>
          {x.take_id}</option>)}
      </select>
    </label>
    <label>3D listener / virtual microphone
      <select aria-label="Native spatial listener" value={listener}
        disabled={playing} onChange={e=>setListener(e.target.value)}>
        {(item?.listeners||[]).map(p=><option key={p} value={p}>{p}</option>)}
      </select>
    </label>
    <label>48-kHz source sample position
      <input aria-label="Native source sample seek" value={sourceSample}
        disabled={playing} onChange={e=>setSourceSample(e.target.value)}
        inputMode="numeric"/>
    </label>
    <label>Sound direction
      <select aria-label="Native sound direction" disabled={playing}
        value={direction} onChange={e=>setDirection(e.target.value)}>
        <option value="forward">Forward</option>
        <option value="reverse">Reverse</option>
      </select>
    </label>
    <div className="actions">
      <button disabled={!native||!item||!listener||playing}
        onClick={begin}>Approve and audition 3D source sound</button>
      <button disabled={!controller.current.ticket}
        onClick={stop}>Stop and revoke native audition</button>
    </div>
    {scene&&<section aria-label="Current frozen USD scene state">
      <h3>World state at requested Film Time</h3>
      <p className="fineprint">Native OpenUSD spatial descriptors, not
        a flattened movie or inferred sound-event causes.</p>
      <ul>
        {(scene.scene?.objects||[]).slice(0,16).map(x=>
          <li key={x.path}>{x.path}: {x.world_translation
            .map(v=>v.toFixed(2)).join(', ')} m</li>)}
      </ul>
      <p className="fineprint">{scene.spatial_audio?.bindings?.length||0}
        spatial audio source(s) active at this moment.</p>
    </section>}
    <p className="fineprint">This first dry spatial mixer includes source
      panning and distance. Real room occlusion, HRTF, reflections and
      photoreal 3D visual presentation require further native acceptance.</p>
  </section>;
}
