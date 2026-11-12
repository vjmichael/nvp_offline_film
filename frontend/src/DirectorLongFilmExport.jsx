import React,{useEffect,useRef,useState} from 'react';
import './director-long-film-export.css';
import DirectorFilmDistribution from './DirectorFilmDistribution.jsx';

const ACTIVE=new Set(['queued','analyzing','rendering','verifying','finalizing']);
const formatSeconds=s=>{
  const n=Math.max(0,Number(s)||0);
  const h=Math.floor(n/3600),m=Math.floor(n/60)%60,x=Math.floor(n)%60;
  return (h?h+':':'')+(h?String(m).padStart(2,'0'):String(m))+
    ':'+String(x).padStart(2,'0');
};
async function call(url,method='GET',body,signal){
  const response=await fetch(url,{
    method,signal,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){
    const problem=await response.json().catch(()=>({}));
    throw Error(typeof problem.detail==='string'?problem.detail:
      'The native film operation could not be completed. Earlier verified reels remain safe.');
  }
  return response.json();
}
export default function DirectorLongFilmExport({movie,edit,disabled=false}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/long-film';
  const [jobs,setJobs]=useState([]);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [page,setPage]=useState(0);
  const alive=useRef(true);
  const duration=edit?.duration_seconds||0;
  const within=duration>30&&duration<=3*3600&&
    Math.abs(duration*24-Math.round(duration*24))<.0001;
  const hasActive=jobs.some(job=>ACTIVE.has(job.status));
  const latest=jobs[0]||null;

  const refresh=async(signal)=>{
    const results=await call(base,'GET',undefined,signal);
    if(alive.current)setJobs(results.jobs||[]);
  };
  useEffect(()=>{
    alive.current=true;setJobs([]);setError('');setNotice('');
    const c=new AbortController();setLoading(true);
    refresh(c.signal).catch(e=>{
      if(e.name!=='AbortError'&&alive.current)setError(e.message)
    }).finally(()=>{if(alive.current)setLoading(false)});
    return()=>{alive.current=false;c.abort()};
  },[base,movie.revision]);
  useEffect(()=>{
    if(!hasActive||!alive.current)return;
    let stopped=false;
    const interval=window.setInterval(()=>{
      call(base).then(value=>{
        if(!stopped&&alive.current)setJobs(value.jobs||[]);
      }).catch(e=>{if(!stopped&&alive.current)setError(e.message)});
    },1200);
    return()=>{stopped=true;window.clearInterval(interval)};
  },[hasActive,base]);

  async function act(jobId,kind){
    if(busy)return;
    const message=kind==='start'?
      'Render this entire saved film in verified segments? The source Takes remain unchanged, and the render can be stopped or explicitly resumed later.':
      kind==='resume'?
      'Resume the original approved film from its independently verified segments? Unfinished parts will be checked or remade.':
      'Stop this long-film render? Completed verified segments will be preserved for a later explicit resume.';
    if(!window.confirm(message))return;
    setBusy(true);setError('');setNotice('');
    try{
      let nativeApproval=null;
      if(movie.encrypted&&kind!=='cancel'){
        const api=window.pywebview?.api?.native_private_film_review;
        if(typeof api!=='function')throw new Error(
          'Protected film rendering requires the installed NVP native desktop window.');
        const preview=await call(base+'/review?expected_revision='+
          encodeURIComponent(edit.revision));
        const decision=await api(preview);
        if(!decision?.approved||!decision.native_approval_id){
          if(alive.current)setNotice('Native private-film authorization was declined.');
          return;
        }
        nativeApproval=decision.native_approval_id;
      }
      const path=kind==='start'?base+'/start':
        base+'/'+encodeURIComponent(jobId)+'/'+kind;
      await call(path,'POST',kind==='start'?
        {expected_revision:edit.revision,director_confirmed:true,
          native_approval_id:nativeApproval}:
        {director_confirmed:true,native_approval_id:nativeApproval});
      await refresh();
      if(alive.current)setNotice(kind==='start'?
        'Your long-film render has a durable source-bound work journal.':
        kind==='resume'?'Rendering resumed from verified work.':
        'Stop requested. The host will reconcile the active worker.');
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }

  if(!edit||duration<=30)return null;
  const canStart=within&&!disabled&&!hasActive&&!busy&&
    edit.revision>0&&edit.clips?.length>0&&!edit.missing_sources?.length;
  const phases={queued:'Queued for original-source rendering',
    analyzing:'Measuring the whole source soundtrack',
    rendering:'Rendering the original 3D scenes',
    verifying:'Independently checking a finished reel',
    finalizing:'Rechecking every reel and assembling the film index',
    completed:'Original-source film reels completed',
    cancelled:'Stopped by the director',
    interrupted:'Interrupted; ready for an explicit resume',
    failed:'One part did not finish its source checks'};
  const pages=latest?Math.ceil(latest.reels_total/12):0;
  const shown=Array.from({
    length:Math.max(0,Math.min(12,(latest?.reels_total||0)-page*12))
  },(_,i)=>page*12+i);
  return <section className="director-long-film" aria-label="Render a long film">
    <div className="director-long-head">
      <div><h3>Finish a Longer Film</h3>
        <p className="film-muted">Build your saved film in small,
          independently checked picture-and-sound reels. All clips follow
          one continuous film clock, and NVP preserves finished work
          across an interruption.</p></div>
      <span>Up to 3 hours · Source-based</span>
    </div>
    <div className="director-long-facts">
      <div><small>Edited length</small><strong>{formatSeconds(duration)}</strong></div>
      <div><small>Picture</small><strong>24fps working SDR</strong></div>
      <div><small>Sound</small><strong>48kHz stereo</strong></div>
      <div><small>Original Takes</small><strong>Preserved</strong></div>
    </div>
    {movie.encrypted&&<p className="director-long-warning" role="status">
      Protected original film: recording and reel outputs remain AES-GCM
      encrypted. Starting or resuming rendering requires a one-use native OS
      approval and a separately confined Windows AppContainer worker.
      If those capabilities are unavailable, NVP refuses the operation.
    </p>}
    {!within&&<p className="director-long-warning">
      Long-film export supports saved films greater than 30 seconds and up
      to three hours, trimmed to complete 24fps picture frames.
      Adjust the current edit before rendering.
    </p>}
    {edit.missing_sources?.length>0&&<p className="director-long-warning">
      One original Take is missing. NVP will not replace it with invented footage.
    </p>}
    {error&&<p className="director-long-error" role="alert">{error}</p>}
    {notice&&<p className="director-long-notice" role="status">{notice}</p>}
    {within&&<div className="director-long-go">
      <button className="film-primary" disabled={!canStart}
        onClick={()=>act(null,'start')}>
        {movie.encrypted?'Approve Protected Film Rendering':
          'Render Complete Film in Verified Reels'}
      </button>
      <p className="film-hint">This version uses bounded ten-second
        native AVI reels. The work can be resumed from verified checkpoints;
        output is not yet one seamless professional cinema movie.</p>
    </div>}
    {loading&&<p role="status">Opening saved film-render history…</p>}
    {!!jobs.length&&<div className="director-long-history">
      <h4>Long film rendering</h4>
      {jobs.slice(0,5).map(job=><article key={job.id}>
        <div className="director-long-job-title">
          <strong>{phases[job.status]||'Review long-film work'}</strong>
          <span>{formatSeconds(job.duration_seconds)}</span>
        </div>
        <progress max={job.reels_total||1} value={job.reels_verified||0}
          aria-label="Independently verified long-film reels"/>
        <p className="director-long-meta">{job.reels_verified} of
          {' '}{job.reels_total} original-source reels verified
          {' · '}{job.progress_percent.toFixed(1)}%</p>
        {job.issue&&<p className="director-long-warning">{job.issue}</p>}
        <div className="director-long-actions">
          {ACTIVE.has(job.status)&&
            <button className="film-secondary" disabled={busy}
              onClick={()=>act(job.id,'cancel')}>Stop Rendering</button>}
          {job.resumable&&
            <button className="film-primary" disabled={busy||hasActive}
              onClick={()=>act(job.id,'resume')}>
              Resume Verified Film Work
            </button>}
          {job.completed&&<>
            <a className="film-primary"
              href={base+'/'+job.id+'/manifest'}
              download={'NVP-Film-Reels-'+job.id.slice(0,8)+'.json'}
              rel="noopener noreferrer">
              Save Verified Film Index
            </a>
          </>}
        </div>
        {job.completed&&job===latest&&<>
          {!movie.encrypted&&<DirectorFilmDistribution
            key={movie.id+':portable:'+job.id}
            movie={movie} job={job}/>}
          <p className="film-hint">{movie.encrypted?
            'Original film reels stay AES-GCM sealed in the NVP project. Each '+
            'authorized download is decrypted only in the trusted host response; '+
            'no plaintext working files are saved for export workers.':
            'Your film is also available as individual AVI reels and a portable
             .nvpfilm package. Other players may not switch AVI reels without gaps.'}</p>
          <div className="director-long-pages">
            <label>Reels to save · page
              <select value={page} onChange={e=>setPage(Number(e.target.value))}>
                {Array.from({length:pages},(_,n)=><option value={n} key={n}>
                  {n+1} of {pages}</option>)}
              </select>
            </label>
            <div className="director-long-reels">
              {shown.map(index=><a key={index} className="film-secondary"
                href={base+'/'+job.id+'/reels/'+index}
                download={'NVP-Film-Reel-'+String(index+1).padStart(5,'0')+'.avi'}
                rel="noopener noreferrer">
                Save Reel {index+1}
              </a>)}
            </div>
          </div>
        </>}
      </article>)}
    </div>}
    <p className="film-hint">Long films are generated from actual
      time-sampled 3D performances and original sound. This is a
      staged working-film capability, not a verified 30-minute
      physical playback pass, a mastered 4K film or SMPTE DCP.</p>
  </section>;
}
