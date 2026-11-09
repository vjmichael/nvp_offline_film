import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import CameraRailGizmo from './CameraRailGizmo.jsx';

const T=7056000000; // DATA-TIME-01, exact original Film Time ticks per second.
const CATALOG='nvp.cam_fx01.trusted_director_rail_catalog.v1';
const PREVIEW='nvp.cam_fx01.verified_director_rail_proposal.v1';
const REOPEN='nvp.cam_fx02.trusted_native_director_rail_reopen.v1';
const SAMPLE='nvp.cam_fx02.native_rail_film_tick_pose.v1';
const SHA=/^[0-9a-f]{64}$/;
const ID=/^[A-Za-z][A-Za-z0-9_]{0,63}$/;
const TECHNIQUES=[
  ['static','Stationary / hold'],
  ['dolly','Dolly / push or pull'],
  ['truck','Truck / lateral tracking'],
  ['crane','Crane / vertical movement'],
  ['arc','Arc around a subject'],
  ['orbit','Orbit around a subject'],
  ['pan_tilt','Pan and tilt'],
  ['rack_focus','Rack focus (lens only)'],
  ['dolly_zoom','Dolly zoom (coupled lens)'],
  ['over_shoulder','Over-the-shoulder framing'],
  ['pov','Character POV'],
  ['reaction','Reaction shot'],
  ['establishing','Establishing movement'],
  ['reveal','Reveal through an opening'],
  ['dutch','Dutch roll'],
  ['compound','Custom compound rail'],
];
const clamp=(x,min,max)=>Math.max(min,Math.min(max,x));
const fix=x=>Number.isFinite(Number(x))?Number(x):0;
const coords=(v,scale=1)=>v.map(x=>Number((x*scale).toFixed(4)));

function node(tick,position,target,optics={}){
  return {tick,position_m:coords(position),target_m:coords(target),
    tangent_in_mps:[0,0,0],tangent_out_mps:[0,0,0],
    roll_deg:optics.roll??0,focal_length_mm:optics.focal??35,
    focus_distance_m:optics.focus??8,f_stop:optics.fstop??5.6,
    segment_mode:optics.mode||'hermite',easing:'smoothstep'};
}
function distance(a,b){
  return Math.sqrt(a.reduce((sum,x,i)=>sum+(x-b[i])**2,0));
}
function techniqueNodes(technique,base,begin,end){
  const p=coords(base.position_m);
  // The eventual actor-specific tracking target comes from CAM-FX-03
  // source scene bindings. This is only editable low-fi initial framing.
  const subject=[p[0],p[1]+8,p[2]];
  const middle=Math.floor((begin+end)/2);
  const origin=[...p],finish=[...p],target=[...subject];
  if(technique==='dolly'||technique==='dolly_zoom'||technique==='reveal')
    finish[1]+=3;
  else if(technique==='truck'||technique==='over_shoulder'||technique==='reaction')
    finish[0]+=2;
  else if(technique==='crane')finish[2]+=3;
  else if(technique==='arc'||technique==='orbit'){
    finish[0]+=2;finish[1]+=1;
  }
  else if(technique==='establishing'){
    finish[2]+=2;finish[1]+=1;
  }
  const mid=p.map((x,i)=>(x+finish[i])/2);
  const f=base.focal_length_mm||35;
  const first=node(begin,origin,target,{
    focal:f,focus:base.focus_distance_m||8});
  const second=node(middle,mid,target,{
    focal:f,focus:base.focus_distance_m||8});
  const last=node(end,finish,target,{
    focal:f,focus:base.focus_distance_m||8});
  if(technique==='pan_tilt'){
    second.target_m=[target[0]+1,target[1],target[2]+1];
    last.target_m=[target[0]+2,target[1],target[2]+2];
  }
  if(technique==='dutch'){
    second.roll_deg=10;last.roll_deg=20;
  }
  if(technique==='rack_focus'){
    second.focus_distance_m=5.5;last.focus_distance_m=3;
  }
  if(technique==='dolly_zoom'){
    const initial=distance(origin,target);
    const later=distance(finish,target);
    last.focal_length_mm=clamp(f*later/initial,8,300);
    second.focal_length_mm=clamp((f+last.focal_length_mm)/2,8,300);
  }
  if(technique==='static'){
    first.segment_mode='hold';second.segment_mode='hold';
  }
  return [first,second,last];
}
function nodeSummary(n){
  return n.position_m.map(x=>x.toFixed(2)).join(', ')+' m';
}

export default function CameraRailsDirector({projectId,nativeBridge}){
  const supported=Boolean(nativeBridge)&&[
    'camfx01_catalog','camfx01_preview','camfx02_publish',
    'camfx02_reopen','camfx02_sample'].every(
    name=>typeof nativeBridge[name]==='function');
  const [catalog,setCatalog]=useState(null);
  const [bankSelection,setBankSelection]=useState('');
  const [cameraId,setCameraId]=useState('');
  const [railId,setRailId]=useState('OriginalCameraRail');
  const [expectedRevision,setExpectedRevision]=useState(0);
  const [technique,setTechnique]=useState('dolly');
  const [start,setStart]=useState(0);
  const [end,setEnd]=useState(0);
  const [origin,setOrigin]=useState([0,0,0]);
  const [filmback,setFilmback]=useState([36,20.25]);
  const [nodes,setNodes]=useState([]);
  const [undoHandles,setUndoHandles]=useState([]);
  const [preview,setPreview]=useState(null);
  const [published,setPublished]=useState(null);
  const [reopened,setReopened]=useState(null);
  const [sampleTick,setSampleTick]=useState(0);
  const [sample,setSample]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const advanced=Boolean(nativeBridge)&&[
    'camfx03_scene_guidance','camfx03_draft_catalog',
    'camfx03_draft_create','camfx03_draft_reopen',
    'camfx03_draft_save','camfx03_draft_undo',
    'camfx03_draft_discard','camfx03_draft_publish',
    'camfx03_draft_recover_publish',
    'camfx04_start_candidate','camfx04_candidate_status',
    'camfx04_cancel_candidate'].every(
      name=>typeof nativeBridge[name]==='function');
  const [sceneGuidance,setSceneGuidance]=useState(null);
  const [selectedActor,setSelectedActor]=useState('');
  const [districtBinding,setDistrictBinding]=useState('');
  const [durableDraft,setDurableDraft]=useState(null);
  const [drafts,setDrafts]=useState([]);
  const [draftDirty,setDraftDirty]=useState(false);
  const [journalNotice,setJournalNotice]=useState('');
  const [modelList,setModelList]=useState([]);
  const [modelId,setModelId]=useState('');
  const [modelDirection,setModelDirection]=useState('');
  const [modelAttempt,setModelAttempt]=useState('');
  const [modelState,setModelState]=useState('');
  const [modelNotice,setModelNotice]=useState('');
  const editEpoch=useRef(0);
  const autoSaving=useRef(false);
  const banks=catalog?.camera_banks||[];
  const rails=catalog?.rails||[];
  const bank=banks.find(x=>
    x.bank_id+'@'+x.revision===bankSelection);
  const bankId=bank?.bank_id||'';
  const camera=bank?.cameras.find(x=>x.camera_id===cameraId);
  const valid=Boolean(preview)&&preview.format===PREVIEW&&
    preview.expected_revision===expectedRevision&&
    preview.world_take_sha256===bank?.world_take_sha256&&
    preview.camera_bank_sha256===bank?.document_sha256&&
    SHA.test(preview.proposal_sha256)&&SHA.test(preview.rail_layer_sha256)&&
    preview.native_blender_workers_started===0&&
    preview.original_actor_takes_and_pcm_unchanged===true;
  const spec=useMemo(()=>({
    camera_bank_id:bankId,
    camera_bank_revision:bank?.revision||0,
    camera_id:cameraId,
    film_start_tick:start,film_end_tick:end,
    technique,rail_origin_m:origin,filmback_mm:filmback,nodes
  }),[bankSelection,bank?.revision,cameraId,start,end,technique,origin,filmback,nodes]);
  const invalidate=()=>{
    editEpoch.current+=1;
    setPreview(null);setPublished(null);setReopened(null);
    setSample(null);setSceneGuidance(null);
    if(durableDraft?.state==='DRAFT')setDraftDirty(true);
  };
  const run=async action=>{
    if(!supported||busy)return;
    setBusy(true);setError('');setNotice('');
    try{await action();}catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  };
  const refresh=useCallback(async()=>{
    const result=await nativeBridge.camfx01_catalog(projectId);
    if(result?.format!==CATALOG||result.project_id!==projectId||
       !Array.isArray(result.camera_banks)||!Array.isArray(result.rails)||
       result.frozen_actor_takes_modified!==false||
       result.native_worker_started!==false)
      throw Error('Trusted source camera bank catalog is unavailable');
    setCatalog(result);
    setBankSelection(current=>result.camera_banks.some(
      x=>x.bank_id+'@'+x.revision===current)?current:
      (result.camera_banks[0]?
       result.camera_banks[0].bank_id+'@'+result.camera_banks[0].revision:''));
    return result;
  },[nativeBridge,projectId]);
  useEffect(()=>{
    if(!supported){setCatalog(null);return;}
    let active=true;
    refresh().catch(e=>{if(active)setError(e?.message||String(e));});
    return()=>{active=false;};
  },[refresh,supported]);
  useEffect(()=>{
    if(!bank)return;
    if(!bank.cameras.some(x=>x.camera_id===cameraId))
      setCameraId(bank.cameras[0]?.camera_id||'');
  },[bankSelection,bank?.revision,catalog,cameraId]);
  const preset=()=>{
    if(!camera||!bank)throw Error('Choose a real original 01M director camera');
    const begin=clamp(Math.floor(start),0,bank.duration_ticks-1);
    const stop=clamp(Math.floor(end)||Math.min(begin+10*T,bank.duration_ticks),
                     begin+1,bank.duration_ticks);
    setStart(begin);setEnd(stop);
    setOrigin([0,0,0]);
    setNodes(techniqueNodes(technique,camera,begin,stop));
    setUndoHandles([]);
    invalidate();
  };
  const remember=()=>setUndoHandles(history=>[...history,nodes].slice(-24));
  const editNode=(i,key,value,axis)=>{
    remember();
    setNodes(old=>old.map((n,j)=>j===i?{
      ...n,[key]:axis==null?value:n[key].map(
        (x,k)=>k===axis?fix(value):x)}:n));
    invalidate();
  };
  const insertNode=i=>{
    if(nodes.length>=48||i>=nodes.length-1)
      throw Error('Source rail must have 2–48 handles');
    const a=nodes[i],b=nodes[i+1],middle=Math.floor(
      (a.tick+b.tick)/2);
    if(middle<=a.tick||middle>=b.tick)
      throw Error('No exact Film Time tick between these camera handles');
    remember();
    const midpoint=(key)=>a[key].map(
      (x,k)=>Number(((x+b[key][k])/2).toFixed(5)));
    const created=node(middle,midpoint('position_m'),midpoint('target_m'),{
      focal:(a.focal_length_mm+b.focal_length_mm)/2,
      focus:(a.focus_distance_m+b.focus_distance_m)/2,
      fstop:(a.f_stop+b.f_stop)/2,
      roll:(a.roll_deg+b.roll_deg)/2});
    setNodes(old=>[...old.slice(0,i+1),created,...old.slice(i+1)]);
    invalidate();
  };
  const deleteNode=i=>{
    if(nodes.length<=2||i<=0||i>=nodes.length-1)
      throw Error('First/last source handles are mandatory');
    remember();
    setNodes(old=>old.filter((_,j)=>j!==i));
    invalidate();
  };
  const undoNodes=()=>{
    if(!undoHandles.length)return;
    setNodes(undoHandles[undoHandles.length-1]);
    setUndoHandles(old=>old.slice(0,-1));
    invalidate();
  };
  const editSpec=(setter,value)=>{setter(value);invalidate();};
  const verifyPreview=()=>run(async()=>{
    if(!ID.test(railId)||!camera||nodes.length<2)
      throw Error('Choose an original camera, valid rail ID and editable handles');
    const receipt=await nativeBridge.camfx01_preview({
      project_id:projectId,rail_id:railId,
      rail_spec:spec,expected_revision:expectedRevision});
    if(receipt?.format!==PREVIEW||receipt.expected_revision!==expectedRevision||
       receipt.world_take_sha256!==bank.world_take_sha256||
       receipt.camera_bank_sha256!==bank.document_sha256||
       receipt.director_creative_approval_granted!==false||
       receipt.original_actor_takes_and_pcm_unchanged!==true||
       !SHA.test(receipt.proposal_sha256)||
       !SHA.test(receipt.rail_layer_sha256))
      throw Error('Host source preview and native OpenUSD layer identity mismatch');
    setPreview(receipt);setNotice(
      'Exact Film Time path and stronger camera USD authored as unapproved preview. No Take changed.');
  });
  const publish=()=>run(async()=>{
    if(!valid)throw Error('Native exact-source preview is stale or missing');
    const receipt=await nativeBridge.camfx02_publish({
      project_id:projectId,rail_id:railId,rail_spec:spec,
      expected_revision:expectedRevision,
      preview_sha256:preview.proposal_sha256});
    if(receipt?.revision!==expectedRevision+1||
       receipt.source_usd_layer_sha256!==preview.rail_layer_sha256||
       receipt.original_actor_takes_and_pcm_unchanged!==true||
       receipt.director_picture_approved!==false||
       !SHA.test(receipt.document_sha256))
      throw Error('Operating-system-approved camera layer was not source pinned');
    const opened=await nativeBridge.camfx02_reopen({
      project_id:projectId,rail_id:railId,revision:receipt.revision});
    if(opened?.format!==REOPEN||
       opened.layer_sha256!==preview.rail_layer_sha256||
       opened.native_stronger_layer_verified!==true||
       opened.frozen_actor_takes_and_pcm_unchanged!==true)
      throw Error('New director camera rail failed independent USD reopen');
    setPublished(receipt);setReopened(opened);
    setExpectedRevision(receipt.revision);setPreview(null);
    await refresh();
    setNotice('OS-approved immutable camera rail layer independently reopened. You may now edit a NEW revision.');
  });
  const openRail=()=>run(async()=>{
    if(!ID.test(railId)||!Number.isInteger(expectedRevision)||expectedRevision<1)
      throw Error('Choose an exact previously approved rail revision');
    const opened=await nativeBridge.camfx02_reopen({
      project_id:projectId,rail_id:railId,revision:expectedRevision});
    if(opened?.format!==REOPEN||opened.rail_id!==railId||
       opened.revision!==expectedRevision||!SHA.test(opened.layer_sha256)||
       opened.native_stronger_layer_verified!==true||
       opened.frozen_actor_takes_and_pcm_unchanged!==true)
      throw Error('Verified source rail revision cannot be reopened');
    setReopened(opened);
    const data=opened.rail_spec;
    setBankSelection(data.camera_bank_id+'@'+data.camera_bank_revision);
    setCameraId(data.camera_id);
    setStart(data.film_start_tick);setEnd(data.film_end_tick);
    setOrigin(data.rail_origin_m);setFilmback(data.filmback_mm);
    setTechnique(data.technique);setNodes(data.nodes);
    setUndoHandles([]);
    setSampleTick(data.film_start_tick);
    setPreview(null);setSample(null);
    setNotice('Existing immutable camera layer reopened. Changes require a new revision and fresh OS approval.');
  });
  const sampleRail=()=>run(async()=>{
    if(!reopened||reopened.rail_id!==railId||
       reopened.revision!==expectedRevision)
      throw Error('Reopen exact original camera layer before Film Time readback');
    const pose=await nativeBridge.camfx02_sample({
      project_id:projectId,rail_id:railId,
      revision:expectedRevision,film_tick:sampleTick});
    if(pose?.format!==SAMPLE||pose.rail_id!==railId||
       pose.revision!==expectedRevision||
       pose.rail_layer_sha256!==reopened.layer_sha256||
       pose.film_tick!==sampleTick||
       pose.native_worker_started!==false||
       pose.source_actor_pcm_changed!==false||
       typeof pose.native_layer_sample_authored_and_read_back!=='boolean'||
       typeof pose.host_exact_film_time_interpolated!=='boolean'||
       pose.native_layer_sample_authored_and_read_back===
         pose.host_exact_film_time_interpolated)
      throw Error('Native source camera pose failed stronger-layer recheck');
    setSample({...pose.sample,
      native_layer_sample_authored_and_read_back:
        pose.native_layer_sample_authored_and_read_back});
    setNotice(pose.native_layer_sample_authored_and_read_back?
      'Exact source-time camera key was independently read from the stronger native USD layer.':
      'Off-grid Film Time camera pose was evaluated by the deterministic host rail, not presented as a native authored USD key.');
  });
  const checkDraft=record=>{
    if(record?.format!=='nvp.cam_fx03.durable_original_camera_rail_draft.v1'||
       record.project_id!==projectId||
       !/^[0-9a-f]{24}$/.test(record.draft_id)||
       !Number.isInteger(record.version)||record.version<1||
       !SHA.test(record.proposal_sha256)||
       !SHA.test(record.stronger_usd_sha256)||
       record.source_actor_takes_and_pcm_changed!==false)
      throw Error('Durable camera draft has no independently verified source receipt');
    return record;
  };
  const applySpec=body=>{
    setBankSelection(body.camera_bank_id+'@'+body.camera_bank_revision);
    setCameraId(body.camera_id);
    setStart(body.film_start_tick);setEnd(body.film_end_tick);
    setTechnique(body.technique);setOrigin(body.rail_origin_m);
    setFilmback(body.filmback_mm);setNodes(body.nodes);
    setSampleTick(body.film_start_tick);setUndoHandles([]);
    setPreview(null);setReopened(null);setSceneGuidance(null);
    editEpoch.current+=1;
  };
  const refreshDrafts=useCallback(async()=>{
    if(!advanced)return;
    const found=await nativeBridge.camfx03_draft_catalog(projectId);
    if(found?.format!=='nvp.cam_fx03.original_camera_draft_catalog.v1'||
       found.project_id!==projectId||!Array.isArray(found.drafts)||
       !Array.isArray(found.model_attempts)||
       found.native_worker_authorized!==false)
      throw Error('Actual SQLite original camera drafts could not be browsed');
    setDrafts(found.drafts);
    if(typeof nativeBridge.wo6_local_models==='function'){
      const models=await nativeBridge.wo6_local_models(projectId);
      if(!Array.isArray(models?.models))
        throw Error('Only trusted host-selected offline model discovery');
      setModelList(models.models);
      setModelId(old=>models.models.some(m=>m.id===old)?
        old:models.models[0]?.id||'');
    }
  },[advanced,nativeBridge,projectId]);
  useEffect(()=>{
    if(!advanced)return;
    let mounted=true;
    setDurableDraft(null);setDraftDirty(false);setSceneGuidance(null);
    setModelAttempt('');
    refreshDrafts().catch(e=>{if(mounted)setError(e.message||String(e));});
    return()=>{mounted=false;};
  },[advanced,refreshDrafts]);
  const requestGuidance=()=>run(async()=>{
    if(nodes.length<2||!bank||typeof nativeBridge.camfx03_scene_guidance!=='function')
      throw Error('First select a source-linked camera rail trajectory');
    const report=await nativeBridge.camfx03_scene_guidance({
      project_id:projectId,rail_spec:spec,
      actor_id:selectedActor||null,
      district_binding_id:districtBinding.trim()||null});
    if(report?.format!=='nvp.cam_fx03.source_grounded_actor_framing_and_occlusion.v1'||
       report.project_id!==projectId||
       report.camera_bank_sha256!==bank.document_sha256||
       report.world_take_sha256!==bank.world_take_sha256||
       report.source_actor_takes_and_pcm_unchanged!==true||
       report.native_scene_reviewed!==true||
       !SHA.test(report.guidance_sha256)||
       !Array.isArray(report.source_guided_frames)||
       report.source_guided_frames.length!==3)
      throw Error('Native original actor/district framing receipt was not source-bound');
    setSceneGuidance(report);
    setNotice('Three exact-time native ActorID camera framings inspected. Center-ray occlusion is advisory, not a proof of a clear full image.');
  });
  const startDurable=()=>run(async()=>{
    if(!advanced||!bank||nodes.length<2||!ID.test(railId))
      throw Error('Select a source-valid original camera trajectory before journal creation');
    const saved=checkDraft(await nativeBridge.camfx03_draft_create({
      project_id:projectId,rail_id:railId,
      expected_revision:expectedRevision,rail_spec:spec}));
    setDurableDraft(saved);setDraftDirty(false);
    setJournalNotice('Camera path durably committed as an UNAPPROVED SQLite draft. All subsequent edits are versioned.');
    await refreshDrafts();
  });
  const reopenDraft=did=>run(async()=>{
    if(!/^[0-9a-f]{24}$/.test(did))
      throw Error('Select an exact saved project-local original camera draft');
    const saved=checkDraft(await nativeBridge.camfx03_draft_reopen({
      project_id:projectId,draft_id:did}));
    applySpec(saved.rail_spec);
    setRailId(saved.rail_id);setExpectedRevision(saved.base_revision);
    setDurableDraft(saved);setDraftDirty(false);
    setJournalNotice('SQLite draft reopened after installed-app restart. Historical OS approval has not been reused.');
  });
  const saveDraft=()=>run(async()=>{
    if(!durableDraft||durableDraft.state!=='DRAFT')
      throw Error('Create or reopen a durable editable rail first');
    const saved=checkDraft(await nativeBridge.camfx03_draft_save({
      project_id:projectId,draft_id:durableDraft.draft_id,
      version:durableDraft.version,rail_spec:spec}));
    setDurableDraft(saved);setDraftDirty(false);
    setJournalNotice('Exact 3D handle edits persisted under SQLite full-synchronous journal version '+saved.version+'.');
  });
  const undoDurable=()=>run(async()=>{
    if(!durableDraft||durableDraft.state!=='DRAFT')
      throw Error('Only a current source-pinned draft may undo a saved edit');
    const saved=checkDraft(await nativeBridge.camfx03_draft_undo({
      project_id:projectId,draft_id:durableDraft.draft_id,
      version:durableDraft.version}));
    applySpec(saved.rail_spec);
    setDurableDraft(saved);setDraftDirty(false);
    setJournalNotice('Previous original-camera director edit restored from durable SQLite history.');
  });
  const discardDraft=()=>run(async()=>{
    if(!durableDraft||durableDraft.state!=='DRAFT')
      throw Error('Only an unapproved draft may be discarded');
    const result=checkDraft(await nativeBridge.camfx03_draft_discard({
      project_id:projectId,draft_id:durableDraft.draft_id,
      version:durableDraft.version}));
    setDurableDraft(result);setDraftDirty(false);
    setJournalNotice('Unapproved camera draft discarded. Original Takes and published rails remain intact.');
    await refreshDrafts();
  });
  const recoverPublish=()=>run(async()=>{
    if(!durableDraft)throw Error('Select interrupted exact camera draft');
    const result=checkDraft(await nativeBridge.camfx03_draft_recover_publish({
      project_id:projectId,draft_id:durableDraft.draft_id}));
    setDurableDraft(result);
    setJournalNotice(result.state==='PUBLISHED'?
      'Existing native FilmIndex rail commit recovered from source SHA; no worker or permission was retried.':
      'No proven source revision was published. A NEW draft and NEW OS approval are required.');
  });
  const publishDurable=()=>run(async()=>{
    if(!valid||draftDirty||!durableDraft||durableDraft.state!=='DRAFT'||
       durableDraft.rail_id!==railId||
       durableDraft.base_revision!==expectedRevision||
       durableDraft.proposal_sha256!==preview.proposal_sha256)
      throw Error('Only exact freshly previewed DURABLE camera draft can seek OS approval');
    const receipt=await nativeBridge.camfx03_draft_publish({
      project_id:projectId,draft_id:durableDraft.draft_id,
      version:durableDraft.version,
      preview_sha256:preview.proposal_sha256});
    if(receipt?.format!=='nvp.cam_fx03.durable_published_director_rail.v1'||
       receipt?.draft?.state!=='PUBLISHED'||
       receipt?.rail_receipt?.revision!==expectedRevision+1||
       receipt.rail_receipt.source_usd_layer_sha256!==
          preview.rail_layer_sha256||
       receipt.actor_pcm_modified!==false)
      throw Error('Native approval did not publish the exact durably reviewed USD source');
    const opened=await nativeBridge.camfx02_reopen({
      project_id:projectId,rail_id:railId,
      revision:receipt.rail_receipt.revision});
    if(opened?.format!==REOPEN||
       opened.layer_sha256!==preview.rail_layer_sha256||
       opened.native_stronger_layer_verified!==true)
      throw Error('Published director camera layer did not independently reopen');
    setDurableDraft(checkDraft(receipt.draft));setDraftDirty(false);
    setPublished(receipt.rail_receipt);setReopened(opened);
    setExpectedRevision(receipt.rail_receipt.revision);
    setPreview(null);await refreshDrafts();
    setJournalNotice('One fresh OS approval published the reviewed original source. ActorID performances and PCM unchanged.');
  });
  useEffect(()=>{
    if(!advanced||!durableDraft||durableDraft.state!=='DRAFT'||
       !draftDirty||modelAttempt||autoSaving.current)return;
    const expectedEpoch=editEpoch.current;
    const task=setTimeout(async()=>{
      if(autoSaving.current)return;
      autoSaving.current=true;
      try{
        const receipt=checkDraft(await nativeBridge.camfx03_draft_save({
          project_id:projectId,draft_id:durableDraft.draft_id,
          version:durableDraft.version,rail_spec:spec}));
        setDurableDraft(receipt);
        const newer=editEpoch.current!==expectedEpoch;
        setDraftDirty(newer);
        setJournalNotice(newer?
          'Earlier edit version persisted; saving latest rail handles next.':
          'Camera rail handles and optical changes recovered in SQLite journal version '+receipt.version+'.');
      }catch(e){
        setError('Native camera autosave rejected; original saved draft remains intact: '+
          (e?.message||String(e)));
      }finally{autoSaving.current=false;}
    },650);
    return()=>clearTimeout(task);
  },[advanced,durableDraft?.draft_id,durableDraft?.version,
     draftDirty,modelAttempt,spec,nativeBridge,projectId]);
  useEffect(()=>{
    if(!advanced||!modelAttempt)return;
    let stopped=false,timeout=null;
    const poll=async()=>{
      try{
        const status=await nativeBridge.camfx04_candidate_status({
          project_id:projectId,attempt_id:modelAttempt});
        if(stopped)return;
        if(status?.format!=='nvp.cam_fx04.durable_unapproved_model_camera_proposal.v1'||
           status.project_id!==projectId||
           status.attempt_id!==modelAttempt||
           status.director_approval_granted!==false||
           status.native_worker_authorized!==false)
          throw Error('Local model attempt is not original-source admitted');
        setModelState(status.state);
        if(status.state==='GENERATING'){
          timeout=setTimeout(poll,1300);return;
        }
        if(status.state==='DRAFT_UPDATED_UNAPPROVED'){
          const proposed=checkDraft(status.draft);
          applySpec(proposed.rail_spec);
          setDurableDraft(proposed);setDraftDirty(false);
          setModelNotice('Native source-verified local model suggestion saved as editable UNAPPROVED rail version '+proposed.version+'. Director changes and OS approval remain separate.');
        }else{
          setModelNotice('Local model attempt '+status.state+
            '. No old model output may resume or publish a rail.');
        }
        setModelAttempt('');
      }catch(e){
        if(!stopped){setModelAttempt('');
          setError(e?.message||String(e));}
      }
    };
    timeout=setTimeout(poll,300);
    return()=>{stopped=true;clearTimeout(timeout);};
  },[advanced,modelAttempt,nativeBridge,projectId]);
  const startModel=()=>run(async()=>{
    if(!durableDraft||durableDraft.state!=='DRAFT'||draftDirty||
       !sceneGuidance||!modelId.trim()||!modelDirection.trim())
      throw Error('Save a current source-framed draft and select a local model');
    const status=await nativeBridge.camfx04_start_candidate({
      project_id:projectId,draft_id:durableDraft.draft_id,
      version:durableDraft.version,model_id:modelId,
      direction:modelDirection,actor_id:selectedActor||null,
      district_binding_id:districtBinding.trim()||null});
    if(status?.format!=='nvp.cam_fx04.durable_unapproved_model_camera_proposal.v1'||
       status.project_id!==projectId||
       status.draft_id!==durableDraft.draft_id||
       status.state!=='GENERATING'||
       status.director_approval_granted!==false||
       !/^[0-9a-f]{24}$/.test(status.attempt_id))
      throw Error('Native local model did not return a durable camera advice attempt');
    setModelAttempt(status.attempt_id);setModelState('GENERATING');
    setModelNotice('Actual selected loopback model is generating untrusted camera data. Director may cancel; no original source can be published.');
  });
  const cancelModel=()=>run(async()=>{
    if(!modelAttempt)return;
    const result=await nativeBridge.camfx04_cancel_candidate({
      project_id:projectId,attempt_id:modelAttempt});
    if(result?.state!=='CANCELLED'&&
       result?.state!=='INTERRUPTED_REQUIRES_NEW_GENERATION')
      throw Error('Camera model attempt cancellation was not durable');
    setModelState(result.state);setModelAttempt('');
    setModelNotice('Camera model cancelled. Late GGUF responses cannot save or approve a new camera layer.');
  });

  if(!supported)return null;
  return <section aria-label="Director digital camera rails and shot techniques"
    style={{borderTop:'1px solid #55616e',marginTop:20,paddingTop:18}}>
    <h4>25 · Director-editable digital camera rails</h4>
    <p className="fineprint">Virtual rails move an original-source-linked
      camera, not an actor or a physical dolly. Control points, timing,
      orientation, lens and focus form a stronger immutable OpenUSD
      director layer. A changed rail needs a new director-approved revision.
      Real motion blur, depth of field and final Cycles quality remain separate.</p>
    <button disabled={busy} onClick={()=>run(refresh)}>
      Refresh frozen source cameras and approved rails</button>
    <label>Original director camera bank
      <select aria-label="Rail source camera bank" disabled={busy}
        value={bankSelection} onChange={e=>{
          editSpec(setBankSelection,e.target.value);
          setCameraId('');setNodes([]);}}>
        <option value="">Select original camera bank</option>
        {banks.map(x=><option key={x.bank_id+'@'+x.revision}
          value={x.bank_id+'@'+x.revision}>
          {x.bank_id} · revision {x.revision}</option>)}
      </select>
    </label>
    <label>Original source camera
      <select aria-label="Rail source camera" value={cameraId}
        disabled={busy} onChange={e=>{editSpec(setCameraId,e.target.value);
          setNodes([]);}}>
        <option value="">Select original virtual camera</option>
        {(bank?.cameras||[]).map(x=><option key={x.camera_id}
          value={x.camera_id}>{x.camera_id}</option>)}
      </select>
    </label>
    <label>Virtual rail ID
      <input aria-label="Original camera rail ID"
        value={railId} disabled={busy} onChange={e=>
          editSpec(setRailId,e.target.value)}/></label>
    <label>Existing approved rail revision (0 = new rail)
      <input aria-label="Expected camera rail revision"
        type="number" min={0} step={1} disabled={busy}
        value={expectedRevision} onChange={e=>
          editSpec(setExpectedRevision,fix(e.target.value))}/></label>
    <div className="actions">
      <label>Load saved rail
        <select aria-label="Saved camera rail revision"
          value="" disabled={busy}
          onChange={e=>{
            const row=rails.find(x=>x.rail_id===e.target.value);
            if(row){setRailId(row.rail_id);setExpectedRevision(
              row.revision);setPreview(null);setReopened(null);
              setNodes([]);setSample(null);}}}>
          <option value="">Choose existing source</option>
          {rails.map(x=><option key={x.rail_id} value={x.rail_id}>
            {x.rail_id} · {x.technique} · rev {x.revision}</option>)}
        </select></label>
      <button disabled={busy||expectedRevision<1}
        onClick={openRail}>Reopen exact approved rail and its handles</button>
    </div>
    <label>Shot technique / editable first-party starting preset
      <select aria-label="Camera rail shot technique" disabled={busy}
        value={technique}
        onChange={e=>editSpec(setTechnique,e.target.value)}>
        {TECHNIQUES.map(([id,label])=><option key={id}
          value={id}>{label}</option>)}
      </select>
    </label>
    <label>Original Film Time begin (integer ticks)
      <input aria-label="Camera rail start tick" type="number" step={1}
        value={start} disabled={busy} onChange={e=>
          editSpec(setStart,fix(e.target.value))}/></label>
    <label>Original Film Time end (integer ticks)
      <input aria-label="Camera rail end tick" type="number" step={1}
        value={end} disabled={busy} onChange={e=>
          editSpec(setEnd,fix(e.target.value))}/></label>
    <button disabled={busy||!camera||!bank}
      onClick={()=>run(preset)}>Create editable camera rail handles from technique</button>
    <p className="fineprint">Source length: {bank?.duration_ticks||0} ticks.
      The selected preset is only a suggested path—drag/numeric rail edits
      and human approval must occur before native use.</p>
    {advanced&&<>
      <section aria-label="Source-grounded native actor framing and district occlusion">
        <h5>Actual ActorID framing, approved geometry and ray warnings</h5>
        <label>Optional approved 02M-H district shot binding ID
          <input aria-label="Native rail approved district shot binding"
            value={districtBinding} maxLength={80} disabled={busy}
            onChange={e=>{setDistrictBinding(e.target.value);setSceneGuidance(null);}}/>
        </label>
        <label>Verified original ActorID framing target
          <select aria-label="Original native ActorID framing target"
            value={selectedActor} disabled={busy}
            onChange={e=>{setSelectedActor(e.target.value);setSceneGuidance(null);}}>
            <option value="">All original actors; select one to test center ray</option>
            {(sceneGuidance?.source_guided_frames?.[0]?.original_actor_views||[])
              .map(a=><option key={a.actor_id} value={a.actor_id}>
                ActorID {a.actor_id}</option>)}
          </select>
        </label>
        <button disabled={busy||nodes.length<2} onClick={requestGuidance}>
          Read actual original USD ActorID framing and bounded occlusion</button>
        {sceneGuidance&&<div role="region"
          aria-label="Verified original ActorID scene and ray guidance">
          <p>Source Take SHA: {sceneGuidance.world_take_sha256}.
            Native original actors: {sceneGuidance.native_actor_count}.
            Original source SHA: {sceneGuidance.guidance_sha256}.
            Approved district SHA: {sceneGuidance.approved_district_sha256||'none'}.
            No ActorID source or PCM was rewritten.</p>
          {sceneGuidance.source_guided_frames.map(frame=>
            <div key={frame.film_tick}>
              <p>Film Time tick {frame.film_tick} ·
                Center-ray: {frame.selected_actor_center_ray.state}.
                Real original district mesh triangles checked:
                {' '+frame.selected_actor_center_ray.reviewed_original_district_triangles}.
                Non-mesh primitives excluded:
                {' '+frame.selected_actor_center_ray.excluded_nonmesh_shapes}.
                {frame.selected_actor_center_ray.hit_source_prim&&
                 ' Source obstruction: '+frame.selected_actor_center_ray.hit_source_prim}.
                Full frame visibility never certified by one ray.</p>
              <ul>{frame.original_actor_views.slice(0,12).map(a=>
                <li key={a.actor_id}>
                  ActorID {a.actor_id}: {a.frame.state}.
                  Projected 2D frame coverage: {
                    Number((a.frame.coverage*100).toFixed(1))}%.
                  Center: {a.center_world_m.map(n=>Number(n.toFixed(2))).join(', ')} m.
                </li>)}</ul>
            </div>)}
        </div>}
      </section>
    </>}
    {nodes.length>=2&&<CameraRailGizmo nodes={nodes} origin={origin}
      guidance={sceneGuidance} disabled={busy||Boolean(modelAttempt)}
      onNodesChange={updated=>{
        remember();setNodes(updated);invalidate();
      }}/>}
    <div className="actions">
      {['X','Y','Z'].map((axis,i)=><label key={axis}>
        Origin rebasing {axis} (m)
        <input type="number" step={.1} aria-label={'Rail origin '+axis}
          value={origin[i]} disabled={busy} onChange={e=>{
            setOrigin(old=>old.map((n,j)=>j===i?fix(e.target.value):n));
            invalidate();}}/></label>)}
      {['W','H'].map((axis,i)=><label key={axis}>
        Filmback {axis} (mm)
        <input type="number" step={.1}
          aria-label={'Rail filmback '+axis}
          value={filmback[i]} disabled={busy} onChange={e=>{
            setFilmback(old=>old.map((n,j)=>j===i?fix(e.target.value):n));
            invalidate();}}/></label>)}
    </div>
    <h5>Director rail handles · exact-time source keys</h5>
    <button disabled={busy||undoHandles.length===0} onClick={undoNodes}>
      Undo last unapproved camera-rail handle edit</button>
    <p className="fineprint">Insert, move, retime, remove or undo handles before
      approving a revised stronger OpenUSD layer. Only source-confirmed
      values survive publication.</p>
    {nodes.map((n,i)=><fieldset key={i}
      style={{padding:8,border:'1px solid #50606f',marginBottom:8}}>
      <legend>Handle {i+1} · {nodeSummary(n)}</legend>
      <div className="actions">
        <button disabled={busy||nodes.length>=48||i===nodes.length-1}
          onClick={()=>run(()=>insertNode(i))}>Insert handle after {i+1}</button>
        <button disabled={busy||nodes.length<=2||i===0||i===nodes.length-1}
          onClick={()=>run(()=>deleteNode(i))}>Remove handle {i+1}</button>
      </div>
      <label>Original Film Time tick
        <input type="number" step={1}
          aria-label={'Rail key '+i+' tick'} value={n.tick}
          onChange={e=>editNode(i,'tick',fix(e.target.value))}/></label>
      {[
        ['position_m','Position'],['target_m','Look-at target'],
        ['tangent_in_mps','Incoming tangent m/s'],
        ['tangent_out_mps','Outgoing tangent m/s']
      ].map(([key,label])=><div key={key} className="actions">
        {['X','Y','Z'].map((axis,k)=><label key={axis}>
          {label} {axis}
          <input type="number" step={.1}
            aria-label={'Rail key '+i+' '+key+' '+axis}
            value={n[key][k]} disabled={busy}
            onChange={e=>editNode(i,key,e.target.value,k)}/></label>)}
      </div>)}
      <div className="actions">
        {[
          ['roll_deg','Roll °'],['focal_length_mm','Focal mm'],
          ['focus_distance_m','Focus m'],['f_stop','F-stop']
        ].map(([key,label])=><label key={key}>{label}
          <input type="number" step={.1} disabled={busy}
            aria-label={'Rail key '+i+' '+key} value={n[key]}
            onChange={e=>editNode(i,key,fix(e.target.value))}/></label>)}
      </div>
      <label>Interpolation
        <select aria-label={'Rail key '+i+' mode'}
          value={n.segment_mode} disabled={busy}
          onChange={e=>editNode(i,'segment_mode',e.target.value)}>
          {['hold','linear','hermite'].map(x=><option key={x} value={x}>
            {x}</option>)}
        </select>
      </label>
      <label>Easing
        <select aria-label={'Rail key '+i+' easing'}
          value={n.easing} disabled={busy}
          onChange={e=>editNode(i,'easing',e.target.value)}>
          <option value="linear">linear</option>
          <option value="smoothstep">smoothstep</option>
        </select>
      </label>
    </fieldset>)}
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    <div className="actions">
      <button disabled={busy||!nodes.length||!ID.test(railId)}
        onClick={verifyPreview}>Preview exact-time stronger camera USD layer</button>
      {advanced?
        <button disabled={busy||!valid||!durableDraft||
          durableDraft.state!=='DRAFT'||draftDirty||
          durableDraft.proposal_sha256!==preview?.proposal_sha256||
          Boolean(modelAttempt)}
          onClick={publishDurable}>
          OS approve exact saved and source-verified camera rail draft</button>:
        <button disabled={busy||!valid}
          onClick={publish}>OS approve exact director-editable camera rail revision</button>}
    </div>
    {preview&&<p role="status">
      Director rail preview SHA: {preview.proposal_sha256}.
      Stronger source USD layer SHA: {preview.rail_layer_sha256}.
      {preview.film_time_samples.length} source preview samples.
      No original actor Takes or PCM changed. No render authorization.</p>}
    {advanced&&<section aria-label="Durable camera rail editing and model proposals">
      <h5>Durable camera source drafts · crash-safe revision history</h5>
      <p className="fineprint">Create a SQLite source draft to enable
        automatic save after edits. Unsaved changes are marked until a native
        journal acknowledgement. Interrupted OS confirmations are never
        replayed; a new approval is required.</p>
      <button disabled={busy||!bank||nodes.length<2||
          durableDraft?.state==='DRAFT'}
        onClick={startDurable}>
        Create source-bound durable camera-rail draft</button>
      <label>Reopen saved native camera draft after restart
        <select aria-label="Reopen a saved camera rail draft"
          defaultValue="" disabled={busy}
          onChange={e=>{if(e.target.value)reopenDraft(e.target.value);}}>
          <option value="">Select project-local unapproved draft</option>
          {drafts.map(d=><option key={d.draft_id} value={d.draft_id}>
            {d.rail_id} · {d.state} · v{d.version}</option>)}
        </select>
      </label>
      <button disabled={busy} onClick={()=>run(refreshDrafts)}>
        Refresh durable original rail history</button>
      {durableDraft&&<div role="region"
        aria-label="Exact saved camera rail source status">
        <p>Draft {durableDraft.draft_id}, journal version {
          durableDraft.version}, state {durableDraft.state}.
          Saved proposal SHA {durableDraft.proposal_sha256}.
          Durable undo depth: {durableDraft.undo_depth}.
          {draftDirty?' Local handle changes still pending journal acknowledgement.':
            ' Current changes confirmed in SQLite.'}</p>
        <div className="actions">
          <button disabled={busy||durableDraft.state!=='DRAFT'||
            !draftDirty} onClick={saveDraft}>Save camera edits now to SQLite</button>
          <button disabled={busy||durableDraft.state!=='DRAFT'||
            draftDirty||durableDraft.undo_depth<1}
            onClick={undoDurable}>Undo saved original camera draft revision</button>
          <button disabled={busy||durableDraft.state!=='DRAFT'}
            onClick={discardDraft}>Discard unapproved camera draft</button>
          <button disabled={busy||durableDraft.state!==
            'INTERRUPTED_REQUIRES_NEW_APPROVAL'}
            onClick={recoverPublish}>
            Reconcile interrupted native camera publication without retry</button>
        </div>
      </div>}
      {journalNotice&&<p role="status">{journalNotice}</p>}
      <h5>Local AI shot technique advice · unapproved editable proposal</h5>
      <p className="fineprint">Only the previously configured host-selected
        loopback model can suggest handles. It receives bounded original
        ActorID/district framing evidence, never a worker or native OS grant.
        Model output is strict JSON and passes a separate native USD source check.</p>
      <label>Verified configured offline local model
        <select aria-label="Camera rail local GGUF model" disabled={busy}
          value={modelId} onChange={e=>setModelId(e.target.value)}>
          <option value="">Choose configured host-selected local model</option>
          {modelList.map(model=><option key={model.id} value={model.id}>
            {model.id}</option>)}
        </select>
      </label>
      <label>Director shot direction
        <textarea aria-label="Native original camera model direction"
          maxLength={1200} value={modelDirection} disabled={busy}
          onChange={e=>setModelDirection(e.target.value)}/>
      </label>
      <div className="actions">
        <button disabled={busy||!durableDraft||
          durableDraft.state!=='DRAFT'||draftDirty||
          !sceneGuidance||!modelId||!modelDirection.trim()||
          Boolean(modelAttempt)}
          onClick={startModel}>
          Suggest and save unapproved source-grounded AI camera rail</button>
        <button disabled={busy||!modelAttempt}
          onClick={cancelModel}>Cancel native camera model proposal</button>
      </div>
      {modelState&&<p role="status">Local model proposal: {modelState}.
        No creative authority was granted.</p>}
      {modelNotice&&<p role="status">{modelNotice}</p>}
    </section>}
    {published&&<p role="status">
      Native camera source revision {published.revision} committed and
      independently reopened. Original performance still immutable.</p>}
    {reopened&&<div role="region" aria-label="Verified original camera rail">
      <p>Actual stronger OpenUSD camera: {reopened.native_camera_path}.
        Layer SHA: {reopened.layer_sha256}.
        Reopened native samples: {reopened.native_reopened_sample_count}.</p>
      <label>Film Time scrub tick
        <input type="number" step={1} disabled={busy}
          aria-label="Camera rail sample tick" value={sampleTick}
          onChange={e=>setSampleTick(fix(e.target.value))}/></label>
      <button disabled={busy} onClick={sampleRail}>
        Read exact original-time native camera pose</button>
      {sample&&<p role="status">
        Director camera position: {sample.position_m.join(', ')} m.
        Target: {sample.target_m.join(', ')} m.
        Focal: {sample.focal_length_mm} mm.
        Focus: {sample.focus_distance_m} m.
        F-stop: {sample.f_stop}.
        No source actor moved.</p>}
    </div>}
  </section>;
}
