import React,{useEffect,useMemo,useRef,useState} from 'react';
import * as THREE from 'three';
import './director-film-editor.css';

const EPS=.0001;
const TPS=7056000000;
const emptyCamera={name:'Custom view',focal_mm:50,position:[8,-12,5],look_at:[0,0,1.5]};
const defaultGrade={exposure:0,saturation:1,warmth:0,contrast:1};

async function directorCall(url,method='GET',body,signal){
  const response=await fetch(url,{
    method,credentials:'same-origin',signal,
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw new Error(typeof error.detail==='string'?error.detail:
      'That editing change could not be saved. Your previous version remains safe.');
  }
  return response.json();
}
const seconds=t=>Number(t||0).toFixed(2);
const timeLabel=t=>{
  const value=Math.max(0,Number(t)||0);
  const min=Math.floor(value/60);
  return String(min).padStart(2,'0')+':'+(value-min*60).toFixed(2).padStart(5,'0');
};
function modelGeometry(shape){
  switch(shape){
    case 'sphere':
    case 'sun':
    case 'lamp':return new THREE.SphereGeometry(.5,14,12);
    case 'cone':return new THREE.ConeGeometry(.5,1,12).rotateX(Math.PI/2);
    case 'cylinder':return new THREE.CylinderGeometry(.5,.5,1,14).rotateX(Math.PI/2);
    case 'camera':return new THREE.ConeGeometry(.42,1,4).rotateX(Math.PI/2);
    default:return new THREE.BoxGeometry(1,1,1);
  }
}
function NativeShotCanvas({shot}){
  const ref=useRef(null);
  const [unavailable,setUnavailable]=useState(false);
  useEffect(()=>{
    const host=ref.current;if(!host||!shot)return;
    let renderer=null,observer=null;
    let meshes=[];
    try{
      renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));
      renderer.outputColorSpace=THREE.SRGBColorSpace;
      host.appendChild(renderer.domElement);
      const scene=new THREE.Scene();
      const dusk=shot.scene_setting?.daylight==='dusk';
      const night=shot.scene_setting?.daylight==='night';
      scene.background=new THREE.Color(night?'#151b2a':
        dusk?'#866e82':'#86adc4');
      scene.add(new THREE.AmbientLight(0xffffff,night?.55:1.5));
      const light=new THREE.DirectionalLight(0xffe9cc,night?.5:2.1);
      light.position.set(-7,-6,13);scene.add(light);
      const ambient=shot.active_events||[];
      if(ambient.some(e=>e.kind==='fog')||shot.scene_setting?.weather==='fog'){
        scene.fog=new THREE.FogExp2(night?0x111827:0xbccbd0,.038);
      }
      for(const object of shot.objects||[]){
        const group=new THREE.Group();
        const mat=new THREE.MeshStandardMaterial({
          color:new THREE.Color(object.color||'#a8b5bb'),
          roughness:.8,side:THREE.DoubleSide});
        const obj=new THREE.Mesh(modelGeometry(object.shape),mat);
        group.add(obj);
        meshes.push(obj);
        if(object.role==='actor'){
          const head=new THREE.Mesh(new THREE.SphereGeometry(.4,12,8),
            mat.clone());
          head.position.z=.45;group.add(head);meshes.push(head);
        }
        group.position.set(...object.position);
        group.rotation.set(...(object.rotation||[0,0,0]).map(v=>
          THREE.MathUtils.degToRad(v)));
        group.scale.set(...object.scale);
        scene.add(group);
      }
      const camera=new THREE.PerspectiveCamera(50,1,.08,450);
      camera.up.set(0,0,1);
      camera.position.set(...shot.camera.position);
      camera.lookAt(...shot.camera.look_at);
      const render=()=>{
        const width=Math.max(300,Math.floor(host.clientWidth||720));
        const height=Math.max(240,Math.min(520,Math.round(width*.56)));
        camera.aspect=width/height;
        camera.fov=2*Math.atan(24/(2*shot.camera.focal_mm))*180/Math.PI;
        camera.updateProjectionMatrix();
        renderer.setSize(width,height);
        renderer.render(scene,camera);
      };
      if(typeof ResizeObserver!=='undefined'){
        observer=new ResizeObserver(render);observer.observe(host);
      }
      render();
      setUnavailable(false);
    }catch(error){
      setUnavailable(true);
    }
    return()=>{
      observer?.disconnect();
      for(const obj of meshes){obj.geometry.dispose();obj.material.dispose()}
      renderer?.dispose();
      if(renderer&&host.contains(renderer.domElement))host.removeChild(renderer.domElement);
    };
  },[shot]);
  const grade=shot.grade||defaultGrade;
  return <div ref={ref} className="film-editor-native-shot"
    style={{filter:[
      'brightness('+Math.max(.06,Math.min(5,Math.pow(2,grade.exposure)))+')',
      'saturate('+grade.saturation+')',
      'contrast('+grade.contrast+')',
      'sepia('+Math.max(0,grade.warmth)*.19+')',
      'hue-rotate('+(-grade.warmth*8)+'deg)'
    ].join(' ')}}>
    {unavailable&&<p role="status">The visual preview is unavailable on this
      display. Your original 3D recording and camera choices remain saved.</p>}
  </div>;
}
function PicturePreview({sample,working,position}){
  const layers=sample?.shots||[];
  return <div className="film-editor-monitor">
    {layers.length?layers.map((shot,i)=><div className="film-editor-shot-layer"
      key={shot.clip_id+':'+i}
      style={{opacity:i===0?1:shot.opacity}}>
      <NativeShotCanvas shot={shot}/>
    </div>):<div className="film-editor-empty-monitor">
      <icon aria-hidden="true">◇</icon>
      <strong>{working?'Preparing your selected shot…':'Choose a recorded Take to begin editing'}</strong>
      <span>The original recording remains unchanged.</span>
    </div>}
    <div className="film-editor-monitor-bottom">
      <span>FILM PREVIEW</span><span>{timeLabel(position)}</span>
    </div>
  </div>;
}
function ThreeFields({label,values,onChange}){
  const v=Array.isArray(values)?values:[0,0,0];
  return <fieldset className="film-editor-axis">
    <legend>{label}</legend>
    {['X','Y','Z'].map((axis,index)=><label key={axis}>
      {axis}<input type="number" step=".1" min="-150" max="150"
        value={v[index]}
        onChange={e=>onChange(v.map((n,i)=>i===index?
          Number(e.target.value):n))}/>
    </label>)}
  </fieldset>;
}
function TakePicker({takes,value,onChange,sceneTitles}){
  return <select aria-label="Select a frozen Take" value={value}
    onChange={e=>onChange(e.target.value)}>
    <option value="">Choose a recorded Take</option>
    {takes.map((take,i)=><option key={take.take_id} value={take.take_id}
      disabled={!take.available}>
      {sceneTitles[take.scene_id]||'Scene'} · Take {takes.length-i}
      {take.available?'':' — needs attention'}
    </option>)}
  </select>;
}
function SoundTrackControls({audio,onChange}){
  return <div className="film-editor-sounds">
    {!audio?.length&&<p className="film-muted">
      This Take contains no original sound. Silence is a valid choice.</p>}
    {(audio||[]).map((source,i)=><article key={source.clip_id}
      className="film-editor-sound-source">
      <label className="film-editor-check"><input type="checkbox"
        checked={source.enabled}
        onChange={e=>onChange(audio.map((x,j)=>j===i?
          {...x,enabled:e.target.checked}:x))}/>
        Original sound {i+1}
      </label>
      <label>Volume
        <input type="range" min="0" max="4" step=".05" value={source.gain}
          onChange={e=>onChange(audio.map((x,j)=>j===i?
            {...x,gain:Number(e.target.value)}:x))}/>
        <small>{Math.round(source.gain*100)}%</small>
      </label>
      <label>Position left / right
        <input type="range" min="-1" max="1" step=".05" value={source.pan}
          onChange={e=>onChange(audio.map((x,j)=>j===i?
            {...x,pan:Number(e.target.value)}:x))}/>
      </label>
      <label className="film-editor-check"><input type="checkbox"
        checked={source.spatial}
        onChange={e=>onChange(audio.map((x,j)=>j===i?
          {...x,spatial:e.target.checked}:x))}/>
        Keep natural scene-space sound
      </label>
      <label>Sound timing adjustment (seconds)
        <input type="number" step=".01" min="-1800" max="1800"
          value={Number((source.offset_tick/TPS).toFixed(2))}
          onChange={e=>{
            const ticks=Math.round(Number(e.target.value)*TPS);
            onChange(audio.map((x,j)=>j===i?{...x,offset_tick:ticks}:x));
          }}/>
      </label>
    </article>)}
  </div>;
}

export default function DirectorFilmEditor({movie}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/edit';
  const [edit,setEdit]=useState(null);
  const [scenes,setScenes]=useState({});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [pendingPreview,setPendingPreview]=useState(false);
  const [sample,setSample]=useState(null);
  const [position,setPosition]=useState(0);
  const [playing,setPlaying]=useState(false);
  const [takeChoice,setTakeChoice]=useState('');
  const [aiAvailable,setAiAvailable]=useState(false);
  const [aiDirection,setAiDirection]=useState('');
  const [selectedId,setSelectedId]=useState(null);
  const [dragId,setDragId]=useState(null);
  const [trimIn,setTrimIn]=useState('0');
  const [trimOut,setTrimOut]=useState('0');
  const [splitAt,setSplitAt]=useState('0');
  const [transition,setTransition]=useState({kind:'cut',seconds:'0'});
  const [camera,setCamera]=useState(emptyCamera);
  const [grade,setGrade]=useState(defaultGrade);
  const [audio,setAudio]=useState([]);
  const [note,setNote]=useState('');
  const [title,setTitle]=useState('');
  const [filmNotes,setFilmNotes]=useState('');
  const [master,setMaster]=useState(1);
  const [listenUrl,setListenUrl]=useState('');
  const [showHistory,setShowHistory]=useState(false);
  const busyRef=useRef(false);
  const previewController=useRef(null);
  const audioController=useRef(null);

  useEffect(()=>{
    let active=true;
    directorCall('/api/creative/models').then(result=>{
      if(active)setAiAvailable(result.state==='available');
    }).catch(()=>{if(active)setAiAvailable(false)});
    return()=>{active=false};
  },[]);

  useEffect(()=>{
    let live=true;
    directorCall(base).then(data=>{if(live){
      setEdit(data);setTitle(data.title);
      setFilmNotes(data.notes);setMaster(data.master_gain);
      if(data.available_takes?.length)setTakeChoice(
        data.available_takes.find(x=>x.available)?.take_id||'');
    }}).catch(e=>{if(live)setError(e.message)});
    directorCall('/api/projects/'+encodeURIComponent(movie.id)+
      (movie.encrypted?'/live':'')+'/preproduction').then(out=>{
        if(live)setScenes(Object.fromEntries((out.scenes||[]).map(s=>
          [s.id,s.heading])));
      }).catch(()=>{});
    return()=>{live=false;
      previewController.current?.abort();
      audioController.current?.abort();
    };
  },[base,movie.revision]);

  useEffect(()=>{
    return()=>{if(listenUrl)URL.revokeObjectURL(listenUrl)};
  },[listenUrl]);

  const selected=edit?.clips?.find(c=>c.id===selectedId)||null;
  const selectedSegment=edit?.timeline?.find(c=>c.clip_id===selectedId)||null;
  useEffect(()=>{
    if(!edit)return;
    if(selectedId&&!edit.clips.some(c=>c.id===selectedId)){
      setSelectedId(edit.clips[0]?.id||null);
    }else if(!selectedId&&edit.clips.length)setSelectedId(edit.clips[0].id);
  },[edit?.revision]);

  useEffect(()=>{
    if(!selected)return;
    setTrimIn(seconds(selected.source_in_tick/TPS));
    setTrimOut(seconds(selected.source_out_tick/TPS));
    setSplitAt(seconds((selected.source_in_tick+
      selected.source_out_tick)/(2*TPS)));
    setTransition({kind:selected.transition.kind,
      seconds:seconds(selected.transition.duration_tick/TPS)});
    setCamera(JSON.parse(JSON.stringify(selected.camera)));
    setGrade({...selected.grade});
    setAudio(selected.audio.map(v=>({...v})));
    setNote(selected.note);
  },[selected?.id,edit?.revision]);

  const previewTick=useMemo(()=>Math.max(0,Math.floor(position*4)/4),
    [position]);
  useEffect(()=>{
    if(!edit?.timeline?.length||edit.missing_sources?.length){
      setSample(null);return;
    }
    previewController.current?.abort();
    const controller=new AbortController();
    previewController.current=controller;
    const timer=window.setTimeout(()=>{
      setPendingPreview(true);
      directorCall(base+'/picture?seconds='+encodeURIComponent(
        String(previewTick)),'GET',undefined,controller.signal)
        .then(data=>{if(!controller.signal.aborted)setSample(data)})
        .catch(err=>{if(err.name!=='AbortError'&&!controller.signal.aborted){
          setError(err.message);setSample(null);
        }}).finally(()=>{if(!controller.signal.aborted)
          setPendingPreview(false)});
    },110);
    return()=>{window.clearTimeout(timer);controller.abort()};
  },[base,edit?.revision,previewTick,edit?.missing_sources?.length]);

  useEffect(()=>{
    if(!playing||!edit?.duration_seconds)return;
    const start=performance.now();
    const original=position;
    let frame=0;
    const step=()=>{
      const current=Math.min(edit.duration_seconds,
        original+(performance.now()-start)/1000);
      setPosition(current);
      if(current>=edit.duration_seconds){setPlaying(false);return}
      frame=window.requestAnimationFrame(step);
    };
    frame=window.requestAnimationFrame(step);
    return()=>window.cancelAnimationFrame(frame);
  },[playing,edit?.duration_seconds]);

  async function commit(operation,details,success){
    if(busyRef.current||!edit)return;
    busyRef.current=true;setBusy(true);setError('');setNotice('');
    setPlaying(false);
    previewController.current?.abort();
    try{
      const result=await directorCall(base+'/change','POST',{
        expected_revision:edit.revision,operation,details});
      setEdit(result);
      setPosition(v=>Math.min(v,result.duration_seconds));
      if(success)setNotice(success);
      return result;
    }catch(e){setError(e.message);
      // Reopen the source of truth rather than continue with stale revisions.
      try{setEdit(await directorCall(base))}catch(_){}
    }finally{busyRef.current=false;setBusy(false)}
    return null;
  }
  async function askEditingAI(){
    if(!aiAvailable||!edit||busyRef.current)return;
    busyRef.current=true;setBusy(true);setError('');
    setNotice('Preparing some editing ideas for you to review…');
    try{
      const result=await directorCall(base+'/ideas','POST',{direction:aiDirection});
      setEdit(result);
      setNotice((result.ai_suggestions||[]).some(i=>i.status==='proposed')?
        'Editing ideas are ready. You choose whether to use them.':
        'The film assistant had no additional changes to suggest.');
    }catch(e){setError(e.message)}
    finally{busyRef.current=false;setBusy(false)}
  }
  async function decideEditingAI(idea,decision){
    if(busyRef.current||!edit)return;
    busyRef.current=true;setBusy(true);setError('');
    try{
      const result=await directorCall(base+'/ideas/'+idea.id+'/decision','POST',{
        expected_revision:edit.revision,decision});
      setEdit(result);
      setNotice(decision==='accept'?
        'Your approved editorial suggestion is saved as a new edit version.':
        'Suggestion declined. Your film edit is unchanged.');
    }catch(e){setError(e.message)}
    finally{busyRef.current=false;setBusy(false)}
  }

  async function restore(version){
    if(!window.confirm('Restore this earlier film edit? All current and previous versions will remain saved.'))return;
    if(busyRef.current)return;
    busyRef.current=true;setBusy(true);setError('');
    try{
      const result=await directorCall(base+'/restore','POST',{
        expected_revision:edit.revision,source_revision:version});
      setEdit(result);setPosition(0);setPlaying(false);
      setNotice('An earlier edit was restored as a new version.');
    }catch(e){setError(e.message)}
    finally{busyRef.current=false;setBusy(false)}
  }
  async function listen(){
    if(!edit?.clips.length)return;
    audioController.current?.abort();
    const controller=new AbortController();audioController.current=controller;
    setError('');setNotice('Preparing a listening preview from the original sound…');
    try{
      const span=Math.min(5,Math.max(.01,edit.duration_seconds-position));
      const url=base+'/sound?start_seconds='+encodeURIComponent(
        Number(position.toFixed(2)))+'&duration_seconds='+
        encodeURIComponent(Number(span.toFixed(2)));
      const response=await fetch(url,{signal:controller.signal,
        credentials:'same-origin',headers:{'x-nvp-director':'1'}});
      if(!response.ok){
        const body=await response.json().catch(()=>({}));
        throw new Error(body.detail||'Sound preview could not be prepared');
      }
      const blob=await response.blob();
      if(blob.type!=='audio/wav')throw new Error('Original sound is not available');
      if(!controller.signal.aborted){
        setListenUrl(URL.createObjectURL(blob));
        setNotice('Listen to the chosen scene moment. The original is unchanged.');
      }
    }catch(e){if(e.name!=='AbortError')setError(e.message)}
  }
  function cancelPreview(){
    previewController.current?.abort();audioController.current?.abort();
    setPendingPreview(false);setPlaying(false);
    setNotice('Preview stopped. Your edits and original Takes are safe.');
  }
  const total=edit?.duration_seconds||0;
  const active=edit?.timeline?.find(seg=>position>=seg.start_seconds-
    EPS&&position<seg.end_seconds-EPS);
  function selectClip(clipId){
    setSelectedId(clipId);
    const seg=edit.timeline.find(s=>s.clip_id===clipId);
    if(seg){setPosition(seg.start_seconds);setPlaying(false)}
  }

  return <div className="film-editor-shell" aria-label="Edit Film">
    <div className="film-editor-toolbar">
      <div>
        <div className="film-eyebrow">YOUR EDITING ROOM</div>
        <h2>Make your movie</h2>
        <p className="film-muted">Choose original Takes, arrange scenes, shape the
          picture and sound. Nothing you do here changes what you filmed.</p>
      </div>
      <div className="film-editor-save-state">{busy?
        'Saving your edit…':edit?'Edit saved · Version '+edit.revision:
          'Opening your film…'}</div>
    </div>
    {error&&<div className="film-editor-error" role="alert">{error}</div>}
    {notice&&<div className="film-editor-notice" role="status">{notice}</div>}
    {edit?.missing_sources?.length>0&&<div className="film-editor-warning"
      role="alert">Some original footage or sound needs attention.
      Your saved edit remains intact. NVP will not substitute preview
      media or export a film with missing sources.
      <p>{edit.missing_sources.join(' · ')}</p></div>}
    {!edit&&!error&&<p role="status">Opening the film editing room…</p>}
    {edit&&<>
      <section className="film-editor-monitor-area">
        <PicturePreview sample={sample} working={pendingPreview}
          position={position}/>
        <div className="film-editor-transport">
          <button className="film-secondary" disabled={!edit.clips.length}
            onClick={()=>{
              if(position>=total-.01)setPosition(0);
              setPlaying(v=>!v);
            }}>{playing?'Pause':'Play preview'}</button>
          <button className="film-secondary" onClick={cancelPreview}
            disabled={!playing&&!pendingPreview}>Stop Preview</button>
          <input type="range" min="0" max={total||1} step=".05"
            value={Math.min(position,total||0)}
            disabled={!total} aria-label="Film playhead position"
            onChange={e=>{setPlaying(false);
              setPosition(Number(e.target.value))}}/>
          <span className="film-editor-time">{timeLabel(position)}
            {' / '}{timeLabel(total)}</span>
          <button className="film-secondary"
            disabled={!edit.clips.length||!!edit.missing_sources.length}
            onClick={listen}>Listen to Sound</button>
        </div>
        {listenUrl&&<audio className="film-editor-listen-player"
          controls autoPlay preload="none" src={listenUrl}>
          Your device could not play this sound preview.
        </audio>}
        <p className="film-hint">This visual workspace previews native 3D source
          at the selected time. Final picture and mastered sound are created
          in the Export Film stage.</p>
      </section>
      <section className="film-editor-assembly">
        <div className="film-editor-section-heading"><h3>Assemble your film</h3>
          <span>{edit.clips.length} {edit.clips.length===1?'shot':'shots'}</span></div>
        <div className="film-editor-add-take">
          <TakePicker takes={edit.available_takes||[]} value={takeChoice}
            onChange={setTakeChoice} sceneTitles={scenes}/>
          <button className="film-primary" disabled={busy||!takeChoice||
            !!edit.missing_sources.length}
            onClick={()=>commit('append',{take_id:takeChoice},
              'The original Take was added to your film.')}>
            Add Take to Film</button>
        </div>
        {!edit.available_takes?.some(t=>t.available)&&<p className="film-muted">
          No frozen Takes are available yet. Record and freeze a scene in
          Film Scenes, then return here.</p>}
        <div className="film-editor-timeline" role="group"
          aria-label="Film edit sequence">
          {edit.timeline.map((seg,index)=><button
            key={seg.clip_id} draggable={!busy}
            onDragStart={()=>setDragId(seg.clip_id)}
            onDragOver={event=>event.preventDefault()}
            onDrop={e=>{
              e.preventDefault();
              if(!dragId||dragId===seg.clip_id)return;
              commit('move',{clip_id:dragId,to_index:index},
                'The film's shot order was updated.');
              setDragId(null);
            }}
            className={'film-editor-strip '+(selectedId===seg.clip_id?
              'selected':'')}
            style={{flexGrow:Math.max(1,seg.duration_seconds)}}
            aria-pressed={selectedId===seg.clip_id}
            onClick={()=>selectClip(seg.clip_id)}>
            <small>Shot {index+1}</small>
            <strong>{scenes[seg.scene_id]||'Recorded scene'}</strong>
            <span>{seg.duration_seconds.toFixed(2)}s</span>
            {seg.transition.kind==='dissolve'&&<em>Soft transition</em>}
          </button>)}
          {!edit.timeline.length&&<div className="film-editor-empty-sequence">
            Add a frozen Take above to create the first shot of your movie.
          </div>}
        </div>
        {edit.timeline.length>0&&<div className="film-editor-timeline-help">
          Select a shot to edit it. Drag shots to rearrange them, or use
          the move controls below.</div>}
      </section>
      <section className="film-editor-assistant">
        <div className="film-editor-section-heading">
          <div><h3>Ask for editing ideas</h3>
            <p className="film-muted">NVP can suggest a different shot order,
              softer cut or color mood. Every change needs your approval.</p>
          </div>
          <button className="film-secondary" disabled={
            busy||!aiAvailable||!edit.clips.length||!!edit.missing_sources.length}
            onClick={askEditingAI}>Ask AI for Suggestions</button>
        </div>
        {aiAvailable&&<label>What would you like to improve? (optional)
          <input maxLength={700} value={aiDirection}
            placeholder="A slower beginning, more tension, warmer outdoor colors…"
            onChange={e=>setAiDirection(e.target.value)}/>
        </label>}
        {!aiAvailable&&<p className="film-hint">
          AI assistance is unavailable right now. All editing controls
          are still available.</p>}
        <div className="film-editor-ai-ideas">
          {(edit.ai_suggestions||[]).filter(i=>i.status==='proposed').map(idea=>
            <article key={idea.id}>
              <strong>{({
                move_earlier:'Move this shot earlier',
                move_later:'Move this shot later',
                soft_dissolve:'Try a soft transition',
                warmer_color:'Make this shot warmer',
                cooler_color:'Make this shot cooler'
              })[idea.kind]||'Editing suggestion'}</strong>
              <p>{idea.reason}</p>
              <div className="film-actions">
                <button className="film-secondary" disabled={busy}
                  onClick={()=>decideEditingAI(idea,'reject')}>Decline</button>
                <button className="film-primary" disabled={busy}
                  onClick={()=>decideEditingAI(idea,'accept')}>Approve Change</button>
              </div>
            </article>)}
        </div>
      </section>
      <div className="film-editor-layout">
        <section className="film-editor-panel">
          <h3>Shape the selected shot</h3>
          {!selected?<p className="film-muted">
            Select a shot in your film to trim, reframe, grade or mix it.</p>:<>
            <div className="film-editor-quick-actions">
              <button className="film-secondary" disabled={busy||
                edit.clips.findIndex(c=>c.id===selectedId)===0}
                onClick={()=>commit('move',{
                  clip_id:selected.id,
                  to_index:Math.max(0,edit.clips.findIndex(c=>
                    c.id===selectedId)-1)},'Shot moved earlier.')}>
                Move Earlier</button>
              <button className="film-secondary" disabled={busy||
                edit.clips.findIndex(c=>c.id===selectedId)===edit.clips.length-1}
                onClick={()=>commit('move',{
                  clip_id:selected.id,
                  to_index:Math.min(edit.clips.length-1,
                    edit.clips.findIndex(c=>c.id===selectedId)+1)},
                    'Shot moved later.')}>Move Later</button>
              <button className="film-secondary" disabled={busy}
                onClick={()=>commit('duplicate',{clip_id:selected.id},
                  'Shot duplicated without copying the original recording.')}>
                Repeat Shot</button>
              <button className="film-secondary" disabled={busy}
                onClick={()=>{
                  if(window.confirm('Remove this shot from your edit? The original Take will remain.'))
                    commit('remove',{clip_id:selected.id},
                      'Shot removed from the edit. Original recording preserved.');
                }}>Remove From Film</button>
            </div>
            <label>Choose another original Take for this shot
              <TakePicker takes={edit.available_takes||[]} value={takeChoice}
                onChange={setTakeChoice} sceneTitles={scenes}/>
            </label>
            <button className="film-secondary" disabled={busy||!takeChoice||
              takeChoice===selected.take_id}
              onClick={()=>commit('replace_take',{
                clip_id:selected.id,take_id:takeChoice},
                'Replacement Take selected. The original remains available.')}>
              Use This Take Instead</button>
            <div className="film-editor-inspector-block">
              <h4>Cut and trim</h4>
              <p className="film-muted">Choose the portion of the original
                performance you want audiences to see.</p>
              <div className="film-editor-two-inputs">
                <label>Start in Take (seconds)
                  <input type="number" min="0" step=".01" value={trimIn}
                    onChange={e=>setTrimIn(e.target.value)}/></label>
                <label>End in Take (seconds)
                  <input type="number" min="0" step=".01" value={trimOut}
                    onChange={e=>setTrimOut(e.target.value)}/></label>
              </div>
              <button className="film-secondary" disabled={busy}
                onClick={()=>commit('trim',{
                  clip_id:selected.id,in_seconds:trimIn,out_seconds:trimOut
                },'Your trim is saved. The original performance is unchanged.')}>
                Apply Trim</button>
              <div className="film-editor-inline-split">
                <label>Split at source time (seconds)
                  <input type="number" min="0" step=".01"
                    value={splitAt} onChange={e=>setSplitAt(e.target.value)}/>
                </label>
                <button className="film-secondary" disabled={busy}
                  onClick={()=>commit('split',{clip_id:selected.id,
                    at_seconds:splitAt},'A new editable shot was created from the same Take.')}>
                  Split Shot</button>
              </div>
            </div>
            <div className="film-editor-inspector-block">
              <h4>Between this and the previous shot</h4>
              <div className="film-editor-two-inputs">
                <label>Transition
                  <select value={transition.kind}
                    onChange={e=>setTransition(v=>({...v,kind:e.target.value,
                      seconds:e.target.value==='cut'?'0':v.seconds==='0'?'.5':v.seconds}))}>
                    <option value="cut">Straight cut</option>
                    <option value="dissolve">Soft dissolve</option>
                  </select></label>
                {transition.kind==='dissolve'&&<label>Length (seconds)
                  <input type="number" step=".01" min=".01" max="20"
                    value={transition.seconds}
                    onChange={e=>setTransition(v=>({...v,
                      seconds:e.target.value}))}/>
                </label>}
              </div>
              <button className="film-secondary" disabled={busy||
                edit.clips[0].id===selected.id}
                onClick={()=>commit('transition',{
                  clip_id:selected.id,kind:transition.kind,
                  seconds:transition.kind==='cut'?'0':transition.seconds
                },'The transition has been saved.')}>Save Transition</button>
            </div>
            <div className="film-editor-inspector-block">
              <h4>Editorial note</h4>
              <textarea rows={2} maxLength={600} value={note}
                onChange={e=>setNote(e.target.value)}
                placeholder="What should this shot communicate?"/>
              <button className="film-secondary" disabled={busy}
                onClick={()=>commit('note',{clip_id:selected.id,note},
                  'Your editorial direction is saved.')}>Save Note</button>
            </div>
          </>}
        </section>
        <section className="film-editor-panel">
          <h3>Picture and sound</h3>
          {!selected?<p className="film-muted">
            Choose a shot to shape the camera, colors and original sound.</p>:<>
            <details open className="film-editor-inspector-block">
              <summary>Camera and framing</summary>
              <p className="film-muted">Move the camera or change the lens
                after filming. The recorded performance stays the same.</p>
              <label>Lens (mm)
                <input type="number" min="12" max="180" step="1"
                  value={camera.focal_mm}
                  onChange={e=>setCamera(v=>({...v,
                    focal_mm:Number(e.target.value)}))}/></label>
              <ThreeFields label="Camera position" values={camera.position}
                onChange={v=>setCamera(c=>({...c,position:v}))}/>
              <ThreeFields label="Look toward" values={camera.look_at}
                onChange={v=>setCamera(c=>({...c,look_at:v}))}/>
              <button className="film-primary" disabled={busy}
                onClick={()=>commit('camera',{clip_id:selected.id,camera},
                  'This shot was reframed without changing the original Take.')}>
                Save Framing</button>
            </details>
            <details open className="film-editor-inspector-block">
              <summary>Picture color</summary>
              <p className="film-muted">Refine mood and visual consistency.
                These are editable look decisions, not changes to the source.</p>
              {[
                ['exposure','Brightness',-4,4,.1],
                ['contrast','Contrast',.25,2.5,.05],
                ['saturation','Color intensity',0,2,.05],
                ['warmth','Warm / cool',-1,1,.05]
              ].map(([field,label,min,max,step])=><label key={field}>
                {label}<input type="range" min={min} max={max} step={step}
                  value={grade[field]}
                  onChange={e=>setGrade(g=>({...g,
                    [field]:Number(e.target.value)}))}/>
                <small>{Number(grade[field]).toFixed(2)}</small>
              </label>)}
              <button className="film-secondary" disabled={busy}
                onClick={()=>commit('grade',{clip_id:selected.id,grade},
                  'Your picture color decisions were saved.')}>
                Save Picture Look</button>
            </details>
            <details open className="film-editor-inspector-block">
              <summary>Original sound</summary>
              <p className="film-muted">Adjust each recording's volume,
                spatial placement, timing or silence. NVP preserves the
                original sound samples.</p>
              <SoundTrackControls audio={audio} onChange={setAudio}/>
              <button className="film-secondary" disabled={busy}
                onClick={()=>commit('audio',{clip_id:selected.id,audio},
                  'Sound choices saved without altering original recordings.')}>
                Save Sound Mix</button>
            </details>
          </>}
        </section>
      </div>
      <section className="film-editor-footer-panel">
        <div><h3>Movie-wide sound</h3>
          <p className="film-muted">Adjust the volume of the assembled film.</p>
          <label>Overall volume
            <input type="range" min="0" max="4" step=".05" value={master}
              onChange={e=>setMaster(Number(e.target.value))}/>
            <span>{Math.round(master*100)}%</span>
          </label>
          <button className="film-secondary" disabled={busy}
            onClick={()=>commit('mix',{master_gain:master},
              'Overall sound level saved.')}>Save Overall Mix</button>
        </div>
        <div><h3>Movie notes</h3>
          <label>Working title<input maxLength={140} value={title}
            onChange={e=>setTitle(e.target.value)}/></label>
          <label>Editing notes<textarea rows={3} maxLength={2000}
            value={filmNotes} onChange={e=>setFilmNotes(e.target.value)}/></label>
          <button className="film-secondary" disabled={busy}
            onClick={()=>commit('film_details',{title,notes:filmNotes},
              'Your film's editorial notes were saved.')}>Save Film Notes</button>
        </div>
      </section>
      <section className="film-editor-history">
        <div className="film-editor-section-heading">
          <h3>Earlier edits</h3>
          <button className="film-secondary"
            onClick={()=>setShowHistory(v=>!v)}>
            {showHistory?'Hide versions':'View previous versions'}</button>
        </div>
        {showHistory&&<>
          <p className="film-muted">Bring back an earlier creative edit without
            losing this version or changing the original Takes.</p>
          <div className="film-editor-history-versions">
            {edit.history.filter(h=>h.revision!==edit.revision).map(h=>
              <div key={h.revision}>
                <span>Editing version {h.revision}</span>
                <button className="film-secondary" disabled={busy}
                  onClick={()=>restore(h.revision)}>Restore</button>
              </div>)}
            {!edit.history.some(h=>h.revision!==edit.revision)&&
              <p className="film-muted">There are no earlier edits yet.</p>}
          </div>
        </>}
      </section>
      <section className="film-editor-next">
        <strong>Next: Export Film</strong>
        <p className="film-muted">Your decisions are saved as a reusable film
          assembly. Final picture and sound will be produced in Export Film,
          without changing your original recordings.</p>
      </section>
    </>}
  </div>;
}
