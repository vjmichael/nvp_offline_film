import React,{useEffect,useRef,useState} from 'react';
import './director-sound-stage.css';

const profiles={
  original:'As filmed',
  interior:'Ordinary room',
  hall:'Large hall',
  outdoor:'Open air',
  forest:'Forest',
  city:'City street',
  cavern:'Cavern',
  space:'Space'};
async function call(url,method='GET',body,signal){
  const r=await fetch(url,{method,signal,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!r.ok){
    const result=await r.json().catch(()=>({}));
    throw Error(typeof result.detail==='string'?result.detail:
      'The scene sound was not changed. Your original recording is safe.');
  }
  return r.json();
}
export default function DirectorSoundStage({movie,takeId}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+
    '/production/sound/'+encodeURIComponent(takeId||'');
  const [record,setRecord]=useState(null);
  const [profile,setProfile]=useState('original');
  const [draft,setDraft]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [historyOpen,setHistoryOpen]=useState(false);
  const live=useRef(true);
  useEffect(()=>{
    live.current=true;setRecord(null);setError('');setNotice('');
    const abort=new AbortController();
    if(takeId)call(base,'GET',undefined,abort.signal).then(data=>{
      if(live.current)setRecord(data);
    }).catch(e=>{if(e.name!=='AbortError'&&live.current)setError(e.message)});
    return()=>{live.current=false;abort.abort()};
  },[base]);
  useEffect(()=>{
    if(!record)return;
    setProfile(record.draft.profile);
    setDraft({...record.draft});
  },[record?.revision,takeId]);
  const approved=record&&record.revision>0&&
    record.revision===record.approved_revision;
  const editField=(key,value)=>setDraft(x=>({...x,[key]:value}));
  async function edit(operation,details,message){
    if(!record||busy)return;
    setBusy(true);setError('');setNotice('');
    try{
      const data=await call(base+'/change','POST',{
        expected_revision:record.revision,operation,details});
      if(live.current){setRecord(data);setNotice(message)}
    }catch(e){if(live.current)setError(e.message)}
    finally{if(live.current)setBusy(false)}
  }
  async function approve(){
    if(!record||record.revision===0||busy)return;
    if(!window.confirm('Use this sound environment in your finished movie? Your original recorded voices and sound remain unchanged.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const data=await call(base+'/approve','POST',{
        expected_revision:record.revision});
      if(live.current){setRecord(data);
        setNotice('This room sound is approved for your movie.')}
    }catch(e){if(live.current)setError(e.message)}
    finally{if(live.current)setBusy(false)}
  }
  async function restore(version){
    if(!record||busy||!window.confirm(
      'Restore this earlier room sound as a new version? Your original recordings will remain.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const data=await call(base+'/restore','POST',{
        source_revision:version,expected_revision:record.revision});
      if(live.current){setRecord(data);setNotice(
        'An earlier sound environment was restored for your review.')}
    }catch(e){if(live.current)setError(e.message)}
    finally{if(live.current)setBusy(false)}
  }
  if(!takeId)return null;
  return <section className="director-sound-stage" aria-label="Shape scene sound">
    <div className="director-sound-header">
      <div><h3>Shape the scene's sound</h3>
        <p className="film-muted">Choose how the room or landscape affects
          the original recorded sound. As characters move, their voices
          follow their position in the filmed scene.</p></div>
      <span>{approved?'Sound approved':
        record?'Changes need review':'Opening room sound…'}</span>
    </div>
    {error&&<p className="director-sound-error" role="alert">{error}</p>}
    {notice&&<p className="director-sound-notice" role="status">{notice}</p>}
    {record&&draft&&<>
      <div className="director-sound-layout">
        <div className="director-sound-panel">
          <h4>Where does this sound take place?</h4>
          <label>Sound environment<select value={profile}
            onChange={e=>setProfile(e.target.value)}>
            {record.profiles.map(name=><option key={name} value={name}>
              {profiles[name]||name}</option>)}
          </select></label>
          <button className="film-secondary" disabled={busy}
            onClick={()=>edit('preset',{profile},
              'Room sound selected. Review and approve it when ready.')}>
            Use This Sound Environment</button>
          <p className="film-hint">Room sound is a separate creative decision.
            Changing the visual set does not overwrite your original audio.</p>
        </div>
        <div className="director-sound-panel">
          <h4>Shape the listening experience</h4>
          {[
            ['reverb','Room echo',0,.85,.01],
            ['reflections','Natural reflections',0,.85,.01],
            ['room_size','Room or open-air size',3,100,1],
            ['obstruction','Sound behind objects',0,1,.01],
            ['distance_rolloff','Distance effect',0,2.5,.05],
            ['air_absorption','Distance softness',0,1,.01],
            ['stereo_width','Width of the sound',0,1.5,.05]
          ].map(([name,label,min,max,step])=><label key={name}>
            {label}
            <input type="range" min={min} max={max} step={step}
              value={draft[name]}
              onChange={e=>editField(name,Number(e.target.value))}/>
            <small>{Number(draft[name]).toFixed(2)}</small>
          </label>)}
          <label className="director-sound-weather">
            <input type="checkbox" checked={draft.weather_sounds}
              onChange={e=>editField('weather_sounds',e.target.checked)}/>
            Add designed wind/rain/snow sound where those scene events occur
          </label>
          <p className="film-hint">Designed weather sound is a creative
            sound effect, not a microphone recording.</p>
          {draft.weather_sounds&&<label>Designed weather sound level
            <input type="range" min="0" max=".4" step=".01"
              value={draft.weather_level}
              onChange={e=>editField('weather_level',
                Number(e.target.value))}/>
            <small>{draft.weather_level.toFixed(2)}</small>
          </label>}
          <label>Director's sound note
            <textarea maxLength={500} rows={2} value={draft.notes}
              onChange={e=>editField('notes',e.target.value)}
              placeholder="The room should feel enclosed; wind is distant…"/>
          </label>
          <button className="film-secondary" disabled={busy}
            onClick={()=>edit('mix',{
              reverb:draft.reverb,reflections:draft.reflections,
              room_size:draft.room_size,obstruction:draft.obstruction,
              distance_rolloff:draft.distance_rolloff,
              air_absorption:draft.air_absorption,
              stereo_width:draft.stereo_width,
              weather_sounds:draft.weather_sounds,
              weather_level:draft.weather_level,notes:draft.notes
            },'Sound choices saved. Listen with the film before approval.')}>
            Save Sound Decisions</button>
        </div>
      </div>
      <div className="director-sound-approval">
        <div><strong>{approved?'The sound of this scene is approved':
          'Review the sound in your film'}</strong>
          <p className="film-muted">Only approved room sound affects the
            finished movie. Your original sound and earlier choices stay safe.</p>
        </div>
        <button className="film-primary" disabled={
          busy||approved||record.revision===0}
          onClick={approve}>{approved?'Approved':'Approve Room Sound'}</button>
      </div>
      {record.history.length>1&&<details
        className="director-sound-history" open={historyOpen}
        onToggle={e=>setHistoryOpen(e.currentTarget.open)}>
        <summary>Earlier sound choices</summary>
        {record.history.filter(x=>x.revision!==record.revision).map(x=>
          <div key={x.revision}>
            <span>Sound version {x.revision}</span>
            <button className="film-secondary" disabled={busy}
              onClick={()=>restore(x.revision)}>Restore</button>
          </div>)}
      </details>}
    </>}
  </section>;
}
