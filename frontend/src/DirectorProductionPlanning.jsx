import React,{useEffect,useRef,useState} from 'react';

const labels={retake:'Film another Take',revise_scene:'Revise scene',revise_camera:'Change camera',revise_performance:'Change performance',revise_sound:'Revise sound',revise_edit:'Revise edit',review_film:'Review film'};
const methods=['wo6_plan_catalog','wo6_plan_preview','wo6_plan_save','wo6_plan_read'];
export default function DirectorProductionPlanning({movie,nativeBridge}){
  const [api,setApi]=useState(null),[catalog,setCatalog]=useState(null),[source,setSource]=useState('');
  const [change,setChange]=useState(''),[note,setNote]=useState(''),[scene,setScene]=useState('');
  const [preview,setPreview]=useState(null),[saved,setSaved]=useState(null),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[notice,setNotice]=useState('');
  const generation=useRef(0),pending=useRef(false);
  useEffect(()=>{
    const discover=()=>{const b=nativeBridge||window.pywebview?.api;if(b&&methods.every(k=>typeof b[k]==='function'))setApi(b);};
    discover();window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[nativeBridge]);
  useEffect(()=>{generation.current++;pending.current=false;setCatalog(null);setSource('');setChange('');setNote('');setScene('');setPreview(null);setSaved(null);setBusy(false);setError('');setNotice('');
    return ()=>{generation.current++;};},[movie.id,movie.revision,movie.encrypted,api]);
  async function perform(work){if(pending.current)return;pending.current=true;const g=generation.current;setBusy(true);setError('');setNotice('');
    const live=()=>g===generation.current;
    try{await work(live);}catch(e){if(live())setError(e?.message||'Unable to open the plan.');}finally{if(live()){pending.current=false;setBusy(false);}}}
  async function load(live){const data=await api.wo6_plan_catalog(movie.id);if(data?.project_id!==movie.id)throw Error('Movie plan unavailable.');if(live())setCatalog(data);}
  const selected=catalog?.sources.find(s=>s.object_id===source);
  function invalidate(){setPreview(null);setSaved(null);setNotice('');}
  if(movie.encrypted||!api)return null;
  return <details className="film-card"><summary>Plan changes (Advanced)</summary>
    <p>Review the original movie sources affected by a creative change. Saving a plan does not edit, film or export anything.</p>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!catalog?<button disabled={busy} onClick={()=>void perform(load)}>Open Production Planning</button>:<>
      {catalog.catalog_truncated&&<p>Some sources or plans are not shown in this list.</p>}
      <label>Choose source <select disabled={busy} value={source} onChange={e=>{const id=e.target.value;setSource(id);setChange(catalog.sources.find(s=>s.object_id===id)?.changes[0]||'');invalidate();}}><option value="">Choose a source</option>{catalog.sources.map(s=><option key={s.object_id} value={s.object_id}>{s.label} ({s.kind})</option>)}</select></label>
      {selected&&<><label>Planned change <select disabled={busy} value={change} onChange={e=>{setChange(e.target.value);invalidate();}}>{selected.changes.map(k=><option key={k} value={k}>{labels[k]||k}</option>)}</select></label>
      <label>Screenplay scene (optional) <select disabled={busy} value={scene} onChange={e=>{setScene(e.target.value);invalidate();}}><option value="">Whole movie</option>{(movie.scenes||[]).map(s=><option key={s.id} value={s.id}>{s.heading||s.id}</option>)}</select></label>
      <label>Creative intention <textarea disabled={busy} maxLength={800} value={note} onChange={e=>{setNote(e.target.value);invalidate();}}/></label>
      <button disabled={busy||!change||!note.trim()} onClick={()=>void perform(async live=>{invalidate();const proposal={project_id:movie.id,source_id:source,source_revision:selected.revision,source_sha256:selected.document_sha256,change_kind:change,intention:note,screenplay_scene_id:scene||null};const p=await api.wo6_plan_preview(proposal);if(p?.project_id!==movie.id||p?.source?.object_id!==source||p?.worker_authorized!==false)throw Error('Plan preview unavailable.');if(live())setPreview({proposal,result:p});})}>Preview Changes</button></>}
      {preview&&<section aria-label="Plan preview"><p>Original source revisions: {preview.result.indexed_source_lineage.length}. Recorded dependent items: {preview.result.indexed_downstream.length}.</p>
      <p>{preview.result.story_context.approved_facts} approved story facts in scope. Other dependent film outputs may exist; media has not been reopened.</p>
      <details><summary>Original sources and affected items</summary><h4>Original sources</h4><ul>{preview.result.indexed_source_lineage.map(r=><li key={r.object_id+':'+r.revision}>{r.label||r.object_id} — revision {r.revision}</li>)}</ul><h4>Affected recorded items</h4><ul>{preview.result.indexed_downstream.map(r=><li key={r.object_id+':'+r.revision}>{r.label||r.object_id} — revision {r.revision}</li>)}</ul></details>
      {!preview.result.planning_approval_available&&<p>This source is no longer current or the dependency review is incomplete. Refresh before saving.</p>}
      <button disabled={busy||!preview.result.planning_approval_available} onClick={()=>void perform(async live=>{const result=await api.wo6_plan_save({proposal:preview.proposal,preview_sha256:preview.result.preview_sha256});if(!live())return;if(result?.status==='DENIED'){setNotice('Plan not saved.');return;}if(result?.status!=='PLAN_SAVED_NOT_EXECUTION_AUTHORITY'||result.worker_authorized!==false)throw Error('Plan was not confirmed.');setPreview(null);await load(live);if(live())setNotice('Creative plan saved. Nothing has been filmed or changed.');})}>Save Creative Plan</button></section>}
      {catalog.saved_plans.length>0&&<><h3>Saved creative plans</h3>{catalog.saved_plans.map((p,i)=><button key={p.object_id} disabled={busy} onClick={()=>void perform(async live=>{const result=await api.wo6_plan_read(movie.id,p.object_id);if(result?.data?.plan?.project_id!==movie.id||result?.worker_authorized!==false)throw Error('Saved plan unavailable.');if(live())setSaved({plan:result.data.plan,record:result.record});})}>Open Plan {i+1}</button>)}</>}
      {saved&&<section aria-label="Saved creative plan"><p>{saved.plan.request.intention}</p><p>Saved intention only. No worker or film changes authorized.</p>
      {saved.plan.request.change_kind==='retake'&&saved.plan.source?.kind==='take'&&saved.record?.document_sha256&&typeof api.wo6_retake_execute==='function'&&<>
        <p>Create a separate Take with the original scene and timing. This does not yet apply the written creative changes.</p>
        <button disabled={busy} onClick={()=>void perform(async live=>{const result=await api.wo6_retake_execute({project_id:movie.id,plan_id:saved.record.object_id,plan_sha256:saved.record.document_sha256});if(!live())return;if(result?.status==='NOT_ADMITTED'){setNotice('This Take could not start. Try again after other production work finishes.');return;}if(result?.status!=='VERIFIED_NEW_TAKE'||result.project_id!==movie.id||result.worker_executed!==true||result.film_approved!==false)throw Error('The new Take is not verified.');setSaved(null);await load(live);if(live())setNotice('New Take created. The original is unchanged; no movie has been rendered.');})}>Create Separate Take</button>
      </>}</section>}
    </>}
  </details>;
}
