import React,{useEffect,useMemo,useState} from 'react';

// P1-D/E/F/P2: filmmaker source choices only. Native host owns every consent,
// USD/PCM worker, source hash and output path; JS cannot mint an approval.
const IDENT=/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/;
const CATALOG='nvp.p1def.p2.native_source_stage_catalog.v1';

export default function FilmSourceStagesPanel({
  projectId,native,sourceRevision=0
}){
  const required=[
    'data_av_film_stage_graph_catalog',
    'data_av_film_stage_edit_draft',
    'data_av_film_stage_edit_commit',
    'data_av_film_stage_catalog',
    'data_av_film_stage_director_commit',
    'data_av_film_stage_actor_bus_commit',
    'data_av_film_stage_longform_publish',
    'data_av_film_stage_longform_page',
    'data_av_film_stage_longform_audit_page',
    'data_av_film_stage_chunk_preflight',
    'data_av_film_stage_chunk_begin',
    'data_av_film_stage_chunk_poll',
    'data_av_film_stage_chunk_cancel',
  ];
  const ready=Boolean(native&&required.every(k=>typeof native[k]==='function'));
  const [catalog,setCatalog]=useState(null);
  const [graphs,setGraphs]=useState([]);
  const [graphId,setGraphId]=useState('');
  const [graphBranchId,setGraphBranchId]=useState('');
  const [sourceSegments,setSourceSegments]=useState([]);
  const [newEditId,setNewEditId]=useState('EditedScene001');
  const [draftPreview,setDraftPreview]=useState(null);
  const [editId,setEditId]=useState('');
  const [checks,setChecks]=useState({});
  const [continuityId,setContinuityId]=useState('DirectorReview001');
  const [continuitySource,setContinuitySource]=useState('');
  const [actorDialogue,setActorDialogue]=useState('');
  const [chosenActorMix,setChosenActorMix]=useState('');
  const [mixId,setMixId]=useState('OriginalActorMix001');
  const [listener,setListener]=useState('');
  const [camera,setCamera]=useState('');
  const [planId,setPlanId]=useState('OriginalFilmPlan001');
  const [chosenPlan,setChosenPlan]=useState('');
  const [page,setPage]=useState(null);
  const [audit,setAudit]=useState(null);
  const [ticket,setTicket]=useState(null);
  const [job,setJob]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');

  const currentGraph=graphs.find(x=>x.graph_id===graphId);
  const graphBranches=currentGraph?.branches||[];
  const currentBranch=graphBranches.find(x=>x.branch_id===graphBranchId);
  const edits=catalog?.edits||[];
  const edit=edits.find(x=>x.edit_id===editId);
  const continuity=catalog?.continuity||[];
  const reviews=continuity.filter(x=>
    x.review_status==='READY_FOR_SEPARATE_EXPORT_AUTHORIZATION');
  const selectedReview=reviews.find(x=>x.continuity_id===continuitySource);
  const plans=catalog?.longform_plans||[];
  const selectedPlan=plans.find(x=>x.plan_id===chosenPlan);
  const dialogues=catalog?.original_dialogue||[];
  const chosenDialogue=dialogues.find(x=>x.dialogue_id===actorDialogue);
  const mixes=(catalog?.actor_spatial_mixes||[]);
  const chosenMix=mixes.find(x=>x.mix_id===chosenActorMix);

  async function refresh(){
    if(!ready||!projectId)return;
    const result=await native.data_av_film_stage_catalog(projectId);
    if(result?.format!==CATALOG||
       result.project_id!==projectId||
       result.source_modified!==false||
       result.export_authorized!==false||
       result.film_master_approved!==false||
       !Array.isArray(result.edits)||
       !Array.isArray(result.continuity)||
       !Array.isArray(result.original_dialogue)||
       !Array.isArray(result.longform_plans)||
       !Array.isArray(result.actor_spatial_mixes))
      throw Error('Original film sources are not verified by the native host');
    setCatalog(result);
    setEditId(old=>result.edits.some(x=>x.edit_id===old)
      ?old:(result.edits[0]?.edit_id||''));
    setContinuitySource(old=>result.continuity.some(x=>x.continuity_id===old)
      ?old:(result.continuity.find(
        x=>x.review_status==='READY_FOR_SEPARATE_EXPORT_AUTHORIZATION'
      )?.continuity_id||''));
    setActorDialogue(old=>result.original_dialogue.some(x=>x.dialogue_id===old)
      ?old:(result.original_dialogue[0]?.dialogue_id||''));
    setChosenPlan(old=>result.longform_plans.some(x=>x.plan_id===old)
      ?old:(result.longform_plans[0]?.plan_id||''));
    setChosenActorMix(old=>result.actor_spatial_mixes.some(x=>x.mix_id===old)
      ?old:'');
    return result;
  }

  useEffect(()=>{
    let active=true;
    setGraphs([]);setGraphId('');setGraphBranchId('');
    setSourceSegments([]);setDraftPreview(null);
    if(!ready||!projectId)return;
    Promise.resolve(native.data_av_film_stage_graph_catalog(projectId))
      .then(result=>{
        if(!active)return;
        if(result?.format!=='nvp.p1d.native_original_source_graph_catalog.v1'||
           result.project_id!==projectId||
           result.original_source_modified!==false||
           result.active_cut_changed!==false||!Array.isArray(result.graphs))
          throw Error('Original digital slate graph cannot be source-verified');
        setGraphs(result.graphs);
        setGraphId(result.graphs[0]?.graph_id||'');
      }).catch(e=>{if(active)setError(e.message)});
    return ()=>{active=false};
  },[native,projectId,sourceRevision,ready]);

  useEffect(()=>{
    setSourceSegments([]);setDraftPreview(null);
    setGraphBranchId(currentGraph?.branches?.[0]?.branch_id||'');
  },[graphId]);

  useEffect(()=>{
    let active=true;
    setCatalog(null);setPage(null);setTicket(null);setJob(null);
    setChecks({});setError('');setMessage('');setAudit(null);
    if(!ready||!projectId)return;
    Promise.resolve(native.data_av_film_stage_catalog(projectId)).then(result=>{
      if(!active)return;
      if(result?.format!==CATALOG||result.project_id!==projectId||
         result.source_modified!==false||result.film_master_approved!==false||
         !Array.isArray(result.edits)||!Array.isArray(result.continuity)||
         !Array.isArray(result.longform_plans)||
         !Array.isArray(result.original_dialogue)||
         !Array.isArray(result.actor_spatial_mixes))
        throw Error('Native project source catalog cannot be verified');
      setCatalog(result);
      setEditId(result.edits[0]?.edit_id||'');
      setContinuitySource(result.continuity.find(
        x=>x.review_status==='READY_FOR_SEPARATE_EXPORT_AUTHORIZATION'
      )?.continuity_id||'');
      setActorDialogue(result.original_dialogue[0]?.dialogue_id||'');
      setChosenPlan(result.longform_plans[0]?.plan_id||'');
      // Default to the full original source mix. Actor-only filtering is
      // always a deliberate filmmaker choice, never silently enabled.
      setChosenActorMix('');
    }).catch(e=>{if(active)setError(e.message)});
    return ()=>{active=false};
  },[native,projectId,sourceRevision,ready]);

  useEffect(()=>{
    if(!edit){setListener('');setCamera('');setChecks({});return}
    setListener(old=>edit.listeners?.includes(old)?old:(edit.listeners?.[0]||''));
    setCamera(old=>edit.cameras?.includes(old)?old:(edit.cameras?.[0]||''));
    setChecks({});
  },[edit?.edit_id,edit?.edit_sha256]);

  function addOriginalSegment(){
    if(!currentBranch)return;
    const used=new Set(sourceSegments.map(x=>x.segment_id));
    let serial=sourceSegments.length+1;
    while(used.has('Cut'+String(serial).padStart(3,'0')))serial+=1;
    const start=Number(currentBranch.source_start_tick);
    const end=Number(currentBranch.source_end_tick);
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||end<=start){
      setError('Original source Film Time cannot be represented precisely');
      return;
    }
    setSourceSegments(v=>[...v,{
      segment_id:'Cut'+String(serial).padStart(3,'0'),
      branch_id:currentBranch.branch_id,
      source_in_tick:start,source_out_tick:end,
    }]);
    setDraftPreview(null);setError('');
  }

  function changeOriginalSegment(i,field,value){
    const n=Number(value);
    setSourceSegments(previous=>previous.map((row,k)=>k===i
      ?{...row,[field]:Number.isSafeInteger(n)&&n>=0?n:-1}:row));
    setDraftPreview(null);
  }

  function moveOriginalSegment(i,shift){
    setSourceSegments(old=>{
      const target=i+shift;
      if(target<0||target>=old.length)return old;
      const reordered=[...old];
      [reordered[target],reordered[i]]=[reordered[i],reordered[target]];
      return reordered;
    });
    setDraftPreview(null);
  }

  function previewSourceCut(){
    run(async()=>{
      if(!currentGraph||!sourceSegments.length)
        throw Error('Choose an original slate and at least one source segment');
      const result=await native.data_av_film_stage_edit_draft({
        project_id:projectId,graph_id:currentGraph.graph_id,
        graph_revision:currentGraph.graph_revision,segments:sourceSegments,
      });
      if(result?.format!=='nvp.p1d.native_source_cut_draft.v1'||
         result.project_id!==projectId||
         result.graph_sha256!==currentGraph.graph_sha256||
         result.draft_uncommitted!==true||
         result.render_approved!==false||
         result.original_source_modified!==false||
         result.segment_count!==sourceSegments.length)
        throw Error('Draft is not source-authentic or immutable');
      setDraftPreview(result);
      setMessage('Original cut is ready for a separate native editorial confirmation.');
    });
  }

  function commitSourceCut(){
    run(async()=>{
      if(!draftPreview||!currentGraph)
        throw Error('Review the exact original cut before committing');
      validateIdentity(newEditId,'Unique source edit');
      const receipt=await native.data_av_film_stage_edit_commit({
        project_id:projectId,edit_id:newEditId,
        graph_id:currentGraph.graph_id,
        graph_revision:currentGraph.graph_revision,
        segments:sourceSegments,expected_revision:0,
      });
      if(receipt?.format!=='nvp.p1d.native_original_cut_commit_receipt.v1'||
         receipt.status!=='IMMUTABLE_EDIT_SOURCE_COMMITTED'||
         receipt.source_modified!==false||
         receipt.render_approved!==false||
         receipt.source_segments_sha256!==draftPreview.source_segment_sha256)
        throw Error('OS-native committed cut failed original source digest check');
      setDraftPreview(null);setSourceSegments([]);
      await refresh();
      setEditId(receipt.edit_id);
      setMessage('New source cut committed with original Take SHA and zero retiming.');
    });
  }

  async function run(action){
    if(busy)return;
    setBusy(true);setError('');setMessage('');
    try{await action()}
    catch(e){setError(e.message||String(e))}
    finally{setBusy(false)}
  }

  function validateIdentity(value,what){
    if(!IDENT.test(value))throw Error(what+' needs a unique source identity');
  }

  function commitDirector(){
    run(async()=>{
      if(!edit)throw Error('Choose a committed original edit');
      validateIdentity(continuityId,'Director review');
      if(!edit.segments.length||
         !edit.segments.every(x=>checks[x.segment_id]===true))
        throw Error('Acknowledge the original continuity of every selected segment');
      const cues=edit.segments.map(x=>({
        segment_id:x.segment_id,
        continuity:'accepted',
        audio_policy:'original_scene',
        note:'Creator checked source continuity and original audio',
      }));
      const receipt=await native.data_av_film_stage_director_commit({
        project_id:projectId,continuity_id:continuityId,
        edit_id:edit.edit_id,edit_revision:edit.edit_revision,
        cues,expected_revision:0,
      });
      if(receipt?.format!=='nvp.p1d.native_director_commit_receipt.v1'||
         receipt.status!=='ORIGINAL_EDIT_REVIEW_COMMITTED'||
         receipt.export_approved!==false||receipt.original_source_modified!==false)
        throw Error('Native original edit was not committed authoritatively');
      await refresh();
      setContinuitySource(receipt.continuity_id);
      setMessage('Director source review saved. A separate export approval remains required.');
    });
  }

  function commitActorBus(){
    run(async()=>{
      if(!chosenDialogue||!listener)
        throw Error('Choose an original actor dialogue and an authored listener');
      validateIdentity(mixId,'Actor-owned spatial bus');
      const receipt=await native.data_av_film_stage_actor_bus_commit({
        project_id:projectId,mix_id:mixId,
        take_id:chosenDialogue.take_id,
        listener_path:listener,
        routes:[{dialogue_id:chosenDialogue.dialogue_id,
                 revision:chosenDialogue.revision,gain:1.0}],
        expected_revision:0,
      });
      if(receipt?.format!=='nvp.p1e.native_actor_bus_receipt.v1'||
         receipt.status!=='SOURCE_DIALOGUE_BUS_COMMITTED'||
         receipt.original_pcm_modified!==false||
         receipt.sound_master_approved!==false)
        throw Error('Original actor voice bus has no native source receipt');
      await refresh();
      setChosenActorMix(receipt.mix_id);
      setMessage('Original ActorID dry spatial dialogue bus saved, no voice synthesis.');
    });
  }

  function publishPlan(){
    run(async()=>{
      if(!selectedReview||!listener||!camera)
        throw Error('Choose a reviewed director cut, its camera and listener');
      validateIdentity(planId,'Original film plan');
      const result=await native.data_av_film_stage_longform_publish({
        project_id:projectId,plan_id:planId,
        continuity_id:selectedReview.continuity_id,
        continuity_revision:selectedReview.revision,
        listener_path:listener,camera_path:camera,
        expected_revision:0,
      });
      if(result?.format!=='nvp.p2.native_longform_source_plan_receipt.v1'||
         result.status!=='SOURCE_ONLY_LONGFORM_PLAN_INDEXED'||
         result.rendered_frames!==0||result.film_master_approved!==false)
        throw Error('Native original long-form schedule was not pinned');
      await refresh();
      setChosenPlan(result.plan_id);
      setMessage('Original film source schedule created. No film frames have been rendered.');
    });
  }

  function showPage(first=0){
    run(async()=>{
      if(!selectedPlan)throw Error('Choose an original long-form plan');
      const result=await native.data_av_film_stage_longform_page({
        project_id:projectId,plan_id:selectedPlan.plan_id,
        revision:selectedPlan.revision,
        first_index:first,limit:8,
      });
      if(result?.format!=='nvp.p2.original_film_longform_source_schedule.v1'||
         result.plan_sha256!==selectedPlan.plan_sha256||
         result.full_film_picture_sound_delivered!==false||
         !Array.isArray(result.chunks))
        throw Error('Source reel page cannot be verified');
      setPage(result);setAudit(null);
    });
  }

  function auditPage(){
    run(async()=>{
      if(!selectedPlan||!page)throw Error('Choose an original reel page');
      const result=await native.data_av_film_stage_longform_audit_page({
        project_id:projectId,plan_id:selectedPlan.plan_id,
        revision:selectedPlan.revision,
        first_index:page.start_index,limit:8,
      });
      if(result?.format!=='nvp.p2.original_film_longform_source_schedule.v1'||
         result.full_film_master_approved!==false)
        throw Error('Independent source-derivative audit was not returned');
      setAudit(result);
    });
  }

  function renderChunk(chunk){
    run(async()=>{
      if(!selectedPlan||!selectedReview)
        throw Error('A director-reviewed original cut is required for rendering');
      if(selectedReview.edit_sha256!==selectedPlan.source_edit_sha256)
        throw Error('This source reel belongs to a different approved director cut');
      if(chosenMix&&(
          chosenMix.take_sha256!==chunk.source_take_sha256||
          chosenMix.listener_path!==listener))
        throw Error('Selected original actor sound bus belongs to a different Take or listener');
      const choice={
        project_id:projectId,
        continuity_id:selectedReview.continuity_id,
        continuity_revision:selectedReview.revision,
        first_frame:chunk.first_frame,frame_count:chunk.frame_count,
        listener_path:listener,camera_path:camera,
        actor_mix_id:chosenMix?.mix_id||null,
        actor_mix_revision:chosenMix?.revision||null,
      };
      const preflight=await native.data_av_film_stage_chunk_preflight(choice);
      if(preflight?.format!=='nvp.p1f.immutable_picture_sound_chunk.v1'||
         preflight.source_take_sha256!==chunk.source_take_sha256||
         preflight.source_start_tick!==chunk.source_start_tick||
         preflight.output_frames_generated!==false||
         preflight.full_film_master_approved!==false)
        throw Error('Selected reel does not match the director-approved source cut');
      const result=await native.data_av_film_stage_chunk_begin({
        ...choice,chunk_id:chunk.chunk_id,
      });
      if(result?.format!=='nvp.p1f.native_source_chunk_ticket.v1'||
         result.status!=='QUEUED_NATIVE_APPROVAL'||
         result.film_master_approved!==false||
         !result.ticket)
        throw Error('Original renderer did not return a native worker ticket');
      setJob(null);setTicket(result.ticket);
      setMessage('One protected original-source chunk awaits native creator approval.');
    });
  }

  useEffect(()=>{
    if(!ticket||!native||!ready)return;
    let active=true;
    const poll=async()=>{
      try{
        const result=await native.data_av_film_stage_chunk_poll(ticket);
        if(!active)return;
        if(result?.format!=='nvp.p1f.native_source_chunk_ticket.v1'||
           result.film_master_approved!==false)
          throw Error('Native chunk receipt is unverified');
        setJob(result);
        if(!['RUNNING_OR_AWAITING_NATIVE_APPROVAL'].includes(result.status)){
          setTicket(null);
        }
      }catch(e){if(active){setError(e.message);setTicket(null)}}
    };
    poll();
    const handle=setInterval(poll,1500);
    return ()=>{active=false;clearInterval(handle)};
  },[ticket,native,ready]);

  async function cancelChunk(){
    if(!ticket)return;
    try{
      await native.data_av_film_stage_chunk_cancel(ticket);
      setMessage('Native cancellation requested; worker custody is verified by host.');
    }catch(e){setError(e.message)}
  }

  return <section className="card" aria-label="Original movie editing and delivery">
    <h2>Edit, direct sound, film and deliver</h2>
    <p className="fineprint">The movie uses your original frozen performances,
      authoritative Film Time and 3D scene. Source decisions are separate from
      sound, supervised picture rendering and release approval.</p>
    {!ready&&<p role="status">Trusted installed NVP is required for creator authorization.</p>}
    {error&&<p role="alert">{error}</p>}
    {message&&<p role="status">{message}</p>}

    <h3>1 · Assemble a non-destructive film cut</h3>
    <p className="fineprint">Choose original digital slate Takes and their
      source Film Time ranges, trim and reorder without changing performances.
      Preview is read-only. The final cut requires a native creator approval.</p>
    <label>Original digital slate
      <select aria-label="Original film slate" value={graphId}
        disabled={busy} onChange={e=>setGraphId(e.target.value)}>
        <option value="">Choose recorded slate</option>
        {graphs.map(x=><option key={x.graph_id} value={x.graph_id}>
          {x.graph_id} · {x.branches.length} recorded angles or Takes</option>)}
      </select>
    </label>
    <label>Original Take or camera angle to add
      <select aria-label="Original source branch" value={graphBranchId}
        disabled={busy} onChange={e=>setGraphBranchId(e.target.value)}>
        <option value="">Choose original source</option>
        {graphBranches.map(x=><option key={x.branch_id} value={x.branch_id}>
          {x.branch_id} · {x.kind} · {x.take_id}</option>)}
      </select>
    </label>
    {currentBranch&&<p className="fineprint">Source interval:
      {' '}{currentBranch.source_start_tick}–
      {currentBranch.source_end_tick} exact native Film Time ticks</p>}
    <button disabled={!ready||busy||!currentBranch||sourceSegments.length>=500}
      onClick={addOriginalSegment}>Add source clip to cut</button>
    {sourceSegments.map((segment,i)=><fieldset key={segment.segment_id}>
      <legend>Clip {i+1} · {segment.branch_id}</legend>
      <label>Source in (Film Time ticks) {segment.segment_id}
        <input aria-label={'Source in '+segment.segment_id}
          type="number" min="0" step="1" disabled={busy}
          value={segment.source_in_tick}
          onChange={e=>changeOriginalSegment(i,'source_in_tick',e.target.value)}/>
      </label>
      <label>Source out (Film Time ticks) {segment.segment_id}
        <input aria-label={'Source out '+segment.segment_id}
          type="number" min="1" step="1" disabled={busy}
          value={segment.source_out_tick}
          onChange={e=>changeOriginalSegment(i,'source_out_tick',e.target.value)}/>
      </label>
      <button disabled={busy||i===0} onClick={()=>moveOriginalSegment(i,-1)}>
        Earlier</button>
      <button disabled={busy||i===sourceSegments.length-1}
        onClick={()=>moveOriginalSegment(i,1)}>Later</button>
      <button disabled={busy} onClick={()=>{
        setSourceSegments(old=>old.filter((_,j)=>j!==i));setDraftPreview(null);
      }}>Remove source clip</button>
    </fieldset>)}
    <button disabled={!ready||busy||!sourceSegments.length}
      onClick={previewSourceCut}>Preview authentic cut without saving</button>
    {draftPreview&&<p role="status">Original source preview verified:
      {' '}{draftPreview.segment_count} clips,
      {' '}{draftPreview.duration_tick} Film Time ticks.
      Nothing has been committed or rendered.</p>}
    <label>Unique new film cut ID
      <input value={newEditId} maxLength={80} disabled={busy}
        onChange={e=>{setNewEditId(e.target.value);setDraftPreview(null)}}/>
    </label>
    <button disabled={!ready||busy||!draftPreview}
      onClick={commitSourceCut}>Ask native editor to commit this source cut</button>

    <h3>Review the committed source cut</h3>
    <label>Committed movie cut
      <select aria-label="Committed original movie cut" value={editId}
        disabled={busy} onChange={e=>setEditId(e.target.value)}>
        <option value="">Choose original source cut</option>
        {edits.map(x=><option key={x.edit_id} value={x.edit_id}>
          {x.edit_id} · {x.segments.length} segments</option>)}
      </select>
    </label>
    <label>Unique director continuity review
      <input value={continuityId} maxLength={80}
        disabled={busy} onChange={e=>setContinuityId(e.target.value)}/>
    </label>
    {(edit?.segments||[]).map(segment=>
      <label key={segment.segment_id}>
        <input type="checkbox" checked={checks[segment.segment_id]===true}
          disabled={busy} onChange={e=>setChecks(x=>({
            ...x,[segment.segment_id]:e.target.checked
          }))}/>
        Reviewed original {segment.segment_id} · source {segment.source_take_id}
        {segment.source_shot_id?' · camera '+segment.source_shot_id:''}
      </label>)}
    <button disabled={!ready||busy||!edit} onClick={commitDirector}>
      Ask director to save source continuity review
    </button>

    <h3>2 · Sound — actor-owned original dialogue</h3>
    <label>Original recorded ActorID voice
      <select aria-label="Original ActorID dialogue" value={actorDialogue}
        disabled={busy} onChange={e=>setActorDialogue(e.target.value)}>
        <option value="">Select recorded voice</option>
        {dialogues.map(x=><option key={x.dialogue_id} value={x.dialogue_id}>
          {x.actor_id} · {x.dialogue_id}</option>)}
      </select>
    </label>
    <label>Original stereo bus identity
      <input value={mixId} maxLength={80} disabled={busy}
        onChange={e=>setMixId(e.target.value)}/>
    </label>
    <label>USD virtual microphone
      <select aria-label="Original film listener" value={listener} disabled={busy}
        onChange={e=>setListener(e.target.value)}>
        <option value="">Choose authored listener</option>
        {(edit?.listeners||[]).map(x=><option key={x} value={x}>{x}</option>)}
      </select>
    </label>
    <button disabled={!ready||busy||!chosenDialogue||!listener}
      onClick={commitActorBus}>Ask director to save original actor mix</button>
    <p className="fineprint">Dry 48-kHz source dialogue, not synthesized voices,
      acoustic HRTF or automatic phoneme lip-sync.</p>

    <label>Optional approved original ActorID bus for finite picture chunks
      <select aria-label="Original film ActorID sound bus" disabled={busy}
        value={chosenActorMix} onChange={e=>setChosenActorMix(e.target.value)}>
        <option value="">Use complete original scene sound</option>
        {mixes.map(x=><option key={x.mix_id} value={x.mix_id}>
          {x.mix_id} · original {x.take_id} · {x.actor_ids.join(', ')}</option>)}
      </select>
    </label>

    <h3>3 · Film — plan the original movie</h3>
    <label>Reviewed director cut
      <select aria-label="Accepted original director review" value={continuitySource}
        disabled={busy} onChange={e=>setContinuitySource(e.target.value)}>
        <option value="">Choose accepted cut</option>
        {reviews.map(x=><option key={x.continuity_id} value={x.continuity_id}>
          {x.continuity_id}</option>)}
      </select>
    </label>
    <label>Actual OpenUSD picture camera
      <select aria-label="Original movie picture camera" value={camera} disabled={busy}
        onChange={e=>setCamera(e.target.value)}>
        <option value="">Choose original camera</option>
        {(edit?.cameras||[]).map(x=><option key={x} value={x}>{x}</option>)}
      </select>
    </label>
    <label>Unique long-form source plan
      <input value={planId} maxLength={80} disabled={busy}
        onChange={e=>setPlanId(e.target.value)}/>
    </label>
    <button disabled={!ready||busy||!selectedReview||!camera||!listener}
      onClick={publishPlan}>Ask creator to index original film schedule</button>
    <label>Original film schedule
      <select aria-label="Original longform source schedule" value={chosenPlan}
        disabled={busy} onChange={e=>{setChosenPlan(e.target.value);setPage(null)}}>
        <option value="">Choose source schedule</option>
        {plans.map(x=><option key={x.plan_id} value={x.plan_id}>
          {x.plan_id} · {x.total_frames} frames planned</option>)}
      </select>
    </label>
    {selectedPlan&&<p className="fineprint">{selectedPlan.total_chunks} finite source chunks
      · {selectedPlan.total_frames} source frames indexed.
      {selectedPlan.longform?' Long-form source cut.':' Short-form source rehearsal.'}
      No scheduled frame is counted as rendered.</p>}
    <button disabled={!ready||busy||!selectedPlan}
      onClick={()=>showPage(0)}>View first source reel chunks</button>

    {page&&<section aria-label="Finite source picture and sound chunks">
      <h3>4 · Deliver — one approved original chunk at a time</h3>
      <p className="fineprint">Each chunk has 1–24 original 24fps frames and
        matching 48-kHz PCM. Separate native approval and protected
        Blender/Cycles custody are required for EACH render.</p>
      <ul>
        {page.chunks.map(x=><li key={x.chunk_id}>
          {x.chunk_id} · source {x.source_take_id} · frames
          {' '}{x.first_frame}–{x.first_frame+x.frame_count-1}
          <button disabled={!ready||busy||!!ticket||
              !selectedReview||!camera||!listener}
            onClick={()=>renderChunk(x)}>Authorize and film this chunk</button>
        </li>)}
      </ul>
      <button disabled={busy||page.next_index===null}
        onClick={()=>showPage(page.next_index)}>Next reel page</button>
      <button disabled={busy} onClick={auditPage}>
        Independently verify this page's finished chunks
      </button>
      {audit&&<p role="status">
        {audit.verified_chunks?.length||0} independently verified,
        {' '}{audit.missing_chunks?.length||0} still missing.
        No completion inferred from queued workers.
      </p>}
    </section>}
    {ticket&&<button onClick={cancelChunk}>Cancel active protected film chunk</button>}
    {job&&<p role="status">Native picture/sound:
      {' '}{job.status}.
      {job.receipt?.status==='INDEPENDENT_SOURCE_CHUNK_VERIFIED'
        ?' Picture and PCM hashes reopened successfully. This is not a master.':''}
    </p>}
    <p className="fineprint">No automatic release, source mutation, plaintext
      original storage or production installation is authorized here. Real
      camera-shot acoustic movement must be explicitly composed before export.</p>
  </section>;
}
