import React,{useEffect,useRef,useState} from 'react';
import './director-export-film.css';
import DirectorFinishingRoom from './DirectorFinishingRoom.jsx';

const active=new Set(['queued','rendering','verifying']);
const baseProject=id=>'/api/projects/'+encodeURIComponent(id);
async function action(url,method='GET',body,signal){
  const response=await fetch(url,{
    method,credentials:'same-origin',signal,
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){
    const result=await response.json().catch(()=>({}));
    throw new Error(typeof result.detail==='string'?result.detail:
      'Your movie could not be exported. Your edit and original Takes are safe.');
  }
  return response.json();
}

export default function DirectorExportFilm({movie,onEditFilm,onFilmScenes}){
  const base=baseProject(movie.id)+(movie.encrypted?'/live':'');
  const [edit,setEdit]=useState(null);
  const [jobs,setJobs]=useState([]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const task=useRef(null);
  const alive=useRef(true);
  const refresh=async ()=>{
    const [e,result]=await Promise.all([
      action(base+'/edit'),
      action(base+'/export')
    ]);
    if(alive.current){setEdit(e);setJobs(result.exports||[])}
  };
  useEffect(()=>{
    alive.current=true;
    refresh().catch(e=>{
      if(!alive.current)return;
      setError(e.message);
    });
    return()=>{alive.current=false};
  },[base,movie.revision]);
  const hasActive=jobs.some(job=>active.has(job.status));
  useEffect(()=>{
    if(!hasActive)return;
    let cancelled=false;
    const timer=window.setInterval(()=>{
      action(base+'/export').then(result=>{
        if(cancelled)return;
        setJobs(result.exports||[]);
      }).catch(e=>{
        if(cancelled)return;
        setError(e.message);
      });
    },1000);
    return()=>{cancelled=true;window.clearInterval(timer)};
  },[base,hasActive]);
  const latest=jobs[0]||null;
  const length=edit?.duration_seconds||0;
  const withinProfile=length>0&&length<=30&&
    Math.abs(length*24-Math.round(length*24))<.0001;
  const ready=edit&&edit.revision>0&&edit.clips?.length>0&&
    !edit.missing_sources?.length&&withinProfile&&!hasActive&&!busy;
  async function start(){
    if(!ready)return;
    if(!window.confirm('Finish this movie from your saved edit? '+
      'The original filming, sound and earlier edits will remain unchanged.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const result=await action(base+'/export/start','POST',{
        expected_revision:edit.revision,director_confirmed:true
      });
      const current=await action(base+'/export');
      setJobs(current.exports?.length?current.exports:[result]);
      setNotice('Your finished movie is being created from your original film.');
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }
  async function cancel(jobId){
    if(!window.confirm('Stop finishing this movie? Your recorded Takes and editing decisions will be preserved.'))return;
    setBusy(true);setError('');
    try{
      await action(base+'/export/'+jobId+'/cancel','POST');
      const result=await action(base+'/export');
      setJobs(result.exports||[]);
      setNotice('Movie export stopped. You can try again later.');
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }
  const fmt=length=>Math.max(0,Number(length||0)).toFixed(2);
  return <section className="film-card director-export"
    aria-label="Finish and save your movie">
    <div className="film-card-head">
      <div><div className="film-eyebrow">FINISH YOUR FILM</div>
        <h2>Export Film</h2>
        <p className="film-muted">Turn your edited scenes and original sound
          into a movie you can watch and share. Your original film remains
          available if you want a different edit or camera angle later.</p>
      </div>
      <button className="film-secondary" onClick={onEditFilm}>
        Return to Editing</button>
    </div>
    {error&&<div className="director-export-error" role="alert">{error}</div>}
    {notice&&<div className="director-export-notice" role="status">{notice}</div>}
    <div className="director-export-summary">
      <div><span>Film length</span><strong>{fmt(length)} seconds</strong></div>
      <div><span>Shots in film</span><strong>{edit?.clips?.length||0}</strong></div>
      <div><span>Picture and sound</span><strong>24 frames/second · Stereo</strong></div>
    </div>
    {edit?.missing_sources?.length>0&&<div className="director-export-warning"
      role="alert">An original recording is unavailable. Your edit is safe,
      but NVP will not replace missing footage with an invented image.
      <p>{edit.missing_sources.join(' · ')}</p></div>}
    {edit&&!edit.clips?.length&&<div className="director-export-needs">
      <h3>Choose what goes into your film</h3>
      <p>No edited shots have been added yet. Choose one or more Digital Takes
        in Post-Production to assemble your movie.</p>
      <button className="film-secondary" onClick={onEditFilm}>
        Open Film Editing</button>
    </div>}
    {edit?.clips?.length>0&&!withinProfile&&<div className="director-export-needs">
      <h3>Finish your first short film</h3>
      <p>This first delivery format supports up to 30 seconds. Trim the
        edited movie to a complete picture frame in Post-Production before
        finishing it. Longer films will be supported as production expands.</p>
      <button className="film-secondary" onClick={onEditFilm}>
        Adjust the Edit</button>
    </div>}
    {edit?.revision>0&&edit?.clips?.length>0&&
      !edit.missing_sources?.length&&
      <DirectorFinishingRoom
        key={movie.id+':finish:'+edit.revision}
        movie={movie} editRevision={edit.revision}
        onChanged={()=>{}}/>}
    {ready&&<div className="director-export-go">
      <h3>Your movie is ready to finish</h3>
      <p className="film-muted">Optional final color and sound choices
        above are applied only after you approve them for this exact edit.
        Without them NVP preserves your existing approved edit and sound.</p>
      <p>Finish the current edit with continuous picture and original-source
        sound. NVP will check the finished movie before making it available.</p>
      <button className="film-primary" onClick={start} disabled={!ready}>
        Finish and Save Movie</button>
      <p className="film-hint">The first movie format is an actual playable
        640×360 AVI with 24fps SDR picture and 48kHz stereo PCM16 sound.
        Finishing uses measured sound levels and your approved picture look.
        Cinema DCP, ProRes, full-resolution ACES and true-peak certification
        are not claimed by this working export.</p>
    </div>}
    {hasActive&&latest&&<div className="director-export-progress"
      role="status" aria-live="polite">
      <h3>{latest.status==='verifying'?'Checking the finished film…':
        'Creating your movie…'}</h3>
      <progress max={100} value={latest.progress_percent||0}
        aria-label="Film export completion"/>
      <div className="director-export-progress-meta">
        <span>{latest.frames_completed} of {latest.frames_total} picture frames</span>
        <span>{latest.progress_percent?.toFixed(1)||'0.0'}%</span>
      </div>
      <p className="film-hint">NVP is processing the original scenes and sound.
        Your recorded material remains unchanged.</p>
      <button className="film-secondary" disabled={busy}
        onClick={()=>cancel(latest.id)}>Stop Export</button>
    </div>}
    {jobs.some(j=>j.status==='completed')&&<div className="director-export-results">
      <h3>Finished movies</h3>
      {jobs.filter(j=>j.status==='completed').map((job,index)=>
        <article key={job.id}>
          <div><strong>{index===0?'Your finished film':'Earlier movie version'}</strong>
            <p>{job.duration_seconds} seconds · Picture and sound independently
              checked · {Math.round((job.output_bytes||0)/1048576*10)/10} MB</p>
          </div>
          <a className="film-primary" href={base+'/export/'+job.id+'/movie'}
            download={'NVP-Film-'+job.id.slice(0,8)+'.avi'}
            rel="noopener noreferrer">Save Movie</a>
        </article>)}
    </div>}
    {jobs.some(j=>['failed','interrupted','cancelled'].includes(j.status))&&
      <details className="director-export-history">
        <summary>Earlier export attempts</summary>
        <p className="film-muted">These attempts did not change your original
          film. You can create a new finished movie from the saved edit.</p>
        {jobs.filter(j=>['failed','interrupted','cancelled'].includes(j.status))
          .map(j=><div key={j.id}>
            <span>{j.status==='interrupted'?'Interrupted':
              j.status==='cancelled'?'Stopped':'Did not finish'}</span>
            {j.issue&&<span>{j.issue}</span>}
          </div>)}
      </details>}
    <p className="film-hint director-export-footnote">
      Your movie can be re-edited and exported differently at any time.
      Digital Takes, scene performances and original microphone recordings
      are preserved.
    </p>
  </section>;
}
