import React,{useCallback,useEffect,useRef,useState} from 'react';
import {filmTimeClock,TICKS_PER_SECOND} from './filmTimeClock.js';

// INDEX-TIME-09. This is a temporary review proxy, NOT a captured original.
// A/V timing is driven entirely by the media element's *single native mux
// clock*, not separate JS audio/picture timers. Video is H.264/AAC derived
// at review-only 24fps/48kHz; exact VFR source/FilmIndex is never modified.
const FORMAT='nvp.index_time09.native_av_host.v1';
const MAX_SIZE=160*1024*1024;
const MAX_CHUNK=1024*1024;
const SHA=/^[0-9a-f]{64}$/;
const STATUS=['QUEUED','PREPARING'];

function hex(bytes){
  return [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
function decode64(text){
  const bytes=atob(text);
  const result=new Uint8Array(bytes.length);
  for(let i=0;i<bytes.length;i++)result[i]=bytes.charCodeAt(i);
  return result;
}
function jumpTick(value,delta){
  const tick=BigInt(value)+BigInt(delta)*TICKS_PER_SECOND;
  return String(tick<0n?0n:tick);
}
function secondsFromTick(tick){
  // The complete source review is <=1200s, so only a bounded difference
  // is sent through Number to HTMLMediaElement.currentTime.
  return Number(BigInt(tick)/TICKS_PER_SECOND)+
    Number(BigInt(tick)%TICKS_PER_SECOND)/Number(TICKS_PER_SECOND);
}
function frameClock(start,seconds){
  // Display purpose only, never a FilmIndex source editorial position.
  const millis=BigInt(Math.round(Math.max(0,seconds)*1000));
  return filmTimeClock(BigInt(start)+millis*(TICKS_PER_SECOND/1000n));
}

export default function SynchronizedAssemblyReview({projectId,edit,clips,native,onInspect}){
  const player=useRef(null);
  const generation=useRef(0);
  const ticket=useRef(null);
  const url=useRef(null);
  const [filmTick,setFilmTick]=useState(clips[0]?.film_start_tick||'0');
  const [review,setReview]=useState(null);
  const [src,setSrc]=useState(null);
  const [status,setStatus]=useState('');
  const [error,setError]=useState('');
  const [preparing,setPreparing]=useState(false);
  const [downloading,setDownloading]=useState(false);
  const [downloaded,setDownloaded]=useState(0);
  const [playhead,setPlayhead]=useState(0);
  const [playing,setPlaying]=useState(false);

  const revoke=useCallback(()=>{
    generation.current++;
    if(ticket.current){
      const previous=ticket.current;
      ticket.current=null;
      Promise.resolve(native.stop_synchronized_av_review(previous)).catch(()=>{});
    }
    if(player.current)player.current.pause();
    if(url.current){
      URL.revokeObjectURL(url.current);
      url.current=null;
    }
    setSrc(null);setReview(null);setPlaying(false);
    setPlayhead(0);setDownloaded(0);setPreparing(false);setDownloading(false);
  },[native]);

  useEffect(()=>{
    revoke();
    setFilmTick(clips[0]?.film_start_tick||'0');
    setStatus('');
    setError('');
    return revoke;
  },[projectId,edit.edit_id,edit.revision,edit.edit_document_sha256,revoke]);

  async function prepare(){
    if(preparing||downloading)return;
    revoke();
    const gen=generation.current;
    setPreparing(true);setError('');
    setStatus('Preparing a temporary synchronized picture-and-sound review…');
    try{
      const start=filmTick;
      const result=await native.start_synchronized_av_review({
        project_id:projectId,edit_id:edit.edit_id,
        edit_revision:edit.revision,
        edit_document_sha256:edit.edit_document_sha256,
        start_tick:start,
      });
      if(generation.current!==gen){
        if(result?.status==='QUEUED'&&typeof result.ticket_id==='string')
          Promise.resolve(native.stop_synchronized_av_review(result.ticket_id))
            .catch(()=>{});
        return;
      }
      if(result?.status==='DENIED'){
        setStatus('You cancelled review. The captured footage is unchanged.');
        return;
      }
      if(result?.format!==FORMAT||result.status!=='QUEUED'||
         result.project_id!==projectId||result.edit_id!==edit.edit_id||
         result.edit_revision!==edit.revision||
         result.edit_document_sha256!==edit.edit_document_sha256||
         result.original_modified!==false||result.master_approved!==false||
         typeof result.ticket_id!=='string'||
         !/^\d+$/.test(result.actual_start_tick||''))
        throw Error('Native picture-and-sound approval did not match the assembly.');
      ticket.current=result.ticket_id;
      setReview(result);
    }catch(err){
      if(generation.current===gen)setError(err.message);
    }finally{
      if(generation.current===gen)setPreparing(false);
    }
  }

  // The server never sends a file path. JS receives bounded verified chunks
  // and checks EACH SHA before constructing a temporary private Blob URL.
  useEffect(()=>{
    if(!review||!ticket.current||!native||url.current)return;
    let alive=true,busy=false;
    const gen=generation.current,token=ticket.current;
    async function poll(){
      if(!alive||busy||url.current)return;
      busy=true;
      try{
        const result=await native.poll_synchronized_av_review(token);
        if(!alive||gen!==generation.current||ticket.current!==token)return;
        if(result?.status==='RECOVERY_REQUIRED'||result?.status==='CANCELLED')
          throw Error('Native review was cancelled or needs worker recovery.');
        if(result?.format!==FORMAT)return;
        if(STATUS.includes(result.status)){
          setStatus('Preparing verified synchronized audio/video; originals remain untouched…');
          return;
        }
        if(result.status!=='READY'||
           result.project_id!==projectId||result.edit_id!==edit.edit_id||
           result.edit_revision!==edit.revision||
           result.edit_document_sha256!==edit.edit_document_sha256||
           result.original_modified!==false||result.master_approved!==false||
           !SHA.test(result.media_sha256||'')||
           !Number.isInteger(result.size_bytes)||
           result.size_bytes<256||result.size_bytes>MAX_SIZE||
           !/^\d+$/.test(result.actual_start_tick||'')){
          throw Error('Native A/V receipt disagreed with the frozen assembly.');
        }
        setDownloading(true);
        setStatus('Receiving a verified temporary picture-and-sound proxy…');
        let offset=0;
        const chunks=[];
        while(offset<result.size_bytes){
          const c=await native.get_synchronized_av_chunk(token,offset);
          if(!alive||gen!==generation.current||ticket.current!==token)return;
          if(c?.format!==FORMAT||c.status!=='VERIFIED_CHUNK'||
             c.ticket_id!==token||c.offset!==offset||
             c.total_size!==result.size_bytes||
             c.original_modified!==false||c.master_approved!==false||
             !SHA.test(c.sha256||'')||
             typeof c.data_base64!=='string')
            throw Error('Native preview chunk identity changed.');
          const data=decode64(c.data_base64);
          if(data.length>MAX_CHUNK||data.length===0||
             c.next_offset!==offset+data.length)
            throw Error('Native preview chunk broke its approved bounds.');
          if(!crypto?.subtle)
            throw Error('The native browser cannot verify preview media SHA.');
          const hash=hex(await crypto.subtle.digest('SHA-256',data));
          if(hash!==c.sha256)
            throw Error('Native preview chunk did not match its SHA256.');
          chunks.push(data);
          offset=c.next_offset;
          setDownloaded(offset);
        }
        const media=new Blob(chunks,{type:'video/mp4'});
        const all=await media.arrayBuffer();
        if(hex(await crypto.subtle.digest('SHA-256',all))!==result.media_sha256)
          throw Error('Complete native synchronized media does not match receipt SHA.');
        if(!alive||gen!==generation.current||ticket.current!==token)return;
        const object=URL.createObjectURL(media);
        if(url.current)URL.revokeObjectURL(url.current);
        url.current=object;
        setReview(result);
        setSrc(object);
        setStatus('Ready. Play picture and sound together on the native media clock.');
      }catch(e){
        if(alive&&gen===generation.current){
          setError(e.message);
          revoke();
        }
      }finally{
        busy=false;
        if(alive&&gen===generation.current)setDownloading(false);
      }
    }
    poll();
    const interval=setInterval(poll,1000);
    return ()=>{alive=false;clearInterval(interval);};
  },[native,review,projectId,edit.edit_id,edit.revision,
     edit.edit_document_sha256,revoke]);

  function changePlayhead(tick){
    revoke();
    setFilmTick(tick);
    setError('');
    setStatus('Playhead moved. Prepare a new preview from this position.');
  }
  function jump(delta){
    const next=jumpTick(filmTick,delta);
    changePlayhead(BigInt(next)>=BigInt(edit.duration_tick)
      ?edit.duration_tick:next);
  }
  function cut(direction){
    const current=BigInt(filmTick);
    const cuts=clips.map(c=>BigInt(c.film_start_tick))
      .filter(t=>direction>0?t>current:t<current)
      .sort((a,b)=>a<b?-1:a>b?1:0);
    if(cuts.length)changePlayhead(String(direction>0?cuts[0]:cuts[cuts.length-1]));
  }
  const progress=review?.size_bytes?
    Math.round(downloaded*100/review.size_bytes):0;
  return <section className="card" aria-label="Synchronized original footage review">
    <h3>Watch your assembly with sound</h3>
    <p className="fineprint">This viewer prepares an unapproved temporary
      H.264/AAC review movie from your original footage. The native video
      player keeps sound and picture synchronized. Your recordings and
      previous edits stay untouched.</p>
    <div style={{maxWidth:'100%',background:'#12151b',
      minHeight:'165px',display:'grid',placeItems:'center'}}>
      {src?<video ref={player} src={src} controls
        style={{width:'100%',maxHeight:'480px'}}
        aria-label="Temporary picture and synchronized sound preview"
        onPlay={()=>setPlaying(true)}
        onPause={()=>setPlaying(false)}
        onTimeUpdate={e=>{
          const seconds=e.currentTarget.currentTime;
          setPlayhead(seconds);
          if(review?.actual_start_tick){
            const tick=BigInt(review.actual_start_tick)+
              BigInt(Math.round(seconds*1000))*(TICKS_PER_SECOND/1000n);
            setFilmTick(String(tick>BigInt(edit.duration_tick)
              ?BigInt(edit.duration_tick):tick));
          }
        }}
        onError={()=>setError('The native media decoder refused this review proxy.')}
        />:<p style={{color:'#ddd',padding:'1rem'}}>
          {preparing||downloading?'Preparing a verified A/V playback proxy…':
          'Choose Prepare review to watch the assembled footage with sound.'}
        </p>}
    </div>
    {src&&<p className="fineprint">Native A/V playback clock:
      {' '}{frameClock(review.actual_start_tick,playhead)} ·
      source samples never modified · not an approved master</p>}
    <label>Film Time playhead · {filmTimeClock(filmTick)}
      <input aria-label="Seek A/V assembly" type="range"
        min="0" max="1000" step="1"
        value={Number(BigInt(filmTick)*1000n/BigInt(edit.duration_tick||'1'))}
        onChange={e=>changePlayhead(String(
          BigInt(e.target.value)*BigInt(edit.duration_tick)/1000n))}/>
    </label>
    <div className="actions" style={{display:'flex',gap:'0.4rem',flexWrap:'wrap'}}>
      <button onClick={()=>jump(-5)}>Back 5s</button>
      <button onClick={()=>cut(-1)}>Previous cut</button>
      <button onClick={()=>cut(1)}>Next cut</button>
      <button onClick={()=>jump(5)}>Forward 5s</button>
      <button onClick={()=>onInspect?.(filmTick)}>Inspect original frame</button>
    </div>
    <div className="actions">
      <button disabled={preparing||downloading}
        onClick={prepare}>{preparing?'Asking for native approval…':
          'Prepare synchronized review…'}</button>
      {src&&review?.review_duration_tick&&
        <button onClick={()=>{
          const end=BigInt(review.actual_start_tick)+
            BigInt(review.review_duration_tick);
          changePlayhead(String(end>BigInt(edit.duration_tick)
            ?BigInt(edit.duration_tick):end));
        }}>Continue from end of review</button>}
      {ticket.current&&<button onClick={()=>{
        revoke();setStatus('Review stopped; temporary audio/video is disposable.');
      }}>Stop and discard review</button>}
    </div>
    {downloading&&<p role="status">Checking private preview bytes: {progress}%</p>}
    {status&&<p role="status">{status}</p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">One approval covers up to 20 minutes of
      24fps picture with 48 kHz stereo sound. Original camera audio is
      used when available; silent source sections stay silent. The preview
      is a separate, compressed review derivative, not frame-accurate
      final conform. Long movies continue in additional bounded sections.</p>
  </section>;
}
