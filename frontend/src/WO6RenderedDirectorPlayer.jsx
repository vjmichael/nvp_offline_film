import React,{useEffect,useRef,useState} from 'react';

// WO6-07F: NVP native CPU OpenUSD picture pixels + ORIGINAL source PCM.
// WebAudio is the ONLY timebase: a missing frame/audio chunk stops playback
// instead of silently skipping or falsely counting a finished 24fps movie.
// No autoplay, native source write, model permission or final DCP proof.
const KIND='nvp.wo6_07f.actual_rendered_frame_pcm_window.v1';
const CAT='nvp.wo6_07e.original_source_review_catalog.v1';
const RATE=24;
const WINDOW=6;
const LEAD=0.30;
const MAX_CACHED=4;
const FRAMETICK=294000000; // TICKS_PER_SECOND / 24

export default function WO6RenderedDirectorPlayer({projectId}){
  const [catalog,setCatalog]=useState(null);
  const [editId,setEditId]=useState('');
  const [timelineId,setTimelineId]=useState('');
  const [frameInput,setFrameInput]=useState('0');
  const [status,setStatus]=useState('idle');
  const [message,setMessage]=useState('');
  const [shown,setShown]=useState(null);
  const [presented,setPresented]=useState(0);
  const [measured,setMeasured]=useState(null);
  const seq=useRef(0);
  const frames=useRef(new Map());
  const windows=useRef(new Map());
  const ctx=useRef(null);
  const nodes=useRef([]);
  const raf=useRef(null);
  const playing=useRef(null);
  const fetching=useRef(false);
  const starting=useRef(false);
  const native=()=>window.pywebview?.api;
  const edit=catalog?.edits?.find(x=>x.edit_id===editId);
  const timeline=catalog?.timelines?.find(x=>x.timeline_id===timelineId);
  const total=edit?Number(BigInt(edit.duration_tick)/BigInt(FRAMETICK)):0;

  function closeAudio(){
    if(raf.current!==null){
      cancelAnimationFrame(raf.current);raf.current=null;
    }
    for(const node of nodes.current){
      try{node.stop()}catch(_){}
      try{node.disconnect()}catch(_){}
    }
    nodes.current=[];
    const old=ctx.current;ctx.current=null;
    if(old){try{void old.close()}catch(_){}}
  }
  function reset(reason='idle'){
    seq.current++;
    closeAudio();
    playing.current=null;
    fetching.current=false;
    starting.current=false;
    frames.current.clear();
    windows.current.clear();
    setShown(null);
    setPresented(0);
    setMeasured(null);
    setStatus(reason);
  }
  useEffect(()=>{
    let alive=true;
    async function discover(){
      try{
        if(typeof native()?.wo6_07e_source_review_catalog!=='function')
          throw new Error('Installed NVP original source catalog unavailable');
        const data=await native().wo6_07e_source_review_catalog(projectId);
        if(!alive)return;
        if(data?.format!==CAT||data.project_id!==projectId||
            data.native_worker_authorized!==false)
          throw new Error('Original project source catalog was not verified');
        setCatalog(data);
        setEditId(data.edits?.[0]?.edit_id||'');
        setTimelineId('');
        setMessage('');
      }catch(e){if(alive)setMessage(String(e?.message||e))}
    }
    void discover();
    window.addEventListener('pywebviewready',discover);
    return ()=>{
      alive=false;
      seq.current++;
      closeAudio();
      window.removeEventListener('pywebviewready',discover);
    };
  },[projectId]);

  function changeSelection(field,value){
    reset();
    setMessage('');
    if(field==='edit')setEditId(value);
    if(field==='timeline')setTimelineId(value);
    if(field==='frame')setFrameInput(value);
  }

  function request(start,count){
    return {
      project_id:projectId,edit_id:edit.edit_id,
      edit_revision:edit.edit_revision,edit_sha256:edit.edit_sha256,
      first_frame:start,count,camera_path:null,
      sound_timeline_id:timeline?.timeline_id||null,
      sound_timeline_revision:timeline?.revision||null,
      sound_timeline_sha256:timeline?.sha256||null,
    };
  }
  async function loadWindow(start,token){
    if(token!==seq.current||!edit)return null;
    if(windows.current.has(start))return windows.current.get(start);
    const count=Math.min(WINDOW,total-start);
    if(count<1)return null;
    const asked=request(start,count);
    const response=await native().wo6_07f_rendered_av_window(asked);
    if(token!==seq.current)return null;
    if(response?.format!==KIND||response.project_id!==projectId||
        response.edit_sha256!==asked.edit_sha256||
        response.first_frame_zero!==start||
        response.count!==count||response.images?.length!==count||
        response.source_audio_rate!==48000||
        response.actual_audio_sample_count!==2000*count||
        response.real_original_usd_pixels_rendered!==true||
        response.native_worker_authorized!==false||
        response.source_modified!==false||
        response.film_delivered!==false||
        !response.source_audio_wav_data_url?.startsWith('data:audio/wav;base64,'))
      throw new Error('Native rendered picture/PCM count or source proof failed');
    for(let j=0;j<count;j++){
      const image=response.images[j];
      if(image.output_frame_zero!==start+j||
          image.output_film_time_tick!==String((start+j)*FRAMETICK)||
          image.actual_rasterized_triangles<1||
          !image.frame_image_data_url?.startsWith('data:image/png;base64,'))
        throw new Error('Unrendered or misaligned 3D source picture frame');
      // Browser decoding must be complete before a real audio clock plays.
      if(typeof Image!=='undefined'){
        const decoded=new Image();
        decoded.src=image.frame_image_data_url;
        if(typeof decoded.decode==='function')await decoded.decode();
      }
      if(token!==seq.current)return null;
      frames.current.set(start+j,image);
    }
    windows.current.set(start,response);
    return response;
  }

  async function prepare(){
    if(!edit||starting.current)return;
    reset('buffering');
    const token=seq.current;
    starting.current=true;
    try{
      if(!/^(0|[1-9][0-9]{0,6})$/.test(frameInput))
        throw new Error('Exact zero-based rendered frame required');
      const start=Number(frameInput);
      if(!Number.isSafeInteger(start)||start>=total)
        throw new Error('Selected original edit has no such output frame');
      await loadWindow(start,token);
      if(start+WINDOW<total)await loadWindow(start+WINDOW,token);
      if(token!==seq.current)return;
      setStatus('ready');
      setMessage('Real source pixels and frame-locked PCM are prebuffered. Playback starts only when you press Play.');
      playing.current={start,next:start+WINDOW*2,last:start-1,
        t0:null,token,scheduled:new Set()};
    }catch(e){
      if(token===seq.current){
        closeAudio();setStatus('error');setMessage(String(e?.message||e));
      }
    }finally{starting.current=false}
  }

  async function schedule(packet,session){
    if(!ctx.current||seq.current!==session.token)return;
    const encoded=packet.source_audio_wav_data_url.split(',',2)[1];
    const chars=atob(encoded);
    const bytes=new Uint8Array(chars.length);
    for(let i=0;i<chars.length;i++)bytes[i]=chars.charCodeAt(i);
    const decoded=await ctx.current.decodeAudioData(bytes.buffer.slice(0));
    if(seq.current!==session.token)return;
    if(decoded.numberOfChannels!==1||
        Math.abs(decoded.duration-packet.count/RATE)>0.002)
      throw new Error('Audio device decoded duration differs from original exact 48k source frame count');
    const when=session.t0+(packet.first_frame_zero-session.start)/RATE;
    if(when<ctx.current.currentTime+0.025)
      throw new Error('Audio-clock buffering underrun before native source picture was ready');
    const node=ctx.current.createBufferSource();
    node.buffer=decoded;
    node.connect(ctx.current.destination);
    node.start(when);
    nodes.current.push(node);
    session.scheduled.add(packet.first_frame_zero);
  }

  function fault(message){
    closeAudio();
    playing.current=null;
    setStatus('underrun');
    setMessage(message);
  }

  async function pump(session){
    if(fetching.current||seq.current!==session.token||!playing.current)return;
    fetching.current=true;
    try{
      while(session.next<total&&seq.current===session.token&&playing.current){
        // Keep at most four windows: consumed image frames may be discarded
        // after their exact audio time, never in advance of the sound clock.
        const latest=Math.max(0,session.last);
        if(session.next-latest>WINDOW*(MAX_CACHED-1))break;
        const start=session.next;
        const packet=await loadWindow(start,session.token);
        if(!packet||seq.current!==session.token)return;
        await schedule(packet,session);
        session.next=start+packet.count;
      }
    }catch(e){
      if(seq.current===session.token)fault(
        'Playback interrupted: '+String(e?.message||e)+'. No frames were silently skipped.');
    }finally{fetching.current=false}
  }

  function tick(session){
    if(!playing.current||seq.current!==session.token||!ctx.current)return;
    const seconds=ctx.current.currentTime-session.t0;
    if(seconds>=0){
      const offset=Math.floor(seconds*RATE+1e-8);
      const target=session.start+offset;
      if(target>=total){
        closeAudio();playing.current=null;setStatus('completed');
        setMessage('Reached the selected source edit end. Only this desktop source-preview session was observed; no film acceptance granted.');
        return;
      }
      if(target>session.last){
        if(target!==session.last+1){
          fault('Presentation clock missed an original 24fps frame; playback stopped rather than skipping.');return;
        }
        const frame=frames.current.get(target);
        if(!frame||!session.scheduled.has(
              session.start+Math.floor((target-session.start)/WINDOW)*WINDOW)){
          fault('Rendered picture or original PCM buffering underrun; playback stopped.');return;
        }
        session.last=target;
        setShown(frame);
        setPresented(target-session.start+1);
        if((target-session.start)%WINDOW===WINDOW-1){
          const old=target-WINDOW+1;
          if(windows.current.has(old)){
            windows.current.delete(old);
            for(let i=old;i<old+WINDOW;i++)frames.current.delete(i);
          }
        }
      }
      if(session.next<total)void pump(session);
    }
    if(playing.current&&seq.current===session.token)
      raf.current=requestAnimationFrame(()=>tick(session));
  }

  async function play(){
    const session=playing.current;
    if(!session||status!=='ready'||!windows.current.size)return;
    try{
      const factory=window.AudioContext||window.webkitAudioContext;
      if(!factory)throw new Error('Native WebView2 WebAudio clock unavailable');
      ctx.current=new factory({sampleRate:48000});
      await ctx.current.resume();
      session.t0=ctx.current.currentTime+LEAD;
      const keys=[...windows.current.keys()].sort((a,b)=>a-b);
      for(const key of keys)await schedule(windows.current.get(key),session);
      setStatus('playing');setMessage('Playing actual CPU-rendered OpenUSD pixels to the original PCM audio clock. No skipped frames allowed.');
      raf.current=requestAnimationFrame(()=>tick(session));
      void pump(session);
    }catch(e){fault('Audio source playback failed: '+String(e?.message||e))}
  }
  return <section aria-label="WO6 rendered OpenUSD and source PCM audio-clock preview">
    <h3>Rendered 3D original edit + source sound</h3>
    <p>Real OpenUSD source geometry/camera/lights become preview pixels
      through NVP's CPU scene-linear raster. Original 48kHz PCM is paired
      at exact 24fps frame offsets. This is uncalibrated preview—not
      Hydra lighting parity, a finished movie, or physical 24fps acceptance.</p>
    <label>Committed source editorial cut<select value={editId}
      onChange={e=>changeSelection('edit',e.target.value)}
      disabled={status==='playing'||status==='buffering'}>
      {catalog?.edits?.map(x=><option value={x.edit_id} key={x.edit_id}>
        {x.edit_id} · {x.segment_count} segments</option>)}
    </select></label>
    <label>Original sound timeline<select value={timelineId}
      onChange={e=>changeSelection('timeline',e.target.value)}
      disabled={status==='playing'||status==='buffering'}>
      <option value="">Use original Take soundtrack per cut</option>
      {catalog?.timelines?.map(x=><option value={x.timeline_id} key={x.timeline_id}>
        {x.timeline_id} · rev {x.revision}</option>)}
    </select></label>
    <label>Start at zero-based output frame<input inputMode="numeric"
      value={frameInput} disabled={status==='playing'||status==='buffering'}
      onChange={e=>changeSelection('frame',e.target.value)}/></label>
    <div className="actions">
      <button type="button" onClick={prepare} disabled={!edit||
        status==='playing'||status==='buffering'}>Pre-render first two A/V windows</button>
      <button type="button" onClick={play} disabled={status!=='ready'}>
        Play with audio clock</button>
      <button type="button" onClick={()=>reset('stopped')}
        disabled={!['playing','buffering','ready','underrun'].includes(status)}>
        Stop and clear native preview</button>
    </div>
    <p role="status">Playback: {status}. {message}</p>
    <p>Frames presented by preview clock: {presented}.
      Full 24fps sustained acceptance: not certified.</p>
    {shown&&<figure>
      <img src={shown.frame_image_data_url} alt={
        'Genuinely rendered original OpenUSD scene at output frame '+shown.output_frame_zero}
        width="640" height="360"/>
      <figcaption>Output frame {shown.output_frame_zero};
        original Take {shown.source_take_id}, segment {shown.source_segment_id}.
        Image SHA {shown.frame_png_sha256}. Preview color uncalibrated.</figcaption>
    </figure>}
  </section>;
}
