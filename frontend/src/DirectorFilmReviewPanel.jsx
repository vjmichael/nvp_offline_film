import React, {useEffect, useMemo, useState} from 'react';
import DataFirstAVPanel from './DataFirstAVPanel.jsx';

const FRAME_TICKS = 294000000; // source Film Time = 7,056,000,000 ticks/s / 24
const REQUIRED = [
  'wo5_review_catalog','wo5_review_read_intent','wo5_review_save_intent',
  'wo5_review_inspect_feature','wo5_review_save_observations'
];
const EMPTY = {
  assemblies: [], features: [], director_intents: [], director_reviews: []
};

function exactFrames(tick){
  if(!Number.isSafeInteger(tick) || tick < FRAME_TICKS ||
     tick % FRAME_TICKS !== 0) return null;
  return tick / FRAME_TICKS;
}

function initialShot(frames){
  return [{shot_id:'Shot01', duration_frames:frames,
    expected_action:'',expected_camera:'',expected_sound:''}];
}

export function buildSourceBoundShots(rows, totalFrames) {
  if(!Number.isSafeInteger(totalFrames) || totalFrames < 24 ||
     totalFrames > 43200 || !Array.isArray(rows) ||
     rows.length < 1 || rows.length > 512)
    throw Error('Choose a bounded 24fps film assembly (up to 30 minutes).');
  let cursor=0;
  const seen=new Set(), result=[];
  for(const row of rows){
    const frames=Number(row.duration_frames);
    if(!Number.isSafeInteger(frames)||frames<1||
       typeof row.shot_id!=='string'||
       !/^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/.test(row.shot_id)||
       seen.has(row.shot_id))
      throw Error('Each shot needs a unique ID and positive whole-frame duration.');
    const next=cursor+frames;
    if(next>totalFrames)throw Error('Shot durations extend past the selected film cut.');
    for(const key of ['expected_action','expected_camera','expected_sound']){
      if(typeof row[key]!=='string'||!row[key].trim()||row[key].length>360)
        throw Error('Describe the action, camera, and sound intended in each shot.');
    }
    seen.add(row.shot_id);
    result.push({shot_id:row.shot_id,start_tick:cursor*FRAME_TICKS,
      end_tick:next*FRAME_TICKS,expected_action:row.expected_action,
      expected_camera:row.expected_camera,expected_sound:row.expected_sound});
    cursor=next;
  }
  if(cursor!==totalFrames)throw Error('Shot durations must cover the entire approved cut.');
  return result;
}

export function emptyObservations(shots){
  return shots.map(s=>({shot_id:s.shot_id,observed_action:'',
    observed_camera:'',observed_sound:'',judgment:'NOT_OBSERVED',
    review_note:''}));
}

export default function DirectorFilmReviewPanel({projectId, nativeBridge=null}){
  const [native,setNative]=useState(nativeBridge);
  const [catalog,setCatalog]=useState(EMPTY);
  const [assemblyId,setAssemblyId]=useState('');
  const [intentId,setIntentId]=useState('');
  const [newIntentId,setNewIntentId]=useState('DirectorIntent001');
  const [draft,setDraft]=useState([]);
  const [chosenIntent,setChosenIntent]=useState(null);
  const [featureId,setFeatureId]=useState('');
  const [audit,setAudit]=useState(null);
  const [previewReel,setPreviewReel]=useState(null);
  const [observations,setObservations]=useState([]);
  const [watched,setWatched]=useState(false);
  const [heard,setHeard]=useState(false);
  const [reviewId,setReviewId]=useState('DirectorReview001');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');

  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    const discover=()=>{
      const bridge=window.pywebview?.api;
      if(bridge && REQUIRED.every(x=>typeof bridge[x]==='function'))setNative(bridge);
    };
    discover();
    window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[nativeBridge]);

  async function refresh(bridge=native){
    if(!bridge || !projectId)return;
    const result=await bridge.wo5_review_catalog(projectId);
    if(result?.status!=='NATIVE_PROJECT_SCOPED_READ_ONLY' ||
       result.project_id!==projectId ||
       !Array.isArray(result.assemblies) || !Array.isArray(result.features))
      throw Error('Trusted desktop FilmIndex catalog could not be verified.');
    setCatalog(result);
    setAssemblyId(prior=>result.assemblies.some(a=>a.assembly_id===prior)
      ? prior : (result.assemblies[0]?.assembly_id||''));
    setFeatureId(prior=>result.features.some(f=>f.feature_id===prior)
      ? prior : (result.features[0]?.feature_id||''));
    setIntentId(prior=>result.director_intents.some(i=>i.intent_id===prior)
      ? prior : (result.director_intents[0]?.intent_id||''));
  }

  useEffect(()=>{
    if(!native || !projectId)return;
    let alive=true;
    Promise.resolve(native.wo5_review_catalog(projectId)).then(result=>{
      if(!alive)return;
      if(result?.status!=='NATIVE_PROJECT_SCOPED_READ_ONLY'||
         result.project_id!==projectId)throw Error('Unverified native project review catalog.');
      setCatalog(result);
      setAssemblyId(result.assemblies[0]?.assembly_id||'');
      setFeatureId(result.features[0]?.feature_id||'');
      setIntentId(result.director_intents[0]?.intent_id||'');
    }).catch(e=>{if(alive)setError(e.message);});
    return ()=>{alive=false;};
  },[native,projectId]);

  const assembly=useMemo(()=>catalog.assemblies.find(a=>a.assembly_id===assemblyId),
    [catalog,assemblyId]);
  const selectedFeature=catalog.features.find(f=>f.feature_id===featureId);
  const totalFrames=exactFrames(assembly?.end_tick);
  const selectedIntent=catalog.director_intents.find(i=>i.intent_id===intentId);
  const belongsToSelectedCut=!!(selectedFeature&&selectedIntent&&
    selectedFeature.assembly_id===selectedIntent.source_assembly_id&&
    selectedFeature.assembly_revision===selectedIntent.source_assembly_revision&&
    selectedFeature.assembly_sha256===selectedIntent.source_assembly_sha256);
  const safeAudit=Boolean(audit?.feature_id===featureId&&
    audit?.status==='SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED'&&
    audit?.production_acceptance===false);

  async function task(fn){
    setBusy(true);setError('');setNotice('');
    try{await fn();}
    catch(e){setError(e.message||'Native director review operation failed.');}
    finally{setBusy(false);}
  }

  function beginDraft(){
    if(!totalFrames){setError('Select a valid frozen source-bound film cut.');return;}
    setDraft(initialShot(totalFrames));setError('');
  }
  function modifyShot(i,key,value){
    setDraft(rows=>rows.map((s,index)=>index===i?{...s,[key]:value}:s));
  }
  function splitLastShot(){
    if(draft.length===0||draft.length>=512)return;
    const last=draft[draft.length-1];
    const frames=Number(last.duration_frames);
    if(!Number.isSafeInteger(frames)||frames<2)return;
    const newId='Shot'+String(draft.length+1).padStart(2,'0');
    const first=Math.floor(frames/2);
    setDraft(rows=>[...rows.slice(0,-1),
      {...last,duration_frames:first},
      {shot_id:newId,duration_frames:frames-first,
       expected_action:'',expected_camera:'',expected_sound:''}]);
  }
  async function saveIntent(){
    await task(async()=>{
      const shots=buildSourceBoundShots(draft,totalFrames);
      const result=await native.wo5_review_save_intent({
        project_id:projectId,assembly_id:assembly.assembly_id,
        assembly_revision:assembly.assembly_revision,
        intent_id:newIntentId,shots});
      if(result.status==='DENIED'){setNotice('Native creator approval declined.');return;}
      if(result.status!=='DIRECTOR_INTENT_FROZEN_NOT_FILM_ACCEPTED')
        throw Error('Original director intent was not committed.');
      await refresh();
      setIntentId(newIntentId);setDraft([]);
      setNotice('Original shot intention frozen in FilmIndex, without generating a movie.');
    });
  }
  async function loadIntent(value=intentId){
    if(!value)return;
    await task(async()=>{
      const result=await native.wo5_review_read_intent(projectId,value);
      if(result.format!=='nvp.wo5.immutable_director_intent.v1')
        throw Error('Original frozen director intent is invalid.');
      setChosenIntent(result);
      setObservations(emptyObservations(result.data.shots));
      setIntentId(value);
      setWatched(false);setHeard(false);
      setAudit(null);setPreviewReel(null);
      setNotice('Original director intention retrieved; no movie has been verified.');
    });
  }
  async function inspectFeature(){
    if(!featureId)return;
    await task(async()=>{
      setAudit(null);setPreviewReel(null);
      const result=await native.wo5_review_inspect_feature(projectId,featureId);
      if(result?.feature_id!==featureId ||
         result.status!=='SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED' ||
         result.production_acceptance!==false)
        throw Error('No verified production feature review evidence.');
      setAudit(result);
      setNotice('Original source and DCP structure rechecked; creative quality still unreviewed.');
    });
  }
  function updateObservation(i,key,value){
    setObservations(rows=>rows.map((s,j)=>i===j?{...s,[key]:value}:s));
  }
  async function saveReview(){
    await task(async()=>{
      if(!safeAudit||!chosenIntent||!belongsToSelectedCut)
        throw Error('Inspect an indexed feature bound to this frozen director intent.');
      if(observations.length!==chosenIntent.data.shots.length)
        throw Error('Record each planned shot, including shots you could not observe.');
      const result=await native.wo5_review_save_observations({
        project_id:projectId,feature_id:featureId,
        intent_id:chosenIntent.intent_id,review_id:reviewId,
        observations,watched_entire_film:watched,
        heard_entire_sound:heard});
      if(result.status==='DENIED'){setNotice('Native creator approval declined.');return;}
      if(result.status!=='DIRECTOR_OBSERVATIONS_RECORDED_NOT_INDEPENDENTLY_VERIFIED' ||
         result.production_acceptance!==false)
        throw Error('Source-bound human review record was not committed.');
      setNotice('Your observations were saved to FilmIndex. This is not NVP production or theatrical approval.');
      await refresh();
    });
  }

  if(!native)return <section className="card" aria-label="Director film review">
    <h2>Review the original film</h2>
    <p role="status">Requires the installed NVP desktop window and its trusted native review bridge.
      A web browser cannot approve or play privileged source material.</p>
  </section>;

  return <div className="columns" aria-label="Director film review">
    <section className="card">
      <h2>Direct, preview and review the film</h2>
      <p className="muted">Three separate milestones: up to 30 minutes proves the workflow;
        a 60–90 minute feature proves production; 3+ hours tests epic-film scale.
        These controls never claim a film has passed merely because its files exist.</p>
      {error&&<p role="alert">{error}</p>}
      {notice&&<p role="status">{notice}</p>}
      <button className="secondary" disabled={busy} onClick={()=>task(()=>refresh())}>
        Refresh native film catalog</button>
      <h3>1 · Freeze what you intended to direct</h3>
      <label>Approved source film cut
        <select aria-label="Approved source film cut" value={assemblyId}
          onChange={e=>{setAssemblyId(e.target.value);setDraft([]);}}>
          <option value="">Choose a frozen FilmIndex cut</option>
          {catalog.assemblies.map(a=><option key={a.assembly_id} value={a.assembly_id}>
            {a.assembly_id} · {exactFrames(a.end_tick)??'invalid'} frames · {a.reel_count} reels
          </option>)}
        </select>
      </label>
      {assembly&&<p className="fineprint">
        Frozen assembly SHA {assembly.assembly_sha256.slice(0,16)}…
        {totalFrames?(' · '+(totalFrames/24).toFixed(2)+' seconds'):' · duration unavailable'}
      </p>}
      <button disabled={busy||!totalFrames} onClick={beginDraft}>
        Plan original film shots</button>
      {draft.length>0&&<div className="context-panel">
        <label>Unique director intent ID
          <input value={newIntentId} maxLength={80}
            onChange={e=>setNewIntentId(e.target.value)}/></label>
        {draft.map((shot,i)=><fieldset key={i} className="scene-item">
          <legend>{shot.shot_id}</legend>
          <label>Shot ID<input aria-label={'Shot '+(i+1)+' ID'} value={shot.shot_id}
            onChange={e=>modifyShot(i,'shot_id',e.target.value)}/></label>
          <label>Duration in 24fps frames<input type="number" min={1} max={43200}
            aria-label={'Shot '+(i+1)+' frames'} value={shot.duration_frames}
            onChange={e=>modifyShot(i,'duration_frames',e.target.value)}/></label>
          {[
            ['expected_action','Intended action'],
            ['expected_camera','Intended camera'],
            ['expected_sound','Intended sound']
          ].map(([key,label])=><label key={key}>{label}
            <textarea rows={2} maxLength={360} value={shot[key]}
              aria-label={'Shot '+(i+1)+' '+label}
              onChange={e=>modifyShot(i,key,e.target.value)}/>
          </label>)}
        </fieldset>)}
        <p className="fineprint">
          {draft.reduce((n,s)=>n+(Number(s.duration_frames)||0),0)} / {totalFrames} original frames covered
        </p>
        <button className="secondary" disabled={busy||draft.length>=512}
          onClick={splitLastShot}>Split last shot</button>
        <button disabled={busy} onClick={saveIntent}>
          Request native approval to freeze intent</button>
      </div>}

      <h3>2 · Inspect genuine production evidence</h3>
      <label>Indexed feature
        <select aria-label="Indexed feature" value={featureId}
          onChange={e=>{setFeatureId(e.target.value);setAudit(null);setPreviewReel(null);}}>
          <option value="">Choose a published feature</option>
          {catalog.features.map(f=><option key={f.feature_id} value={f.feature_id}>
            {f.assembly_id} · {f.state} · {f.feature_id.slice(0,8)}
          </option>)}
        </select>
      </label>
      <button disabled={busy||!featureId||selectedFeature?.state!=='INDEXED'}
        onClick={inspectFeature}>Verify original source and delivery receipts</button>
      {selectedFeature?.state!=='INDEXED'&&selectedFeature&&
        <p className="fineprint">Feature not indexed. Interrupted/queued outputs are not reviewable.</p>}
      {safeAudit&&<div className="context-panel">
        <p role="status">Source custody verified · {audit.frame_count} frames ·
          {audit.reel_count} reels · {audit.seconds} seconds.
          Creative review, independent decode and SMPTE Bv2.1 remain unverified.</p>
        <p className="fineprint">Original picture SHA audit:
          {audit.ordered_picture_custody_sha256.slice(0,24)}…</p>
        <h4>Listen and watch the original source Takes</h4>
        <p className="fineprint">The native 3D/sound viewer below plays a real
          source-authored OpenUSD Take at its approved source time.
          This is <strong>not</strong> playback of the final flattened DCP;
          finished-film A/V and cinema-server playback remain separate acceptance gates.</p>
        {(audit.source_reels_for_native_take_audition||[]).map(reel=>
          <div className="scene-item" key={reel.reel_number}>
            Reel {reel.reel_number}: {reel.take_id} ·
            frames {reel.approved_frame_count}
            <button className="secondary" disabled={busy}
              onClick={()=>setPreviewReel(reel)}>Audition original source</button>
          </div>)}
        {previewReel&&<>
          <button className="secondary" onClick={()=>setPreviewReel(null)}>
            Close source playback</button>
          <DataFirstAVPanel
            key={featureId+':'+previewReel.reel_number}
            projectId={projectId}
            initialTakeId={previewReel.take_id}
            initialTakeSha256={previewReel.take_document_sha256}
            initialSourceSample={Math.floor(previewReel.take_start_tick/147000)}/>
        </>}
      </div>}
    </section>
    <section className="card">
      <h2>3 · Compare the film to your original direction</h2>
      <label>Previously approved director intent
        <select aria-label="Previously approved director intent" value={intentId}
          onChange={e=>{setIntentId(e.target.value);setChosenIntent(null);setObservations([]);}}>
          <option value="">Choose saved director intent</option>
          {catalog.director_intents.map(i=><option key={i.intent_id} value={i.intent_id}>
            {i.intent_id} · {i.shot_count} shots
          </option>)}
        </select>
      </label>
      <button className="secondary" disabled={busy||!intentId}
        onClick={()=>loadIntent()}>Read frozen director intent</button>
      {chosenIntent&&<div className="context-panel">
        <p className="fineprint">Original intention:
          {chosenIntent.intent_sha256.slice(0,24)}…
          {belongsToSelectedCut?' · matches selected original cut':' · choose its matching feature'}</p>
        {chosenIntent.data.shots.map((shot,i)=><fieldset key={shot.shot_id} className="scene-item">
          <legend>Shot {shot.shot_id}</legend>
          <p className="fineprint">Intended action: {shot.expected_action}<br/>
          Intended camera: {shot.expected_camera}<br/>
          Intended sound: {shot.expected_sound}</p>
          {[
            ['observed_action','Actual action observed'],
            ['observed_camera','Actual camera observed'],
            ['observed_sound','Actual sound heard']
          ].map(([field,label])=><label key={field}>{label}
            <textarea maxLength={360} rows={2} value={observations[i]?.[field]||''}
              aria-label={label+' '+shot.shot_id}
              onChange={e=>updateObservation(i,field,e.target.value)}/>
          </label>)}
          <label>Your judgment
            <select value={observations[i]?.judgment||'NOT_OBSERVED'}
              aria-label={'Judgment '+shot.shot_id}
              onChange={e=>updateObservation(i,'judgment',e.target.value)}>
              <option value="NOT_OBSERVED">Not observed</option>
              <option value="NEEDS_REVISION">Needs correction</option>
              <option value="MATCHED">Matches intended result</option>
            </select>
          </label>
          <label>Notes for correction
            <textarea maxLength={360} rows={2}
              value={observations[i]?.review_note||''}
              onChange={e=>updateObservation(i,'review_note',e.target.value)}/>
          </label>
        </fieldset>)}
        <label><input type="checkbox" checked={watched}
          onChange={e=>setWatched(e.target.checked)}/>
          I personally watched the complete finished film</label>
        <label><input type="checkbox" checked={heard}
          onChange={e=>setHeard(e.target.checked)}/>
          I personally listened to the complete finished soundtrack</label>
        <label>Unique review record ID
          <input maxLength={80} value={reviewId} onChange={e=>setReviewId(e.target.value)}/>
        </label>
        <button disabled={busy||!safeAudit||!belongsToSelectedCut}
          onClick={saveReview}>Request native approval to save observations</button>
        <p className="fineprint">Both statements above are your own claims, not
          machine-verifiable evidence. Original Take playback does not establish
          that the complete delivered DCP was watched or heard.
          Saving a review never certifies SMPTE, DCI or production readiness.</p>
      </div>}
      {catalog.director_reviews?.length>0&&<details>
        <summary>Earlier human review records ({catalog.director_reviews.length})</summary>
        <ul>{catalog.director_reviews.map(x=><li key={x.review_id}>
          {x.review_id} — {x.director_requests_revisions?'Revisions requested':'Review recorded'};
          not production accepted
        </li>)}</ul>
      </details>}
    </section>
  </div>;
}
