import React,{useEffect,useState} from 'react';
import FinishedFilmPlaybackPanel from './FinishedFilmPlaybackPanel.jsx';

const FRAME_TICKS=294000000;
const fields=['action','camera','sound'];
export default function DirectorFinishedReview({movie}){
  const [api,setApi]=useState(null),[catalog,setCatalog]=useState(null),[feature,setFeature]=useState('');
  const [assembly,setAssembly]=useState(''),[intent,setIntent]=useState(''),[shots,setShots]=useState([]);
  const [observations,setObservations]=useState([]),[watched,setWatched]=useState(false),[heard,setHeard]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const id=movie.id;
  useEffect(()=>{
    const discover=()=>{const b=window.pywebview?.api;if(b&&['wo5_review_catalog','wo5_review_save_intent','wo5_review_read_intent','wo5_review_save_observations'].every(k=>typeof b[k]==='function'))setApi(b);};
    discover();window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[]);
  async function refresh(){const data=await api.wo5_review_catalog(id);if(data?.project_id!==id)throw Error('Movie review unavailable.');setCatalog(data);}
  useEffect(()=>{let live=true;setCatalog(null);setFeature('');setAssembly('');setIntent('');setShots([]);setObservations([]);setWatched(false);setHeard(false);
    if(api&&!movie.encrypted)api.wo5_review_catalog(id).then(data=>{if(live&&data?.project_id===id)setCatalog(data);}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};},[api,id,movie.encrypted]);
  function chooseAssembly(value){setAssembly(value);const cut=catalog?.assemblies.find(x=>x.assembly_id===value);
    setShots(cut?[{shot_id:'Shot1',start_tick:0,end_tick:cut.end_tick,expected_action:'',expected_camera:'',expected_sound:''}]:[]);}
  function editShot(i,key,value){setShots(prev=>prev.map((s,n)=>n===i?{...s,[key]:value}:s));}
  async function perform(fn){if(busy)return;setBusy(true);setNotice('');setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
  function addShot(){setShots(prev=>{const last=prev.at(-1);if(!last||last.end_tick-last.start_tick<2*FRAME_TICKS)return prev;const split=last.end_tick-FRAME_TICKS;return [...prev.slice(0,-1),{...last,end_tick:split},{shot_id:'Shot'+(prev.length+1),start_tick:split,end_tick:last.end_tick,expected_action:'',expected_camera:'',expected_sound:''}];});}
  const selected=catalog?.assemblies.find(x=>x.assembly_id===assembly);
  const finished=catalog?.features.filter(x=>x.state==='INDEXED')||[];
  const chosen=finished.find(x=>x.feature_id===feature);
  const matching=catalog?.director_intents.filter(x=>chosen&&x.source_assembly_id===chosen.assembly_id&&x.source_assembly_revision===chosen.assembly_revision&&x.source_assembly_sha256===chosen.assembly_sha256)||[];
  if(movie.encrypted||!api)return null;
  return <details className="film-card"><summary>Review finished film (Advanced)</summary>
    <p>Plan what each shot should convey, then record your own picture and sound observations after viewing the finished movie. This is separate from editing the original movie.</p>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!catalog?<button onClick={()=>void perform(refresh)}>Load Film Review</button>:<>
      <label>Choose an edit for your director's notes <select value={assembly} onChange={e=>chooseAssembly(e.target.value)}><option value="">Choose edit</option>{catalog.assemblies.map(x=><option key={x.assembly_id} value={x.assembly_id}>{x.assembly_id}</option>)}</select></label>
      {selected&&<div>{shots.map((s,i)=><fieldset key={s.shot_id}><legend>Shot {i+1}</legend>
        <label>Start frame <input type="number" min="0" value={s.start_tick/FRAME_TICKS} onChange={e=>editShot(i,'start_tick',Number(e.target.value)*FRAME_TICKS)}/></label>
        <label>End frame <input type="number" min="1" value={s.end_tick/FRAME_TICKS} onChange={e=>editShot(i,'end_tick',Number(e.target.value)*FRAME_TICKS)}/></label>
        {fields.map(f=><label key={f}>Expected {f}<textarea maxLength={360} value={s['expected_'+f]} onChange={e=>editShot(i,'expected_'+f,e.target.value)}/></label>)}</fieldset>)}
        <button disabled={busy||shots.length>=512} onClick={addShot}>Add shot</button>
        <button disabled={busy||!shots.length} onClick={()=>void perform(async()=>{const result=await api.wo5_review_save_intent({project_id:id,assembly_id:assembly,assembly_revision:selected.assembly_revision,intent_id:'Intent'+crypto.randomUUID().replaceAll('-',''),shots});setNotice(result.status==='DENIED'?'Not saved.':'Director notes saved.');await refresh();})}>Save Director Notes</button>
      </div>}
      <label>Finished film <select value={feature} onChange={e=>{setFeature(e.target.value);setIntent('');setObservations([]);setWatched(false);setHeard(false);}}><option value="">Choose finished film</option>{finished.map(x=><option value={x.feature_id} key={x.feature_id}>{x.assembly_id}</option>)}</select></label>
      {!finished.length&&<p>No finished cinema film is ready for review.</p>}
      {feature&&<FinishedFilmPlaybackPanel key={id+':'+feature} projectId={id} featureId={feature} nativeBridge={api}/>}
      {feature&&<label>Director notes <select value={intent} onChange={e=>{const value=e.target.value;setIntent(value);setObservations([]);setWatched(false);setHeard(false);if(value)void perform(async()=>{const result=await api.wo5_review_read_intent(id,value);setObservations(result.data.shots.map(s=>({shot_id:s.shot_id,observed_action:'',observed_camera:'',observed_sound:'',judgment:'NOT_OBSERVED',review_note:''})));});}}><option value="">Choose saved notes</option>{matching.map(x=><option key={x.intent_id} value={x.intent_id}>{x.intent_id}</option>)}</select></label>}
      {observations.map((s,i)=><fieldset key={s.shot_id}><legend>Shot {i+1}</legend>{[...fields.map(f=>'observed_'+f),'review_note'].map(k=><label key={k}>{k.replaceAll('_',' ')}<textarea maxLength={360} value={s[k]} onChange={e=>setObservations(prev=>prev.map((item,n)=>n===i?{...item,[k]:e.target.value}:item))}/></label>)}<label>Assessment<select value={s.judgment} onChange={e=>setObservations(prev=>prev.map((item,n)=>n===i?{...item,judgment:e.target.value}:item))}><option value="NOT_OBSERVED">Not yet reviewed</option><option value="MATCHED">Matches my intention</option><option value="NEEDS_REVISION">Needs revision</option></select></label></fieldset>)}
      {observations.length>0&&<><label><input type="checkbox" checked={watched} onChange={e=>setWatched(e.target.checked)}/>I watched the entire film</label><label><input type="checkbox" checked={heard} onChange={e=>setHeard(e.target.checked)}/>I heard the entire soundtrack</label><button disabled={busy} onClick={()=>void perform(async()=>{const result=await api.wo5_review_save_observations({project_id:id,feature_id:feature,intent_id:intent,review_id:'Review'+crypto.randomUUID().replaceAll('-',''),observations,watched_entire_film:watched,heard_entire_sound:heard});setNotice(result.status==='DENIED'?'Not saved.':'Your observations have been saved.');await refresh();})}>Save Film Review</button></>}
    </>}
  </details>;
}
