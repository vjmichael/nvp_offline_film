import React,{useEffect,useRef,useState} from 'react';
import './director-finishing-room.css';

/** Finishing is a director decision; underlying sources remain originals. */
const baseProject=id=>'/api/projects/'+encodeURIComponent(id);
const intentNames={
  working:'Working film',
  dialogue_review:'Dialogue review',
  broadcast_review:'Sound level review'
};
async function call(url,method='GET',body,signal){
  const result=await fetch(url,{
    method,signal,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!result.ok){
    const msg=await result.json().catch(()=>({}));
    throw Error(typeof msg.detail==='string'?msg.detail:
      'Your film finishing decision could not be saved.');
  }
  return result.json();
}
const input=(label,key,value,onChange,min,max,step)=><label key={key}>
  {label}
  <input type="range" min={min} max={max} step={step} value={value}
    onChange={e=>onChange(key,Number(e.target.value))}/>
  <small>{Number(value).toFixed(2)}</small>
</label>;

export default function DirectorFinishingRoom({movie,editRevision,onChanged}){
  const base=baseProject(movie.id)+(movie.encrypted?'/live':'')+'/finish';
  const [record,setRecord]=useState(null);
  const [color,setColor]=useState(null);
  const [audio,setAudio]=useState(null);
  const [intent,setIntent]=useState('working');
  const [notes,setNotes]=useState('');
  const [time,setTime]=useState('0');
  const [still,setStill]=useState('');
  const [sound,setSound]=useState('');
  const [readiness,setReadiness]=useState(null);
  const [busy,setBusy]=useState(false);
  const [audition,setAudition]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const alive=useRef(true);
  const abort=useRef(null);

  useEffect(()=>{
    alive.current=true;setRecord(null);setError('');setNotice('');
    let active=true;const controller=new AbortController();
    Promise.all([
      call(base,'GET',undefined,controller.signal),
      call(base+'/cinema-readiness','GET',undefined,controller.signal)
    ]).then(([doc,dcp])=>{
      if(active){setRecord(doc);setReadiness(dcp)}
    }).catch(e=>{if(active&&e.name!=='AbortError')setError(e.message)});
    return()=>{active=false;alive.current=false;controller.abort();
      abort.current?.abort()};
  },[base,editRevision]);

  useEffect(()=>{
    if(!record)return;
    const doc=record.draft;
    if(record.source_changed){
      setColor({exposure:0,contrast:1,saturation:1,lift:0,warmth:0});
      setAudio({target_lufs:-18,peak_ceiling_dbfs:-1.5,
        fade_in_seconds:0,fade_out_seconds:0});
      setIntent('working');setNotes('');
    }else{
      setColor({...doc.color});setAudio({...doc.audio});
      setIntent(doc.finishing_intent);setNotes(doc.notes);
    }
  },[record?.revision,record?.source_changed]);

  useEffect(()=>()=>{if(still)URL.revokeObjectURL(still)},[still]);
  useEffect(()=>()=>{if(sound)URL.revokeObjectURL(sound)},[sound]);

  async function change(section,details,noticeText){
    if(!record||busy)return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await call(base+'/change','POST',{
        expected_revision:record.revision,section,details});
      if(alive.current){
        setRecord(doc);setNotice(noticeText);onChanged?.(doc);
      }
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }

  async function approve(){
    if(!record||busy||record.source_changed||!record.revision)return;
    if(!window.confirm('Approve these final picture and sound decisions for this exact film? Your original Digital Takes, sound and previous edits remain unchanged.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await call(base+'/approve','POST',{
        expected_revision:record.revision});
      if(alive.current){
        setRecord(doc);
        setNotice('Finishing approved for this saved version of your film.');
        onChanged?.(doc);
      }
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }

  async function restore(revision){
    if(!record||busy||!window.confirm(
      'Restore an earlier finishing choice as a new version? Your original film remains safe.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await call(base+'/restore','POST',{
        expected_revision:record.revision,source_revision:revision});
      if(alive.current){setRecord(doc);
        setNotice('Earlier finishing choices restored for review.');
        onChanged?.(doc)}
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }

  async function preview(kind){
    if(!record||record.source_changed||audition||busy)return;
    abort.current?.abort();
    const controller=new AbortController();abort.current=controller;
    setAudition(true);setError('');setNotice('');
    try{
      const url=base+(kind==='sound'?
        '/listen?at_seconds='+encodeURIComponent(
          Number(time).toFixed(2))+'&duration_seconds=3':
        '/picture?seconds='+encodeURIComponent(Number(time).toFixed(2)));
      const response=await fetch(url,{signal:controller.signal,
        credentials:'same-origin',headers:{'x-nvp-director':'1'}});
      if(!response.ok){
        const detail=await response.json().catch(()=>({}));
        throw Error(detail.detail||'The saved film cannot be auditioned');
      }
      const blob=await response.blob();
      if(controller.signal.aborted)return;
      const resource=URL.createObjectURL(blob);
      if(kind==='sound')setSound(resource);else setStill(resource);
      setNotice(kind==='sound'?
        'Listen to your current finishing choice before approval.':
        'Your actual film frame is shown with the current finishing choices.');
    }catch(e){if(e.name!=='AbortError')setError(e.message)}
    finally{if(alive.current)setAudition(false)}
  }

  if(!editRevision)return null;
  const approved=record?.approved_for_current_film&&!record.source_changed;
  return <section className="director-finishing-room" aria-label="Finish picture and sound">
    <div className="director-finishing-head">
      <div><h3>Final Picture and Sound</h3>
        <p className="film-muted">Give your edited movie its final look and
          listening level. NVP makes a new finished copy while keeping
          all original performances and sound exactly as they were.</p></div>
      <span>{approved?'Approved for this film':
        record?.source_changed?'Review new film changes':
        record?'Needs your approval':'Opening finishing decisions…'}</span>
    </div>
    {error&&<p className="director-finishing-error" role="alert">{error}</p>}
    {notice&&<p className="director-finishing-notice" role="status">{notice}</p>}
    {record?.source_changed&&<p className="director-finishing-warning">
      The film or one of its approved performances, sets or sound choices
      changed. Save new finishing directions before approving this movie.</p>}
    {record&&color&&audio&&<>
      <div className="director-finishing-layout">
        <section className="director-finishing-panel">
          <h4>Picture finishing</h4>
          <p className="film-muted">Shape the brightness, contrast and color
            of the film you will share.</p>
          {[
            ['exposure','Light and dark',-2,2,.05],
            ['contrast','Contrast',.65,1.55,.05],
            ['saturation','Color richness',.4,1.6,.05],
            ['lift','Shadow brightness',-.12,.12,.01],
            ['warmth','Warm or cool tone',-.2,.2,.02]
          ].map(([key,label,min,max,step])=>
            input(label,key,color[key],(k,v)=>setColor(old=>({
              ...old,[k]:v})),min,max,step))}
          <button className="film-secondary" disabled={busy}
            onClick={()=>change('color',color,
              'Your picture finishing choices were saved for review.')}>
            Save Picture Look</button>
          <p className="film-hint">This first output is standard-definition
            SDR. Genuine high-dynamic-range color and cinema mastering
            require the professional renderer and display validation.</p>
        </section>
        <section className="director-finishing-panel">
          <h4>Sound finishing</h4>
          <p className="film-muted">Choose a measured overall listening level,
            a maximum sound peak and smooth opening/closing fades.</p>
          {[
            ['target_lufs','Overall sound level',-26,-12,.5],
            ['peak_ceiling_dbfs','Maximum digital peak',-6,-1,.5],
            ['fade_in_seconds','Fade in (seconds)',0,3,.1],
            ['fade_out_seconds','Fade out (seconds)',0,3,.1]
          ].map(([key,label,min,max,step])=>
            input(label,key,audio[key],(k,v)=>setAudio(old=>({
              ...old,[k]:v})),min,max,step))}
          <button className="film-secondary" disabled={busy}
            onClick={()=>change('audio',audio,
              'Sound mastering settings saved. Listen before approval.')}>
            Save Sound Levels</button>
          <p className="film-hint">NVP measures the entire source-derived
            soundtrack. A reviewed loudness target that conflicts with
            the selected peak limit will not be falsely marked as met.</p>
        </section>
      </div>
      <section className="director-finishing-audition">
        <h4>Review the film</h4>
        <div className="director-finishing-preview-controls">
          <label>Choose a moment (seconds)
            <input type="number" min="0" max="30" step=".1"
              value={time} onChange={e=>setTime(e.target.value)}/>
          </label>
          <button className="film-secondary" disabled={busy||audition||record.source_changed}
            onClick={()=>preview('picture')}>
            Show Finished Picture</button>
          <button className="film-secondary" disabled={busy||audition||record.source_changed}
            onClick={()=>preview('sound')}>
            Listen to Finished Sound</button>
        </div>
        {audition&&<p role="status">Preparing your original-source preview…</p>}
        {still&&<img src={still} className="director-finishing-still"
          alt="A real frame from the edited film with selected finishing choices"/>}
        {sound&&<audio controls autoPlay src={sound} preload="none">
          The sound preview is unavailable on this device.
        </audio>}
      </section>
      <section className="director-finishing-purpose">
        <h4>What is this finish for?</h4>
        <label>Audience and purpose
          <select value={intent} onChange={e=>setIntent(e.target.value)}>
            {record.levels.map(name=><option key={name} value={name}>
              {intentNames[name]||name}</option>)}
          </select>
        </label>
        <label>Final director notes
          <textarea rows={2} maxLength={900} value={notes}
            placeholder="Keep the voice clear and the final scene a little warmer…"
            onChange={e=>setNotes(e.target.value)}/>
        </label>
        <button className="film-secondary" disabled={busy}
          onClick={()=>change('intent',{intent,notes},
            'The finishing purpose was saved for review.')}>
          Save Finishing Purpose</button>
      </section>
      <section className="director-finishing-approval">
        <div><strong>{approved?'Your final picture and sound are approved':
          'Approve the final look and sound for this saved edit'}</strong>
          <p className="film-muted">Approval includes the current film, sets,
            actors and sound. If any of them changes, review the finish again.</p>
        </div>
        <button className="film-primary" disabled={
          busy||approved||record.source_changed||record.revision===0}
          onClick={approve}>{approved?'Approved':'Approve Final Finish'}</button>
      </section>
      {record.history.length>1&&<details className="director-finishing-history">
        <summary>Earlier finishing decisions</summary>
        {record.history.filter(v=>v.revision!==record.revision).map(v=>
          <div key={v.revision}>
            <span>Finishing version {v.revision}</span>
            <button className="film-secondary" disabled={busy}
              onClick={()=>restore(v.revision)}>Restore</button>
          </div>)}
      </details>}
      {readiness&&<details className="director-finishing-cinema">
        <summary>Cinema mastering readiness</summary>
        <p>A playable working film is not yet a cinema projection package.
          Cinema export will become available only when genuine cinema
          picture and sound, independent compliance checks and projector
          acceptance are completed.</p>
      </details>}
    </>}
  </section>;
}
