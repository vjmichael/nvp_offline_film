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
  const native=()=>window.pywebview?.api;
  const currentScene=catalog?.scenes?.find(x=>x.id===sceneId)||null;
  const currentTake=catalog?.takes?.find(x=>x.id===takeId)||null;
  const currentTimeline=catalog?.timelines?.find(x=>x.id===timelineId)||null;
  const scene=(kind==='take'||kind==='camera_sequence')?currentScene:
    (currentTake?.data?.scene_id
      ?catalog?.scenes?.find(x=>x.id===currentTake.data.scene_id)||null
      :currentScene);
  const matchingRoles=scene?.data?.prim_roles||{};
  const paths=Object.entries(matchingRoles).filter(([path,role])=>
    (kind==='camera'||kind==='camera_sequence')?role==='camera':
    kind==='lighting'?role==='light':
    kind==='blocking'?(role==='actor'||role==='prop'):false);
  const selectedOriginal=sourceFor(kind,kind==='take'||kind==='camera_sequence'?currentScene:scene,currentTake);
  const fingerprint=selectedOriginal
    ?[projectId,kind,selectedOriginal.id,selectedOriginal.revision,
      selectedOriginal.sha256].join('|'):null;
  const usableImpact=impact?.fingerprint===fingerprint &&
    impact?.data?.status==='READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT' &&
    impact?.data?.indexed_downstream_truncated===false;
  useEffect(()=>{setImpact(null)},[fingerprint]);
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
        setProblem('');
      }catch(e){if(live)setProblem(errorText(e))}
    }
    void load();
    window.addEventListener('pywebviewready',load);
    return ()=>{live=false;window.removeEventListener('pywebviewready',load)};
  },[projectId]);
  const refresh=async()=>{
    const data=await native().wo6_source_catalog(projectId);
    setCatalog(data);
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
    const data=await native().wo6_source_impact({
      project_id:projectId,source_id:selectedOriginal.id,
      source_revision:selectedOriginal.revision,
      source_sha256:selectedOriginal.sha256,
      change_kind:selectedOriginal.change,
    });
    if(!data?.preview_sha256)throw new Error('Native source impact proof is incomplete');
    setImpact({fingerprint,data});
    setReceipt(null);
  });
  function exactInteger(text,label){
    if(!/^(0|[1-9][0-9]{0,14})$/.test(text))
      throw new Error(label+' requires canonical nonnegative Film Time ticks');
    const number=Number(text);
    if(!Number.isSafeInteger(number))throw new Error(label+' exceeds exact JS integer');
    return number;
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
        reason:'Director deliberately approved this isolated shot change',
      });
    }
    setReceipt(response);
    setImpact(null);
    await refresh();
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
    {!catalog&&<p role="status">Checking the installed native host and FilmIndex…</p>}
    <label>Operation<select value={kind} disabled={busy}
      onChange={e=>{setKind(e.target.value);setValue(e.target.value==='blocking'?'0,0,0':'50');setSelectedPath('');setImpact(null)}}>
      {ACTIONS.map(([id,label])=><option key={id} value={id}>{label}</option>)}
    </select></label>
    <label>Original scene<select value={sceneId} disabled={busy} onChange={e=>{setSceneId(e.target.value);setImpact(null)}}>
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
      <input disabled={busy} value={value} onChange={e=>setValue(e.target.value)}/>
    </label>}
    {kind!=='color'&&kind!=='take'&&<label>End Film Time tick<input
      value={endTick} disabled={busy} onChange={e=>setEndTick(e.target.value)}/></label>}
    {kind!=='color'&&kind!=='take'&&kind!=='camera_sequence'&&<label>Start tick<input
      value={startTick} disabled={busy} onChange={e=>setStartTick(e.target.value)}/></label>}
    <label>New immutable object ID<input value={newId} disabled={busy}
      onChange={e=>setNewId(e.target.value)} placeholder="director_new_shot_001"/></label>
    <div className="actions">
      <button type="button" className="secondary" disabled={busy||!selectedOriginal} onClick={preview}>
        Inspect source impact</button>
      <button type="button" className="primary" disabled={busy||!usableImpact||!newId} onClick={submit}>
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
