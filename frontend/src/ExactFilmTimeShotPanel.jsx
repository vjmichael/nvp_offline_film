import React,{useEffect,useMemo,useRef,useState} from 'react';

// DA-01/DA-02: author one continuous 3D scene by exact integer Film Time.
// Camera shots are observations of that world, not recorded picture frames.
// Decimal seconds are only an author convenience; the transport exclusively
// uses exact *integer decimal strings* to avoid JS number rounding errors.
const T=7056000000n;
const US=7056n;
const MAX_TICK=(1n<<63n)-1n;

function exactTick(value){
  if(typeof value!=='string'||!/^(0|[1-9][0-9]*)$/.test(value))
    throw Error('Use a canonical nonnegative integer Film Time tick.');
  const n=BigInt(value);
  if(n>MAX_TICK)throw Error('Film Time exceeds signed 64-bit tick range.');
  return n;
}

function secondsFromTicks(value){
  const n=BigInt(value);
  const whole=n/T, fraction=n%T;
  if(fraction===0n)return whole.toString();
  // Film Time has sub-microsecond resolution. Preserve the exact tick
  // count as an explicit read-only value rather than rounding it in UI.
  if(fraction%US!==0n)return null;
  return whole.toString()+'.'+(fraction/US).toString().padStart(6,'0').replace(/0+$/,'');
}

function ticks(seconds){
  if(typeof seconds!=='string'||!/^(0|[1-9][0-9]{0,7})(?:\.\d{1,6})?$/.test(seconds))
    throw Error('Use nonnegative seconds with up to six decimal places.');
  const [whole,part='']=seconds.split('.');
  return (BigInt(whole)*T+BigInt(part.padEnd(6,'0')||'0')*US).toString();
}

const SHAPES=['continuous','master','single','two_shot',
 'over_shoulder','reaction','insert','tracking'];

export default function ExactFilmTimeShotPanel({project,api,action,busy}){
  const draftEpoch=useRef(0);
  const [scenes,setScenes]=useState([]);
  const [sceneId,setSceneId]=useState('');
  const [cameraPath,setCameraPath]=useState('');
  const [shots,setShots]=useState([]);
  const [duration,setDuration]=useState('60');
  const [exactDuration,setExactDuration]=useState(null);
  const [start,setStart]=useState('0');
  const [seconds,setSeconds]=useState('3');
  const [tickMode,setTickMode]=useState(false);
  const [startTick,setStartTick]=useState('0');
  const [lengthTick,setLengthTick]=useState((3n*T).toString());
  const [durationTick,setDurationTick]=useState((60n*T).toString());
  const [pattern,setPattern]=useState('continuous');
  const [revision,setRevision]=useState(0);
  const [timelineSha,setTimelineSha]=useState('');
  const [takeId,setTakeId]=useState('Take001');
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');
  const [native,setNative]=useState(null);
  const source=useMemo(()=>scenes.find(x=>x.scene_id===sceneId),[scenes,sceneId]);
  const timelineId=source?'Cuts'+source.document_sha256.slice(0,28):'';

  useEffect(()=>{
    const discover=()=>{
      const next=window.pywebview?.api;
      if(next&&typeof next.data_av_freeze_timed_take==='function')
        setNative(next);
    };
    discover();window.addEventListener('pywebviewready',discover);
    return ()=>window.removeEventListener('pywebviewready',discover);
  },[]);

  useEffect(()=>{
    let active=true;
    setSceneId('');setError('');setScenes([]);
    Promise.resolve(api('/projects/'+encodeURIComponent(project.id)+
      '/film/camera-scenes')).then(x=>{
      if(!active)return;
      if(x?.format!=='nvp.slate08.camera_source_list.v1'||
         x.project_id!==project.id||!Array.isArray(x.scenes))
        throw Error('Source list failed exact scene identity verification');
      setScenes(x.scenes);setSceneId(x.scenes[0]?.scene_id||'');
    }).catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[project.id,api]);

  useEffect(()=>{
    // Invalidate any pending publication belonging to the previous scene.
    draftEpoch.current++;
    setCameraPath(source?.cameras?.[0]?.path||'');
    setShots([]);setRevision(0);setTimelineSha('');setExactDuration(null);setTickMode(false);setNotice('');
    if(!source)return;
    let active=true;
    const loadingEpoch=draftEpoch.current;
    api('/projects/'+encodeURIComponent(project.id)+
        '/film/native-time-shots/'+encodeURIComponent(timelineId))
      .then(x=>{
        if(!active||draftEpoch.current!==loadingEpoch)return;
        if(x?.format!=='nvp.exact_time.usd_camera_shots.v1'||
           x.scene_id!==source.scene_id||
           x.scene_document_sha256!==source.document_sha256||
           x.video_frames_created!==false)
          throw Error('Saved exact-time sequence source identity mismatch');
        setShots(x.shots.map(s=>({shot_id:s.shot_id,
          camera_path:s.camera_path,pattern:s.pattern,
          start_tick:s.start_tick,end_tick:s.end_tick})));
        setRevision(x.revision);setTimelineSha(x.document_sha256);
        const display=secondsFromTicks(x.duration_tick);
        setExactDuration(display===null?x.duration_tick:null);
        setDurationTick(x.duration_tick);
        if(display!==null)setDuration(display);
        else setTickMode(true);
      }).catch(e=>{
        // A new scene has no timeline yet; do not convert/read old 24-fps
        // sequences as native source data by guessing their timing.
        if(active&&!/not found|does not exist/i.test(e.message))
          setNotice('No compatible native Film Time sequence yet: '+e.message);
      });
    return ()=>{active=false;};
  },[project.id,source?.scene_id,source?.document_sha256,timelineId,api]);

  function editDraftShot(shotId, field, value){
    draftEpoch.current++;
    setTimelineSha(''); // Any edit revokes authority to freeze the saved revision.
    setShots(previous=>previous.map(s=>s.shot_id===shotId?{...s,[field]:value}:s));
    setNotice('Unsaved camera revision; freeze requires publication.');
  }

  function removeDraftShot(shotId){
    draftEpoch.current++;
    setTimelineSha('');
    setShots(previous=>previous.filter(s=>s.shot_id!==shotId));
    setNotice('Draft observation removed; prior immutable revisions are preserved.');
  }

  function appendShot(){
    setError('');
    if(!source||!cameraPath)return;
    try{
      const first=(tickMode?exactTick(startTick):exactTick(ticks(start))).toString();
      const length=tickMode?exactTick(lengthTick):exactTick(ticks(seconds));
      const last=(exactTick(first)+length).toString();
      exactTick(last);
      if(BigInt(first)>=BigInt(last))throw Error('Shot duration must be positive.');
      if(shots.length>=128)throw Error('Maximum 128 shot observations per sequence.');
      if(shots.length&&BigInt(first)<BigInt(shots.at(-1).end_tick))
        throw Error('Shots must not overlap; intentional empty-time gaps are supported.');
      draftEpoch.current++;
      setTimelineSha(''); // Draft edits must never authorize freezing a stale saved revision.
      const used=new Set(shots.map(s=>s.shot_id));
      let number=1;
      while(used.has('Shot'+String(number).padStart(3,'0')))number++;
      setShots(a=>[...a,{shot_id:'Shot'+String(number).padStart(3,'0'),
        camera_path:cameraPath,pattern,start_tick:first,end_tick:last}]);
      const micros=BigInt(last)/US;
      setStartTick(last);
      setStart((micros/1000000n).toString()+
        ((micros%1000000n)!==0n?'.'+(micros%1000000n).toString()
          .padStart(6,'0').replace(/0+$/,''):''));
      setNotice('Unsaved shot observation added; the 3D world was not copied.');
    }catch(e){setError(e.message);}
  }

  async function save(){
    if(!source||!shots.length||busy)return;
    setError('');setNotice('');
    try{
      const requested=(tickMode?exactTick(durationTick):exactTick(ticks(duration))).toString();
      let previousEnd=0n;
      const identities=new Set();
      for(const shot of shots){
        const first=exactTick(shot.start_tick),last=exactTick(shot.end_tick);
        if(first<previousEnd||last<=first)
          throw Error('Camera observations must be ordered, non-overlapping and positive.');
        if(identities.has(shot.shot_id))throw Error('Duplicate camera shot identity.');
        if(!(source.cameras||[]).some(c=>c.path===shot.camera_path))
          throw Error('Camera observation refers to a camera absent from the source scene.');
        if(!SHAPES.includes(shot.pattern))throw Error('Unsupported camera coverage pattern.');
        identities.add(shot.shot_id);
        previousEnd=last;
      }
      const far=shots.reduce((a,s)=>BigInt(s.end_tick)>a?
        BigInt(s.end_tick):a,0n);
      const end=far>BigInt(requested)?far:BigInt(requested);
      exactTick(end.toString());
      const publishingEpoch=draftEpoch.current;
      await action(async()=>{
        const next=await api('/projects/'+encodeURIComponent(project.id)+
          '/film/native-time-shots/'+encodeURIComponent(timelineId),'POST',{
            scene_id:source.scene_id,scene_revision:source.revision,
            expected_revision:revision,duration_tick:end.toString(),
            shots,
          });
        if(next.format!=='nvp.exact_time.usd_camera_shots.v1'||
           next.scene_document_sha256!==source.document_sha256||
           next.video_frames_created!==false||
           next.shots.length!==shots.length)
          throw Error('Published timeline did not preserve source identity.');
        // The server revision advances even if the creator edited locally.
        // Never overwrite newer draft timing with an older in-flight response.
        setRevision(next.revision);
        if(draftEpoch.current===publishingEpoch){
          setTimelineSha(next.document_sha256);
          setDurationTick(next.duration_tick);
          const display=secondsFromTicks(next.duration_tick);
          setExactDuration(display===null?next.duration_tick:null);
          if(display!==null)setDuration(display);
          setNotice('Saved exact-time source revision '+next.revision+
            '. No frames, audio master or Digital Take generated.');
        }else{
          setTimelineSha('');
          setNotice('An older revision was published while you edited. '+
            'Your newer draft remains unsaved; review and publish again.');
        }
      });
    }catch(e){setError(e.message);}
  }

  async function freeze(){
    if(!native||!source||!timelineSha||!revision||busy)return;
    setError('');setNotice('');
    try{
      await action(async()=>{
        const saved=await native.data_av_freeze_timed_take({
          project_id:project.id,take_id:takeId,
          scene_id:source.scene_id,scene_revision:source.revision,
          scene_document_sha256:source.document_sha256,
          timeline_id:timelineId,timeline_revision:revision,
          timeline_document_sha256:timelineSha,
        });
        if(saved?.format!=='nvp.data_av.native_session.v1'||
           saved.status!=='FROZEN_DATA_FIRST_TAKE'||
           saved.scene_document_sha256!==source.document_sha256||
           saved.timeline_document_sha256!==timelineSha||
           saved.original_modified!==false||
           saved.frame_based_capture!==false)
          throw Error('Native Take freeze denied or identity mismatch');
        setNotice('Immutable 3D Digital Take frozen: '+takeId+
          ' · SHA-256 '+saved.take_document_sha256);
      });
    }catch(e){setError(e.message);}
  }

  return <div className="columns">
    <section className="card" aria-label="Frame-independent Film Time authoring">
      <h2>Film the continuous 3D world</h2>
      <p className="muted">All shots observe one persistent 3D scene. Author exact
        Film Time, keep performance and sound data intact, and edit camera
        choices without recording or copying video frames.</p>
      <label>OpenUSD scene
        <select aria-label="Authoring scene" value={sceneId}
          onChange={e=>setSceneId(e.target.value)}>
          {!scenes.length&&<option value="">No native camera scene yet</option>}
          {scenes.map(s=><option key={s.scene_id} value={s.scene_id}>
            {s.scene_id} · revision {s.revision}</option>)}
        </select>
      </label>
      <label>Observation camera
        <select aria-label="Observation camera" value={cameraPath}
          onChange={e=>setCameraPath(e.target.value)}>
          {(source?.cameras||[]).map(c=><option key={c.path} value={c.path}>
            {c.label}</option>)}
        </select>
      </label>
      <label><input type="checkbox" checked={tickMode}
        onChange={e=>{
          if(e.target.checked){
            // Convert convenience seconds to ticks only when no finer-than-us
            // persisted duration exists; that original tick value is authoritative.
            try{
              setStartTick(ticks(start));setLengthTick(ticks(seconds));
              if(exactDuration===null)setDurationTick(ticks(duration));
            }catch(err){setError(err.message);return;}
          }else{
            // A tick-mode edit must not be silently replaced by stale
            // seconds fields when the creator switches back to convenience units.
            try{
              const values=[startTick,lengthTick,durationTick].map(x=>
                secondsFromTicks(exactTick(x).toString()));
              if(values.some(x=>x===null)){
                setError("Sub-microsecond Film Time requires exact tick mode.");
                return;
              }
              setStart(values[0]);setSeconds(values[1]);setDuration(values[2]);
              setExactDuration(null);
            }catch(err){setError(err.message);return;}
          }
          setTickMode(e.target.checked);setError("");
        }}/> Author exact integer Film Time ticks</label>
      {tickMode?<>
        <label>Start Film Time tick
          <input aria-label="Start Film Time tick" value={startTick} onChange={e=>setStartTick(e.target.value)}/></label>
        <label>Observation duration ticks
          <input aria-label="Observation duration ticks" value={lengthTick} onChange={e=>setLengthTick(e.target.value)}/></label>
      </>:<>
        <label>Start at Film Time (seconds, up to 6 decimal places)
          <input value={start} onChange={e=>setStart(e.target.value)}/></label>
        <label>Observation duration (seconds)
          <input value={seconds} onChange={e=>setSeconds(e.target.value)}/></label>
      </>}
      <label>Camera coverage
        <select value={pattern} onChange={e=>setPattern(e.target.value)}>
          {SHAPES.map(x=><option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}
        </select>
      </label>
      <button disabled={busy||!source} onClick={appendShot}>Add timed camera observation</button>
      {tickMode?<label>Film Time duration limit (exact ticks)
        <input aria-label="Film Time duration limit ticks" value={durationTick}
          onChange={e=>{draftEpoch.current++;setDurationTick(e.target.value);setTimelineSha('');}}/></label>:
        <label>Film Time duration limit (seconds)
          <input value={duration} onChange={e=>{draftEpoch.current++;setDuration(e.target.value);setTimelineSha('');}}/></label>}
      <div className="actions">
        <button disabled={busy||!shots.length||!source||(!tickMode&&exactDuration!==null)} onClick={save}>
          Save immutable timing revision</button>
        <button disabled={busy||!shots.length} onClick={()=>{
          draftEpoch.current++;setShots(s=>s.slice(0,-1));setTimelineSha('');
        }}>Undo last draft shot</button>
      </div>
      <p className="fineprint">Current saved revision: {revision||'not saved'}.
        Gaps remain empty Film Time, not placeholder pictures.</p>
      {shots.map(s=><div key={s.shot_id} className="scene-item">
        <strong>{s.shot_id}</strong>
        <label>Camera <select aria-label={`${s.shot_id} camera`} value={s.camera_path}
          onChange={e=>editDraftShot(s.shot_id,'camera_path',e.target.value)}>
          {(source?.cameras||[]).map(c=><option key={c.path} value={c.path}>{c.label}</option>)}
        </select></label>
        <label>Start tick <input aria-label={`${s.shot_id} start tick`} value={s.start_tick}
          onChange={e=>editDraftShot(s.shot_id,'start_tick',e.target.value)}/></label>
        <label>End tick <input aria-label={`${s.shot_id} end tick`} value={s.end_tick}
          onChange={e=>editDraftShot(s.shot_id,'end_tick',e.target.value)}/></label>
        <label>Coverage <select aria-label={`${s.shot_id} coverage`} value={s.pattern}
          onChange={e=>editDraftShot(s.shot_id,'pattern',e.target.value)}>
          {SHAPES.map(x=><option key={x} value={x}>{x.replaceAll('_',' ')}</option>)}
        </select></label>
        <button disabled={busy} onClick={()=>removeDraftShot(s.shot_id)}>Remove draft observation</button>
      </div>)}
    </section>
    <section className="card">
      <h2>Freeze the Digital Take</h2>
      <p className="muted">Saving the shot list does not capture a Take.
        The installed NVP application asks for explicit native approval
        before freezing the exact OpenUSD scene and Film Time event revisions.</p>
      <label>New Digital Take identity
        <input value={takeId} maxLength={80}
          onChange={e=>setTakeId(e.target.value)}/></label>
      {!native&&<p>Open installed NVP to authorize the immutable Take.</p>}
      <button disabled={busy||!native||!revision||!timelineSha}
        onClick={freeze}>Approve and freeze original 3D Take</button>
      {notice&&<p role="status">{notice}</p>}
      {error&&<p role="alert">{error}</p>}
      <p className="fineprint">No FFmpeg, fixed FPS, pre-rendered film,
        background audio bounce or 2D master is created here.</p>
    </section>
  </div>;
}
