import React,{useEffect,useState} from 'react';

// PLAN-02-B: host-verified original sound capture, never a browser writer.
// Each operation passes ONLY exact source identities and typed options.
// Native pywebview dialogs authorize recording and later Take publication.
const FORMAT='nvp.data_av.original_capture_catalog.v1';
const ID=/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/;
const DEFAULT={
  take_id:'OriginalMicTake001',sound_timeline_id:'OriginalSoundEvents001',
  source_id:'OriginalMicSource001',event_id:'OriginalMicEvent001',
  subject_id:'OriginalActor001',second_source_id:'OriginalMicSource002',
  second_event_id:'OriginalMicEvent002',second_subject_id:'OriginalActor002',
};
export default function NativeOriginalCapturePanel({projectId,native,onCompleted=null}){
  const [catalog,setCatalog]=useState([]);
  const [selected,setSelected]=useState('');
  const [emitter,setEmitter]=useState('');
  const [secondEmitter,setSecondEmitter]=useState('');
  const [draft,setDraft]=useState(DEFAULT);
  const [mode,setMode]=useState('mono');
  const [devices,setDevices]=useState([]);
  const [firstDevice,setFirstDevice]=useState('');
  const [secondDevice,setSecondDevice]=useState('');
  const [active,setActive]=useState(false);
  const [busy,setBusy]=useState(false);
  const [note,setNote]=useState('');
  const [error,setError]=useState('');
  const [receipt,setReceipt]=useState(null);
  const plan=catalog.find(p=>p.timeline_id+':'+p.revision===selected);
  const emitters=plan?.emitter_paths||[];

  useEffect(()=>{
    let alive=true;
    setCatalog([]);setSelected('');setEmitter('');setSecondEmitter('');
    if(!native||!projectId||typeof native.data_av_capture_catalog!=='function')
      return ()=>{alive=false;};
    native.data_av_capture_catalog(projectId).then(response=>{
      if(!alive)return;
      if(response?.format!==FORMAT||response.project_id!==projectId||
         !Array.isArray(response.timelines))
        throw Error('Native original capture catalog source identity mismatch');
      setCatalog(response.timelines);
      const first=response.timelines[0];
      setSelected(first?first.timeline_id+':'+first.revision:'');
    }).catch(e=>{if(alive)setError(e.message);});
    return ()=>{alive=false;};
  },[native,projectId]);

  useEffect(()=>{
    setEmitter(emitters[0]||'');
    setSecondEmitter(emitters.find(x=>x!==emitters[0])||'');
  },[selected,catalog]);

  useEffect(()=>{
    let alive=true;
    if(mode!=='dual'||!native||
       typeof native.data_av_capture_devices!=='function')
      return ()=>{alive=false;};
    native.data_av_capture_devices().then(response=>{
      if(!alive)return;
      if(response?.format!=='nvp.data_av.native_capture_session.v1'||
         !Array.isArray(response.input_devices))
        throw Error('Native microphone inventory was not verified');
      setDevices(response.input_devices);
      setFirstDevice(String(response.input_devices[0]?.device_id??''));
      setSecondDevice(String(response.input_devices[1]?.device_id??''));
    }).catch(e=>{if(alive)setError(e.message);});
    return ()=>{alive=false;};
  },[mode,native]);

  const update=(name,value)=>setDraft(old=>({...old,[name]:value}));
  const ids=['take_id','sound_timeline_id','source_id','event_id','subject_id'];
  const dualIds=['second_source_id','second_event_id','second_subject_id'];
  const valid=Boolean(plan&&emitter&&
    ids.every(k=>ID.test(draft[k]))&&
    (mode==='mono'||(secondEmitter&&secondEmitter!==emitter&&
     dualIds.every(k=>ID.test(draft[k]))&&firstDevice!==secondDevice&&
     firstDevice!==''&&secondDevice!=='')));

  async function start(){
    if(!valid||busy||active)return;
    setBusy(true);setError('');setNote('');setReceipt(null);
    try{
      const request={
        project_id:projectId,take_id:draft.take_id,
        scene_id:plan.scene_id,scene_revision:plan.scene_revision,
        scene_document_sha256:plan.scene_document_sha256,
        camera_timeline_id:plan.timeline_id,
        camera_timeline_revision:plan.revision,
        camera_timeline_document_sha256:plan.document_sha256,
        sound_timeline_id:draft.sound_timeline_id,
        source_id:draft.source_id,emitter_path:emitter,
        event_id:draft.event_id,subject_id:draft.subject_id,
      };
      if(mode==='dual'){
        Object.assign(request,{
          independent_device_ids:[Number(firstDevice),Number(secondDevice)],
          second_source_id:draft.second_source_id,
          second_emitter_path:secondEmitter,
          second_event_id:draft.second_event_id,
          second_subject_id:draft.second_subject_id,
        });
      }
      const result=await native.data_av_capture_begin(request);
      if(result?.format!=='nvp.data_av.native_capture_session.v1'||
         result.status!=='RECORDING'||result.take_id!==draft.take_id||
         result.scene_document_sha256!==plan.scene_document_sha256)
        throw Error('Native recording did not return exact original-source authorization');
      setActive(true);
      setNote('Recording original PCM in a durable native spool. A separate native approval is required before freezing a Take.');
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }

  async function finish(){
    if(!active||busy)return;
    setBusy(true);setError('');
    try{
      const result=await native.data_av_capture_finish();
      if(result?.format!=='nvp.data_av.native_capture_session.v1'||
         result.status!=='FROZEN_ORIGINAL_LIVE_TAKE'||
         result.take_id!==draft.take_id||
         !/^[a-f0-9]{64}$/.test(result.take_document_sha256||'')||
         result.picture_frames_generated!==false)
        throw Error('Native source publication has no verified frozen Take receipt');
      setReceipt(result);
      setNote('Original Digital Take frozen from source audio and Film Time; no film master or picture frames generated.');
      onCompleted?.(result);
    }catch(e){setError(e.message);}
    finally{setActive(false);setBusy(false);}
  }

  async function cancel(){
    if(!active||busy)return;
    setBusy(true);setError('');
    try{
      const result=await native.data_av_capture_cancel();
      if(result?.status!=='CANCELLED')
        throw Error('Native recorder stop/recovery requires review');
      setNote('Recording stopped without freezing a Take.');
    }catch(e){setError(e.message);}
    finally{setActive(false);setBusy(false);}
  }

  return <section aria-label="Record original scene sound" className="card">
    <h3>Capture original sound into the Film World</h3>
    <p className="fineprint">Choose an already authored OpenUSD camera timeline.
      Input capture belongs to the trusted native host; two separate OS
      confirmations govern start and immutable Take freeze. No FFmpeg or
      flattened movie is created.</p>
    {error&&<p role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    <label>Original camera Film Time plan
      <select aria-label="Original source camera timeline" value={selected}
        disabled={active||busy} onChange={e=>setSelected(e.target.value)}>
        {!catalog.length&&<option value="">No exact Film Time source timeline published</option>}
        {catalog.map(x=><option key={x.timeline_id+':'+x.revision}
          value={x.timeline_id+':'+x.revision}>
          {x.timeline_id} · revision {x.revision}
        </option>)}
      </select>
    </label>
    <label>Original sound emitter
      <select aria-label="Original sound emitter" value={emitter}
        disabled={active||busy} onChange={e=>setEmitter(e.target.value)}>
        {emitters.map(x=><option key={x}>{x}</option>)}
      </select>
    </label>
    <label>Original capture input
      <select aria-label="Original input mode" value={mode}
        disabled={active||busy} onChange={e=>setMode(e.target.value)}>
        <option value="mono">One original microphone</option>
        <option value="dual">Two independent source clocks</option>
      </select>
    </label>
    {mode==='dual'&&<>
      <label>First input device
        <select aria-label="First original input device" value={firstDevice}
          disabled={active||busy} onChange={e=>setFirstDevice(e.target.value)}>
          {devices.map(x=><option key={x.device_id} value={x.device_id}>
            {x.name} · {x.host_api}</option>)}
        </select>
      </label>
      <label>Second input device
        <select aria-label="Second original input device" value={secondDevice}
          disabled={active||busy} onChange={e=>setSecondDevice(e.target.value)}>
          {devices.map(x=><option key={x.device_id} value={x.device_id}>
            {x.name} · {x.host_api}</option>)}
        </select>
      </label>
      <label>Second sound emitter
        <select aria-label="Second original sound emitter" value={secondEmitter}
          disabled={active||busy} onChange={e=>setSecondEmitter(e.target.value)}>
          {emitters.map(x=><option key={x} value={x}>{x}</option>)}
        </select>
      </label>
    </>}
    {[...ids,...(mode==='dual'?dualIds:[])].map(k=>
      <label key={k}>{k.replaceAll('_',' ')}
        <input aria-label={k} value={draft[k]} maxLength={80}
          disabled={active||busy} onChange={e=>update(k,e.target.value)}/>
      </label>)}
    <div className="actions">
      <button disabled={!valid||busy||active||
        typeof native?.data_av_capture_begin!=='function'} onClick={start}>
        Start original recording (OS approval)
      </button>
      <button disabled={!active||busy} onClick={finish}>
        Stop and request Take freeze
      </button>
      <button disabled={!active||busy} onClick={cancel}>
        Cancel without freezing
      </button>
    </div>
    {receipt&&<p role="status">Frozen original Take:
      {receipt.take_id} · SHA {receipt.take_document_sha256.slice(0,16)}…</p>}
    <p className="fineprint">Original source hashes are pinned by the host.
      Independent device sync is not a hardware-genlock claim; physical
      sound-card, Windows microphone and latency acceptance remain open.</p>
  </section>;
}
