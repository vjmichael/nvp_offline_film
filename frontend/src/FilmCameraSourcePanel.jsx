import React,{useEffect,useMemo,useRef,useState} from 'react';
import CameraLensWorkbench from './CameraLensWorkbench.jsx';

// SLATE-08: the ordinary NVP planning UI only reads real versioned scene
// sources. Do not let browser-only actions create render approvals or commit
// a Take/SHOT. Such actions must be wired by an authenticated native host.
export default function FilmCameraSourcePanel({projectId,api,nativeBridge=null}){
  const [scenes,setScenes]=useState([]);
  const [sceneId,setSceneId]=useState('');
  const [cameraPath,setCameraPath]=useState('');
  const [tickDraft,setTickDraft]=useState('0');
  const [tick,setTick]=useState(0);
  const [snapshot,setSnapshot]=useState(null);
  const [loadingList,setLoadingList]=useState(true);
  const [loadingPose,setLoadingPose]=useState(false);
  const [error,setError]=useState('');
  const [truncated,setTruncated]=useState(false);
  const [native,setNative]=useState(nativeBridge);
  const [nativeReady,setNativeReady]=useState(Boolean(nativeBridge));
  const [renderTicket,setRenderTicket]=useState(null);
  const [renderResult,setRenderResult]=useState(null);
  const [renderError,setRenderError]=useState('');
  const activeTicket=useRef(null);
  useEffect(()=>{
    let active=true;
    if(!native){setNativeReady(false);return ()=>{active=false;};}
    // Native WebView2 owns renderer discovery; ordinary React must never
    // infer an executable path, permission receipt, or worker availability.
    if(typeof native.camera_render_capabilities!=='function'){
      setNativeReady(Boolean(nativeBridge));
      return ()=>{active=false;};
    }
    setNativeReady(false);
    Promise.resolve(native.camera_render_capabilities())
      .then(result=>{
        if(active)setNativeReady(
          result?.format==='nvp.camera.desktop_capability.v1' &&
          result?.native_window===true &&
          result?.blender_discovered===true &&
          result?.supports_approved_still===true);
      })
      .catch(()=>{if(active)setNativeReady(false);});
    return ()=>{active=false;};
  },[native,nativeBridge]);
  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    function installedBridge(){
      const api=window.pywebview?.api;
      if(api && ['request_camera_still','poll_camera_still',
                 'cancel_camera_still'].every(name=>typeof api[name]==='function'))
        setNative(api);
    }
    window.addEventListener('pywebviewready',installedBridge);
    installedBridge();
    return ()=>window.removeEventListener('pywebviewready',installedBridge);
  },[nativeBridge]);
  const scene=useMemo(()=>scenes.find(s=>s.scene_id===sceneId)||null,
    [scenes,sceneId]);

  useEffect(()=>{
    let active=true;
    setScenes([]);setSceneId('');setCameraPath('');
    setSnapshot(null);setError('');setLoadingList(true);
    activeTicket.current=null;setRenderTicket(null);setRenderResult(null);
    api('/projects/'+encodeURIComponent(projectId)+'/film/camera-scenes')
      .then(result=>{
        if(!active)return;
        if(result?.format!=='nvp.slate08.camera_source_list.v1'
            ||result.project_id!==projectId
            ||!Array.isArray(result.scenes)){
          throw new Error('Camera source listing failed identity verification');
        }
        setScenes(result.scenes);
        setTruncated(result.truncated===true);
        setSceneId(result.scenes[0]?.scene_id||'');
      })
      .catch(err=>{if(active)setError(err.message);})
      .finally(()=>{if(active)setLoadingList(false);});
    return ()=>{active=false;};
  },[api,projectId]);

  useEffect(()=>{
    setCameraPath(scene?.cameras?.[0]?.path||'');
    setSnapshot(null);
    activeTicket.current=null;setRenderTicket(null);setRenderResult(null);
    setTick(0);setTickDraft('0');
  },[sceneId,scenes]);

  useEffect(()=>{
    let active=true;
    setSnapshot(null);
    activeTicket.current=null;setRenderTicket(null);setRenderResult(null);
    if(!scene||!cameraPath)return ()=>{active=false;};
    setLoadingPose(true);setError('');
    const params=new URLSearchParams({
      revision:String(scene.revision),source_tick:String(tick),
      camera_path:cameraPath,
    });
    api('/projects/'+encodeURIComponent(projectId)+
      '/film/camera-scenes/'+encodeURIComponent(scene.scene_id)+
      '/snapshot?'+params)
      .then(data=>{
        if(!active)return;
        if(data?.format!=='nvp.camera.lens_workbench.v1'
          ||data.scene_document_sha256!==scene.document_sha256
          ||data.scene_id!==scene.scene_id
          ||data.scene_revision!==scene.revision
          ||data.source_tick!==tick ||data.camera_path!==cameraPath)
          throw new Error('Camera snapshot no longer matches the selected source');
        setSnapshot(data);
      })
      .catch(err=>{if(active)setError(err.message);})
      .finally(()=>{if(active)setLoadingPose(false);});
    return ()=>{active=false;};
  },[api,projectId,scene,cameraPath,tick]);

  useEffect(()=>{
    if(!native||!renderTicket)return;
    let active=true;
    let pending=false;
    async function poll(){
      if(pending||!active)return;
      pending=true;
      try{
        const answer=await native.poll_camera_still(renderTicket);
        if(!active||activeTicket.current!==renderTicket)return;
        if(answer.status==='READY'){
          if(answer.format!=='nvp.camera.desktop_delivery.v1' ||
             answer.source_modified!==false ||
             answer.frozen_take_created!==false ||
             answer.film_master_approved!==false)
            throw new Error('Desktop verified still identity or source custody failed');
          setRenderResult(answer);
          setRenderTicket(null);
        }else if(answer.status==='RECOVERY_REQUIRED'||answer.status==='FAILED'){
          setRenderError(answer.status==='RECOVERY_REQUIRED'
            ?'Native render needs worker recovery before a still can be accepted.'
            :'Native render did not complete.');
          setRenderResult({status:'FAILED'});
          setRenderTicket(null);
        }else if(answer.status!=='QUEUED'){
          throw new Error('Unsupported native render state');
        }
      }catch(err){
        if(active&&activeTicket.current===renderTicket){
          setRenderError(err.message);setRenderTicket(null);
          setRenderResult({status:'FAILED'});
        }
      }finally{pending=false;}
    }
    poll();
    const interval=setInterval(poll,700);
    return ()=>{active=false;clearInterval(interval);};
  },[native,renderTicket]);

  async function requestNativeStill(payload){
    if(!native||!nativeReady||renderTicket)return;
    setRenderError('');setRenderResult({status:'QUEUED'});
    try{
      const result=await native.request_camera_still({project_id:projectId,...payload});
      if(result.status==='DENIED'){
        setRenderResult(null);
        setRenderError('Native camera render was not approved.');
        return;
      }
      if(result.format!=='nvp.camera.desktop_ticket.v1' ||
          !['QUEUED','CACHE_HIT'].includes(result.status) ||
          typeof result.ticket_id!=='string' ||
          result.scene_document_sha256!==payload.source_scene_document_sha256 ||
          result.camera_path!==payload.camera_path ||
          result.source_tick!==payload.source_tick){
        throw new Error('Desktop did not return an exact source-scoped render ticket');
      }
      activeTicket.current=result.ticket_id;
      setRenderTicket(result.ticket_id);
    }catch(err){
      setRenderError(err.message);setRenderResult({status:'FAILED'});
    }
  }
  async function cancelNativeStill(){
    if(!native||!renderTicket)return;
    try{
      const reply=await native.cancel_camera_still(renderTicket);
      if(reply.status==='DENIED')return;
      if(reply.status!=='CANCELLED_QUEUED'&&reply.status!=='CANCEL_REQUESTED')
        throw new Error('Unexpected native worker cancellation result');
      activeTicket.current=null;
      setRenderTicket(null);
      setRenderResult({status:'FAILED'});
      setRenderError(reply.status==='CANCEL_REQUESTED'
        ?'Cancellation requested. Native worker termination must still be verified.'
        :'Queued render cancelled without starting Blender.');
    }catch(err){setRenderError(err.message);}
  }

  function selectScene(id) {
    setSceneId(id);setSnapshot(null);
  }
  function selectCamera(path) {
    if(!scene?.cameras?.some(c=>c.path===path))return;
    setCameraPath(path);setSnapshot(null);
  }
  function evaluateTick(event) {
    event.preventDefault();
    const number=Number(tickDraft);
    if(!Number.isSafeInteger(number)||number<0||number>1000000000){
      setError('Film Time must be an integer between 0 and 1,000,000,000 ticks.');
      return;
    }
    setError('');
    setSnapshot(null);
    activeTicket.current=null;setRenderTicket(null);setRenderResult(null);
    setTick(number);
  }
  return <section className="card" aria-label="Film source camera">
    <h2>Virtual camera · source scene</h2>
    <p className="fineprint">Choose an authored OpenUSD scene and camera. The source
      remains immutable; lens changes update only an instant framing diagram.</p>
    {loadingList&&<p role="status">Loading published film scenes…</p>}
    {!loadingList && scenes.length===0 &&
      <p>No native OpenUSD camera source is published in this film yet.
         Stage and publish a native scene before testing lenses.</p>}
    {truncated&&<p className="fineprint">Showing a bounded set of source scenes.</p>}
    {scenes.length>0&&<div className="actions">
      <label>Published scene
        <select aria-label="Published film scene" value={sceneId}
          onChange={e=>selectScene(e.target.value)}>
          {scenes.map(s=><option key={s.scene_id} value={s.scene_id}>
            {s.scene_id} · revision {s.revision}
          </option>)}
        </select>
      </label>
      <label>Source camera
        <select aria-label="Published source camera" value={cameraPath}
          onChange={e=>selectCamera(e.target.value)}>
          {(scene?.cameras||[]).map(c=><option key={c.path} value={c.path}>
            {c.label||c.path}
          </option>)}
        </select>
      </label>
      <form onSubmit={evaluateTick}>
        <label>Film Time (source ticks)
          <input type="number" min="0" max="1000000000" step="1"
            aria-label="Source Film Time" value={tickDraft}
            onChange={e=>setTickDraft(e.target.value)}/>
        </label>
        <button type="submit">Inspect source moment</button>
      </form>
    </div>}
    {error&&<p role="alert">{error}</p>}
    {loadingPose&&<p role="status">Reading selected source pose…</p>}
    {renderError&&<p role="alert">{renderError}</p>}
    {scene&&<CameraLensWorkbench key={scene.scene_id+':'+cameraPath}
      sceneSnapshot={snapshot}
      onRequestRenderedPreview={nativeReady?requestNativeStill:null}
      onCancelRenderedPreview={nativeReady?cancelNativeStill:null}
      renderBusy={Boolean(renderTicket)}
      renderResult={renderResult}/>}
    {scene&&<p className="fineprint">
      The instant projection uses camera-space markers, not actual rendered
      character pixels. {nativeReady
        ? 'Verified native stills require a separate desktop confirmation. Saving an approved lens preset and applying optics to a frozen shot are not wired yet.'
        : native
          ? 'A trusted native Blender executable has not been discovered. Real stills are disabled; source scene and lens controls remain available.'
          : 'Native Blender still rendering requires the installed desktop application. Preset and shot approval are not exposed to ordinary browsers.'}
    </p>}
  </section>;
