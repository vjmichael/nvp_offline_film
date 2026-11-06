import React,{useCallback,useEffect,useRef,useState} from 'react';
import {filmTimeClock,TICKS_PER_SECOND} from './filmTimeClock.js';

// INDEX-TIME-09. This is a temporary review proxy, NOT a captured original.
// A/V timing is driven entirely by the media element's *single native mux
// clock*, not separate JS audio/picture timers. Video is H.264/AAC derived
// at review-only 24fps/48kHz; exact VFR source/FilmIndex is never modified.
const FORMAT='nvp.index_time09.native_av_host.v1';
const MAX_SIZE=160*1024*1024;
const SHA=/^[0-9a-f]{64}$/;
const STATUS=['QUEUED','PREPARING'];

function jumpTick(value,delta){
  const tick=BigInt(value)+BigInt(delta)*TICKS_PER_SECOND;
  return String(tick<0n?0n:tick);
}
function frameClock(start,seconds){
  // Display purpose only, never a FilmIndex source editorial position.
  const millis=BigInt(Math.round(Math.max(0,seconds)*1000));
  return filmTimeClock(BigInt(start)+millis*(TICKS_PER_SECOND/1000n));
}

export default function SynchronizedAssemblyReview({projectId,edit,clips,native,onInspect,api}){
  const player=useRef(null);
  const generation=useRef(0);
  const ticket=useRef(null);
  const url=useRef(null);
  const progressiveSession=useRef(null);
  const nextTicket=useRef(null);
  const [progressive,setProgressive]=useState(false);
  const [nextPending,setNextPending]=useState(null);
  const [nextReady,setNextReady]=useState(null);
  const [nextEnd,setNextEnd]=useState(false);
  const [waitingForNext,setWaitingForNext]=useState(false);
  const [autoResume,setAutoResume]=useState(false);
  const [filmTick,setFilmTick]=useState(clips[0]?.film_start_tick||'0');
  const [review,setReview]=useState(null);
  const [src,setSrc]=useState(null);
  const [status,setStatus]=useState('');
  const [error,setError]=useState('');
  const [preparing,setPreparing]=useState(false);
  const [playhead,setPlayhead]=useState(0);
  const [playing,setPlaying]=useState(false);
  const [allClips,setAllClips]=useState([]);
  const [loadingManifest,setLoadingManifest]=useState(true);
  const [manifestError,setManifestError]=useState('');
  const fullManifest=allClips.length===edit.clip_count &&
    allClips.every((c,i)=>c.ordinal===i);

  // A film editor may show only 40 clips on its initial browsing page.
  // The playback cut map MUST use the complete immutable edit, not its
  // partial viewport. Only bounded metadata is loaded, never source video.
  useEffect(()=>{
    let live=true;
    setAllClips([]);setManifestError('');
    setLoadingManifest(true);
    if(edit.clip_count>256||edit.clip_count<1){
      setManifestError('This review supports 1–256 original source clips.');
      setLoadingManifest(false);
      return ()=>{live=false;};
    }
    if(clips.length===edit.clip_count&&
       clips.every((c,i)=>c.ordinal===i)){
      setAllClips(clips);setLoadingManifest(false);
      return ()=>{live=false;};
    }
    if(typeof api!=='function'){
      setManifestError('The full saved original source edit is unavailable.');
      setLoadingManifest(false);
      return ()=>{live=false;};
    }
    async function load(){
      const rows=[];
      try{
        while(rows.length<edit.clip_count){
          const params=new URLSearchParams({
            revision:String(edit.revision),
            expected_edit_sha256:edit.edit_document_sha256,
            after_ordinal:String(rows.length-1),
            limit:'100',
          });
          const page=await api('/projects/'+encodeURIComponent(projectId)+
            '/film-time/edits/'+encodeURIComponent(edit.edit_id)+
            '/clips?'+params);
          if(!live)return;
          if(page?.format!=='nvp.index_time05.editor_source_read.v1'||
             page.status!=='INDEXED_EDIT_CLIPS'||
             page.project_id!==projectId||
             page.edit_id!==edit.edit_id||
             page.edit_revision!==edit.revision||
             page.edit_document_sha256!==edit.edit_document_sha256||
             page.clip_count!==edit.clip_count||
             page.original_media_read!==false||
             !Array.isArray(page.clips)||page.clips.length===0||
             page.clips.some((c,i)=>c.ordinal!==rows.length+i))
            throw Error('The complete indexed edit manifest changed during review.');
          rows.push(...page.clips);
          if(rows.length<edit.clip_count &&
             page.next_after_ordinal!==rows.length-1)
            throw Error('Saved source cut pagination stopped unexpectedly.');
        }
        if(rows.length!==edit.clip_count)
          throw Error('Incomplete saved source clip manifest.');
        if(live)setAllClips(rows);
      }catch(e){if(live)setManifestError(e.message);}
      finally{if(live)setLoadingManifest(false);}
    }
    load();
    return ()=>{live=false;};
  },[api,projectId,edit.edit_id,edit.revision,
     edit.edit_document_sha256,edit.clip_count]);

  const revoke=useCallback(()=>{
    generation.current++;
    const previousSession=progressiveSession.current;
    const previousTicket=ticket.current;
    progressiveSession.current=null;
    ticket.current=null;
    nextTicket.current=null;
    if(previousSession){
      Promise.resolve(native.stop_progressive_av_review(previousSession)).catch(()=>{});
    }else if(previousTicket){
      Promise.resolve(native.stop_synchronized_av_review(previousTicket)).catch(()=>{});
    }
    setProgressive(false);
    setNextPending(null);
    setNextReady(null);
    setNextEnd(false);
    setWaitingForNext(false);
    setAutoResume(false);
    if(player.current)player.current.pause();
    if(url.current){
      if(url.current.startsWith('blob:'))URL.revokeObjectURL(url.current);
      url.current=null;
    }
    setSrc(null);setReview(null);setPlaying(false);
    setPlayhead(0);setPreparing(false);
  },[native]);

  useEffect(()=>{
    revoke();
    setFilmTick(clips[0]?.film_start_tick||'0');
    setStatus('');
    setError('');
    return revoke;
  },[projectId,edit.edit_id,edit.revision,edit.edit_document_sha256,revoke]);

  async function prepare(progressiveMode=false){
    if(preparing||!fullManifest)return;
    if(progressiveMode&&typeof native?.start_progressive_av_review!=='function'){
      setError('This native NVP build does not support progressive review.');
      return;
    }
    revoke();
    const gen=generation.current;
    setPreparing(true);setError('');
    setStatus('Preparing a temporary synchronized picture-and-sound review…');
    try{
      const start=filmTick;
      const result=await (progressiveMode
        ?native.start_progressive_av_review
        :native.start_synchronized_av_review).call(native,{
        project_id:projectId,edit_id:edit.edit_id,
        edit_revision:edit.revision,
        edit_document_sha256:edit.edit_document_sha256,
        start_tick:start,
      });
      if(generation.current!==gen){
        if(result?.status==='QUEUED'&&progressiveMode&&
           typeof result.progressive_session_id==='string')
          Promise.resolve(native.stop_progressive_av_review(
            result.progressive_session_id)).catch(()=>{});
        else if(result?.status==='QUEUED'&&typeof result.ticket_id==='string')
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
         !/^\d+$/.test(result.actual_start_tick||'')||
         (progressiveMode&&
          (typeof result.progressive_session_id!=='string'||
           result.progressive_session_id.length<20||
           !/^\d+$/.test(result.progressive_limit_tick||''))))
        throw Error('Native picture-and-sound approval did not match the assembly.');
      ticket.current=result.ticket_id;
      if(progressiveMode){
        progressiveSession.current=result.progressive_session_id;
        setProgressive(true);
      }
      setReview(result);
    }catch(err){
      if(generation.current===gen)setError(err.message);
    }finally{
      if(generation.current===gen)setPreparing(false);
    }
  }

  // INDEX-TIME-09 bounded-memory playback: verified MP4 stays in NVP's
  // private scratch directory. The native media element requests <=1MiB
  // HTTP 206 byte ranges through the opaque, per-window review ticket.
  // No 160MiB JS Blob or full ArrayBuffer is ever created.
  useEffect(()=>{
    if(!review||!ticket.current||!native||url.current)return;
    let alive=true,busy=false;
    const gen=generation.current,token=ticket.current;
    async function poll(){
      if(!alive||busy||gen!==generation.current||ticket.current!==token)return;
      busy=true;
      try{
        const result=await native.poll_synchronized_av_review(token);
        if(!alive||gen!==generation.current||ticket.current!==token)return;
        if(result?.status==='RECOVERY_REQUIRED'||result?.status==='CANCELLED')
          throw Error('Native review was cancelled or needs worker recovery.');
        if(result?.format!==FORMAT)
          throw Error('Untrusted native review response.');
        if(STATUS.includes(result.status)){
          setStatus('Rendering a bounded, disk-backed original-footage review…');
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
        const descriptor=await native.get_synchronized_av_stream(token);
        if(!alive||gen!==generation.current||ticket.current!==token)return;
        const expected='/api/native-av-review/'+encodeURIComponent(token)+'/media';
        if(descriptor?.format!==FORMAT||
           descriptor.status!=='VERIFIED_STREAM'||
           descriptor.url!==expected||
           descriptor.media_sha256!==result.media_sha256||
           descriptor.total_size!==result.size_bytes||
           descriptor.content_type!=='video/mp4'||
           descriptor.original_modified!==false||
           descriptor.master_approved!==false)
          throw Error('Disk-backed verified media ticket was refused.');
        url.current=descriptor.url;
        setReview(result);
        setSrc(descriptor.url);
        setStatus('Ready. Sound and picture share one native clock; video stays on disk.');
      }catch(e){
        if(alive&&gen===generation.current){
          setError(e.message);
          revoke();
        }
      }finally{busy=false;}
    }
    poll();
    const interval=setInterval(poll,900);
    return ()=>{alive=false;clearInterval(interval);};
  },[native,review,projectId,edit.edit_id,edit.revision,
     edit.edit_document_sha256,revoke]);

  function changePlayhead(tick){
    revoke();
    setFilmTick(tick);
    setError('');
    setStatus('Playhead moved outside this review. Prepare a new section from this position.');
  }
  function seekToTick(tick){
    // An approved, SHA-checked section is already a seekable MP4 on private
    // disk. Reuse its native A/V clock rather than rerendering source footage
    // on every timeline click, cut jump or small scrub.
    if(src&&player.current&&review?.actual_start_tick!=null&&
       review?.review_duration_tick!=null){
      const start=BigInt(review.actual_start_tick);
      const length=BigInt(review.review_duration_tick);
      const target=BigInt(tick);
      if(length>0n&&target>=start&&target<start+length){
        // Only the bounded <=20 minute delta converts to Number; absolute
        // film ticks remain BigInt to avoid losing long-form positions.
        const seconds=Number(target-start)/Number(TICKS_PER_SECOND);
        player.current.currentTime=seconds;
        setPlayhead(seconds);
        setFilmTick(String(target));
        setStatus('Seeking within this prepared section. Original footage unchanged.');
        setError('');
        return;
      }
    }
    changePlayhead(tick);
  }
  function jump(delta){
    const next=jumpTick(filmTick,delta);
    seekToTick(BigInt(next)>=BigInt(edit.duration_tick)
      ?edit.duration_tick:next);
  }
  function cut(direction){
    const current=BigInt(filmTick);
    const cuts=allClips.map(c=>BigInt(c.film_start_tick))
      .filter(t=>direction>0?t>current:t<current)
      .sort((a,b)=>a<b?-1:a>b?1:0);
    if(cuts.length)seekToTick(String(direction>0?cuts[0]:cuts[cuts.length-1]));
  }
  return <section className="card" aria-label="Synchronized original footage review">
    <h3>Watch your assembly with sound</h3>
    {loadingManifest&&<p role="status">Checking every saved source cut…</p>}
    {manifestError&&<p role="alert">{manifestError}</p>}
    <p className="fineprint">This viewer prepares an unapproved temporary
      H.264/AAC review movie from your original footage. The native video
      player keeps sound and picture synchronized. Your recordings and
      previous edits stay untouched.</p>
    <div style={{maxWidth:'100%',background:'#12151b',
      minHeight:'165px',display:'grid',placeItems:'center'}}>
      {src?<video ref={player} src={src} controls preload="metadata" playsInline
        style={{width:'100%',maxHeight:'480px'}}
        aria-label="Temporary picture and synchronized sound preview"
        onPlay={()=>setPlaying(true)}
        onPause={()=>setPlaying(false)}
        onEnded={sectionEnded}
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
          {preparing?'Preparing a verified A/V playback proxy…':
          'Choose Prepare review to watch the assembled footage with sound.'}
        </p>}
    </div>
    {progressive&&nextReady&&
      <video aria-hidden="true" muted playsInline preload="metadata"
        src={nextReady.url} style={{display:'none'}} />}
    {src&&<p className="fineprint">Native A/V playback clock:
      {' '}{frameClock(review.actual_start_tick,playhead)} ·
      source samples never modified · not an approved master</p>}
    <label>Film Time playhead · {filmTimeClock(filmTick)}
      <input aria-label="Seek A/V assembly" type="range"
        min="0" max="1000" step="1"
        value={Number(BigInt(filmTick)*1000n/BigInt(edit.duration_tick||'1'))}
        onChange={e=>seekToTick(String(
          BigInt(e.target.value)*BigInt(edit.duration_tick)/1000n))}/>
    </label>
    <div className="actions" style={{display:'flex',gap:'0.4rem',flexWrap:'wrap'}}>
      <button onClick={()=>jump(-5)}>Back 5s</button>
      <button disabled={!fullManifest} onClick={()=>cut(-1)}>Previous cut</button>
      <button disabled={!fullManifest} onClick={()=>cut(1)}>Next cut</button>
      <button onClick={()=>jump(5)}>Forward 5s</button>
      <button onClick={()=>onInspect?.(filmTick)}>Inspect original frame</button>
    </div>
    <div className="actions">
      <button disabled={preparing||!fullManifest}
        onClick={()=>prepare(false)}>{preparing?'Asking for native approval…':
          'Prepare synchronized review…'}</button>
      {typeof native?.start_progressive_av_review==='function'&&
        <button disabled={preparing||!fullManifest}
          onClick={()=>prepare(true)}>Start progressive long-form review…</button> 
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
    {status&&<p role="status">{status}</p>}
    {error&&<p role="alert">{error}</p>}
    {progressive&&<p className="fineprint">
      Progressive review approval covers up to four hours of one exact saved
      edit, but only the current verified section and one next section may
      be present. Consecutive media-element files are not yet proven gapless.
    </p>}
    <p className="fineprint">Each review section contains up to 20 minutes of
      24fps picture with 48 kHz stereo sound. Original camera audio is
      used when available; silent source sections stay silent. Scrubbing and cut jumps inside a prepared section reuse its native A/V clock; leaving it asks for a new bounded section. The preview
      remains on private disk and the native player requests up to 1 MiB
      per verified byte range. The browser manages its own decoded buffer;
      an exact 256 MiB RAM ceiling is not yet independently enforced.
      This is not a final conform. Long films use further bounded sections.</p>
  </section>;
}
