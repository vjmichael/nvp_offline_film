import React,{useEffect,useState} from 'react';

// P1-B: creator-selected actual registered GLB to authoritative FilmIndex/USD.
// No browser URI, local executable path, GLB bytes, or approval token crosses IPC.
const IDENT=/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/;
const initial={actor_id:'',character_asset_id:'',position:'0,0,0',
  motion_joint:'',travel:'0',face_target:'',face_strength:'0'};

export default function ActorSceneCastingPanel({
    projectId,native,actorCatalog=[],sourceRevision=0,onScenePublished=()=>{}}){
  const ready=Boolean(native&&typeof native.data_av_actor_asset_catalog==='function'&&
    typeof native.data_av_actor_scene_cast==='function');
  const [assets,setAssets]=useState([]);
  const [unsupported,setUnsupported]=useState([]);
  const [sceneId,setSceneId]=useState('ActorSourceScene001');
  const [cameraHeight,setCameraHeight]=useState('8');
  const [rows,setRows]=useState([{...initial}]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [receipt,setReceipt]=useState(null);

  useEffect(()=>{
    let alive=true;
    setAssets([]);setUnsupported([]);setReceipt(null);setError('');
    setRows([{...initial}]);
    if(!ready||!projectId)return;
    Promise.resolve(native.data_av_actor_asset_catalog(projectId)).then(result=>{
      if(!alive)return;
      if(result?.format!=='nvp.p1bc.native_original_character_assets.v1'||
         result.project_id!==projectId||
         result.source_bytes_modified!==false||
         result.redistribution_rights_independently_verified!==false||
         !Array.isArray(result.assets)||!Array.isArray(result.unsupported))
        throw Error('Original registered character inventory was not source-verified');
      setAssets(result.assets);setUnsupported(result.unsupported);
    }).catch(e=>{if(alive)setError(e.message)});
    return ()=>{alive=false};
  },[ready,native,projectId,sourceRevision]);

  function replaceRow(i,field,value){
    setRows(old=>old.map((x,n)=>n===i?{...x,[field]:value}:x));
    setReceipt(null);
  }

  function compile(){
    if(!IDENT.test(sceneId))throw Error('Choose a unique source scene identity.');
    const height=Number(cameraHeight);
    if(!Number.isFinite(height)||height<2||height>30)
      throw Error('Camera height must be between 2 and 30 metres.');
    if(!rows.length||rows.length>8)
      throw Error('A scene requires one to eight genuine skinned actors.');
    const selected=new Set();
    const cast=rows.map(item=>{
      if(!actorCatalog.some(x=>x.actor_id===item.actor_id))
        throw Error('Choose a registered original ActorID for every character.');
      if(selected.has(item.actor_id))
        throw Error('Each ActorID may occur only once in one source scene.');
      selected.add(item.actor_id);
      const glb=assets.find(x=>x.character_asset_id===item.character_asset_id);
      if(!glb)throw Error('Choose a verified registered original rigged GLB.');
      const xyz=item.position.split(',').map(x=>Number(x.trim()));
      if(xyz.length!==3||xyz.some(v=>!Number.isFinite(v)||Math.abs(v)>100))
        throw Error('Stage positions must be three bounded metre coordinates.');
      const travel=Number(item.travel);
      if(!Number.isFinite(travel)||Math.abs(travel)>0.5)
        throw Error('Rig motion must be between -0.5 and 0.5 metres.');
      if(item.motion_joint&&!glb.joints.includes(item.motion_joint))
        throw Error('Acting motion joint is not in the original GLB rig.');
      const faceStrength=Number(item.face_strength);
      if(!Number.isFinite(faceStrength)||faceStrength<0||faceStrength>1||
         (item.face_target&&!glb.facial_targets?.includes(item.face_target))||
         (!item.face_target&&faceStrength!==0))
        throw Error('Facial performance must use original imported GLB morphs.');
      return {actor_id:item.actor_id,
        character_asset_id:item.character_asset_id,
        position:xyz,motion_joint:item.motion_joint||null,travel,
        face_target:item.face_target||null,face_strength:faceStrength};
    });
    return {project_id:projectId,scene_id:sceneId,camera_height:height,cast};
  }

  async function publish(){
    if(!ready||busy)return;
    setError('');setReceipt(null);setBusy(true);
    try{
      const request=compile();
      const response=await native.data_av_actor_scene_cast(request);
      if(response?.format!=='nvp.p1bc.native_actor_scene_cast_receipt.v1'||
         response.status!=='AUTHORITATIVE_ACTOR_SCENE_PUBLISHED'||
         response.scene_id!==request.scene_id||
         response.scene_revision!==1||
         response.original_sources_modified!==false||
         response.picture_rendered!==false||
         response.imported_glb_skins!==request.cast.length||
         response.director_authorized!==true)
        throw Error('Native original scene casting receipt is not authoritative');
      setReceipt(response);
      onScenePublished();
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  return <section className="card" aria-label="Native original GLB scene casting">
    <h3>Cast real rigged characters into a 3D source scene</h3>
    <p className="fineprint">Select creator-registered GLB source assets and
      their canonical ActorIDs. NVP verifies original geometry, weighted bones,
      PBR, source SHA and FilmIndex ancestry before publishing a fresh
      OpenUSD scene. Your approval appears in the native OS window.
      No original Digital Take is rewritten.</p>
    {!ready&&<p role="status">Available only in trusted installed NVP.</p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">{assets.length} supported original GLB sources;
      {' '}{unsupported.length} require a specialist rig/material converter.</p>
    {unsupported.length>0&&<p className="fineprint">
      Unsupported sources: {unsupported.map(x=>x.character_asset_id).join(', ')}.
      No proxy character will be substituted.</p>}
    <label>Unique new OpenUSD source scene identity
      <input value={sceneId} maxLength={80} disabled={busy}
        onChange={e=>{setSceneId(e.target.value);setReceipt(null)}}/>
    </label>
    <label>Camera height in metres
      <input value={cameraHeight} inputMode="decimal" disabled={busy}
        onChange={e=>setCameraHeight(e.target.value)}/>
    </label>
    {rows.map((row,i)=>{
      const asset=assets.find(x=>x.character_asset_id===row.character_asset_id);
      return <fieldset key={i}>
        <legend>Actor {i+1} · actual GLB skin and motion</legend>
        <label>Cast ActorID {i+1}
          <select value={row.actor_id} disabled={busy}
            onChange={e=>replaceRow(i,'actor_id',e.target.value)}>
            <option value="">Choose a registered ActorID</option>
            {actorCatalog.map(x=><option key={x.actor_id} value={x.actor_id}>
              {x.actor_id} · {x.display_name}</option>)}
          </select>
        </label>
        <label>Imported GLB source {i+1}
          <select value={row.character_asset_id} disabled={busy}
            onChange={e=>setRows(old=>old.map((x,n)=>n===i
              ?{...x,character_asset_id:e.target.value,
                 motion_joint:'',face_target:'',face_strength:'0'}:x))}>
            <option value="">Choose imported, source-verified GLB</option>
            {assets.map(x=><option key={x.character_asset_id}
              value={x.character_asset_id}>
              {x.character_asset_id} · {x.vertex_count} vertices ·
              {' '}{x.joint_count} joints</option>)}
          </select>
        </label>
        <label>Original 3D position X,Y,Z (metres) {i+1}
          <input value={row.position} disabled={busy}
            onChange={e=>replaceRow(i,'position',e.target.value)}/>
        </label>
        <label>Authentic joint to animate {i+1}
          <select value={row.motion_joint} disabled={busy||!asset}
            onChange={e=>replaceRow(i,'motion_joint',e.target.value)}>
            <option value="">Keep source GLB at rest</option>
            {(asset?.joints||[]).map(x=>
              <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label>Original GLB facial morph {i+1}
          <select value={row.face_target} disabled={busy||!asset}
            onChange={e=>setRows(old=>old.map((x,n)=>n===i
              ?{...x,face_target:e.target.value,
                face_strength:e.target.value?x.face_strength:'0'}:x))}>
            <option value="">No facial expression</option>
            {(asset?.facial_targets||[]).map(x=>
              <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label>Author facial strength 0..1 {i+1}
          <input value={row.face_strength} inputMode="decimal"
            disabled={busy||!row.face_target}
            onChange={e=>replaceRow(i,'face_strength',e.target.value)}/>
        </label>
        <label>Director-authored joint X travel (metres) {i+1}
          <input value={row.travel} inputMode="decimal" disabled={busy}
            onChange={e=>replaceRow(i,'travel',e.target.value)}/>
        </label>
        <button disabled={busy||rows.length===1}
          onClick={()=>setRows(old=>old.filter((_,n)=>n!==i))}>
          Remove actor {i+1}</button>
      </fieldset>;
    })}
    <button disabled={!ready||busy||rows.length>=8}
      onClick={()=>setRows(old=>[...old,{...initial}])}>
      Add another original actor</button>
    <button disabled={!ready||busy||!assets.length||!actorCatalog.length}
      onClick={publish}>Ask native director to publish exact 3D cast</button>
    {receipt&&<p role="status">New native OpenUSD source scene
      {' '}{receipt.scene_id} · SHA {receipt.scene_document_sha256.slice(0,16)}…
      {' '}· {receipt.imported_glb_skins} original rigged characters.
      Compose a camera timeline and freeze an original Take separately.</p>}
    <p className="fineprint">Original GLB rights remain creator-declared,
      not independently cleared for distribution. Joint travel is a
      director-authored test gesture, not captured actor motion.
      Facial morph deltas are real original GLB geometry, with explicit
      creator keyframes rather than inferred speech phonemes.
      Complex glTF materials and incompatible rigs fail closed.</p>
  </section>;
}
