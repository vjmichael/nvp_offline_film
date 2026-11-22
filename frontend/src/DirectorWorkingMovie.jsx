import React,{useEffect,useRef,useState} from 'react';
import DirectorReelPlayback from './DirectorReelPlayback.jsx';
import DirectorProductionInventory from './DirectorProductionInventory.jsx';
import DirectorFinishingRoom from './DirectorFinishingRoom.jsx';

// The desktop host owns the approval, production plan, worker and saved media.
// The only renderer-supplied handle is a random correlation ID for stop/status.
export default function DirectorWorkingMovie({projectId,edit,api}){
  const [busy,setBusy]=useState(false),[stopping,setStopping]=useState(false),[prepared,setPrepared]=useState(false),[complete,setComplete]=useState(false),[progress,setProgress]=useState(null),[notice,setNotice]=useState('');
  const [finishing,setFinishing]=useState(false),[job,setJob]=useState(null),[watch,setWatch]=useState(false);
  const active=useRef(null);
  const base=`/api/projects/${projectId}/live/edit/sections`;
  useEffect(()=>()=>{
    const run=active.current;
    if(run){run.closed=true;clearInterval(run.timer);active.current=null;void api(base+'/feature-stop','POST',{operation_id:run.id}).catch(()=>{});}
  },[base,edit.revision,edit.active_digest,api]);
  function matches(out,run){return out?.project_id===projectId&&out.operation_id===run.id;}
  function validProgress(out){return Number.isSafeInteger(out.saved_frames)&&Number.isSafeInteger(out.total_frames)&&out.saved_frames>=0&&out.saved_frames<=out.total_frames&&out.total_frames<=259200;}
  async function status(run){
    if(run.closed||run.polling||active.current!==run)return;run.polling=true;
    try{
      const out=await api(base+'/feature-status','POST',{operation_id:run.id});
      if(!run.closed&&active.current===run&&matches(out,run)&&out.active===true&&validProgress(out)&&['preparing','reviewing','starting','rendering','verifying'].includes(out.phase)){
        setProgress(out);if(out.stop_requested===true)setStopping(true);
      }
    }catch{/* A failed status poll is not evidence of worker exit. */}finally{run.polling=false;}
  }
  async function start(){
    if(active.current||complete)return;
    setFinishing(false);
    const id=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
    const run={id,closed:false,polling:false};active.current=run;setBusy(true);setStopping(false);setNotice('');
    run.timer=setInterval(()=>void status(run),750);
    try{
      const out=await api(base+'/feature-step','POST',{revision:edit.revision,digest:edit.active_digest,operation_id:id});
      if(run.closed||active.current!==run)return;
      if(!matches(out,run)||out.revision!==edit.revision||out.active_digest!==edit.active_digest||out.final_movie_exported!==false)throw Error('Movie scope changed');
      if(out.state==='refused')setNotice('Not started. Your saved material is unchanged.');
      else if(out.state==='stopped'){setNotice('Stopped. Verified parts remain saved; choose continue when ready.');setPrepared(true);}
      else if(['prepared','complete'].includes(out.state)&&validProgress(out)&&out.total_frames>0){
        if(out.state==='complete'&&out.saved_frames!==out.total_frames)throw Error('Movie incomplete');
        setProgress(out);setPrepared(true);setComplete(out.state==='complete');
        if(out.state==='complete'&&/^[a-f0-9]{64}$/.test(out.job_id||''))setJob(out.job_id);
        setNotice(out.state==='complete'?'Working movie verified and saved. This is not a final export.':'Sound preparation complete. Your working movie is ready to render.');
      }else throw Error('Unverified result');
    }catch{if(!run.closed&&active.current===run)setNotice('Working movie production needs review. Reopen the approved finishing and try again in NVP. Saved material has not been replaced.');}
    finally{clearInterval(run.timer);if(active.current===run){active.current=null;setBusy(false);setStopping(false);}}
  }
  async function stop(){
    const run=active.current;if(!run||stopping)return;
    setStopping(true);setNotice('Requesting stop…');
    try{
      const out=await api(base+'/feature-stop','POST',{operation_id:run.id});
      if(run.closed||active.current!==run)return;
      if(!matches(out,run)||out.stop_requested!==true)throw Error('Stop not acknowledged');
      setNotice('Stopping… waiting for the current work to close safely.');
    }catch{if(!run.closed&&active.current===run){setStopping(false);setNotice('Stop has not been confirmed. Try Stop again.');}}
  }
  return <details className="film-sections film-working-movie" data-production-phase={busy?progress?.phase:undefined}><summary>Working movie</summary>
    <p className="film-muted">Prepare and render the approved edit in protected parts. You can stop and continue later; your originals remain unchanged.</p>
    <button className="film-secondary" disabled={busy} onClick={()=>setFinishing(v=>!v)}>{finishing?'Close picture and sound':'Review picture and sound'}</button>
    {finishing&&<DirectorFinishingRoom movie={{id:projectId,encrypted:true}} editRevision={edit.revision} durationSeconds={Number(edit.duration_tick||0)/7056000000} chapterBased onChanged={()=>{setPrepared(false);setComplete(false);setJob(null);setWatch(false);setProgress(null);setNotice('');}}/>}
    {progress?.total_frames>0&&<div><progress max={progress.total_frames} value={progress.saved_frames} aria-label="Verified working movie progress"/><span> {Math.floor(100*progress.saved_frames/progress.total_frames)}% saved</span></div>}
    {busy&&!stopping&&<p role="status">{progress?.phase==='rendering'?'Rendering and saving…':progress?.phase==='verifying'?'Checking the complete movie…':'Preparing or reviewing the movie…'}</p>}
    <button className="film-secondary" disabled={busy||complete||finishing} onClick={start}>{prepared?'Continue working movie':'Prepare or continue working movie'}</button>
    {busy&&<button className="film-secondary" disabled={stopping} onClick={stop}>{stopping?'Stopping…':'Stop'}</button>}
    {complete&&job&&!busy&&!finishing&&<><button className="film-secondary" onClick={()=>setWatch(v=>!v)}>{watch?'Close playback':'Watch working movie'}</button>{watch&&<DirectorReelPlayback sourceBase={`${base}/playback/${edit.revision}/${edit.active_digest}/${job}`} title="Watch working movie"/>}</>}
    <DirectorProductionInventory projectId={projectId} api={api}/>
    {notice&&<p role="status">{notice}</p>}
  </details>;
}
