import React,{useEffect,useMemo,useState} from 'react';
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
  // DA-06: retired Blender still IPC is never discovered or invoked here.
  // Native Film Time/scene inspection remains read-only until the data-first
  // live scene renderer is independently accepted.
  const scene=useMemo(()=>scenes.find(s=>s.scene_id===sceneId)||null,
    [scenes,sceneId]);

  useEffect(()=>{
    let active=true;
    setScenes([]);setSceneId('');setCameraPath('');
    setSnapshot(null);setError('');setLoadingList(true);
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
    setTick(0);setTickDraft('0');
  },[sceneId,scenes]);

  useEffect(()=>{
    let active=true;
    setSnapshot(null);
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
          ||data.project_id!==projectId
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
    {scene&&<CameraLensWorkbench key={scene.scene_id+':'+cameraPath}
      sceneSnapshot={snapshot}
      onRequestRenderedPreview={null}
      onCancelRenderedPreview={null}
      renderBusy={false}
      renderResult={null}/>}
    {scene&&<p className="fineprint">
      The instant projection uses camera-space markers, not rendered pixels.
      Retired Blender still delivery is unavailable; live native OpenUSD
      visual evaluation requires its separate acceptance gate.
    </p>}
  </section>;
}
