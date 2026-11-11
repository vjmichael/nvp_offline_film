import React,{useEffect,useMemo,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import './director-world-stage.css';

// This is a THREE-DIMENSIONAL EDITOR of original OpenUSD scene records.
// NVP independently parses/saves the OpenUSD on every authored change.
// No generated image, render worker, film Take or remote asset is involved.
const PRESET_LABELS={
  box:'Simple object',table:'Table',chair:'Chair',rock:'Rock',
  tree:'Tree',mountain:'Mountain',water:'Water',lamp:'Lamp',
  sun:'Sunlight',camera:'Camera',sphere:'Sphere'
};
const CAMERA_VIEWS={
  perspective:[19,-23,17],above:[0,-.1,35],front:[0,-32,10],
  side:[32,0,9]
};
const EPS=.00001;
const rounded=(n)=>Number(Number(n).toFixed(3));
const vector=(v)=>v.map(rounded);
const radToDeg=(v)=>vector([v.x,v.y,v.z].map(x=>THREE.MathUtils.radToDeg(x)));
const keysAreText=(node)=>node?.closest?.('input,textarea,select,[contenteditable="true"]');

async function filmAction(url,method='GET',payload) {
  const response=await fetch(url,{
    method,credentials:'same-origin',
    headers:{'Content-Type':'application/json','x-nvp-director':'1'},
    ...(payload===undefined?{}:{body:JSON.stringify(payload)})
  });
  if(!response.ok){
    const message=await response.json().catch(()=>({}));
    throw new Error(typeof message.detail==='string'?message.detail:
      'The scene could not be updated. Your saved version has been preserved.');
  }
  return response.json();
}

function geometryFor(item) {
  switch(item.shape){
    case 'box':return new THREE.BoxGeometry(1,1,1);
    case 'sphere':return new THREE.SphereGeometry(.5,16,12);
    case 'cone':{
      const geometry=new THREE.ConeGeometry(.5,1,10);
      geometry.rotateX(Math.PI/2);
      return geometry;
    }
    case 'cylinder':{
      const geometry=new THREE.CylinderGeometry(.5,.5,1,16);
      geometry.rotateX(Math.PI/2);
      return geometry;
    }
    case 'camera':{
      const geometry=new THREE.ConeGeometry(.46,1,4);
      geometry.rotateX(Math.PI/2);
      return geometry;
    }
    case 'sun':return new THREE.SphereGeometry(.48,12,8);
    case 'lamp':return new THREE.SphereGeometry(.48,12,8);
    default:return new THREE.BoxGeometry(.5,.5,.5);
  }
}

function disposeGraph(parent) {
  parent.traverse(node=>{
    node.geometry?.dispose();
    if(Array.isArray(node.material))node.material.forEach(m=>m?.dispose());
    else node.material?.dispose();
  });
}

function StageCanvas({objects,setting,selected,onChoose,mode,onTransform,view,
                      onOpenContext}) {
  const mountRef=useRef(null);
  const worldRef=useRef(null);
  const callbacksRef=useRef({onChoose,onTransform,onOpenContext});
  callbacksRef.current={onChoose,onTransform,onOpenContext};
  const [unavailable,setUnavailable]=useState(false);

  useEffect(()=>{
    const host=mountRef.current;
    if(!host)return;
    let renderer,scene,camera,orbit,gizmo,resize,raf=0,disposed=false;
    const groups=new Map();
    const raycaster=new THREE.Raycaster();
    const pointer=new THREE.Vector2();
    let dragGizmo=false;
    try{
      renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.75));
      renderer.outputColorSpace=THREE.SRGBColorSpace;
      renderer.domElement.setAttribute('aria-label',
        'Editable three-dimensional film scene. Select an object or orbit the view.');
      renderer.domElement.setAttribute('tabindex','0');
      host.appendChild(renderer.domElement);
      scene=new THREE.Scene();
      camera=new THREE.PerspectiveCamera(48,1,.08,450);
      camera.up.set(0,0,1);
      camera.position.set(...CAMERA_VIEWS.perspective);
      camera.lookAt(0,0,1);
      orbit=new OrbitControls(camera,renderer.domElement);
      orbit.target.set(0,0,1);
      orbit.enableDamping=false;
      orbit.minDistance=1;
      orbit.maxDistance=160;
      orbit.maxPolarAngle=Math.PI;
      const ambient=new THREE.AmbientLight(0xffffff,1.6);
      scene.add(ambient);
      const direct=new THREE.DirectionalLight(0xffe6c6,2.8);
      direct.position.set(-8,-5,16);
      scene.add(direct);
      const grid=new THREE.GridHelper(30,30,0x72808c,0x485762);
      grid.rotation.x=Math.PI/2;
      grid.position.z=.016;
      scene.add(grid);
      const world=new THREE.Group();
      scene.add(world);
      gizmo=new TransformControls(camera,renderer.domElement);
      gizmo.setSpace('world');
      scene.add(gizmo.getHelper());
      const redraw=()=>{
        if(disposed||raf)return;
        raf=window.requestAnimationFrame(()=>{
          raf=0;
          if(disposed)return;
          renderer.render(scene,camera);
        });
      };
      const updateSize=()=>{
        if(disposed)return;
        const width=Math.max(300,Math.floor(host.clientWidth||720));
        const height=Math.max(360,Math.min(580,Math.round(width*.63)));
        renderer.setSize(width,height);
        camera.aspect=width/height;
        camera.updateProjectionMatrix();
        redraw();
      };
      const chooseAt=(e)=>{
        if(dragGizmo)return;
        const bounds=renderer.domElement.getBoundingClientRect();
        pointer.set((e.clientX-bounds.left)/bounds.width*2-1,
                    -((e.clientY-bounds.top)/bounds.height)*2+1);
        raycaster.setFromCamera(pointer,camera);
        const hits=raycaster.intersectObjects([...groups.values()],true);
        let found=null;
        for(const hit of hits){
          let target=hit.object;
          while(target&&!target.userData.objectId)target=target.parent;
          if(target?.userData.objectId){found=target.userData.objectId;break;}
        }
        callbacksRef.current.onChoose(found);
        return found;
      };
      const click=(e)=>{if(e.button===0)chooseAt(e)};
      const context=(e)=>{
        e.preventDefault();
        const objectId=chooseAt(e);
        if(objectId)callbacksRef.current.onOpenContext(objectId,e.clientX,e.clientY);
      };
      const keyboard=(e)=>{
        if(e.key==='Escape')callbacksRef.current.onChoose(null);
        if(e.key==='m')gizmo.setMode('translate');
        if(e.key==='r')gizmo.setMode('rotate');
        if(e.key==='s'&&!e.ctrlKey)gizmo.setMode('scale');
        redraw();
      };
      const onTransformChange=()=>redraw();
      const drag=(e)=>{dragGizmo=e.value;orbit.enabled=!e.value;redraw()};
      const release=()=>{
        const group=gizmo.object;
        if(!group||!group.userData.objectId)return;
        callbacksRef.current.onTransform(group.userData.objectId,{
          position:vector([group.position.x,group.position.y,group.position.z]),
          rotation:radToDeg(group.rotation),
          scale:vector([group.scale.x,group.scale.y,group.scale.z])
        });
      };
      renderer.domElement.addEventListener('pointerup',click);
      renderer.domElement.addEventListener('contextmenu',context);
      renderer.domElement.addEventListener('keydown',keyboard);
      orbit.addEventListener('change',redraw);
      gizmo.addEventListener('change',onTransformChange);
      gizmo.addEventListener('dragging-changed',drag);
      gizmo.addEventListener('mouseUp',release);
      if(typeof ResizeObserver!=='undefined'){
        resize=new ResizeObserver(updateSize);resize.observe(host);
      }
      worldRef.current={groups,scene,camera,orbit,gizmo,world,ambient,direct,
        redraw,updateSize};
      updateSize();
      setUnavailable(false);
      return ()=>{
        disposed=true;
        if(raf)window.cancelAnimationFrame(raf);
        resize?.disconnect();
        renderer.domElement.removeEventListener('pointerup',click);
        renderer.domElement.removeEventListener('contextmenu',context);
        renderer.domElement.removeEventListener('keydown',keyboard);
        orbit.removeEventListener('change',redraw);
        orbit.dispose();
        gizmo.removeEventListener('change',onTransformChange);
        gizmo.removeEventListener('dragging-changed',drag);
        gizmo.removeEventListener('mouseUp',release);
        gizmo.detach();gizmo.dispose();
        for(const group of groups.values())disposeGraph(group);
        grid.geometry.dispose();grid.material.dispose();
        renderer.dispose();
        if(host.contains(renderer.domElement))host.removeChild(renderer.domElement);
        worldRef.current=null;
      };
    }catch(error){
      setUnavailable(true);
      renderer?.dispose();
      if(renderer&&host.contains(renderer.domElement))host.removeChild(renderer.domElement);
      worldRef.current=null;
    }
  },[]);

  useEffect(()=>{
    const world=worldRef.current;
    if(!world)return;
    const {groups,world:root,scene,ambient,direct,gizmo,redraw}=world;
    const incoming=new Set();
    for(const item of Array.isArray(objects)?objects.slice(0,96):[]){
      if(!item||typeof item.id!=='string'||!Array.isArray(item.position)||
        !Array.isArray(item.scale)||!Array.isArray(item.rotation)||
        item.position.some(x=>!Number.isFinite(x)))continue;
      incoming.add(item.id);
      let group=groups.get(item.id);
      const signature=[item.shape,item.color,item.role].join(':');
      if(group&&group.userData.signature!==signature){
        if(gizmo.object===group)gizmo.detach();
        root.remove(group);disposeGraph(group);groups.delete(item.id);group=null;
      }
      if(!group){
        group=new THREE.Group();
        group.userData.objectId=item.id;
        group.userData.signature=signature;
        const material=new THREE.MeshStandardMaterial({
          color:new THREE.Color(item.color||'#bdaca0'),roughness:.8,
          metalness:.03,side:THREE.DoubleSide});
        const mesh=new THREE.Mesh(geometryFor(item),material);
        mesh.userData.objectId=item.id;
        group.add(mesh);
        if(item.role==='actor'){
          const head=new THREE.Mesh(new THREE.SphereGeometry(.42,12,8),
            material.clone());
          head.position.z=.45;
          head.userData.objectId=item.id;
          group.add(head);
        }
        root.add(group);groups.set(item.id,group);
      }
      group.position.set(...item.position);
      group.rotation.set(...item.rotation.map(d=>THREE.MathUtils.degToRad(d)));
      group.scale.set(...item.scale);
      group.visible=true;
      group.traverse(node=>{
        if(node.isMesh&&node.material?.emissive){
          node.material.emissive.set(item.id===selected?'#2c3740':'#000000');
        }
      });
    }
    for(const [id,group] of groups){
      if(!incoming.has(id)){
        if(gizmo.object===group)gizmo.detach();
        root.remove(group);disposeGraph(group);groups.delete(id);
      }
    }
    if(selected&&groups.has(selected))gizmo.attach(groups.get(selected));
    else gizmo.detach();
    const daylight=setting?.daylight||'day';
    const weather=setting?.weather||'clear';
    scene.background=new THREE.Color(daylight==='night'?'#101628':
      daylight==='dusk'?'#8e7992':daylight==='dawn'?'#b7a0a1':'#8db4cc');
    const fogAmount=weather==='fog'?.055:weather==='rain'?.019:
      weather==='snow'?.025:weather==='cloudy'?.012:0;
    scene.fog=fogAmount?new THREE.FogExp2(
      daylight==='night'?0x151e2a:0xb1c1c6,fogAmount):null;
    ambient.intensity=daylight==='night'?.65:daylight==='dusk'?1.2:1.6;
    direct.intensity=daylight==='night'?.35:daylight==='dusk'?1.7:2.8;
    const key=objects.find(x=>x.role==='light'&&x.shape==='sun');
    if(key)direct.position.set(...key.position);
    redraw();
  },[objects,setting?.weather,setting?.daylight,selected]);

  useEffect(()=>{
    const world=worldRef.current;
    if(!world)return;
    world.gizmo.setMode(mode||'translate');
    world.redraw();
  },[mode]);

  useEffect(()=>{
    const world=worldRef.current;
    if(!world)return;
    world.camera.position.set(...(CAMERA_VIEWS[view]||CAMERA_VIEWS.perspective));
    world.orbit.target.set(0,0,1);
    world.orbit.update();
    world.redraw();
  },[view]);

  return <div className="director-stage-live">
    <div ref={mountRef} className="director-stage-canvas"
      aria-label="Interactive three-dimensional film scene"/>
    {unavailable&&<div className="director-stage-fallback" role="status">
      Visual scene viewing is unavailable here, but your scene and saved
      object positions are preserved. You can still use the controls below.
    </div>}
  </div>;
}

export default function DirectorWorldStage({movie,scene}) {
  const endpoint='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/stage/'+encodeURIComponent(scene.id);
  const [stage,setStage]=useState(null);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [selected,setSelected]=useState(null);
  const [mode,setMode]=useState('translate');
  const [view,setView]=useState('perspective');
  const [addPreset,setAddPreset]=useState('box');
  const [addActor,setAddActor]=useState('');
  const [draftTransform,setDraftTransform]=useState(null);
  const [editName,setEditName]=useState('');
  const [editColor,setEditColor]=useState('#a4b3be');
  const [directorNote,setDirectorNote]=useState('');
  const [wardrobeNote,setWardrobeNote]=useState('');
  const [context,setContext]=useState(null);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [refresh,setRefresh]=useState(0);
  const stageRef=useRef(null);
  const busyRef=useRef(false);
  stageRef.current=stage;

  useEffect(()=>{
    let active=true;
    setStage(null);setError('');setSelected(null);
    filmAction(endpoint).then(value=>{if(active)setStage(value)})
      .catch(err=>{if(active)setError(err.message)});
    return ()=>{active=false};
  },[endpoint,scene.notes_revision,movie.revision,refresh]);

  const chosen=useMemo(()=>stage?.objects?.find(x=>x.id===selected)||null,
    [stage,selected]);
  useEffect(()=>{
    if(!chosen){setDraftTransform(null);return}
    setDraftTransform({position:[...chosen.position],
      rotation:[...chosen.rotation],scale:[...chosen.scale]});
    setEditName(chosen.name);
    setEditColor(chosen.color);
    setDirectorNote(chosen.director_note||'');
    setWardrobeNote(chosen.wardrobe_note||'');
  },[chosen?.id,stage?.revision]);

  async function update(work,message) {
    if(busyRef.current)return null;
    busyRef.current=true;setBusy(true);setError('');setNotice('');setContext(null);
    try{
      const result=await work();
      if(result?.created!==undefined)setStage(result);
      if(message)setNotice(message);
      return result;
    }catch(err){
      setError(err.message);
      setRefresh(v=>v+1); // discard unsaved optimistic drag after rejection
      return null;
    }finally{busyRef.current=false;setBusy(false)}
  }

  function revise(operation,details,message) {
    const old=stageRef.current;
    if(!old?.created||!old.current)return;
    return update(()=>filmAction(endpoint+'/edit','POST',{
      expected_revision:old.revision,operation,details
    }),message||'Scene updated. You can keep refining it.');
  }

  function generate() {
    const old=stageRef.current;
    if(old?.created&&!window.confirm(
      'Create a fresh visual scene from your current screenplay and notes? '+
      'Your existing scene is preserved in its history.'))return;
    update(()=>filmAction(endpoint+'/generate','POST',{
      expected_revision:old?.revision||0
    }),'A real three-dimensional scene has been created. Review and refine it.');
  }
  function choose(id) {
    setSelected(id);setContext(null);
  }
  function transform(id,value) {
    if(!stageRef.current?.current||busyRef.current)return;
    revise('transform',{id,...value},'Object position and orientation saved.');
  }
  function saveTransform() {
    if(!chosen||!draftTransform)return;
    revise('transform',{id:chosen.id,
      position:vector(draftTransform.position.map(Number)),
      rotation:vector(draftTransform.rotation.map(Number)),
      scale:vector(draftTransform.scale.map(Number))},
      'Object placement updated.');
  }
  function add() {
    const details=addPreset==='actor'?{preset:'actor',actor_id:addActor}:
      {preset:addPreset};
    revise('add',details,'Object added. Position it in the world.');
  }
  function restore(version) {
    if(!window.confirm('Restore this earlier scene? Your current stage will be preserved.'))return;
    update(()=>filmAction(endpoint+'/restore','POST',{
      expected_revision:stage.revision,source_revision:version
    }),'Earlier scene restored as a new editable version.');
  }
  function approve() {
    update(()=>filmAction(endpoint+'/approve','POST',{
      expected_revision:stage.revision
    }),'Scene approved. Your original creative source remains unchanged.');
  }
  function openContext(id,x,y) {
    setSelected(id);
    setContext({id,x,y});
  }
  function changeAxis(group,index,value) {
    setDraftTransform(existing=>{
      if(!existing)return existing;
      const next={...existing,[group]:[...existing[group]]};
      next[group][index]=value;
      return next;
    });
  }
  const editable=!!stage?.created&&stage?.current&&!busy;
  const past=stage?.past_versions?.filter(v=>v.revision!==stage.revision)||[];

  return <section className="director-world" aria-label="Visual Scene Builder">
    <div className="director-world-heading">
      <div><h4>Your visual scene</h4>
        <p className="film-muted">See your setting in 3D. Move things, change
          the light and arrange your scene before filming.</p></div>
      {stage?.created&&<span className={'director-stage-status '+
        (stage.status==='approved'?'approved':'draft')}>
        {stage.status==='approved'?'Approved':
         stage.status==='outdated'?'Needs updating':'Scene draft'}</span>}
    </div>
    {error&&<div role="alert" className="director-world-error">{error}</div>}
    {notice&&<div role="status" className="director-world-notice">{notice}</div>}
    {!stage&&!error&&<p role="status" className="film-muted">Opening the scene…</p>}
    {stage&&!stage.created&&<div className="director-stage-start">
      <div className="director-stage-start-icon" aria-hidden="true">◇</div>
      <h4>Bring this scene to life</h4>
      <p>Start with a simple editable world based on the scene you described.
        Nothing is filmed yet; you can change everything before approval.</p>
      <button className="film-primary" disabled={busy} onClick={generate}>
        Create Visual Scene</button>
    </div>}
    {stage?.created&&<>
      {!stage.current&&<div className="director-world-warning">
        Your screenplay or scene description has changed. You can keep the
        earlier scene in your history or rebuild it using your latest choices.
        <div className="film-actions"><button className="film-primary"
          disabled={busy} onClick={generate}>Rebuild Visual Scene</button></div>
      </div>}
      <div className="director-world-tools">
        <div className="director-world-toolgroup" aria-label="Arrange objects">
          {[
            ['translate','Move'],['rotate','Rotate'],['scale','Resize']
          ].map(([id,label])=><button type="button" key={id}
            aria-pressed={mode===id} className={mode===id?'selected':''}
            onClick={()=>setMode(id)}>{label}</button>)}
        </div>
        <label className="director-view-select">View
          <select value={view} onChange={e=>setView(e.target.value)}>
            <option value="perspective">3D orbit</option>
            <option value="above">From above</option>
            <option value="front">Front</option>
            <option value="side">Side</option>
          </select>
        </label>
      </div>
      <StageCanvas objects={stage.objects} setting={stage.setting}
        selected={selected} onChoose={choose} mode={mode} view={view}
        onTransform={transform} onOpenContext={openContext}/>
      <p className="director-world-help">Drag to orbit · Scroll to zoom · Click
        an object to select it · Drag the handles to place it.</p>
      <div className="director-world-layout">
        <div className="director-world-list">
          <h5>Objects in this scene</h5>
          <div className="director-world-object-list">
            {stage.objects?.map(item=><button key={item.id}
              className={selected===item.id?'selected':''}
              aria-pressed={selected===item.id} onClick={()=>choose(item.id)}>
              <span>{item.name}</span><small>{
                item.role==='actor'?'Performer placement':
                item.role==='light'?'Light':item.role==='camera'?'Camera':
                item.role==='set'?'Set':'Scene object'}</small>
            </button>)}
          </div>
          <div className="director-world-asset-picker">
            <h5>Add to your scene</h5>
            <div className="director-world-row">
              <select aria-label="Choose a new object" value={addPreset}
                onChange={e=>setAddPreset(e.target.value)}>
                {(stage.available_presets||[]).map(key=><option key={key} value={key}>
                  {PRESET_LABELS[key]||key}</option>)}
                {!!stage.actor_choices?.length&&<option value="actor">Performer</option>}
              </select>
              <button className="film-secondary" disabled={!editable||
                (addPreset==='actor'&&!addActor)} onClick={add}>Add</button>
            </div>
            {addPreset==='actor'&&<label>
              Choose a character
              <select value={addActor} onChange={e=>setAddActor(e.target.value)}>
                <option value="">Choose one</option>
                {(stage.actor_choices||[]).map(a=><option
                  key={a.actor_id} value={a.actor_id}>{a.name}</option>)}
              </select>
            </label>}
            <p className="film-hint">The objects here are editable building blocks.
              You can replace their look as your film develops.</p>
          </div>
        </div>
        <div className="director-world-inspector">
          {chosen?<>
            <h5>Selected: {chosen.name}</h5>
            <label>Object name
              <input maxLength={100} value={editName}
                onChange={e=>setEditName(e.target.value)}/></label>
            <div className="film-actions">
              <button className="film-secondary" disabled={!editable||
                editName.trim()===chosen.name||!editName.trim()}
                onClick={()=>revise('rename',{id:chosen.id,name:editName})}>
                Save Name</button>
            </div>
            {[
              ['position','Position','m'],
              ['rotation','Rotation','°'],
              ['scale','Size','']
            ].map(([key,label,unit])=><fieldset className="director-world-axes"
                key={key}>
              <legend>{label} {unit}</legend>
              {['X','Y','Z'].map((axis,index)=><label key={axis}>{axis}
                <input aria-label={label+' '+axis} type="number"
                  min={key==='scale'?.04:key==='position'?-150:-360}
                  max={key==='scale'?100:key==='position'?150:360}
                  step={key==='rotation'?5:.1}
                  value={draftTransform?.[key]?.[index]??0}
                  onChange={e=>changeAxis(key,index,e.target.value)}/>
              </label>)}
            </fieldset>)}
            <div className="film-actions">
              <button className="film-secondary" disabled={!editable}
                onClick={saveTransform}>Apply Placement</button>
            </div>
            <label>Object color
              <input aria-label="Object color" type="color" value={editColor}
                onChange={e=>setEditColor(e.target.value)}/></label>
            <div className="film-actions"><button className="film-secondary"
              disabled={!editable||chosen.color.toLowerCase()===editColor.toLowerCase()}
              onClick={()=>revise('recolor',{id:chosen.id,color:editColor})}>
              Apply Color</button></div>
            <label>Give a note
              <textarea rows={3} maxLength={1500} value={directorNote}
                onChange={e=>setDirectorNote(e.target.value)}
                placeholder="How should this object or performer behave?"/></label>
            <div className="film-actions"><button className="film-secondary"
              disabled={!editable||directorNote===(chosen.director_note||'')}
              onClick={()=>revise('note',{id:chosen.id,value:directorNote})}>
              Save Note</button></div>
            {chosen.role==='actor'&&<>
              <label>Wardrobe or appearance
                <textarea rows={2} maxLength={1500} value={wardrobeNote}
                  placeholder="Describe the look of this character…"
                  onChange={e=>setWardrobeNote(e.target.value)}/></label>
              <div className="film-actions"><button className="film-secondary"
                disabled={!editable||wardrobeNote===(chosen.wardrobe_note||'')}
                onClick={()=>revise('wardrobe',{
                  id:chosen.id,value:wardrobeNote})}>
                Save Look</button></div>
            </>}
            <div className="film-actions">
              <button className="film-secondary" disabled={!editable}
                onClick={()=>{
                  if(window.confirm('Remove this object from the current scene? Your earlier version is preserved.')){
                    revise('remove',{id:chosen.id},'Object removed from this scene.');
                    setSelected(null);
                  }
                }}>Remove Object</button>
            </div>
          </>:<>
            <h5>Scene atmosphere</h5>
            <p className="film-muted">Select an object to arrange it, or
              choose the atmosphere for your scene.</p>
          </>}
          <h5>Atmosphere</h5>
          <label>Time of day
            <select value={stage.setting?.daylight||'day'}
              disabled={!editable}
              onChange={e=>revise('daylight',{daylight:e.target.value},
                'Scene lighting updated.')}>
              <option value="dawn">Dawn</option>
              <option value="day">Day</option>
              <option value="dusk">Dusk</option>
              <option value="night">Night</option>
            </select></label>
          <label>Weather
            <select value={stage.setting?.weather||'clear'}
              disabled={!editable}
              onChange={e=>revise('weather',{weather:e.target.value},
                'Scene atmosphere updated.')}>
              <option value="clear">Clear</option>
              <option value="cloudy">Cloudy</option>
              <option value="fog">Fog or mist</option>
              <option value="rain">Rain</option>
              <option value="snow">Snow</option>
            </select></label>
        </div>
      </div>
      <div className="director-world-footer">
        <button className="film-secondary" onClick={()=>setHistoryOpen(x=>!x)}>
          {historyOpen?'Hide earlier scenes':'Earlier versions'}</button>
        {stage.status!=='approved'&&<button className="film-primary"
          disabled={!editable} onClick={approve}>
          Approve Scene</button>}
      </div>
      {historyOpen&&<div className="director-world-history">
        <h5>Earlier versions</h5>
        {past.length===0?<p className="film-muted">
          Your earlier scene versions will appear here as you make changes.</p>:
          past.map(x=><div key={x.revision} className="director-world-history-row">
            <span>Scene version {x.revision} · {
              x.status==='approved'?'Approved':'Draft'}</span>
            <button className="film-secondary" disabled={!editable}
              onClick={()=>restore(x.revision)}>Restore</button>
          </div>)}
      </div>}
      {context&&chosen&&<div className="director-world-context"
        role="menu" aria-label={'Actions for '+chosen.name}>
        <strong>{chosen.name}</strong>
        <button role="menuitem" onClick={()=>{setMode('translate');setContext(null)}}>
          Move this object</button>
        <button role="menuitem" onClick={()=>{setMode('rotate');setContext(null)}}>
          Rotate this object</button>
        <button role="menuitem" onClick={()=>{
          setContext(null);
          document.querySelector('.director-world-note-target')?.focus();
        }}>Give a note</button>
        <button role="menuitem" onClick={()=>setContext(null)}>Close menu</button>
      </div>}
    </>}
  </section>;
}
