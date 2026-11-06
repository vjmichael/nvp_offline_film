import React,{useEffect,useRef,useState} from 'react';
import {filmTimeClock,TICKS_PER_SECOND} from './filmTimeClock.js';

// Native-only, source-PTS picture review. The session decodes a short,
// explicitly approved bounded window; it never edits a recording or
// produces an approved master. One PNG is retained in JS memory at a time.
const FORMAT='nvp.index_time08.original_assembly_review.v1';
const MAX_IMAGE_DATA_URL=17*1024*1024;
const MAX_FRAMES=96;
const TICK_PER_MILLISECOND=TICKS_PER_SECOND/1000n;

function clampTick(value,duration){
  const tick=BigInt(value),last=BigInt(duration);
  return (tick<0n?0n:tick>last?last:tick).toString();
}
function toMilliseconds(ticks){
  const n=BigInt(ticks)/TICK_PER_MILLISECOND;
  // Expose long gaps explicitly as a black-frame pause, bounded to 5 s.
  return Number(n>5000n?5000n:n<1n?1n:n);
}
function scrubPercent(value,duration){
  const d=BigInt(duration);
  return Number(d===0n?0n:BigInt(value)*1000n/d);
}
function scrubTick(position,duration){
  return (BigInt(position)*BigInt(duration)/1000n).toString();
}

export default function FilmTimePlaybackPanel({
  projectId,edit,clips,native,onInspect,selection,
}){
  const [seekTick,setSeekTick]=useState(
    selection?.requested_film_tick||clips[0]?.film_start_tick||'0');
  const [ticket,setTicket]=useState(null);
  const [frames,setFrames]=useState([]);
  const [cursor,setCursor]=useState(0);
  const [picture,setPicture]=useState(null);
  const [playing,setPlaying]=useState(false);
  const [blank,setBlank]=useState(false);
  const [finished,setFinished]=useState(false);
  const [pending,setPending]=useState(false);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [status,setStatus]=useState('');
  const session=useRef(null);
  const generation=useRef(0);

  // Revision changes invalidate all old images and exact source receipts.
  useEffect(()=>{
    generation.current++;
    if(session.current && native){
      Promise.resolve(native.cancel_assembly_review(session.current)).catch(()=>{});
    }
    session.current=null;
    setTicket(null);setFrames([]);setCursor(0);setPicture(null);
    setPlaying(false);setBlank(false);setFinished(false);
    setPending(false);setLoading(false);setError('');setStatus('');
    setSeekTick(clips[0]?.film_start_tick||'0');
    return ()=>{
      generation.current++;
      if(session.current && native)
        Promise.resolve(native.cancel_assembly_review(session.current)).catch(()=>{});
    };
  },[projectId,edit.edit_id,edit.revision,edit.edit_document_sha256,native]);

  useEffect(()=>{
    if(selection?.edit_document_sha256===edit.edit_document_sha256 &&
       typeof selection.requested_film_tick==='string' && !ticket)
      setSeekTick(selection.requested_film_tick);
  },[selection,edit.edit_document_sha256,ticket]);

  async function start(){
    if(pending||!native)return;
    setError('');setStatus('');setPending(true);setPicture(null);
    setPlaying(false);setBlank(false);
    const generationId=++generation.current;
    if(session.current){
      try{await native.cancel_assembly_review(session.current);}catch{}
      session.current=null;
    }
    try{
      const begin=clampTick(seekTick,edit.duration_tick);
      if(BigInt(begin)>=BigInt(edit.duration_tick))
        throw new Error('Move the playhead before the end of the assembly.');
      const reply=await native.start_assembly_review({
        project_id:projectId,edit_id:edit.edit_id,
        edit_revision:edit.revision,
        edit_document_sha256:edit.edit_document_sha256,
        start_tick:begin,
      });
      if(generationId!==generation.current)return;
      if(reply?.status==='DENIED'){
        setStatus('Picture review was not approved. No source was changed.');
        return;
      }
      if(reply?.format!==FORMAT||reply.status!=='QUEUED'||
         reply.project_id!==projectId||reply.edit_id!==edit.edit_id||
         reply.edit_revision!==edit.revision||
         reply.edit_document_sha256!==edit.edit_document_sha256||
         reply.requested_film_tick!==begin||
         reply.original_modified!==false||
         reply.master_approved!==false||
         !Number.isInteger(reply.planned_frames)||
         reply.planned_frames<1||reply.planned_frames>MAX_FRAMES||
         typeof reply.ticket_id!=='string')
        throw new Error('Native source playback refused the expected edit identity.');
      session.current=reply.ticket_id;
      setTicket(reply.ticket_id);
      setFrames([]);setCursor(0);setFinished(false);
      setLoading(true);setPlaying(true);
      setStatus('Preparing verified review pictures from the original footage…');
    }catch(e){
      if(generationId===generation.current)setError(e.message);
    }finally{
      if(generationId===generation.current)setPending(false);
    }
  }

  useEffect(()=>{
    if(!ticket||!native)return;
    let live=true,busy=false;
    const expectedGeneration=generation.current;
    async function poll(){
      if(!live||busy)return;
      busy=true;
      try{
        const reply=await native.poll_assembly_review(ticket);
        if(!live||session.current!==ticket||
           generation.current!==expectedGeneration)return;
        if(reply?.status==='RECOVERY_REQUIRED'||
           reply?.status==='CANCELLED'){
          throw new Error(reply.status==='CANCELLED'
            ?'Review cancelled; original footage was not changed.'
            :'Native source review requires worker recovery before playback.');
        }
        if(reply?.format!==FORMAT||
           !['BUFFERING','READY','COMPLETE'].includes(reply.status)||
           reply.project_id!==projectId||reply.edit_id!==edit.edit_id||
           reply.edit_revision!==edit.revision||
           reply.edit_document_sha256!==edit.edit_document_sha256||
           reply.original_modified!==false||
           reply.master_approved!==false||
           !Number.isInteger(reply.ready_frames)||
           reply.ready_frames>MAX_FRAMES||
           !Array.isArray(reply.frames)||
           reply.frames.length!==reply.ready_frames||
           reply.frames.some((frame,i)=>frame.index!==i ||
             !/^\d+$/.test(frame.film_time_tick||'') ||
             !/^\d+$/.test(frame.film_end_tick||'') ||
             BigInt(frame.film_end_tick)<=BigInt(frame.film_time_tick)))
          throw new Error('Native playback metadata did not match the frozen edit.');
        setFrames(old=>{
          if(reply.frames.length<old.length||
             old.some((frame,i)=>
               JSON.stringify(frame)!==JSON.stringify(reply.frames[i]))){
            setError('Previously verified source frames changed during review.');
            setPlaying(false);
            return [];
          }
          return reply.frames.length===old.length?old:reply.frames;
        });
        setFinished(reply.status==='COMPLETE');
        setLoading(reply.ready_frames===0);
        setStatus(reply.status==='BUFFERING'
          ?'Buffering verified original video frames…'
          :reply.status==='COMPLETE'
            ?'Ready to review. These are unapproved preview pictures.'
            :'Playing verified original frames as they are decoded…');
      }catch(e){
        if(live&&session.current===ticket){
          setError(e.message);setPlaying(false);setLoading(false);
          session.current=null;setTicket(null);setPicture(null);
          Promise.resolve(native.cancel_assembly_review(ticket)).catch(()=>{});
        }
      }finally{busy=false;}
    }
    poll();
    const interval=setInterval(poll,600);
    return ()=>{live=false;clearInterval(interval);};
  },[ticket,native,projectId,edit.edit_id,edit.revision,
     edit.edit_document_sha256]);

  useEffect(()=>{
    if(!ticket||!frames[cursor]||!native)return;
    let live=true;
    const entry=frames[cursor];
    const expectedGeneration=generation.current;
    setPicture(null);setBlank(false);
    async function load(){
      try{
        const reply=await native.get_assembly_review_frame(ticket,cursor);
        if(!live||session.current!==ticket||
           generation.current!==expectedGeneration)return;
        if(reply?.format!==FORMAT||reply.status!=='VERIFIED_FRAME'||
           reply.project_id!==projectId||reply.edit_id!==edit.edit_id||
           reply.edit_revision!==edit.revision||
           reply.edit_document_sha256!==edit.edit_document_sha256||
           reply.index!==cursor||reply.source_pts!==entry.source_pts||
           reply.source_id!==entry.source_id||
           reply.source_frame_zero!==entry.source_frame_zero||
           reply.film_time_tick!==entry.film_time_tick||
           reply.film_end_tick!==entry.film_end_tick||
           reply.original_modified!==false||
           reply.master_approved!==false||
           !reply.image_data_url?.startsWith('data:image/png;base64,')||
           reply.image_data_url.length>MAX_IMAGE_DATA_URL)
          throw new Error('Source frame or PNG receipt disagreed with the frozen assembly.');
        setPicture(reply);
      }catch(e){
        if(live){setError(e.message);setPlaying(false);setPicture(null);}
      }
    }
    load();
    return ()=>{live=false;};
  },[native,ticket,cursor,frames,projectId,edit.edit_id,
     edit.revision,edit.edit_document_sha256]);

  useEffect(()=>{
    if(!playing||!picture||picture.index!==cursor||
       !frames[cursor]||blank)return;
    const entry=frames[cursor];
    const next=frames[cursor+1];
    if(!next&&!finished)return;
    let rest=null;
    const hold=toMilliseconds(
      BigInt(entry.film_end_tick)-BigInt(entry.film_time_tick));
    const timer=setTimeout(()=>{
      if(next){
        const gap=BigInt(next.film_time_tick)-BigInt(entry.film_end_tick);
        if(gap>0n){
          setBlank(true);
          rest=setTimeout(()=>{setBlank(false);setCursor(cursor+1);},
            toMilliseconds(gap));
        }else{
          setCursor(cursor+1);
        }
      }else{
        setPlaying(false);
        setStatus('Review section ended. Continue from the next Film Time position.');
      }
    },hold);
    return ()=>{clearTimeout(timer);if(rest!==null)clearTimeout(rest);};
  },[picture,playing,blank,cursor,frames,finished]);

  async function stop(){
    generation.current++;
    setPlaying(false);setPicture(null);setBlank(false);
    setFrames([]);setCursor(0);setTicket(null);setLoading(false);
    if(session.current){
      const token=session.current;
      session.current=null;
      try{await native.cancel_assembly_review(token);}catch{}
    }
    setStatus('Playback stopped; your original recordings remain unchanged.');
  }

  function movePlayhead(tick){
    const exact=clampTick(tick,edit.duration_tick);
    generation.current++;
    if(session.current){
      const obsolete=session.current;
      session.current=null;
      Promise.resolve(native.cancel_assembly_review(obsolete)).catch(()=>{});
    }
    setTicket(null);setFrames([]);setCursor(0);setPicture(null);
    setPlaying(false);setBlank(false);setFinished(false);setLoading(false);
    setError('');
    setSeekTick(exact);
    setStatus('Playhead moved. Review from here to show the exact original picture.');
  }
  function navigate(delta){
    const next=BigInt(seekTick)+BigInt(delta)*TICKS_PER_SECOND;
    movePlayhead(next);
  }
  function cut(direction){
    const here=BigInt(seekTick);
    const candidates=clips.map(c=>BigInt(c.film_start_tick))
      .filter(x=>direction>0?x>here:x<here)
      .sort((a,b)=>a<b?-1:a>b?1:0);
    if(candidates.length){
      movePlayhead(direction>0?candidates[0]:
        candidates[candidates.length-1]);
    }
  }

  const current=frames[cursor];
  const canContinue=current && finished &&
    BigInt(current.film_end_tick)<BigInt(edit.duration_tick);
  return <section className="card" aria-label="Non-destructive footage playback">
    <h3>Review your film assembly</h3>
    <p className="fineprint">Play, pause, scrub, and inspect your edits.
      NVP reads the frozen camera footage and makes temporary pictures.
      The source recordings and edit history cannot be overwritten here.</p>
    <figure aria-label="Original source film preview" style={{margin:'0'}}>
      <div style={{background:'#12151b',height:'min(48vw,350px)',
        minHeight:'170px',display:'grid',placeItems:'center',
        overflow:'hidden',borderRadius:'0.45rem'}}>
        {picture&&!blank?<img
          src={picture.image_data_url} alt="Audited temporary original-camera review frame"
          style={{width:'100%',height:'100%',objectFit:'contain'}}/>:
          <span style={{color:'#ccc'}}>
            {blank?'Intentional gap · no recorded video placed here':
              loading?'Decoding verified original frames…':
              ticket?'Review picture loading…':
              'Choose Review & play to see your footage'}
          </span>}
      </div>
      <figcaption className="fineprint">
        {current?('Original '+current.source_id+
          ' · frame '+current.source_frame_zero+
          ' · PTS '+current.source_pts+
          ' · '+filmTimeClock(current.film_time_tick)):'No picture decoded'}
        {' '} · Temporary preview, not an approved film master
      </figcaption>
    </figure>
    <label>Film playhead · {filmTimeClock(seekTick)}
      <input aria-label="Scrub film assembly" type="range"
        min="0" max="1000" step="1"
        value={scrubPercent(seekTick,edit.duration_tick)}
        onChange={e=>movePlayhead(scrubTick(e.target.value,edit.duration_tick))}/>
    </label>
    <div className="actions" style={{display:'flex',flexWrap:'wrap',gap:'0.35rem'}}>
      <button onClick={()=>navigate(-5)}>Back 5s</button>
      <button onClick={()=>cut(-1)}>Previous cut</button>
      <button onClick={()=>cut(1)}>Next cut</button>
      <button onClick={()=>navigate(5)}>Forward 5s</button>
      <button onClick={()=>{setPlaying(false);onInspect?.(seekTick);}}>
        Inspect playhead</button>
    </div>
    <div className="actions" style={{display:'flex',flexWrap:'wrap',gap:'0.35rem'}}>
      <button disabled={pending} onClick={start}>
        {pending?'Requesting native approval…':
          ticket?'Review from playhead…':'Review & play original footage…'}</button>
      {ticket&&<>
        <button onClick={()=>setPlaying(value=>!value)}>
          {playing?'Pause':'Play'}</button>
        <button disabled={cursor<=0} onClick={()=>{
          setPlaying(false);setCursor(x=>x-1);
        }}>Previous frame</button>
        <button disabled={cursor>=frames.length-1} onClick={()=>{
          setPlaying(false);setCursor(x=>x+1);
        }}>Next frame</button>
        <button onClick={stop}>Stop review</button>
      </>}
      {canContinue&&<button onClick={()=>movePlayhead(current.film_end_tick)}>
        Continue from section end</button>}
    </div>
    {ticket&&<p className="fineprint">
      Verified buffer: {frames.length} / {MAX_FRAMES} maximum original
      frames · {finished?'Section fully decoded':'Contained native decoding active'}
    </p>}
    {status&&<p role="status">{status}</p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">Playback approval is limited to one
      short, auditable native section. Long gaps display an empty frame;
      the player can skip directly to the next cut. No whole-film
      loading into RAM, and no background rendering or export.</p>
  </section>;
}
