import React,{useEffect,useMemo,useRef,useState} from 'react';
import * as THREE from 'three';
import './director-filming-studio.css';

/* G06: filmmaker language only. Original OpenUSD/Film Time and native PCM are
   owned by NVP, not the browser. Preview can be reframed independently. */
const EVENTS={
  actor:[
    ['walk','Walk'],['jog','Jog'],['run','Run'],['crawl','Crawl'],
    ['gesture','Gesture'],['look','Look toward something'],
    ['expression','Expression'],['dialogue','Speak a line'],
    ['wardrobe','Change wardrobe or appearance']],
  object:[['prop_move','Move object'],['prop_turn','Turn object'],
          ['prop_action','Interact with object']],
  ambience:[
    ['wind','Wind'],['fog','Fog'],['rain','Rain'],
    ['snow','Snow'],['light','Lighting changes'],
    ['ambient_action','Other environmental action']]
};
const MOTION=new Set(['walk','jog','run','crawl','prop_move']);
const AMBIENT=new Set(['wind','fog','rain','snow','light','ambient_action']);
const frameLabels=['Wide','Medium','Close-up'];
const standardFrames=[
  {name:'Wide',focal_mm:24,position:[13,-23,12],look_at:[0,0,1.5]},
  {name:'Medium',focal_mm:50,position:[8,-12,5],look_at:[0,0,1.4]},
  {name:'Close-up',focal_mm:85,position:[3.6,-5,2.4],look_at:[0,0,1.7]},
];

async function call(url,method='GET',payload){
  const r=await fetch(url,{method,credentials:'same-origin',
    headers:{'Content-Type':'application/json','x-nvp-director':'1'},
    ...(payload===undefined?{}:{body:JSON.stringify(payload)})});
  if(!r.ok){
    const body=await r.json().catch(()=>({}));
    throw new Error(typeof body.detail==='string'?body.detail:
      'The scene could not be updated. Your earlier work is safe.');
  }
  return r.json();
}
function boxOf(x){
  if(x.shape==='sphere'||x.shape==='sun'||x.shape==='lamp')
    return new THREE.SphereGeometry(.5,12,8);
  if(x.shape==='cone')return new THREE.ConeGeometry(.5,1,10).rotateX(Math.PI/2);
  if(x.shape==='cylinder')
    return new THREE.CylinderGeometry(.5,.5,1,12).rotateX(Math.PI/2);
  if(x.shape==='camera')return new THREE.ConeGeometry(.5,1,4).rotateX(Math.PI/2);
  return new THREE.BoxGeometry(1,1,1);
}
function positionAt(object,events,second){
  let position=[...object.position];
  const moves=events.filter(x=>x.object_id===object.id&&MOTION.has(x.kind))
    .sort((a,b)=>a.start_seconds-b.start_seconds);
  for(const event of moves){
    const start=Number(event.start_seconds);
    const end=Number(event.end_seconds);
    if(second<start)break;
    if(second>=end){position=[...event.target_position];continue;}
    const part=(second-start)/(end-start);
    position=position.map((p,i)=>
      p+(event.target_position[i]-p)*part);
    break;
  }
  return position;
}
function activeEvents(events,seconds){
  return events.filter(x=>x.start_seconds<=seconds&&
    x.end_seconds>=seconds);
}
function LookPreview({objects,events,second,views,weather,daylight,onContext}){
  const nodeRef=useRef(null);
  const [failed,setFailed]=useState(false);
  const engine=useRef(null);
  const callback=useRef(onContext);
  callback.current=onContext;
  useEffect(()=>{
    if(!nodeRef.current)return;
    const root=nodeRef.current;
    let renderer=null,scene=null,resize=null;
    const meshes=new Map();
    try{
      renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));
      root.appendChild(renderer.domElement);
      renderer.domElement.setAttribute('aria-label','Three film camera previews');
      scene=new THREE.Scene();
      scene.background=new THREE.Color('#2a3d52');
      scene.add(new THREE.AmbientLight(0xffffff,1.35));
      const sun=new THREE.DirectionalLight(0xffe4c4,2);
      sun.position.set(-7,-7,14);scene.add(sun);
      for(const item of objects||[]){
        const group=new THREE.Group();
        group.userData.id=item.id;
        group.add(new THREE.Mesh(boxOf(item),new THREE.MeshStandardMaterial({
          color:new THREE.Color(item.color||'#adadae'),roughness:.82,
          side:THREE.DoubleSide})));
        if(item.role==='actor'){
          const head=new THREE.Mesh(new THREE.SphereGeometry(.38,10,8),
            new THREE.MeshStandardMaterial({color:'#bfadd0'}));
          head.position.z=.45;group.add(head);
        }
        group.scale.set(...item.scale);
        group.position.set(...item.position);
        meshes.set(item.id,group);
        scene.add(group);
      }
      const cameras=views.map(()=>new THREE.PerspectiveCamera(45,1,.1,350));
      const render=()=>{
        const width=Math.max(root.clientWidth||720,320);
        const panel=Math.floor(width/3);
        const height=Math.max(160,Math.min(265,Math.floor(panel*.9)));
        renderer.setSize(panel*3,height);
        renderer.setScissorTest(true);
        for(let i=0;i<3;i++){
          const view=engine.current?.views?.[i]||standardFrames[i];
          const cam=cameras[i];
          const lens=Number(view.focal_mm)||standardFrames[i].focal_mm;
          cam.fov=2*Math.atan(24/(2*lens))*180/Math.PI;
          cam.aspect=panel/height;
          cam.updateProjectionMatrix();
          cam.up.set(0,0,1);
          cam.position.set(...view.position);
          cam.lookAt(...view.look_at);
          renderer.setViewport(i*panel,0,panel,height);
          renderer.setScissor(i*panel,0,panel,height);
          renderer.render(scene,cam);
        }
        renderer.setScissorTest(false);
      };
      engine.current={meshes,scene,renderer,views,events,second,
        render,sun,cameras,root};
      const rightClick=(e)=>{
        e.preventDefault();
        const state=engine.current;
        if(!state)return;
        const bounds=renderer.domElement.getBoundingClientRect();
        const panel=bounds.width/3;
        const local=e.clientX-bounds.left;
        const index=Math.max(0,Math.min(2,Math.floor(local/panel)));
        const pointer=new THREE.Vector2(
          (local-index*panel)/panel*2-1,
          -(e.clientY-bounds.top)/bounds.height*2+1);
        const ray=new THREE.Raycaster();
        ray.setFromCamera(pointer,cameras[index]);
        const found=ray.intersectObjects([...meshes.values()],true);
        let objectId=null;
        for(const hit of found){
          let node=hit.object;
          while(node&&!node.userData.id)node=node.parent;
          if(node?.userData.id){objectId=node.userData.id;break;}
        }
        callback.current?.(objectId,e.clientX,e.clientY);
      };
      renderer.domElement.addEventListener('contextmenu',rightClick);
      if(typeof ResizeObserver!=='undefined'){
        resize=new ResizeObserver(render);resize.observe(root);
      }
      render();
      setFailed(false);
      return()=>{
        resize?.disconnect();
        renderer.domElement.removeEventListener('contextmenu',rightClick);
        for(const group of meshes.values()){
          group.traverse(node=>{
            node.geometry?.dispose();node.material?.dispose();
          });
        }
        renderer.dispose();
        if(root.contains(renderer.domElement))root.removeChild(renderer.domElement);
        engine.current=null;
      };
    }catch(e){
      renderer?.dispose();
      if(renderer&&root.contains(renderer.domElement))root.removeChild(renderer.domElement);
      setFailed(true);engine.current=null;
    }
  },[objects]);
  useEffect(()=>{
    const state=engine.current;
    if(!state)return;
    state.views=views;
    const current=activeEvents(events,second);
    const fog=current.filter(x=>x.kind==='fog').length||weather==='fog';
    const dark=daylight==='night';
    state.scene.background.set(dark?'#111626':
      daylight==='dusk'?'#806c83':'#789cb5');
    state.scene.fog=fog?new THREE.FogExp2(dark?0x1a2430:0xaabcc1,.045):null;
    state.sun.intensity=dark?.5:daylight==='dusk'?1.3:2;
    for(const item of objects){
      const group=state.meshes.get(item.id);
      if(group)group.position.set(...positionAt(item,events,second));
    }
    state.render();
  },[objects,events,second,views,weather,daylight]);
  return <div className="director-film-three">
    <div ref={nodeRef} className="director-film-three-canvas"/>
    <div className="director-film-three-labels">{frameLabels.map(x=>
      <span key={x}>{x}</span>)}</div>
    {failed&&<p className="film-muted">The camera preview is unavailable,
      but the original performance and camera settings remain saved.</p>}
  </div>;
}
function TimeLine({duration,events,position,onChange,playing,onPlay}){
  return <div className="director-film-timeline">
    <div className="director-film-time-head"><strong>Performance timeline</strong>
      <span>{Number(position).toFixed(1)} / {Number(duration).toFixed(1)} seconds</span></div>
    <div className="director-film-time-controls">
      <button className="film-secondary" onClick={onPlay}>
        {playing?'Pause':'Play preview'}</button>
      <input aria-label="Move through scene time" type="range" min="0"
        max={duration} step=".1" value={position}
        onChange={e=>onChange(Number(e.target.value))}/>
    </div>
    <div className="director-film-events-scale">
      {events.map(e=><div className="director-film-event-mark"
        key={e.id} style={{left:(e.start_seconds/duration*100)+'%',
          width:Math.max(1.8,(e.end_seconds-e.start_seconds)/duration*100)+'%'}}
        title={e.kind+' at '+e.start_seconds+' seconds}/>)}
    </div>
  </div>;
}
function AxisFields({label,values,onChange}){
  return <fieldset className="director-film-axes"><legend>{label}</legend>
    {['X','Y','Z'].map((axis,index)=><label key={axis}>{axis}
      <input type="number" step=".1" min="-150" max="150"
        value={values[index]}
        onChange={e=>onChange(values.map((v,i)=>
          i===index?Number(e.target.value):v))}/></label>)}
  </fieldset>;
}

export default function DirectorFilmingStudio({movie,onSetUpScenes}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/film';
  const [scenes,setScenes]=useState([]);
  const [sceneId,setSceneId]=useState('');
  const [film,setFilm]=useState(null);
  const [stage,setStage]=useState(null);
  const [selectedObject,setSelectedObject]=useState('');
  const [kind,setKind]=useState('walk');
  const [startSeconds,setStartSeconds]=useState('0');
  const [endSeconds,setEndSeconds]=useState('3');
  const [target,setTarget]=useState([0,0,1]);
  const [intensity,setIntensity]=useState(1);
  const [note,setNote]=useState('');
  const [duration,setDuration]=useState('30');
  const [time,setTime]=useState(0);
  const [playing,setPlaying]=useState(false);
  const [recordSession,setRecordSession]=useState(null);
  const sessionRef=useRef(null);
  const [micActor,setMicActor]=useState('');
  const [selectedClips,setSelectedClips]=useState([]);
  const [clipStarts,setClipStarts]=useState({});
  const [listenUrl,setListenUrl]=useState('');
  const [aiReady,setAiReady]=useState(false);
  const [notePopup,setNotePopup]=useState(null);
  const [noteInstruction,setNoteInstruction]=useState('');
  const [noteEdits,setNoteEdits]=useState({});
  const reelRef=useRef(null);
  const [take,setTake]=useState(null);
  const [views,setViews]=useState(standardFrames);
  const [activeView,setActiveView]=useState(0);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [reload,setReload]=useState(0);
  const busyRef=useRef(false);

  useEffect(()=>{
    let alive=true;
    call('/api/creative/models').then(out=>{
      if(alive)setAiReady(out.state==='available');
    }).catch(()=>{if(alive)setAiReady(false)});
    return()=>{alive=false};
  },[]);
  useEffect(()=>()=>{
    if(listenUrl)URL.revokeObjectURL(listenUrl);
  },[listenUrl]);

  useEffect(()=>{
    let active=true;
    call('/api/projects/'+encodeURIComponent(movie.id)+
      (movie.encrypted?'/live':'')+'/preproduction').then(doc=>{
      if(!active)return;
      setScenes(doc.scenes||[]);
      if(!sceneId&&doc.scenes?.length)setSceneId(doc.scenes[0].id);
    }).catch(err=>{if(active)setError(err.message)});
    return()=>{active=false};
  },[movie.id,movie.revision]);

  const endpoint=sceneId?base+'/scene/'+encodeURIComponent(sceneId):'';
  useEffect(()=>{
    if(!endpoint)return;
    let mounted=true;
    setFilm(null);setStage(null);setTake(null);setError('');
    setListenUrl('');setNotePopup(null);
    Promise.all([
      call(endpoint),
      call('/api/projects/'+encodeURIComponent(movie.id)+
        (movie.encrypted?'/live':'')+'/stage/'+encodeURIComponent(sceneId))
    ]).then(([f,s])=>{
      if(!mounted)return;
      setFilm(f);setStage(s);setDuration(String(f.duration_seconds));
      setSelectedObject(f.stage_objects.find(o=>o.role==='actor')?.id||
        f.stage_objects.find(o=>o.role==='prop')?.id||'');
      setTime(0);setSelectedClips([]);setClipStarts({});
    }).catch(err=>{if(mounted)setError(err.message)});
    return()=>{mounted=false};
  },[endpoint,reload,movie.revision]);

  // A microphone session does not continue simply because the director
  // navigates away. The trusted host also cancels on project lock.
  useEffect(()=>{
    return()=>{
      const session=sessionRef.current;
      if(session&&session.endpoint){
        call(session.endpoint+'/microphone/cancel','POST',
          {session_id:session.session_id}).catch(()=>{});
      }
    };
  },[movie.id]);

  useEffect(()=>{
    if(!film||!playing)return;
    const start=performance.now(),baseTime=time;
    let frame=0;
    const step=()=>{
      const current=Math.min(film.duration_seconds,
        baseTime+(performance.now()-start)/1000);
      setTime(current);
      if(current>=film.duration_seconds){setPlaying(false);return}
      frame=requestAnimationFrame(step);
    };
    frame=requestAnimationFrame(step);
    return()=>cancelAnimationFrame(frame);
  },[playing,film?.duration_seconds]);

  const objects=take?.stage_objects||film?.stage_objects||[];
  const options=useMemo(()=>{
    const target=objects.find(o=>o.id===selectedObject);
    if(target?.role==='actor')return EVENTS.actor;
    if(target&&['prop','environment','set'].includes(target.role))return EVENTS.object;
    return EVENTS.ambience;
  },[selectedObject,objects]);
  useEffect(()=>{
    if(!options.some(item=>item[0]===kind))setKind(options[0]?.[0]||'wind');
  },[options,kind]);
  const activeObject=objects.find(x=>x.id===selectedObject);
  const actorObjects=objects.filter(x=>x.role==='actor');
  const clips=film?.audio_clips||[];
  const takeId=take?.take_id||film?.takes?.[0]?.id||null;
  const filmEvents=take?.events||film?.events||[];

  async function perform(task,ok){
    if(busyRef.current)return;
    busyRef.current=true;setBusy(true);setError('');setNotice('');
    try{
      const outcome=await task();
      if(outcome?.format==='nvp.g06.film.performance.v1')setFilm(outcome);
      if(ok)setNotice(ok);
      return outcome;
    }catch(err){setError(err.message)}
    finally{busyRef.current=false;setBusy(false)}
  }

  async function addEvent(){
    if(!film)return;
    const moving=MOTION.has(kind);
    const ambient=AMBIENT.has(kind);
    const body={
      expected_revision:film.work_revision,kind,
      object_id:ambient?null:selectedObject,
      start_seconds:startSeconds,end_seconds:endSeconds,
      target_position:moving?target:null,
      intensity:ambient?Number(intensity):null,note
    };
    const result=await perform(()=>call(endpoint+'/events','POST',body),
      'Performance direction added. It is still editable.');
    if(result)setNote('');
  }
  function retake(){
    if(!film||!window.confirm('Start a new performance draft? Frozen Takes and earlier directions remain preserved.'))return;
    setTake(null);setViews(standardFrames);
    perform(()=>call(endpoint+'/retake','POST',{
      expected_revision:film.work_revision,reason:'director_retakes_scene'
    }),'A fresh performance draft is ready. Earlier Takes remain safe.');
  }
  function changeDuration(){
    perform(()=>call(endpoint+'/duration','POST',{
      expected_revision:film.work_revision,seconds:duration
    }),'Scene duration updated.');
  }
  function removeEvent(id){
    if(!window.confirm('Remove this direction from the current performance?'))return;
    perform(()=>call(endpoint+'/events/'+id+
      '?expected_revision='+film.work_revision,'DELETE'),
      'Direction removed. Earlier versions remain in the film history.');
  }
  function startMicrophone(){
    perform(async()=>{
      const opened=await call(endpoint+'/microphone/start','POST',{
        actor_id:micActor||null});
      sessionRef.current={session_id:opened.session_id,endpoint};
      setRecordSession(opened);
      return opened;
    },'Original sound is being recorded from your microphone.');
  }
  function stopMicrophone(){
    if(!recordSession)return;
    perform(async()=>{
      const result=await call(endpoint+'/microphone/finish','POST',{
        session_id:recordSession.session_id});
      sessionRef.current=null;setRecordSession(null);
      const updated=await call(endpoint);setFilm(updated);
      setSelectedClips(x=>[...x,result.clip_id]);
      return result;
    },'Original sound recorded and saved. You can include it in a Take.');
  }
  function cancelMicrophone(){
    if(!recordSession)return;
    perform(async()=>{
      await call(endpoint+'/microphone/cancel','POST',{
        session_id:recordSession.session_id});
      sessionRef.current=null;setRecordSession(null);
    },'Recording stopped without publishing any original sound.');
  }
  async function freeze(){
    if(!film||recordSession)return;
    if(!window.confirm('Freeze this performance as an original Digital Take? '+
        'You will still be able to make another Take and change the camera framing later.'))return;
    const result=await perform(()=>call(endpoint+'/takes','POST',{
      expected_revision:film.work_revision,clip_ids:selectedClips,
      clip_starts:Object.fromEntries(selectedClips.map(id=>[
        id,String(clipStarts[id]||'0')]))
    }),'Original performance frozen. The film source will not be changed by later framing.');
    if(result?.take_id){
      setTake(await call(endpoint+'/takes/'+result.take_id));
      setViews(standardFrames);
      const updated=await call(endpoint);setFilm(updated);
    }
  }
  function chooseTake(id){
    perform(async()=>{
      const result=await call(endpoint+'/takes/'+id);
      setTake(result);
      setViews(result.camera.views);
      setActiveView(0);setPlaying(false);setTime(0);
      return result;
    },'Original Take opened. Camera changes will not alter its performance.');
  }
  function saveCamera(){
    if(!take)return;
    const targetView=views[activeView];
    perform(async()=>{
      const change=await call(endpoint+'/takes/'+take.take_id+'/camera','PUT',{
        expected_revision:take.camera.revision,
        view_index:activeView,
        focal_mm:Number(targetView.focal_mm),
        position:targetView.position,look_at:targetView.look_at
      });
      setTake(x=>({...x,camera:change.camera}));
      return change;
    },'Camera framing saved without altering the original Take.');
  }
  function cameraField(field,value){
    setViews(x=>x.map((v,i)=>i===activeView?{...v,[field]:value}:v));
  }
  function contextAt(objectId,x,y){
    const chosen=objects.find(o=>o.id===objectId);
    const rect=reelRef.current?.getBoundingClientRect();
    setSelectedObject(chosen?.role==='actor'||chosen?.role==='prop'||
      chosen?.role==='set'||chosen?.role==='environment'?chosen.id:'');
    setNotePopup({
      object_id:chosen?.role==='actor'?chosen.id:null,
      target_id:chosen?.id||null,
      role:chosen?.role||'environment',name:chosen?.name||'Environment',
      x:rect?Math.max(8,Math.min(rect.width-210,x-rect.left)):12,
      y:rect?Math.max(65,Math.min(rect.height-220,y-rect.top)):90
    });
  }
  function giveNote(type='gesture'){
    if(notePopup){
      setSelectedObject(notePopup.target_id||'');
      const chosen=objects.find(o=>o.id===notePopup.target_id);
      setKind(chosen?.role==='actor'?type:
        chosen?.role==='environment'||chosen?.role==='prop'||
          chosen?.role==='set'?'prop_action':'ambient_action');
    }
    setNotePopup(null);
    document.querySelector('.director-film-direction-target')?.focus();
  }
  function askAINote(){
    const popup=notePopup;
    perform(()=>call(endpoint+'/notes/suggest','POST',{
      object_id:popup?.object_id||(
        activeObject?.role==='actor'?activeObject.id:null),
      at_seconds:String(Number(time.toFixed(2))),
      instructions:noteInstruction
    }),'Here is a performance idea for you to review.');
    setNotePopup(null);
  }
  function reviewNote(idea,decision){
    perform(()=>call(endpoint+'/notes/'+idea.id+'/decision','POST',{
      decision,expected_revision:film.work_revision,
      ...(decision==='accept'&&noteEdits[idea.id]!==undefined
        ?{edited_note:noteEdits[idea.id]}:{})
    }),decision==='accept'?'Direction approved and added to the scene.':
      'Suggestion declined; no performance change was made.');
  }
  async function listenTo(clipId){
    await perform(async()=>{
      const result=await fetch(endpoint+'/originals/'+clipId+'/listen',{
        credentials:'same-origin',headers:{'x-nvp-director':'1'}});
      if(!result.ok){
        const msg=await result.json().catch(()=>({}));
        throw new Error(msg.detail||'Original sound could not be played');
      }
      const raw=await result.blob();
      if(raw.type!=='audio/wav')throw new Error('Original sound format is unavailable');
      setListenUrl(URL.createObjectURL(raw));
    },'Original sound ready to listen to. The source recording is unchanged.');
  }

  return <section className="film-card director-film-studio"
    aria-label="Film Scenes">
    <div className="film-card-head">
      <div><div className="film-eyebrow">DIRECT YOUR FILM</div>
        <h2>Film Scenes</h2>
        <p className="film-muted">Direct performances, the environment and sound.
          The cameras can be changed later without changing the recording.</p></div>
      <button className="film-secondary" onClick={onSetUpScenes}>
        Set Up Scenes</button>
    </div>
    <label className="director-film-select">Choose a scene
      <select value={sceneId} onChange={e=>{
        if(recordSession)return;
        setSceneId(e.target.value);setPlaying(false);
      }}>{scenes.map(scene=><option key={scene.id} value={scene.id}>
        {String(scene.number).padStart(2,'0')} · {scene.heading}
      </option>)}</select></label>
    {error&&<div className="director-film-error" role="alert">{error}
      {!film&&<div className="film-actions">
        <button className="film-secondary" onClick={onSetUpScenes}>
          Review and approve the visual scene</button>
      </div>}</div>}
    {notice&&<div className="director-film-notice" role="status">{notice}</div>}
    {!film&&scenes.length>0&&!error&&<p role="status" className="film-muted">
      Opening your filming scene…</p>}
    {scenes.length===0&&<p className="film-muted">
      Create a scene in Set Up Scenes to start filming.</p>}
    {film&&<>
      {!film.work_current&&<div className="director-film-warning">
        The approved scene changed. Start a new performance draft to use the
        latest arrangement. Earlier directions and Takes remain preserved.
        <button className="film-secondary" onClick={retake} disabled={busy}>
          Start Fresh Performance</button>
      </div>}
      <div className="director-film-reel" ref={reelRef}>
        <div className="director-film-reel-heading">
          <h3>Scene preview</h3>
          <p className="film-muted">These are three different views of the same
            performance—not three separate recordings.</p>
        </div>
        <LookPreview objects={objects} events={filmEvents} second={time}
          views={take?views:standardFrames}
          weather={stage?.setting?.weather||'clear'}
          daylight={stage?.setting?.daylight||'day'}
          onContext={contextAt}/>
        <TimeLine duration={film.duration_seconds} events={filmEvents}
          position={time} onChange={t=>{setTime(t);setPlaying(false)}}
          playing={playing} onPlay={()=>setPlaying(x=>!x)}/>
        {notePopup&&<div className="director-film-context"
          style={{left:notePopup.x,top:notePopup.y}} role="menu"
          aria-label={'Direct '+notePopup.name}>
          <strong>{notePopup.name}</strong>
          <button role="menuitem" onClick={()=>giveNote(
            notePopup.role==='actor'?'gesture':'prop_action')}>
            Give Note</button>
          {notePopup.role==='actor'&&<button role="menuitem"
            onClick={()=>giveNote('wardrobe')}>Change Wardrobe</button>}
          {aiReady&&<button role="menuitem" onClick={askAINote}>
            Ask AI for a suggestion</button>}
          <button role="menuitem" onClick={()=>setNotePopup(null)}>Close</button>
        </div>}
      </div>
      <div className="director-film-grid">
        <section className="director-film-panel">
          <h3>Direct the action</h3>
          <p className="film-muted">Choose a performer or object, or direct
            changes to the scene around them.</p>
          <label>Who or what?
            <select value={selectedObject} onChange={e=>setSelectedObject(e.target.value)}>
              <option value="">The environment</option>
              {objects.filter(o=>['actor','prop','set','environment'].includes(o.role))
                .map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
          <label>What happens?
            <select value={kind} onChange={e=>setKind(e.target.value)}>
              {options.map(([value,label])=><option key={value} value={value}>
                {label}</option>)}
            </select>
          </label>
          <div className="director-film-time-inputs">
            <label>Start (seconds)
              <input type="number" min="0" max={film.duration_seconds}
                step=".1" value={startSeconds}
                onChange={e=>setStartSeconds(e.target.value)}/></label>
            <label>End (seconds)
              <input type="number" min="0" max={film.duration_seconds}
                step=".1" value={endSeconds}
                onChange={e=>setEndSeconds(e.target.value)}/></label>
          </div>
          {MOTION.has(kind)&&<AxisFields label="Where should it end up?"
            values={target} onChange={setTarget}/>}
          {AMBIENT.has(kind)&&<label>Strength
            <input type="range" min="0" max="10" step=".25"
              value={intensity} onChange={e=>setIntensity(Number(e.target.value))}/>
            <small>{intensity} / 10</small></label>}
          <label>Direction note (optional)
            <textarea className="director-film-direction-target"
              rows={3} maxLength={1000} value={note}
              onChange={e=>setNote(e.target.value)}
              placeholder="Describe the timing, intention or mood…"/>
          </label>
          <div className="film-actions"><button className="film-primary"
            disabled={busy||!film.work_current||!!take}
            onClick={addEvent}>Add Direction</button></div>
          <details className="director-film-directions" open={film.events.length<7}>
            <summary>Performance directions ({film.events.length})</summary>
            {film.events.length===0?<p className="film-muted">
              No movement or scene events have been directed yet. A quiet,
              actor-free scene is also a valid performance.</p>:
              <ul>{film.events.map(e=><li key={e.id}>
                <strong>{e.kind.replaceAll('_',' ')}</strong> · {
                  e.start_seconds}–{e.end_seconds}s
                {e.note&&<p>{e.note}</p>}
                <button className="film-link" disabled={busy||!!take}
                  onClick={()=>removeEvent(e.id)}>Remove</button>
              </li>)}</ul>}
          </details>
        </section>
        <section className="director-film-panel">
          <h3>Record original sound</h3>
          <p className="film-muted">Record a voice, footsteps, room tone, wind
            or other actual sound using your microphone. Sound is kept as
            original recordings, not flattened into a movie.</p>
          <label>Sound belongs to
            <select value={micActor} disabled={!!recordSession}
              onChange={e=>setMicActor(e.target.value)}>
              <option value="">The scene or environment</option>
              {actorObjects.map(o=><option key={o.actor_id}
                value={o.actor_id}>{o.name}</option>)}
            </select></label>
          <div className="film-actions">
            {!recordSession?<button className="film-primary"
              disabled={busy||!film.work_current}
              onClick={startMicrophone}>Start Sound Recording</button>:
              <>
                <button className="film-primary" onClick={stopMicrophone}
                  disabled={busy}>Stop and Save Recording</button>
                <button className="film-secondary" onClick={cancelMicrophone}
                  disabled={busy}>Cancel Recording</button>
              </>}
          </div>
          {recordSession&&<p className="director-film-recording" role="status">
            Recording original sound… Maximum two minutes per clip.</p>}
          <h4>Original recordings</h4>
          {clips.length===0?<p className="film-muted">
            No original sound has been recorded yet. Silent scenes are allowed.</p>:
            <div className="director-film-clips">{clips.map(clip=><label key={clip.id}>
              <input type="checkbox" disabled={!!take}
                checked={selectedClips.includes(clip.id)}
                onChange={e=>setSelectedClips(old=>e.target.checked?
                  [...old,clip.id]:old.filter(id=>id!==clip.id))}/>
              {clip.actor_id?'Performer sound':'Scene sound'} · {
                clip.seconds}s
            </label>)}</div>}
          <div className="director-film-duration">
            <h4>Scene duration</h4>
            <div className="director-film-time-inputs">
              <input type="number" min="5" max="1800" step="1"
                aria-label="Scene duration in seconds"
                value={duration} onChange={e=>setDuration(e.target.value)}/>
              <button className="film-secondary" disabled={busy||!!take}
                onClick={changeDuration}>Set Duration</button>
            </div>
          </div>
          <div className="director-film-freeze">
            <h4>Make a Digital Take</h4>
            <p className="film-muted">Freeze this performance and the selected
              original sounds. You can film another Take or reframe later.</p>
            <div className="film-actions">
              <button className="film-secondary" disabled={busy||!!recordSession}
                onClick={retake}>Start a Retake</button>
              <button className="film-primary" disabled={busy||!!recordSession||
                !film.work_current} onClick={freeze}>Freeze Digital Take</button>
            </div>
          </div>
        </section>
      </div>
      <section className="director-film-takes">
        <h3>Recorded Takes</h3>
        {(film.takes||[]).length===0?<p className="film-muted">
          No original Takes have been frozen for this scene yet.</p>:
          <div className="director-film-take-list">{film.takes.map((record,i)=>
            <button key={record.id} aria-pressed={takeId===record.id}
              className={takeId===record.id?'selected':''}
              onClick={()=>chooseTake(record.id)}>
              Take {film.takes.length-i} · {new Date(record.created_at).toLocaleString()}
            </button>)}</div>}
        {take&&<section className="director-film-camera">
          <h4>Choose the framing</h4>
          <p className="film-muted">Wide, medium and close-up are three suggested
            views. Moving a camera does not change the original Take.</p>
          <div className="director-film-view-tabs">
            {frameLabels.map((v,i)=><button key={v}
              className={i===activeView?'selected':''}
              aria-pressed={i===activeView}
              onClick={()=>setActiveView(i)}>{v}</button>)}
          </div>
          <label>Lens (mm)
            <input type="number" min="12" max="180" step="1"
              value={views[activeView]?.focal_mm||35}
              onChange={e=>cameraField('focal_mm',Number(e.target.value))}/></label>
          <AxisFields label="Camera location"
            values={views[activeView]?.position||[0,0,5]}
            onChange={v=>cameraField('position',v)}/>
          <AxisFields label="Camera points toward"
            values={views[activeView]?.look_at||[0,0,1]}
            onChange={v=>cameraField('look_at',v)}/>
          <div className="film-actions"><button className="film-secondary"
            disabled={busy} onClick={saveCamera}>Save Camera View</button></div>
          <p className="film-hint">Your original scene, performance and sound
            remain unchanged when you save a new camera view.</p>
        </section>}
      </section>
    </>}
  </section>;
}
