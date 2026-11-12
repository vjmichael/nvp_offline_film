import React,{useEffect,useState} from 'react';

// INT-02: native-only source identities, no browser-selected output paths.
const F='nvp.int02.native_edited_export_ticket.v1';

export default function EditedFilmDeliveryPanel({projectId,native}){
  const [edits,setEdits]=useState([]);
  const [selected,setSelected]=useState('');
  const [listener,setListener]=useState('');
  const [presentation,setPresentation]=useState('FirstEditedFilm');
  const [ticket,setTicket]=useState('');
  const [state,setState]=useState(null);
  const [error,setError]=useState('');
  const [preflight,setPreflight]=useState(null);
  const ready=Boolean(native&&[
    'data_av_edited_30s_catalog','data_av_edited_30s_preflight',
    'data_av_edited_30s_begin','data_av_edited_30s_poll',
    'data_av_edited_30s_cancel',
  ].every(k=>typeof native[k]==='function'));
  const choice=edits.find(x=>x.edit_id===selected);
  const pending=Boolean(ticket&&['QUEUED_NATIVE_APPROVAL',
    'RUNNING_OR_AWAITING_NATIVE_APPROVAL',
    'CANCELLATION_REQUESTED_NOT_VERIFIED'].includes(state?.status));

  useEffect(()=>{
    setEdits([]);setSelected('');setListener('');setTicket('');
    setState(null);setPreflight(null);setError('');
    if(!ready||!projectId)return;
    let active=true;
    Promise.resolve(native.data_av_edited_30s_catalog(projectId)).then(result=>{
      if(!active)return;
      if(result?.format!=='nvp.int02.native_edited_catalog.v1'||
         result.project_id!==projectId||!Array.isArray(result.edits)||
         result.master_approved!==false)
        throw Error('Installed native edit catalog could not be verified');
      setEdits(result.edits);
      setSelected(result.edits[0]?.edit_id||'');
    }).catch(e=>{if(active)setError(e.message)});
    return ()=>{active=false};
  },[ready,native,projectId]);

  useEffect(()=>{
    setListener(choice?.listeners?.[0]||'');
    setPreflight(null);
  },[selected,edits]);

  useEffect(()=>{
    if(!ticket||!native||!pending)return;
    let active=true;
    const poll=async()=>{
      try{
        const reply=await native.data_av_edited_30s_poll(ticket);
        if(!active)return;
        if(reply?.format!==F||reply.original_modified!==false||
           reply.master_approved!==false)
          throw Error('Native film export status failed authority check');
        setState(reply);
      }catch(e){if(active)setError(e.message);}
    };
    poll();
    const interval=setInterval(poll,350);
    return ()=>{active=false;clearInterval(interval);};
  },[ticket,native,pending]);

  async function inspect(){
    if(!choice||pending)return;
    setError('');setPreflight(null);
    try{
      const result=await native.data_av_edited_30s_preflight(
        projectId,choice.edit_id,choice.edit_revision);
      if(result?.format!=='nvp.int02.edited_original_30s.v1'||
         result.edit_sha256!==choice.edit_sha256||
         result.frame_count!==720||result.pcm_samples!==1440000||
         result.render_approved!==false)
        throw Error('Edited source readiness differs from committed original');
      setPreflight(result);
    }catch(e){setError(e.message);}
  }

  async function exportFilm(){
    if(!choice||!listener||!preflight||pending)return;
    setError('');
    if(!/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/.test(presentation)){
      setError('Choose a unique, valid presentation identity.');return;
    }
    try{
      const reply=await native.data_av_edited_30s_begin({
        project_id:projectId,edit_id:choice.edit_id,
        edit_revision:choice.edit_revision,
        presentation_id:presentation,listener_path:listener});
      if(reply?.format!==F||reply.status!=='QUEUED_NATIVE_APPROVAL'||
         typeof reply.ticket!=='string'||reply.original_modified!==false||
         reply.master_approved!==false)
        throw Error('OS-native film authorization was not queued');
      setTicket(reply.ticket);setState(reply);
    }catch(e){setError(e.message);}
  }

  async function cancel(){
    if(!pending)return;
    try{
      const reply=await native.data_av_edited_30s_cancel(ticket);
      if(reply?.format!==F||reply.status!=='CANCELLATION_REQUESTED_NOT_VERIFIED')
        throw Error('Cancellation was not acknowledged');
      setState(reply);
    }catch(e){setError(e.message);}
  }

  return <section className="card" aria-label="Committed original film delivery">
    <h3>Make a 30-second film from your committed edit</h3>
    <p className="fineprint">The original OpenUSD scene, performances, camera
      selection and native PCM remain frozen. NVP now requests an OS-contained Blender Cycles USD picture render.
      The resulting PNG/WAV remains an independently verified derivative,
      not an accepted cinema master or color-calibrated production release.
      Exported PNG/WAV files are unencrypted and saved outside original
      project storage only after explicit native approval.</p>
    {!ready&&<p role="status">Requires installed NVP native filmmaker bridge.</p>}
    <label>Committed edit
      <select value={selected} onChange={e=>setSelected(e.target.value)}
        disabled={!ready||pending}>
        {!edits.length&&<option value="">No eligible committed 30-second edits</option>}
        {edits.map(item=><option key={item.edit_id} value={item.edit_id}>
          {item.edit_id} · revision {item.edit_revision}
        </option>)}
      </select>
    </label>
    <label>Original virtual microphone
      <select value={listener} onChange={e=>setListener(e.target.value)}
        disabled={!choice||pending}>
        {(choice?.listeners||[]).map(path=><option key={path} value={path}>{path}</option>)}
      </select>
    </label>
    <label>New derived presentation identity
      <input value={presentation} onChange={e=>setPresentation(e.target.value)}
        maxLength={80} disabled={pending}/>
    </label>
    <div className="actions">
      <button disabled={!choice||pending} onClick={inspect}>
        Verify committed film sources</button>
      <button disabled={!preflight||!listener||pending} onClick={exportFilm}>
        Request OS approval and derive film</button>
      <button disabled={!pending} onClick={cancel}>
        Request cancellation</button>
    </div>
    {preflight&&<p role="status">Committed SHA {preflight.edit_sha256.slice(0,16)}…
      · {preflight.segments.length} source segments · 720 picture samples
      · 1,440,000 original PCM samples. No render approved yet.</p>}
    {state&&<p role="status" aria-live="polite">
      {state.status}
      {state.progress&&(' · '+state.progress.stage+': '+state.progress.count)}
      {state.reason&&(' · '+state.reason)}
      {state.receipt&&(' · verified package: '+state.receipt.directory)}
    </p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">Native host selects the output directory and
      asks for one-use source-scoped approval. Cancellation requests do not
      establish stopped-worker custody. Physical Windows and production
      rendering acceptance remain open.</p>
  </section>;
}
