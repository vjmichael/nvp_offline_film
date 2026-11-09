import React,{useCallback,useEffect,useMemo,useState} from 'react';
import ModularWorldSourcePreview from './ModularWorldSourcePreview.jsx';

const PROPOSAL='nvp.usd_film02m_f.durable_director_proposal.v1';
const PREVIEW='nvp.usd_film02m_f.original_source_lowfi_preview.v1';
const SAVED='nvp.usd_film02m_f.original_director_approved_commit.v1';
const CATALOG='nvp.usd_film02m_f.native_source_catalog.v1';
const METHODS=[
  'film02mf_catalog','film02mf_propose','film02mf_reopen',
  'film02mf_preview','film02mf_edit','film02mf_undo',
  'film02mf_discard','film02mf_commit'];

export default function ModularWorldDirector({projectId,nativeBridge}){
  const ready=Boolean(nativeBridge)&&METHODS.every(
    m=>typeof nativeBridge[m]==='function');
  const [catalog,setCatalog]=useState(null);
  const [buildingIds,setBuildingIds]=useState([]);
  const [districtId,setDistrictId]=useState('OriginalFilmDistrict');
  const [baseRevision,setBaseRevision]=useState(0);
  const [seed,setSeed]=useState(7);
  const [cols,setCols]=useState(3),[rows,setRows]=useState(2);
  const [pitch,setPitch]=useState(30);
  const [triangleBudget,setTriangleBudget]=useState(100000);
  const [instanceBudget,setInstanceBudget]=useState(32);
  const [origin,setOrigin]=useState([0,0,0]);
  const [submission,setSubmission]=useState('director');
  const [modelId,setModelId]=useState('');
  const [modelDirection,setModelDirection]=useState('');
  const [observedModel,setObservedModel]=useState(null);
  const [modelAttempt,setModelAttempt]=useState(null);
  const [localModels,setLocalModels]=useState([]);
  const [localModelStatus,setLocalModelStatus]=useState('not checked');
  const [worldTakeId,setWorldTakeId]=useState('');
  const [filmTick,setFilmTick]=useState(0);
  const [shotBindingId,setShotBindingId]=useState('OriginalDistrictFilmShot');
  const [shotPreview,setShotPreview]=useState(null);
  const [shotPublished,setShotPublished]=useState(null);
  const [draft,setDraft]=useState(null),[preview,setPreview]=useState(null);
  const [selectedGenerated,setSelectedGenerated]=useState('');
  const [manualName,setManualName]=useState('DirectorShopfront');
  const [manualBuilding,setManualBuilding]=useState('');
  const [manualXYZ,setManualXYZ]=useState([0,60,0]);
  const [manualYaw,setManualYaw]=useState(0);
  const [selectedManual,setSelectedManual]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [notice,setNotice]=useState(''),[committed,setCommitted]=useState(null);
  const source=catalog?.source_buildings||[];
  const approved=catalog?.approved_districts||[];
  const worldTakes=catalog?.original_world_takes||[];
  const chosenTake=worldTakes.find(x=>x.take_id===worldTakeId);
  const chosenDistrict=approved.find(x=>x.district_id===districtId);
  useEffect(()=>{
    if(chosenTake?.checkpoint_ticks?.length)
      setFilmTick(current=>chosenTake.checkpoint_ticks.includes(current)?
        current:chosenTake.checkpoint_ticks[0]);
  },[worldTakeId,catalog]);
  const active=draft?.format===PROPOSAL&&draft.state==='DRAFT';
  const validPreview=active&&preview?.format===PREVIEW&&
    preview?.proposal?.draft_id===draft.draft_id&&
    preview?.proposal?.version===draft.version&&
    preview?.source_plan_sha256===draft.original_plan_sha256&&
    preview?.usd_layer_root_sha256===draft.original_usd_root_sha256&&
    preview?.native_usd_source_reopened===true&&
    preview?.native_blender_workers_started===0;
  const originalGenerated=useMemo(
    ()=>preview?.instances?.filter(x=>!x.director_placed)||[],
    [preview]);
  const manual=useMemo(
    ()=>preview?.instances?.filter(x=>x.director_placed)||[],
    [preview]);
  const proposalSourceBuildingIds=useMemo(
    ()=>[...new Set((preview?.instances||[]).map(x=>x.building_id))],
    [preview]);
  const refresh=useCallback(async()=>{
    if(!ready)return null;
    const result=await nativeBridge.film02mf_catalog(projectId);
    if(result?.format!==CATALOG||result.project_id!==projectId||
       result.native_blender_workers_started!==0||
       !Array.isArray(result.source_buildings)||
       !Array.isArray(result.drafts))
      throw Error('Trusted original OpenUSD building catalog failed');
    setCatalog(result);
    // Reattach to an in-process generation after switching director tabs.
    // A different host session has already marked old attempts interrupted.
    if(typeof nativeBridge.film02mg_candidate_status==='function'){
      setModelAttempt(current=>current||
        result.model_attempts?.find(x=>x.state==='GENERATING')?.attempt_id||null);
    }
    setWorldTakeId(current=>{
      if(result.original_world_takes?.some(x=>x.take_id===current))
        return current;
      return result.original_world_takes?.[0]?.take_id||'';
    });
    if(typeof nativeBridge.wo6_local_models==='function'){
      const found=await nativeBridge.wo6_local_models(projectId);
      if(!Array.isArray(found?.models)||typeof found.state!=='string')
        throw Error('Native model discovery did not provide a typed receipt');
      setLocalModels(found.models);
      setLocalModelStatus(found.state);
      setModelId(current=>found.models.some(x=>x.id===current)?
        current:found.models[0]?.id||'');
    }
    setBuildingIds(ids=>ids.length?ids.filter(id=>result.source_buildings.some(
      x=>x.building_id===id)):(result.source_buildings[0]?
      [result.source_buildings[0].building_id]:[]));
    setManualBuilding(id=>id||result.source_buildings[0]?.building_id||'');
    return result;
  },[nativeBridge,ready,projectId]);
  useEffect(()=>{
    if(!ready){setCatalog(null);return;}
    let active=true;
    refresh().catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[ready,refresh]);

  const transact=async callback=>{
    if(!ready||busy)return;
    setBusy(true);setError('');setNotice('');
    try{await callback();}
    catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  };
  const requireDraft=response=>{
    if(response?.format!==PROPOSAL||response.project_id!==projectId||
       typeof response.draft_id!=='string'||
       typeof response.version!=='number'||
       response.original_actor_takes_modified!==false||
       response.native_blender_workers_started!==0)
      throw Error('Untrusted source proposal receipt');
    return response;
  };
  const loadPreview=async receipt=>{
    const data=await nativeBridge.film02mf_preview({
      project_id:projectId,draft_id:receipt.draft_id});
    if(data?.format!==PREVIEW||data.proposal?.draft_id!==receipt.draft_id||
       data.proposal?.version!==receipt.version||
       data.source_plan_sha256!==receipt.original_plan_sha256||
       data.usd_layer_root_sha256!==receipt.original_usd_root_sha256||
       data.native_blender_workers_started!==0||
       data.original_world_takes_modified!==false)
      throw Error('Original director draft preview is not source-pinned');
    setDraft(receipt);setPreview(data);setCommitted(null);
    setManualBuilding(current=>data.instances.some(
      x=>x.building_id===current)?current:data.instances[0]?.building_id||'');
    return data;
  };
  const propose=()=>transact(async()=>{
    if(!source.length||!buildingIds.length)
      throw Error('Approve original 02M source building modules before proposing a district');
    const selected=buildingIds.map(id=>source.find(
      s=>s.building_id===id)).filter(Boolean);
    if(!selected.length||selected.length>8)
      throw Error('Select between one and eight approved original 3D buildings');
    const params={
      seed:Number(seed),
      source_buildings:selected.map(b=>({
        building_id:b.building_id,revision:b.revision})),
      grid_cols:Number(cols),grid_rows:Number(rows),
      lot_spacing_m:Number(pitch),
      world_origin_m:origin.map(Number),
      source_triangle_budget:Number(triangleBudget),
      source_instance_budget:Number(instanceBudget)};
    const proposed=requireDraft(await nativeBridge.film02mf_propose({
      project_id:projectId,district_id:districtId,
      expected_revision:Number(baseRevision),
      params,proposed_by:submission}));
    await loadPreview(proposed);
    await refresh();
    setNotice('Original USD proposal saved as a DRAFT. No published world or Blender job changed.');
  });
  const modelPropose=()=>transact(async()=>{
    if(!modelId.trim()||!modelDirection.trim())
      throw Error('Choose the locally configured model and provide director intent');
    const request={
      project_id:projectId,district_id:districtId,
      expected_revision:Number(baseRevision),
      model_id:modelId.trim(),direction:modelDirection.trim()};
    // Native background task returns immediately. Source admission and
    // cancellation are owned by the same host as the durable draft ledger.
    if(typeof nativeBridge.film02mg_start_candidate==='function'&&
       typeof nativeBridge.film02mg_candidate_status==='function'){
      const begun=await nativeBridge.film02mg_start_candidate(request);
      if(begun?.format!=='nvp.usd_film02m_g.durable_model_attempt_status.v1'||
         begun.state!=='GENERATING'||begun.project_id!==projectId||
         !/^[0-9a-f]{24}$/.test(begun.attempt_id)||
         begun.director_approval_granted!==false||
         begun.native_worker_authorized!==false)
        throw Error('Trusted background world model did not return a host-owned attempt');
      setModelAttempt(begun.attempt_id);
      setNotice('Local model source proposal is generating. The director editor remains interactive.');
      return;
    }
    if(typeof nativeBridge.film02mg_generate_candidate!=='function')
      throw Error('Installed NVP local model world planning is unavailable');
    // Older installed versions only: retain original sync bridge contract.
    const response=await nativeBridge.film02mg_generate_candidate(request);
    if(response?.format!=='nvp.usd_film02m_g.model_saved_original_draft.v1'||
       response.director_approval_granted!==false||
       response.actor_takes_modified!==false||
       response.model_evidence?.status!=='GENERATED_UNAPPROVED'||
       response.proposal?.observed_model_evidence?.model_text_sha256!==
         response.model_evidence?.model_text_sha256)
      throw Error('Native model proposal lacks matching durable model evidence');
    await loadPreview(requireDraft(response.proposal));
    await refresh();
    setObservedModel(response.model_evidence);
    setNotice('Host-observed local model generated a bounded source proposal. It is a durable unapproved draft.');
  });
  useEffect(()=>{
    if(!modelAttempt||!ready||
       typeof nativeBridge.film02mg_candidate_status!=='function')return;
    let stopped=false,timer=null;
    const poll=async()=>{
      try{
        const state=await nativeBridge.film02mg_candidate_status({
          project_id:projectId,attempt_id:modelAttempt});
        if(stopped)return;
        if(state?.format!=='nvp.usd_film02m_g.durable_model_attempt_status.v1'||
           state.project_id!==projectId||
           state.attempt_id!==modelAttempt||
           state.director_approval_granted!==false||
           state.actor_takes_modified!==false)
          throw Error('Local model generation status is not source-bound');
        if(state.state==='GENERATING'){
          timer=setTimeout(poll,800);
          return;
        }
        if(state.state==='DRAFT_SAVED'){
          if(state.model_evidence?.status!=='GENERATED_UNAPPROVED'||
             state.proposal?.observed_model_evidence?.model_text_sha256!==
               state.model_evidence?.model_text_sha256)
            throw Error('Durable model draft has no matching completion receipt');
          await loadPreview(requireDraft(state.proposal));
          if(stopped)return;
          await refresh();
          if(stopped)return;
          setObservedModel(state.model_evidence);
          setNotice('Host-owned local model draft saved and reopened. It remains unapproved.');
        }else{
          await refresh();
          if(stopped)return;
          setNotice('Local model attempt '+state.state+
            '. No original world revision was published or authorized.');
        }
        if(!stopped)setModelAttempt(null);
      }catch(e){
        if(!stopped){setModelAttempt(null);setError(
          e?.message||'Source-locked model attempt could not be verified');}
      }
    };
    timer=setTimeout(poll,250);
    return()=>{stopped=true;clearTimeout(timer);};
  },[modelAttempt,ready,nativeBridge,projectId]);
  const cancelModel=()=>transact(async()=>{
    if(!modelAttempt||typeof nativeBridge.film02mg_cancel_candidate!=='function')
      throw Error('No cancellable native world model attempt');
    const state=await nativeBridge.film02mg_cancel_candidate({
      project_id:projectId,attempt_id:modelAttempt});
    if(state?.format!=='nvp.usd_film02m_g.durable_model_attempt_status.v1'||
       state.project_id!==projectId||
       state.director_approval_granted!==false)
      throw Error('Native cancellation did not return a durable attempt state');
    setModelAttempt(null);
    await refresh();
    setNotice(state.state==='CANCELLED'?
      'Model generation cancelled. Late completion cannot create a source draft or approval.':
      'Model attempt finished before cancellation; inspect the existing unapproved draft.');
  });
  const previewOriginalShot=()=>transact(async()=>{
    if(!chosenDistrict||!chosenTake||
       typeof nativeBridge.film02mh_preview_shot!=='function')
      throw Error('Select an approved world and an original frozen 01E film Take');
    const result=await nativeBridge.film02mh_preview_shot({
      project_id:projectId,district_id:chosenDistrict.district_id,
      district_revision:chosenDistrict.revision,
      world_take_id:chosenTake.take_id,film_tick:Number(filmTick)});
    if(result?.format!=='nvp.usd_film02m_h.native_source_district_shot_preview.v1'||
       result.district_document_sha256!==chosenDistrict.document_sha256||
       result.world_take_sha256!==chosenTake.take_sha256||
       result.native_approved_district_layer_composed!==true||
       result.native_original_actor_pose_verified!==true||
       result.native_original_camera_verified!==true||
       result.original_actor_takes_unchanged!==true||
       typeof result.binding_preview_sha256!=='string')
      throw Error('Native USD actor/camera source binding failed independent verification');
    setShotPreview(result);setShotPublished(null);
    setNotice('The original district, actor Takes and camera now share one source-verified disposable USD shot view.');
  });
  const publishOriginalShot=()=>transact(async()=>{
    if(!shotPreview||!chosenDistrict||!chosenTake||
       shotPreview.district_id!==chosenDistrict.district_id||
       shotPreview.district_revision!==chosenDistrict.revision||
       shotPreview.world_take_id!==chosenTake.take_id||
       shotPreview.film_tick!==Number(filmTick))
      throw Error('Original district/actor/camera preview has changed');
    const published=await nativeBridge.film02mh_commit_shot_binding({
      project_id:projectId,binding_id:shotBindingId,
      district_id:shotPreview.district_id,
      district_revision:shotPreview.district_revision,
      world_take_id:shotPreview.world_take_id,
      film_tick:shotPreview.film_tick,
      source_preview_sha256:shotPreview.binding_preview_sha256});
    if(published?.revision!==1||typeof published.document_sha256!=='string')
      throw Error('No original immutable 01D/01E scene binding receipt');
    const reopened=await nativeBridge.film02mh_reopen_shot_binding({
      project_id:projectId,binding_id:shotBindingId});
    if(reopened?.native_source_reopened!==true||
       reopened.binding_document_sha256!==published.document_sha256||
       reopened.source_actor_takes_unchanged!==true)
      throw Error('New shot source binding failed independent reopen');
    setShotPublished(reopened);
    setNotice('OS-approved immutable actor/camera/district binding saved; actor Takes and shot source remain unchanged.');
  });
  const reopen=id=>transact(async()=>{
    const receipt=await nativeBridge.film02mf_reopen({
      project_id:projectId,draft_id:id});
    if(receipt?.state==='DRAFT'){
      await loadPreview(requireDraft(receipt));
      setNotice('Original source draft reopened from durable installed-host storage.');
    }else{
      setDraft(receipt);setPreview(null);setNotice(
        'Original proposal is '+receipt.state+'; no old native approval can be replayed.');
    }
  });
  const apply=action=>transact(async()=>{
    if(!active)throw Error('No active original source proposal');
    const receipt=requireDraft(await nativeBridge.film02mf_edit({
      project_id:projectId,draft_id:draft.draft_id,
      version:draft.version,action}));
    setPreview(null);
    await loadPreview(receipt);
    setNotice('Draft-only director layer change saved. Original source unmodified.');
  });
  const undo=()=>transact(async()=>{
    if(!active)throw Error('No active draft');
    const receipt=requireDraft(await nativeBridge.film02mf_undo({
      project_id:projectId,draft_id:draft.draft_id,version:draft.version}));
    setPreview(null);await loadPreview(receipt);
    setNotice('Previous original director layer opinions restored without changing approved source.');
  });
  const discard=()=>transact(async()=>{
    if(!active)throw Error('No discardable source proposal');
    const receipt=await nativeBridge.film02mf_discard({
      project_id:projectId,draft_id:draft.draft_id,version:draft.version});
    if(receipt?.format!==PROPOSAL||receipt.state!=='DISCARDED')
      throw Error('Native discard did not finish');
    setDraft(receipt);setPreview(null);
    await refresh();
    setNotice('Unapproved source proposal discarded; approved FilmIndex worlds preserved.');
  });
  const commit=()=>transact(async()=>{
    if(!validPreview)
      throw Error('Preview the exact current source draft before native director approval');
    const receipt=await nativeBridge.film02mf_commit({
      project_id:projectId,draft_id:draft.draft_id,
      version:draft.version,
      source_plan_sha256:preview.source_plan_sha256,
      usd_layer_root_sha256:preview.usd_layer_root_sha256});
    if(receipt?.format!==SAVED||receipt.state!=='COMMITTED'||
       receipt.original_source_plan_sha256!==preview.source_plan_sha256||
       receipt.original_usd_root_sha256!==preview.usd_layer_root_sha256||
       receipt.original_film_take_modified!==false||
       !Number.isInteger(receipt.published_revision)||
       typeof receipt.published_sha256!=='string')
      throw Error('Installed original-world commit has no independent exact SHA receipt');
    setCommitted(receipt);setDraft(receipt);setPreview(null);
    await refresh();
    setNotice('Native-approved original FilmIndex scene revision saved and independently reopened.');
  });
  const selectApproved=value=>{
    const item=approved.find(x=>x.district_id===value);
    if(!item){
      setDistrictId('OriginalFilmDistrict');setBaseRevision(0);
      return;
    }
    const p=item.base_parameters;
    setDistrictId(item.district_id);setBaseRevision(item.revision);
    setSeed(p.seed);setCols(p.grid_cols);setRows(p.grid_rows);
    setPitch(p.lot_spacing_m);setTriangleBudget(p.source_triangle_budget);
    setInstanceBudget(p.source_instance_budget);
    setOrigin(p.world_origin_m);
    setBuildingIds(p.source_buildings.map(x=>x.building_id));
    setNotice('Existing approved source settings loaded; new proposal will be a separate revision.');
  };
  return <section aria-label="Original OpenUSD modular world director"
    style={{borderTop:'1px solid #55616e',paddingTop:18,marginTop:20}}>
    <h3>23 · Build the world from data</h3>
    <p className="fineprint">USD-FILM-02M-F — source-first modular district editor.
      Generated building placements and stronger manual opinions are separate
      USD layers. An AI suggestion is only a draft; only the installed NVP
      host can request explicit operating-system director approval.</p>
    {!ready&&<p role="status">Original world authoring is read-only here.
      Install NVP with the trusted native WebView bridge to propose, undo,
      discard or approve OpenUSD scene revisions. No browser HTTP writer.</p>}
    {ready&&<>
      <div className="actions">
        <button disabled={busy} onClick={()=>transact(refresh)}>
          Refresh original building catalog</button>
        <label>Approved source district
          <select aria-label="Approved original film district" disabled={busy}
            value={approved.some(x=>x.district_id===districtId)?districtId:''}
            onChange={e=>selectApproved(e.target.value)}>
            <option value="">New original scene</option>
            {approved.map(x=><option key={x.district_id} value={x.district_id}>
              {x.district_id} · rev {x.revision}</option>)}
          </select>
        </label>
      </div>
      <div className="actions">
        <label>Proposed district ID<input aria-label="Original district ID"
          value={districtId} disabled={busy}
          onChange={e=>setDistrictId(e.target.value)}/></label>
        <span>Original base revision: {baseRevision}</span>
        <label>Proposal origin
          <select aria-label="Original proposal origin"
            value={submission} disabled={busy}
            onChange={e=>setSubmission(e.target.value)}>
            <option value="director">Director drafted</option>
            <option value="ai">AI-suggested plan (unapproved data)</option>
          </select>
        </label>
      </div>
      {(typeof nativeBridge.film02mg_generate_candidate==='function'||
         typeof nativeBridge.film02mg_start_candidate==='function')&&
        <fieldset disabled={busy} style={{
          padding:10,border:'1px solid #50606f',borderRadius:7}}>
          <legend>Loaded local AI · original world candidate</legend>
          <p className="fineprint">This calls the existing host-selected WO6 local
            model and independently reopens original source geometry.
            Its provider receipt is evidence of a completed generation,
            not proof of model weights or creative approval.</p>
          <label>Configured local model
            <select aria-label="Original world local model ID"
              value={modelId} onChange={e=>setModelId(e.target.value)}>
              <option value="">Select a discovered local model</option>
              {localModels.map(model=><option key={model.id} value={model.id}>
                {model.id}</option>)}
            </select>
          </label>
          <small>Local model status: {localModelStatus}. Refresh the catalog
            to repeat local model discovery. No remote model endpoints are accepted.</small>
          <label>Director instruction<textarea
            aria-label="Original world model direction" maxLength={1200}
            value={modelDirection}
            onChange={e=>setModelDirection(e.target.value)}/></label>
          <button disabled={!source.length||!modelId.trim()||
              !modelDirection.trim()||localModelStatus!=='available'||
              Boolean(modelAttempt)}
            onClick={modelPropose}>Generate and save unapproved AI world draft</button>
          {modelAttempt&&<>
            <p role="status">Native model generation in progress; the original
              world and actor Takes remain unchanged. Attempt: {modelAttempt}</p>
            {typeof nativeBridge.film02mg_cancel_candidate==='function'&&
              <button onClick={cancelModel}>
                Cancel local model generation</button>}
          </>}
        </fieldset>}
      <fieldset disabled={busy||active} style={{
        padding:10,border:'1px solid #50606f',borderRadius:7}}>
        <legend>Approved original building source prototypes</legend>
        <div className="actions">
          {source.slice(0,24).map(x=><label key={x.building_id}
            style={{display:'inline-flex',alignItems:'center',gap:5}}>
            <input type="checkbox" aria-label={'Use building '+x.building_id}
              checked={buildingIds.includes(x.building_id)}
              onChange={e=>setBuildingIds(s=>e.target.checked?
                [...s,x.building_id].slice(0,8):s.filter(id=>id!==x.building_id))}/>
            {x.building_id} · {x.modules} real meshes
          </label>)}
        </div>
        <div className="actions">
          <label>Original generator seed<input type="number"
            aria-label="Original district seed" value={seed}
            onChange={e=>setSeed(Number(e.target.value))}/></label>
          <label>Lot columns<input type="number" min="1" max="16"
            aria-label="Original district columns" value={cols}
            onChange={e=>setCols(Number(e.target.value))}/></label>
          <label>Lot rows<input type="number" min="1" max="16"
            aria-label="Original district rows" value={rows}
            onChange={e=>setRows(Number(e.target.value))}/></label>
          <label>Lot pitch (metres)<input type="number" min="4" step=".5"
            aria-label="Original district lot pitch" value={pitch}
            onChange={e=>setPitch(Number(e.target.value))}/></label>
        </div>
        <div className="actions">
          <label>Triangle budget<input type="number" min="100"
            aria-label="Source triangle budget" value={triangleBudget}
            onChange={e=>setTriangleBudget(Number(e.target.value))}/></label>
          <label>Instance budget<input type="number" min="1" max="256"
            aria-label="Source instance budget" value={instanceBudget}
            onChange={e=>setInstanceBudget(Number(e.target.value))}/></label>
          {['X','Y','Z'].map((axis,i)=><label key={axis}>
            World origin {axis} (m)<input type="number"
              aria-label={'Original world origin '+axis}
              value={origin[i]}
              onChange={e=>setOrigin(old=>old.map(
                (x,j)=>j===i?Number(e.target.value):x))}/>
          </label>)}
        </div>
        <button onClick={propose} disabled={!source.length||!buildingIds.length}>
          Save source-verified draft proposal (no OS approval)</button>
      </fieldset>
      {catalog?.model_attempts?.length>0&&<div>
        <h4>Native model attempt recovery</h4>
        <div role="status">
          {catalog.model_attempts.slice(0,8).map(x=>
            <p key={x.attempt_id}>{x.district_id} · {x.model_id} ·
              {x.state}. {x.failure_category||''}
              {x.draft_id&&' · draft '+x.draft_id}</p>)}
        </div>
      </div>}
      {catalog?.drafts?.length>0&&<div>
        <h4>Durable original proposal history</h4>
        <div className="actions">
          {catalog.drafts.slice(0,12).map(x=><button
            key={x.draft_id} disabled={busy}
            onClick={()=>reopen(x.draft_id)}>
            {x.district_id} · draft v{x.version} · {x.state}
          </button>)}
        </div>
      </div>}
      {typeof nativeBridge.film02mh_preview_shot==='function'&&
       <section aria-label="Original film actor camera world integration">
        <h4>24 · Place approved world in an original actor-and-camera shot</h4>
        <p className="fineprint">This reads an existing immutable 01E actor
          world Take and its 01D authored camera. Preview composes the actual
          approved district USD as a disposable stronger session reference;
          it never changes frozen performances, camera, dialogue or PCM.</p>
        <label>Approved original building district
          <select aria-label="Shot approved district"
            value={chosenDistrict?.district_id||''}
            onChange={e=>{selectApproved(e.target.value);setShotPreview(null);}}>
            <option value="">Select approved district</option>
            {approved.map(x=><option key={x.district_id} value={x.district_id}>
              {x.district_id} · rev {x.revision}</option>)}
          </select>
        </label>
        <label>Frozen original actor world Take
          <select aria-label="Original 01E world Take"
            value={worldTakeId}
            onChange={e=>{setWorldTakeId(e.target.value);
              setFilmTick((worldTakes.find(x=>x.take_id===e.target.value)
                ?.checkpoint_ticks||[0])[0]);setShotPreview(null);}}>
            <option value="">Select 01E Take</option>
            {worldTakes.map(x=><option key={x.take_id} value={x.take_id}>
              {x.take_id} · {x.original_actor_count} original actors</option>)}
          </select>
        </label>
        <label>Original authored film checkpoint
          <select aria-label="Original film tick"
            value={filmTick}
            onChange={e=>{setFilmTick(Number(e.target.value));setShotPreview(null);}}>
            {(chosenTake?.checkpoint_ticks||[0]).map(n=>
              <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button disabled={busy||!chosenDistrict||!chosenTake}
          onClick={previewOriginalShot}>Preview native source actor/camera world</button>
        {shotPreview&&<div role="status">
          <p>Actual original USD instances: {shotPreview.native_original_instance_count}.
            Original actors: {shotPreview.original_actor_poses.length}.
            Camera: {shotPreview.original_camera_path}.
            Film tick: {shotPreview.film_tick}.
            No actor Takes or source camera changed.</p>
          <p>Approved district SHA: <code>
            {shotPreview.district_document_sha256}</code></p>
          <p>Original frozen 01E world Take SHA: <code>
            {shotPreview.world_take_sha256}</code></p>
          <label>New immutable shot-world binding ID
            <input aria-label="Original actor camera shot binding ID"
              value={shotBindingId}
              onChange={e=>setShotBindingId(e.target.value)}/></label>
          <button disabled={busy||!shotBindingId}
            onClick={publishOriginalShot}>
            OS approve exact actor-camera-world binding</button>
        </div>}
        {shotPublished&&<p role="status">Independent 3D source binding
          reopened: {shotPublished.binding_id}.
          Source SHA: {shotPublished.binding_document_sha256}.
          Original performances unchanged; movie frames not rendered.</p>}
      </section>}
      {draft&&<div role="region" aria-label="Original world draft controls">
        <h4>Source proposal · {draft.district_id} · v{draft.version}</h4>
        <p role="status">Native draft: {draft.state}.
          Original plan SHA: <code>{draft.original_plan_sha256}</code>.
          {draft.undo_steps} reversible draft changes.
          Actor performances and Takes unchanged.
          {draft.observed_model_evidence&&
            <span> Host-observed model: {draft.observed_model_evidence.model_id}.
              Model text SHA: {draft.observed_model_evidence.model_text_sha256}.
              Model weights are not independently attested.</span>}</p>
        <div className="actions">
          <button disabled={busy||!active} onClick={()=>transact(
            ()=>loadPreview(draft))}>Verify 3D source preview and exact layer diff</button>
          <button disabled={busy||!active||draft.undo_steps===0}
            onClick={undo}>Undo last draft change</button>
          <button disabled={busy||!active} onClick={discard}>
            Discard unapproved draft</button>
        </div>
        {validPreview&&<>
          <ModularWorldSourcePreview preview={preview}/>
          <h4>Director differences from approved source</h4>
          <p role="status">Generated original USD instances: {preview.diff.generated_slots};
            approx. source triangles: {preview.source_triangles_estimated}.
            Approved base revision: {preview.diff.base_revision}.
            Generated source changed: {preview.diff.generated_source_changed?'yes':'no'}.
            Manual additions: {preview.diff.added_director_opinions.length}.
            Removed opinions: {preview.diff.removed_director_opinions.length}.</p>
          <div className="actions">
            <label>Generated instance
              <select aria-label="Generated original building instance"
                value={selectedGenerated}
                onChange={e=>setSelectedGenerated(e.target.value)}>
                <option value="">Choose ID</option>
                {originalGenerated.map(x=><option key={x.instance_id}
                  value={String(x.instance_id)}>
                  #{x.instance_id} {x.building_id} {x.hidden?'(hidden)':''}
                </option>)}
              </select>
            </label>
            <button disabled={busy||!selectedGenerated}
              onClick={()=>apply({op:'hide_generated',
                instance_id:Number(selectedGenerated)})}>
              Hide generated original instance</button>
            <button disabled={busy||!selectedGenerated}
              onClick={()=>apply({op:'unhide_generated',
                instance_id:Number(selectedGenerated)})}>
              Restore generated original instance</button>
          </div>
          <h4>Hand-place an approved reusable 3D building</h4>
          <div className="actions">
            <label>Placement ID<input aria-label="Manual original placement ID"
              value={manualName} onChange={e=>setManualName(e.target.value)}/></label>
            <label>Source building
              <select aria-label="Manual original source building"
                value={manualBuilding} onChange={e=>setManualBuilding(e.target.value)}>
                <option value="">Choose original</option>
                {proposalSourceBuildingIds.map(id=>
                  <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
            {['X','Y','Z'].map((axis,i)=><label key={axis}>
              Local {axis} m<input type="number" aria-label={'Manual local '+axis}
                value={manualXYZ[i]} onChange={e=>setManualXYZ(old=>old.map(
                  (x,j)=>j===i?Number(e.target.value):x))}/></label>)}
            <label>Yaw
              <select aria-label="Manual building yaw" value={manualYaw}
                onChange={e=>setManualYaw(Number(e.target.value))}>
                {[0,90,180,270].map(n=><option key={n} value={n}>{n}°</option>)}
              </select>
            </label>
            <button disabled={busy||!manualName||!manualBuilding}
              onClick={()=>apply({op:'place_original',name:manualName,
                building_id:manualBuilding,position_m:manualXYZ.map(Number),
                yaw_deg:manualYaw})}>Add original source placement</button>
          </div>
          {manual.length>0&&<div className="actions">
            <label>Existing manual placement
              <select aria-label="Remove manual placement selection"
                value={selectedManual} onChange={e=>setSelectedManual(e.target.value)}>
                <option value="">Select</option>
                {manual.map(x=><option key={x.name}
                  value={x.name}>{x.name}</option>)}
              </select>
            </label>
            <button disabled={busy||!selectedManual}
              onClick={()=>apply({op:'remove_manual',name:selectedManual})}>
              Remove manual draft placement</button>
          </div>}
          <p className="fineprint">The weaker generated USD layer and stronger
            director override layer have been independently composed
            from the original source. No picture or Blender worker ran.
            Preview only shows source-verified building bounds—not a finished set.</p>
          <button disabled={busy||!validPreview}
            onClick={commit}>OS director approval · publish exact world revision</button>
        </>}
        {committed&&<p role="status">Approved original FilmIndex revision
          {committed.published_revision}; immutable source SHA:
          {committed.published_sha256}. Previous revisions remain readable.
          No film render or actor performance has been modified.</p>}
      </div>}
      <p className="fineprint">AI-generated plan values have no host authority.
        The manual AI origin selector is only a user-submitted label.
        Only the separate loaded-model action produces a host-observed
        completion receipt, atomically bound to the saved draft.
        Genuine loaded GGUF and physical installed Windows acceptance
        remain independent gates.</p>
    </>}
    {notice&&<p role="status">{notice}</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
