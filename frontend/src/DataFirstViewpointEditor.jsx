import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import SourceUSDViewport from './SourceUSDViewport.jsx';

const FRAMES=720;
const CATALOG='nvp.usd_film01r.original_world_viewpoint_catalog.v1';
const SNAPSHOT='nvp.usd_film01r.source_3d_lofi_viewpoint.v1';
const defaultCut=id=>[{camera_id:id,source_in_frame:0,source_out_frame:720,edit_in_frame:0,edit_out_frame:720}];
const exactCuts=(cuts,cameras)=>{
  if(!Array.isArray(cuts)||!cuts.length||cuts.length>96)return false;
  let cursor=0;
  for(const c of cuts){
    if(!cameras.includes(c.camera_id)||c.edit_in_frame!==cursor||
       c.source_in_frame!==cursor||!Number.isInteger(c.edit_out_frame)||
       c.edit_out_frame!==c.source_out_frame||
       c.edit_out_frame<=cursor||c.edit_out_frame>FRAMES)return false;
    cursor=c.edit_out_frame;
  }
  return cursor===FRAMES;
};

export default function DataFirstViewpointEditor({projectId,api,nativeBridge=null}){
  const [native,setNative]=useState(nativeBridge);
  const [catalog,setCatalog]=useState(null),[bankId,setBankId]=useState('');
  const [cameraId,setCameraId]=useState(''),[frame,setFrame]=useState(0);
  const [snapshot,setSnapshot]=useState(null),[orbit,setOrbit]=useState(false);
  const [playing,setPlaying]=useState(false),[busy,setBusy]=useState(false);
  const [cuts,setCuts]=useState([]),[savedEdit,setSavedEdit]=useState(null);
  const [editId,setEditId]=useState(''),[newCamId,setNewCamId]=useState('NewAngle');
  const [newBankId,setNewBankId]=useState('DirectorCameraBank');
  const [takeId,setTakeId]=useState('');
  const [quality,setQuality]=useState('technical_smoke');
  const [groupSize,setGroupSize]=useState('auto'),[parallel,setParallel]=useState('auto');
  const [estimate,setEstimate]=useState(null),[ticket,setTicket]=useState(null);
  const [renderStatus,setRenderStatus]=useState(null);
  const [error,setError]=useState(''),[notice,setNotice]=useState('');
  const undo=useRef([]),generation=useRef(0);
  const banks=catalog?.camera_banks||[];
  const bank=banks.find(x=>x.camera_bank_id===bankId)||null;
  const cameras=bank?.cameras||[];
  const selectedCamera=cameras.find(x=>x.camera_id===cameraId)||null;
  const selectedCut=cuts.find(x=>x.edit_in_frame<=frame&&frame<x.edit_out_frame)||null;
  const nativeReady=Boolean(native)&&[
    'film01r_create_bank','film01r_revise_bank','film01r_save_edit',
    'film01r_render_next','film01r_render_poll'].every(k=>typeof native[k]==='function');

  const reload=useCallback(async()=>{
    const record=await api('/projects/'+encodeURIComponent(projectId)+'/film/data-first-viewpoints');
    if(record?.format!==CATALOG||record.project_id!==projectId||
       !Array.isArray(record.camera_banks)||!Array.isArray(record.edits))
      throw Error('Real original FilmIndex source catalog could not be verified');
    setCatalog(record);
    setBankId(old=>record.camera_banks.some(x=>x.camera_bank_id===old)?
      old:record.camera_banks[0]?.camera_bank_id||'');
    setTakeId(old=>record.original_world_takes?.some(x=>x.world_take_id===old)?
      old:record.original_world_takes?.[0]?.world_take_id||'');
    return record;
  },[api,projectId]);
  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    const found=()=>setNative(window.pywebview?.api||null);
    found();window.addEventListener('pywebviewready',found);
    return ()=>window.removeEventListener('pywebviewready',found);
  },[nativeBridge]);
  useEffect(()=>{
    setCatalog(null);setBankId('');setSnapshot(null);setError('');
    let active=true;
    reload().catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[reload]);
  useEffect(()=>{
    const first=cameras[0]?.camera_id||'';
    setCameraId(first);setFrame(0);setSnapshot(null);setPlaying(false);
    undo.current=[];setTicket(null);setRenderStatus(null);setEstimate(null);
    const prior=catalog?.edits?.find(x=>x.camera_bank_id===bankId&&
      x.camera_bank_revision===bank?.revision);
    setSavedEdit(prior||null);
    setEditId(prior?.edit_id||(bank?'Edit_'+bank.document_sha256.slice(0,24):''));
    setCuts(prior?.cuts?.map(x=>({...x}))||(first?defaultCut(first):[]));
  },[bankId,bank?.revision,bank?.document_sha256]);
  useEffect(()=>{
    if(!bank||!cameraId)return;
    const gen=++generation.current;
    let active=true;
    setSnapshot(null);setError('');
    const timer=setTimeout(()=>{
      const qs=new URLSearchParams({
        revision:String(bank.revision),frame:String(frame),camera_id:cameraId});
      api('/projects/'+encodeURIComponent(projectId)+
          '/film/data-first-viewpoints/'+encodeURIComponent(bankId)+'/preview?'+qs)
      .then(record=>{
        if(!active||gen!==generation.current)return;
        if(record?.format!==SNAPSHOT||record.project_id!==projectId||
           record.camera_bank_sha256!==bank.document_sha256||
           record.original_performance_sha256!==bank.original_performance_sha256||
           record.frame!==frame||record.camera_id!==cameraId||
           record.native_blender_workers_started!==0)
          throw Error('Low-fi geometry was not source verified at this frame/camera');
        setSnapshot(record);
      }).catch(e=>{if(active&&gen===generation.current)setError(e.message);});
    },160);
    return ()=>{active=false;clearTimeout(timer);};
  },[api,projectId,bankId,bank?.revision,bank?.document_sha256,frame,cameraId]);
  useEffect(()=>{
    if(!playing)return;
    const timer=setInterval(()=>setFrame(n=>(n+12)%FRAMES),500);
    return ()=>clearInterval(timer);
  },[playing]);
  useEffect(()=>{
    if(!ticket||!native)return;
    let alive=true,pending=false;
    const poll=async()=>{
      if(!alive||pending)return;
      pending=true;
      try{
        const state=await native.film01r_render_poll(ticket);
        if(!alive)return;
        if(state?.format!=='nvp.film01r.native_selected_frame_status.v1'||
           state.ticket_id!==ticket)
          throw Error('Native selected-view job receipt lost its identity');
        setRenderStatus(state);
        if(['REVERIFIED_SELECTED_FRAMES','NATIVE_FAILED_NEEDS_INSPECTION',
          'DENIED_OR_RECOVERY_REQUIRED','RECOVERY_REQUIRED'].includes(state.state))
          setTicket(null);
      }catch(e){if(alive){setError(e.message);setTicket(null);}}
      finally{pending=false;}
    };
    poll();const timer=setInterval(poll,1300);
    return ()=>{alive=false;clearInterval(timer);};
  },[ticket,native]);
  const modify=next=>{
    if(!exactCuts(next,cameras.map(x=>x.camera_id)))
      throw Error('Cuts must cover all 720 original frames with valid cameras');
    undo.current=[...undo.current.slice(-24),cuts.map(x=>({...x}))];
    setCuts(next);setSavedEdit(null);setEstimate(null);
  };
  const split=()=>{
    try{
      if(cuts.length>=96)throw Error('Maximum 96 cuts per film');
      const at=cuts.findIndex(c=>c.edit_in_frame<frame&&frame<c.edit_out_frame);
      if(at<0)throw Error('Position playhead inside a shot before splitting');
      const shot=cuts[at];
      modify([...cuts.slice(0,at),
        {...shot,edit_out_frame:frame,source_out_frame:frame},
        {...shot,edit_in_frame:frame,source_in_frame:frame},
        ...cuts.slice(at+1)]);
    }catch(e){setError(e.message);}
  };
  const useCamera=()=>{
    try{modify(cuts.map(x=>x===selectedCut?{...x,camera_id:cameraId}:x));}
    catch(e){setError(e.message);}
  };
  const merge=()=>{
    try{
      const at=cuts.indexOf(selectedCut);
      if(at<1)throw Error('Choose a shot after the first cut');
      modify([...cuts.slice(0,at-1),
        {...cuts[at-1],source_out_frame:cuts[at].source_out_frame,
          edit_out_frame:cuts[at].edit_out_frame},...cuts.slice(at+1)]);
    }catch(e){setError(e.message);}
  };
  const doNative=async fn=>{
    setBusy(true);setError('');setNotice('');
    try{await fn();}
    catch(e){setError(e.message||String(e));}
    finally{setBusy(false);}
  };
  const saveEdit=()=>doNative(async()=>{
    if(!exactCuts(cuts,cameras.map(x=>x.camera_id)))
      throw Error('Original film edit has gaps or invalid source cameras');
    const old=catalog.edits.find(x=>x.edit_id===editId);
    const result=await native.film01r_save_edit({
      project_id:projectId,edit_id,expected_revision:old?.revision||0,
      camera_bank_id:bankId,camera_bank_revision:bank.revision,cuts});
    if(result?.format!=='nvp.film01r.authenticated_source_edit_saved.v1'||
       result.edit_id!==editId||result.original_performance_modified!==false)
      throw Error('Native edit did not preserve the original Take');
    const fresh=await reload();
    const verified=fresh.edits.find(x=>x.edit_id===editId&&
      x.document_sha256===result.document_sha256&&x.revision===result.revision);
    if(!verified)throw Error('Saved source edit did not reopen from FilmIndex');
    setSavedEdit(verified);setNotice('Native-approved source edit revision '+verified.revision+' saved.');
  });
  const makeBank=()=>doNative(async()=>{
    const camera={
      camera_id:'CameraA',setup:'Establishing',framing:'wide',
      position_m:[0,0,12],rotation_euler_deg:[0,0,0],
      focal_length_mm:35,focus_distance_m:12,
      clip_range_m:[.01,10000],move_keys:[],camera_ray_exclusions:[]};
    const result=await native.film01r_create_bank({
      project_id:projectId,camera_bank_id:newBankId,
      world_take_id:takeId,cameras:[camera]});
    if(result?.format!=='nvp.film01r.authenticated_camera_bank_saved.v1')
      throw Error('No original director rig creation receipt');
    await reload();setBankId(newBankId);setNotice('Native original camera bank created.');
  });
  const addCamera=()=>doNative(async()=>{
    const camera={...selectedCamera,camera_id:newCamId,setup:'New angle',
      position_m:[selectedCamera.position_m[0]+2,
        selectedCamera.position_m[1],selectedCamera.position_m[2]]};
    const result=await native.film01r_revise_bank({
      project_id:projectId,camera_bank_id:bankId,
      expected_revision:bank.revision,changes:[{op:'add',camera}]});
    if(result?.revision!==bank.revision+1)
      throw Error('Camera was not saved as a new native revision');
    await reload();setCameraId(newCamId);
    setNotice('Virtual camera added without rerecording any actors.');
  });
  const removeCamera=()=>doNative(async()=>{
    const result=await native.film01r_revise_bank({
      project_id:projectId,camera_bank_id:bankId,
      expected_revision:bank.revision,
      changes:[{op:'remove',camera_id:cameraId}]});
    if(result?.revision!==bank.revision+1)
      throw Error('Camera removal did not persist as a new revision');
    await reload();setNotice('Camera removed from latest rig; history retained.');
  });
  const previewBatch=()=>doNative(async()=>{
    const report=await api('/system/shot-batch-estimate','POST',{
      viewpoint_count:cuts.length,selected_final_shots:cuts.length,
      shots_per_batch:groupSize==='auto'?null:Number(groupSize),
      parallel_worker_limit:parallel==='auto'?null:Number(parallel),
      renderer:'cpu',gpu_device_id:null});
    if(report?.format!=='nvp.film01s.read_only_batch_capacity_preview.v1'||
       report.render_jobs_started!==0)
      throw Error('NVP source-independent batch estimate failed');
    setEstimate(report);
  });
  const renderNext=()=>doNative(async()=>{
    const receipt=await native.film01r_render_next({
      project_id:projectId,edit_id:savedEdit.edit_id,
      revision:savedEdit.revision,render_quality:quality,
      shots_per_batch:groupSize==='auto'?null:Number(groupSize),
      parallel_worker_limit:parallel==='auto'?null:Number(parallel)});
    if(receipt?.format!=='nvp.film01r.native_selected_frame_ticket.v1')
      throw Error('Native render request lacked reviewed worker receipt');
    setRenderStatus(receipt);
    setTicket(receipt.state==='QUEUED_NATIVE_APPROVAL'?receipt.ticket_id:null);
  });

  return <section className="card" aria-label="Data-first director editor">
    <h2>Direct the data · virtual camera film editor</h2>
    <p className="fineprint">One original scene performance, unlimited cinematic
      viewpoints in principle, and only the selected views rendered for the
      finished movie. Scrub the source, make camera cuts, then go low-fi → hi-fi.</p>
    {!banks.length&&<p role="status">No native director camera bank in this film.
      Freeze an original OpenUSD world Take first.</p>}
    {!banks.length&&catalog?.original_world_takes?.length>0&&<div className="actions">
      <label>Frozen original Take<select aria-label="Original world Take"
        value={takeId} onChange={e=>setTakeId(e.target.value)}>
        {catalog.original_world_takes.map(x=><option key={x.world_take_id}
          value={x.world_take_id}>{x.world_take_id}</option>)}</select></label>
      <label>Camera rig ID<input aria-label="New camera rig ID" value={newBankId}
        onChange={e=>setNewBankId(e.target.value)}/></label>
      <button disabled={!nativeReady||busy} onClick={makeBank}>
        Native approve first virtual camera</button>
    </div>}
    {bank&&<div className="actions">
      <label>Original virtual camera rig<select aria-label="Original virtual camera bank"
        value={bankId} onChange={e=>setBankId(e.target.value)}>
        {banks.map(x=><option key={x.camera_bank_id}
          value={x.camera_bank_id}>{x.camera_bank_id} · r{x.revision}</option>)}
      </select></label>
      <label>Perspective<select aria-label="Virtual viewpoint" value={cameraId}
        onChange={e=>setCameraId(e.target.value)}>
        {cameras.map(x=><option key={x.camera_id} value={x.camera_id}>
          {x.camera_id} · {x.framing}</option>)}</select></label>
      <button onClick={()=>setOrbit(x=>!x)}>
        {orbit?'Lock authored viewpoint':'Orbit source geometry'}</button>
    </div>}
    {bank&&<p className="fineprint">Frozen actor-performance SHA:
      <code>{bank.original_performance_sha256}</code>. Source camera revision:
      <code>{bank.document_sha256}</code>.</p>}
    <SourceUSDViewport snapshot={snapshot} orbit={orbit}/>
    {bank&&<div className="actions">
      <label>Original Film Time frame
        <input aria-label="Film frame scrubber" type="range" min="0" max="719"
          value={frame} onChange={e=>setFrame(Number(e.target.value))}/></label>
      <span>{frame}/719 · {(frame/24).toFixed(2)}s</span>
      <button onClick={()=>setPlaying(x=>!x)}>
        {playing?'Pause source preview':'Play low-fi · 2fps'}</button>
    </div>}
    {bank&&<div>
      <h3>Non-destructive 30-second edit</h3>
      <div className="actions">
        <button onClick={split}>Split at playhead</button>
        <button onClick={useCamera}>Use selected camera for this shot</button>
        <button disabled={cuts.length<2} onClick={merge}>Merge with previous</button>
        <button disabled={!undo.current.length} onClick={()=>{
          const previous=undo.current.pop();
          if(previous){setCuts(previous);setSavedEdit(null);}
        }}>Undo draft cut</button>
      </div>
      <div aria-label="Camera cut timeline"
        style={{display:'flex',minHeight:48,border:'1px solid #536070',borderRadius:6}}>
        {cuts.map((cut,i)=><button key={i}
          aria-label={'Shot '+(i+1)+' using '+cut.camera_id}
          onClick={()=>{setFrame(cut.edit_in_frame);setCameraId(cut.camera_id);}}
          style={{flex:String(cut.edit_out_frame-cut.edit_in_frame)+' 1 0',
            minWidth:0,overflow:'hidden',color:'white',fontSize:11,
            background:selectedCut===cut?'#315f7b':'#273640'}}>
          {cut.camera_id}</button>)}
      </div>
      <p className="fineprint">Shot at playhead: {selectedCut?.camera_id||'none'}.
        {cuts.length} cuts cover exactly 720 frames. Nothing here changes
        an ActorID, original performance, or soundtrack.</p>
      <div className="actions">
        <label>Editable source edit ID
          <input aria-label="Original edit ID" value={editId}
            onChange={e=>{setEditId(e.target.value);setSavedEdit(null);}}/>
        </label>
        <button disabled={!nativeReady||busy||!!ticket||!cuts.length}
          onClick={saveEdit}>Native approve &amp; save edit</button>
      </div>
      {savedEdit&&<p role="status">Source edit saved:
        {savedEdit.edit_id} · revision {savedEdit.revision} ·
        {savedEdit.document_sha256}</p>}
    </div>}
    {bank&&<div>
      <h3>Virtual camera collection</h3>
      <div className="actions">
        <label>Extra camera ID<input aria-label="New virtual camera ID"
          value={newCamId} onChange={e=>setNewCamId(e.target.value)}/></label>
        <button disabled={!nativeReady||busy||!selectedCamera}
          onClick={addCamera}>Native approve additional viewpoint</button>
        <button disabled={!nativeReady||busy||cameras.length<2}
          onClick={removeCamera}>Native remove viewpoint</button>
      </div>
      <p className="fineprint">New viewpoints clone the selected optics and
        move two meters sideways; native approval preserves old revisions.
        They do not recapture the original scene.</p>
    </div>}
    {bank&&<div>
      <h3>Render only what the audience sees</h3>
      <div className="actions">
        <label>Reviewed Cycles quality<select aria-label="Original film render quality"
          value={quality} onChange={e=>setQuality(e.target.value)}>
          <option value="technical_smoke">320×180 / 8 · source smoke</option>
          <option value="draft_360p">640×360 / 16 · draft</option>
          <option value="final_720p">1280×720 / 48 · candidate final</option>
          <option value="final_1080p">1920×1080 / 96 · candidate final</option>
        </select></label>
        <label>Shots per batch<select aria-label="Director shots per batch"
          value={groupSize} onChange={e=>setGroupSize(e.target.value)}>
          <option value="auto">Auto</option>
          {[1,2,3,4,6,8,12,16,24,32,48,64].map(n=>
            <option value={String(n)} key={n}>{n}</option>)}</select></label>
        <label>Maximum parallel workers<select aria-label="Max director render workers"
          value={parallel} onChange={e=>setParallel(e.target.value)}>
          <option value="auto">Auto</option>
          {[1,2,3,4,6,8,12,16,24,32].map(n=>
            <option value={String(n)} key={n}>{n}</option>)}</select></label>
      </div>
      <div className="actions">
        <button onClick={previewBatch} disabled={busy}>Estimate batches</button>
        <button disabled={!nativeReady||busy||!savedEdit||!!ticket}
          onClick={renderNext}>Native approve next 8 selected frames</button>
      </div>
      {estimate&&<p role="status">Adaptive batch estimate:
        {estimate.shots_per_batch} shots per group,
        {estimate.safe_parallel_workers?.hifi?.safe_workers??0}
        safe concurrent hi-fi workers measured now.</p>}
      {renderStatus&&<p role="status">Native render: {renderStatus.state}.
        {renderStatus.native_result?.start_frame!==undefined&&
          ' Independently checked frames '+
          renderStatus.native_result.start_frame+'–'+
          (renderStatus.native_result.start_frame+7)+'.'}
        {renderStatus.reason||''}</p>}
      <p className="fineprint">The installed NVP host authorizes each exact
        original-source Blender job. Runtime currently executes one chunk per
        approval. Estimated batches are not executable permissions. Full
        720-frame picture/audio conform and director review remain open.</p>
    </div>}
    {!nativeReady&&<p role="status">Browser source inspection only:
      approved camera/edit writes and protected rendering require the installed
      NVP WebView and real OS director confirmation.</p>}
    {notice&&<p role="status">{notice}</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}