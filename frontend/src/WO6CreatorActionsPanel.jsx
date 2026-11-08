import React, {useEffect, useState} from 'react';

// WO6 first-party WebView2 only. An LLM, ordinary HTTP browser or project
// JSON cannot grant creator/native execution. The Python OS host must show
// TWO separate native confirmation dialogs before running ANY worker.
const TICKS_PER_SECOND = 7056000000;
const DEFAULT_COLOR = {
  exposure_stops: 0, contrast: 1, saturation: 1,
  temperature_kelvin: 5600, tint_magenta_green: 0,
};
const ACTIONS = [
  ['take','New immutable Take'],
  ['camera','Camera shot adjustment'],
  ['blocking','Actor/prop blocking'],
  ['lighting','Lighting shot adjustment'],
  ['color','New derived color decision'],
  ['camera_sequence','New exact Film Time camera sequence'],
  ['sound_cue','New original PCM sound cue timeline'],
  ['editorial_cut','New assembled digital-slate film edit'],
];
function errorText(e){return e?.message || String(e)}
function sourceFor(kind,scene,take){
  if(kind==='take'||kind==='camera_sequence'){
    if(!scene)return null;
    return {id:scene.id,revision:scene.revision,sha256:scene.sha256,
      change:kind==='take'?'retake':'revise_camera'};
  }
  if(kind==='color'){
    if(!take)return null;
    return {id:take.id,revision:take.revision,sha256:take.sha256,change:'revise_color'};
  }
  if(!take||!scene)return null;
  return {id:scene.id,revision:scene.revision,sha256:scene.sha256,
    change:kind==='camera'?'revise_camera':
      kind==='blocking'?'revise_actor_performance':'revise_scene'};
}

export default function WO6CreatorActionsPanel({projectId}){
  const [catalog,setCatalog]=useState(null);
  const [problem,setProblem]=useState('');
  const [busy,setBusy]=useState(false);
  const [kind,setKind]=useState('take');
  const [sceneId,setSceneId]=useState('');
  const [takeId,setTakeId]=useState('');
  const [timelineId,setTimelineId]=useState('');
  const [newId,setNewId]=useState('');
  const [impact,setImpact]=useState(null);
  const [receipt,setReceipt]=useState(null);
  const [status,setStatus]=useState(null);
  const [selectedPath,setSelectedPath]=useState('');
  const [value,setValue]=useState('50');
  const [startTick,setStartTick]=useState('0');
  const [endTick,setEndTick]=useState(String(TICKS_PER_SECOND));
  const [color,setColor]=useState(DEFAULT_COLOR);
  const [localModels,setLocalModels]=useState([]);
  const [localModelState,setLocalModelState]=useState('');
  const [localModelId,setLocalModelId]=useState('');
  const [aiDirection,setAiDirection]=useState('');
  const [aiFilmTick,setAiFilmTick]=useState('0');
  const [aiProposalTicket,setAiProposalTicket]=useState(null);
  const [aiProposal,setAiProposal]=useState(null);
  const [aiReviewKind,setAiReviewKind]=useState('');
  const [aiReview,setAiReview]=useState(null);
  const [directorReason,setDirectorReason]=useState('');
  const [directorTypedChange,setDirectorTypedChange]=useState(false);
  const [slateGraphId,setSlateGraphId]=useState('');
  const [soundSourceId,setSoundSourceId]=useState('');
  const [soundEventId,setSoundEventId]=useState('');
  const [soundSubject,setSoundSubject]=useState('');
  const [soundFirstSample,setSoundFirstSample]=useState('0');
  const [soundGain,setSoundGain]=useState('1');
  const [editSegments,setEditSegments]=useState([{
    segment_id:'',branch_id:'',source_in_tick:'',source_out_tick:'',
  }]);
  const native=()=>window.pywebview?.api;
  const currentScene=catalog?.scenes?.find(x=>x.id===sceneId)||null;
  const currentTake=catalog?.takes?.find(x=>x.id===takeId)||null;
  const currentTimeline=catalog?.timelines?.find(x=>x.id===timelineId)||null;
  const currentTakeTimeline=catalog?.timelines?.find(x=>
    x.id===currentTake?.data?.timeline_id &&
    x.revision===currentTake?.data?.timeline_revision) ||null;
  const currentGraph=catalog?.slate_graphs?.find(x=>x.id===slateGraphId)||null;
  const currentSound=catalog?.audio_sources?.find(x=>x.id===soundSourceId)||null;
  const scene=(kind==='take'||kind==='camera_sequence')?currentScene:
    (currentTake?.data?.scene_id
      ?catalog?.scenes?.find(x=>x.id===currentTake.data.scene_id)||null
      :currentScene);
  const matchingRoles=scene?.data?.prim_roles||{};
  const paths=Object.entries(matchingRoles).filter(([path,role])=>
    (kind==='camera'||kind==='camera_sequence')?role==='camera':
    kind==='lighting'?role==='light':
    kind==='blocking'?(role==='actor'||role==='prop'):false);
  const selectedOriginal=(kind==='sound_cue'?
    (currentTakeTimeline?{id:currentTakeTimeline.id,
      revision:currentTakeTimeline.revision,sha256:currentTakeTimeline.sha256,
      change:'revise_sound'}:null):kind==='editorial_cut'?
    (currentGraph?{id:currentGraph.id,revision:currentGraph.revision,
      sha256:currentGraph.sha256,change:'revise_edit'}:null):
    sourceFor(kind,kind==='take'||kind==='camera_sequence'?
      currentScene:scene,currentTake));
  const fingerprint=selectedOriginal
    ?[projectId,kind,selectedOriginal.id,selectedOriginal.revision,
      selectedOriginal.sha256].join('|'):null;
  const typedOperation=(kind==='sound_cue'||kind==='editorial_cut');
  const usableImpact=impact?.fingerprint===fingerprint &&
    impact?.data?.status==='READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT' &&
    impact?.data?.indexed_downstream_truncated===false &&
    (!typedOperation || (impact.typed?.status==='READ_ONLY_TYPED_DECISION_NO_GRANT'
      && impact.typed?.creative_approval_granted===false
      && impact.typed?.native_worker_authorized===false));
  useEffect(()=>{setImpact(null)},[fingerprint]);
  // Never present prior Take/project suggestions as if selected for the
  // currently viewed original source. The native receipt itself remains
  // SHA-bound even if the user changes the panel selection mid-generation.
  useEffect(()=>{
    setAiProposalTicket(null);
    setAiProposal(null);
    setAiReview(null);
    setAiReviewKind('');
    setDirectorTypedChange(false);
  },[projectId,takeId]);
  useEffect(()=>{
    let live=true;
    async function load(){
      const bridge=native();
      if(typeof bridge?.wo6_source_catalog!=='function'){
        if(live)setProblem('Creator-native operations require the installed NVP desktop WebView2 host.');
        return;
      }
      try{
        const response=await bridge.wo6_source_catalog(projectId);
        if(!live)return;
        if(response?.format!=='nvp.wo6.director_desktop_native_consent.v1')
          throw new Error('Unverified native FilmIndex catalog');
        setCatalog(response);
        setSceneId(old=>old||response.scenes[0]?.id||'');
        setTakeId(old=>old||response.takes[0]?.id||'');
        setTimelineId(old=>old||response.timelines[0]?.id||'');
        setSoundSourceId(old=>old||response.audio_sources?.[0]?.id||'');
        setSlateGraphId(old=>old||response.slate_graphs?.[0]?.id||'');
        setProblem('');
      }catch(e){if(live)setProblem(errorText(e))}
    }
    void load();
    window.addEventListener('pywebviewready',load);
    return ()=>{live=false;window.removeEventListener('pywebviewready',load)};
  },[projectId]);
  const refresh=async()=>{
    const data=await native().wo6_source_catalog(projectId);
    setAiReview(null);
    setDirectorTypedChange(false);
    setCatalog(data);
    setSoundSourceId(old=>data.audio_sources?.some(x=>x.id===old)?
      old:(data.audio_sources?.[0]?.id||''));
    setSlateGraphId(old=>data.slate_graphs?.some(x=>x.id===old)?
      old:(data.slate_graphs?.[0]?.id||''));
    setSceneId(old=>data.scenes.find(x=>x.id===old)?old:(data.scenes[0]?.id||''));
    setTakeId(old=>data.takes.find(x=>x.id===old)?old:(data.takes[0]?.id||''));
  };
  const run=async(fn)=>{
    setProblem('');setBusy(true);
    try{await fn()}
    catch(e){setProblem(errorText(e))}
    finally{setBusy(false)}
  };
  const preview=()=>run(async()=>{
    if(!selectedOriginal)throw new Error('Select a real source revision first');
    let typed=null;
    let typedFingerprint=null;
    if(typedOperation){
      const request=typedDecision();
      typedFingerprint=JSON.stringify(request);
      typed=await native().wo6_preview_typed_decision(request);
      if(typed?.status!=='READ_ONLY_TYPED_DECISION_NO_GRANT'||
          !typed.typed_preview_sha256||
          typed.native_worker_authorized!==false)
        throw new Error('Real native sound/editorial preview was not source-verified');
    }
    const data=await native().wo6_source_impact({
      project_id:projectId,source_id:selectedOriginal.id,
      source_revision:selectedOriginal.revision,
      source_sha256:selectedOriginal.sha256,
      change_kind:selectedOriginal.change,
    });
    if(!data?.preview_sha256)throw new Error('Native source impact proof is incomplete');
    setImpact({fingerprint,data,typed,typedFingerprint});
    setReceipt(null);
  });
  function exactInteger(text,label){
    if(!/^(0|[1-9][0-9]{0,14})$/.test(text))
      throw new Error(label+' requires canonical nonnegative Film Time ticks');
    const number=Number(text);
    if(!Number.isSafeInteger(number))throw new Error(label+' exceeds exact JS integer');
    return number;
  }
  function typedDecision(){
    if(!typedOperation||!selectedOriginal)
      throw new Error('Choose a native recorded sound timeline or slate graph');
    if(!/^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/.test(newId))
      throw new Error('Choose a new immutable native sound/edit ID');
    let payload,duration_tick;
    if(kind==='sound_cue'){
      if(!currentTake||!currentTakeTimeline||!currentSound||
          !/^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/.test(soundEventId)||
          !/^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/.test(soundSubject))
        throw new Error('Choose a source sound, cue ID and subject for the selected Take');
      const gain=Number(soundGain);
      if(!soundGain.trim()||!Number.isFinite(gain)||gain<0||gain>2)
        throw new Error('Enter bounded independent PCM gain');
      payload={
        cue_id:soundEventId,subject_id:soundSubject,
        start_tick:exactInteger(startTick,'Sound start'),
        end_tick:exactInteger(endTick,'Sound end'),
        recorded_sound_id:currentSound.id,
        recorded_sound_revision:currentSound.revision,
        recorded_sound_sha256:currentSound.sha256,
        first_sample:exactInteger(soundFirstSample,'PCM start sample'),
        gain,
      };
      duration_tick=String(currentTakeTimeline.data.duration_tick);
    }else{
      if(!currentGraph||!currentTake||!editSegments.length||
          editSegments.length>64)
        throw new Error('Select one bounded original-slate edit');
      payload=editSegments.map((entry,i)=>{
        if(!/^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/.test(entry.segment_id)||
            !currentGraph.data.nodes.some(node=>node.branch_id===entry.branch_id))
          throw new Error('Choose original branch and unique segment ID for row '+(i+1));
        return {
          segment_id:entry.segment_id,branch_id:entry.branch_id,
          source_in_tick:exactInteger(entry.source_in_tick,'Source in'),
          source_out_tick:exactInteger(entry.source_out_tick,'Source out'),
        };
      });
      duration_tick=null;
    }
    return {
      project_id:projectId,decision_kind:kind,decision_id:newId,
      source_id:selectedOriginal.id,source_revision:selectedOriginal.revision,
      source_sha256:selectedOriginal.sha256,payload,duration_tick,
    };
  }
  function shotOpinions(){
    const target=selectedPath||paths[0]?.[0];
    if(!target)throw new Error('Selected source has no supported OpenUSD target');
    if(kind==='camera'){
      const focal=Number(value);
      if(!Number.isFinite(focal))throw new Error('Finite focal length required');
      return [{path:target,property:'camera_focal_length_mm',value:focal}];
    }
    if(kind==='lighting'){
      const level=Number(value);
      if(!Number.isFinite(level))throw new Error('Finite light intensity required');
      return [{path:target,property:'light_intensity',value:level}];
    }
    const vector=value.split(',').map(Number);
    if(vector.length!==3||vector.some(v=>!Number.isFinite(v)))
      throw new Error('Actor/prop offset requires three finite numbers, x,y,z');
    return [{path:target,property:'translation_offset',value:vector}];
  }
  const submit=()=>run(async()=>{
    if(!usableImpact)throw new Error('Refresh the exact native source impact before approval');
    if(!/^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/.test(newId))
      throw new Error('Enter a new stable source/decision ID (letters, digits, _, ., :, -)');
    if(aiReview&&(kind!==aiReview.action_kind||
        currentTake?.sha256!==aiReview.take_sha256||
        !directorTypedChange||directorReason.trim().length<12))
      throw new Error('Enter independent values and a director-written reason');
    const typed=typedOperation?typedDecision():null;
    if(typedOperation&&(!impact?.typed?.typed_preview_sha256||
        impact.typedFingerprint!==JSON.stringify(typed)))
      throw new Error('Sound/editorial values changed after native typed preview; inspect again');
    const preview_sha256=impact.data.preview_sha256;
    const common={project_id:projectId,preview_sha256};
    let response;
    if(kind==='take'){
      if(!currentScene||!currentTimeline)throw new Error('Select real scene and timeline');
      response=await native().wo6_create_take({
        ...common,new_take_id:newId,
        scene_id:currentScene.id,scene_revision:currentScene.revision,
        scene_sha256:currentScene.sha256,
        timeline_id:currentTimeline.id,timeline_revision:currentTimeline.revision,
        timeline_sha256:currentTimeline.sha256,
        sample_ticks:[0],
      });
    }else if(kind==='color'){
      if(!currentTake)throw new Error('Select an immutable original Take');
      response=await native().wo6_create_decision({
        ...common,decision_kind:'color',decision_id:newId,
        source_id:currentTake.id,source_revision:currentTake.revision,
        source_sha256:currentTake.sha256,payload:color,duration_tick:null,
      });
    }else if(typedOperation){
      response=await native().wo6_create_decision({
        ...typed,
        preview_sha256,
        typed_preview_sha256:impact.typed.typed_preview_sha256,
        ...(aiReview?{reviewed_proposal_id:aiReview.proposal_id}:{}),
      });
    }else if(kind==='camera_sequence'){
      if(!currentScene)throw new Error('Select current scene');
      const end=exactInteger(endTick,'Sequence end');
      if(end<2)throw new Error('Sequence interval must be positive');
      const cam=selectedPath||paths[0]?.[0];
      if(!cam)throw new Error('Original scene must contain one authored camera');
      response=await native().wo6_create_decision({
        ...common,decision_kind:'camera_sequence',decision_id:newId,
        source_id:currentScene.id,source_revision:currentScene.revision,
        source_sha256:currentScene.sha256,payload:[{
          shot_id:'camera_a',camera_path:cam,start_tick:'0',
          end_tick:String(end),pattern:'master',
        }],duration_tick:String(end+1),
      });
    }else{
      if(!currentTake||!scene)throw new Error('Select a scene-bound Take');
      response=await native().wo6_create_shot({
        ...common,action_kind:kind,shot_id:newId,
        take_id:currentTake.id,take_sha256:currentTake.sha256,
        scene_id:scene.id,scene_revision:scene.revision,
        scene_sha256:scene.sha256,
        start_tick:exactInteger(startTick,'Start'),
        end_tick:exactInteger(endTick,'End'),
        changes:shotOpinions(),
        purpose:kind==='lighting'?'lighting':'framing',
        continuity_policy:'intentional_cheat',
        reason:aiReview?directorReason.trim():
          'Director deliberately approved this isolated shot change',
        ...(aiReview?{reviewed_proposal_id:aiReview.proposal_id}:{}),
      });
    }
    setReceipt(response);
    setImpact(null);
    await refresh();
  });
  const discoverLocalModels=()=>run(async()=>{
    if(typeof native()?.wo6_local_models!=='function')
      throw new Error('Installed NVP host has no local model discovery');
    const result=await native().wo6_local_models(projectId);
    setLocalModelState(result.state);
    setLocalModels(result.models||[]);
    setLocalModelId(result.models?.[0]?.id||'');
  });
  const requestLocalSuggestion=()=>run(async()=>{
    if(!currentTake||!localModelId)
      throw new Error('Select a frozen original Take and connected local model');
    if(!aiDirection.trim())
      throw new Error('Enter the intended scene direction');
    if(!/^(0|[1-9][0-9]{0,14})$/.test(aiFilmTick))
      throw new Error('Choose canonical exact Film Time tick');
    const result=await native().wo6_suggest_from_local_model({
      project_id:projectId,
      take_id:currentTake.id,take_sha256:currentTake.sha256,
      film_tick:aiFilmTick,direction:aiDirection,model_id:localModelId,
    });
    if(result?.state!=='GENERATING'||!result.proposal_id)
      throw new Error('No native read-only model proposal was admitted');
    setAiProposalTicket(result.proposal_id);
    setAiProposal(null);
    setAiReview(null);
    setDirectorTypedChange(false);
  });
  const readLocalSuggestion=()=>run(async()=>{
    if(!aiProposalTicket)throw new Error('No model proposal has been requested');
    const result=await native().wo6_model_proposal_status(
      projectId,aiProposalTicket);
    setAiProposal(result);
  });
  const reviewAdviceForManualShot=()=>run(async()=>{
    const advice=aiProposal?.proposal;
    if(!aiProposalTicket||aiProposal?.state!=='READY_FOR_HUMAN_REVIEW'||!advice)
      throw new Error('Read a completed original-source suggestion first');
    if(!['camera','blocking','lighting'].includes(aiReviewKind))
      throw new Error('The director must select a specific shot operation');
    if(!currentTake||currentTake.id!==advice.take_id||
        currentTake.sha256!==advice.take_sha256)
      throw new Error('This advice does not belong to the selected original Take');
    const reviewed=await native().wo6_review_model_proposal({
      project_id:projectId,proposal_id:aiProposalTicket,
      take_id:advice.take_id,take_sha256:advice.take_sha256,
      model_text_sha256:advice.model_text_sha256,
      verified_source_context_sha256:advice.verified_source_context_sha256,
      action_kind:aiReviewKind,
    });
    if(reviewed?.status!=='HUMAN_SELECTED_AI_CONSULTATION_NO_GRANT'||
        reviewed.proposal_id!==aiProposalTicket||
        reviewed.action_kind!==aiReviewKind||
        reviewed.take_sha256!==advice.take_sha256||
        reviewed.native_worker_authorized!==false||
        reviewed.creative_approval_granted!==false)
      throw new Error('Unverified native AI consultation response');
    // The model NEVER writes the chosen numeric parameter or reason.
    // These empty fields and fresh impact preview must be set by the human.
    setAiReview(reviewed);
    setKind(aiReviewKind);
    setValue('');
    setNewId('');
    setSelectedPath('');
    setDirectorReason('');
    setDirectorTypedChange(false);
    setImpact(null);
    setReceipt(null);
  });
  const selectedTask=receipt?.queued_task_id||receipt?.task_id;
  const readStatus=()=>run(async()=>{
    if(!selectedTask)throw new Error('No owned task has been queued');
    const result=await native().wo6_task_status(projectId,selectedTask);
    setStatus(result);
  });
  const cancel=()=>run(async()=>{
    if(!selectedTask)throw new Error('No native task is selected');
    const result=await native().wo6_cancel_native_task(projectId,selectedTask);
    setStatus(result);
  });
  return <section className="card" aria-label="Director native source operations">
    <h2>Director-approved native source operations</h2>
    <p className="muted">Source impact first, then separate OS creative and native
    execution permission. All operations preserve the original Take. No film or DCP is
    approved by this screen.</p>
    <div aria-label="Local model director suggestion (read-only)">
      <h3>Local AI scene advice — director review only</h3>
      <p className="muted">Uses an existing local model and reopened immutable
      Take context. Model text cannot select or execute a native tool, fill
      an approval, save a Take, or approve a film. Review it manually.</p>
      <div className="actions">
        <button type="button" disabled={busy||!catalog} onClick={discoverLocalModels}>
          Find local models</button>
        <span role="status">Local model: {localModelState||'not checked'}</span>
      </div>
      <label>Available locally reported model<select value={localModelId}
        disabled={busy||!localModels.length}
        onChange={e=>setLocalModelId(e.target.value)}>
        {!localModels.length&&<option value="">No verified local selection</option>}
        {localModels.map(x=><option key={x.id} value={x.id}>
          {x.id}</option>)}
      </select></label>
      <label>Direction for the current frozen Take<textarea
        value={aiDirection} maxLength={1200} disabled={busy}
        onChange={e=>setAiDirection(e.target.value)}
        placeholder="Suggest a clearer camera or actor direction for this Take"/>
      </label>
      <label>Exact original Film Time tick<input value={aiFilmTick}
        disabled={busy} onChange={e=>setAiFilmTick(e.target.value)}/></label>
      <div className="actions">
        <button type="button" disabled={busy||!currentTake||!localModelId||!aiDirection.trim()}
          onClick={requestLocalSuggestion}>Ask local model for read-only advice</button>
        <button type="button" disabled={busy||!aiProposalTicket}
          onClick={readLocalSuggestion}>Read local model proposal status</button>
      </div>
      {aiProposalTicket&&<p>Read-only proposal ID: {aiProposalTicket}.
        No native task has been dispatched.</p>}
      {aiProposal&&<div role="status">
        <p>Local AI state: {aiProposal.state}.
          Creator and native execution approvals: not granted.</p>
        {aiProposal.proposal&&<div>
          <p>Bound original Take SHA: {aiProposal.proposal.take_sha256}</p>
          <p>Verified context SHA: {aiProposal.proposal.verified_source_context_sha256}</p>
          <pre style={{maxHeight:280,overflow:'auto',whiteSpace:'pre-wrap'}}>
            {aiProposal.proposal.suggestion_text}
          </pre>
          <p>Untrusted advice only. A human must choose the operation and
          type every numeric change. A fresh source-impact review and
          two independent native OS confirmations remain mandatory.</p>
          <label>Director-selected operation to consider<select
            value={aiReviewKind} disabled={busy}
            onChange={e=>setAiReviewKind(e.target.value)}>
            <option value="">Select an operation manually</option>
            <option value="camera">Camera adjustment</option>
            <option value="blocking">Actor or prop blocking</option>
            <option value="lighting">Lighting adjustment</option>
          </select></label>
          <button type="button" disabled={busy||!aiReviewKind||
            !currentTake||currentTake.sha256!==aiProposal.proposal.take_sha256}
            onClick={reviewAdviceForManualShot}>
            Review advice and plan my own shot</button>
        </div>}
      </div>}
    </div>
    {!catalog&&<p role="status">Checking the installed native host and FilmIndex…</p>}
    <label>Operation<select value={kind} disabled={busy}
      onChange={e=>{setKind(e.target.value);setValue(e.target.value==='blocking'?'0,0,0':'50');setSelectedPath('');setImpact(null);setAiReview(null);setDirectorTypedChange(false)}}>
      {ACTIONS.map(([id,label])=><option key={id} value={id}>{label}</option>)}
    </select></label>
    <label>Original scene<select value={sceneId} disabled={busy} onChange={e=>{setSceneId(e.target.value);setImpact(null);setAiReview(null);setDirectorTypedChange(false)}}>
      {catalog?.scenes?.map(x=><option key={x.id} value={x.id}>{x.id} · rev {x.revision}</option>)}
    </select></label>
    {(kind!=='take'&&kind!=='camera_sequence')&&<label>Frozen Take<select
      value={takeId} disabled={busy} onChange={e=>{setTakeId(e.target.value);setImpact(null)}}>
      {catalog?.takes?.map(x=><option key={x.id} value={x.id}>{x.id} · {x.sha256.slice(0,14)}</option>)}
    </select></label>}
    {kind==='take'&&<label>Original authored timeline<select value={timelineId}
      disabled={busy} onChange={e=>setTimelineId(e.target.value)}>
      {catalog?.timelines?.map(x=><option key={x.id} value={x.id}>{x.id} · rev {x.revision}</option>)}
    </select></label>}
    {paths.length>0&&kind!=='take'&&kind!=='color'&&<label>Authored OpenUSD object<select
      value={selectedPath||paths[0]?.[0]||''} disabled={busy} onChange={e=>setSelectedPath(e.target.value)}>
      {paths.map(([path,role])=><option key={path} value={path}>{path} · {role}</option>)}
    </select></label>}
    {kind==='color'&&<div className="columns">{Object.entries(color).map(([key,n])=><label key={key}>
      {key.replaceAll('_',' ')}<input type="number" step="any" disabled={busy} value={n}
        onChange={e=>setColor(old=>({...old,[key]:Number(e.target.value)}))}/></label>)}</div>}
    {(kind==='camera'||kind==='lighting'||kind==='blocking')&&<label>
      {kind==='camera'?'Focal length (mm)':kind==='lighting'?'Light intensity':'XYZ offset (x,y,z)'}
      <input disabled={busy} value={value} onChange={e=>{setValue(e.target.value);if(aiReview)setDirectorTypedChange(true)}}/>
    </label>}
    {kind!=='color'&&kind!=='take'&&<label>End Film Time tick<input
      value={endTick} disabled={busy} onChange={e=>setEndTick(e.target.value)}/></label>}
    {kind!=='color'&&kind!=='take'&&kind!=='camera_sequence'&&<label>Start tick<input
      value={startTick} disabled={busy} onChange={e=>setStartTick(e.target.value)}/></label>}
    {aiReview&&<div aria-label="Human-reviewed AI consultation for manual source change">
      <h3>Director's independent shot decision</h3>
      <p>AI consultation {aiReview.proposal_id} was reviewed but granted
      no native permission. The model suggestion is linked by SHA;
      it cannot choose your numeric values or your new shot identity.</p>
      <p>Model text SHA: {aiReview.model_text_sha256}</p>
      <label>Director-written creative reason<textarea value={directorReason}
        maxLength={512} disabled={busy}
        placeholder="Explain my independently selected camera, actor or lighting change"
        onChange={e=>setDirectorReason(e.target.value)}/></label>
      <p>After entering your own shot value, new object ID and reason,
      inspect a fresh source impact before requesting both OS confirmations.</p>
    </div>}
    <label>New immutable object ID<input value={newId} disabled={busy}
      onChange={e=>setNewId(e.target.value)} placeholder="director_new_shot_001"/></label>
    <div className="actions">
      <button type="button" className="secondary" disabled={busy||!selectedOriginal} onClick={preview}>
        Inspect source impact</button>
      <button type="button" className="primary" disabled={busy||!usableImpact||!newId||
        (aiReview&&(!directorTypedChange||directorReason.trim().length<12))}
        onClick={submit}>
        Request two OS approvals and execute</button>
      <button type="button" className="secondary" disabled={busy} onClick={()=>run(refresh)}>Refresh FilmIndex</button>
    </div>
    {impact&&<div><h3>Read-only source-impact receipt</h3>
      <p>{impact.data.status}. Source SHA: {impact.data.preview_sha256}.
        This review does not grant tool permission.</p>
      <pre style={{maxHeight:280,overflow:'auto'}}>{JSON.stringify(
        impact.data,null,2).slice(0,7000)}</pre>
      </div>}
    {receipt&&<div role="status"><h3>Native action result</h3>
      <pre style={{maxHeight:240,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</pre>
      <div className="actions">
        <button disabled={busy} onClick={readStatus}>Read durable job status</button>
        <button disabled={busy} onClick={cancel}>Request native cancellation</button>
      </div></div>}
    {status&&<pre style={{maxHeight:250,overflow:'auto'}}>{JSON.stringify(status,null,2)}</pre>}
    {busy&&<p role="status">Native authorization/worker operation in progress. No finished-film claim is implied.</p>}
    {problem&&<p role="alert">{problem}</p>}
  </section>;
}
