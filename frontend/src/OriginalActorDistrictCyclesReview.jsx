import React,{useCallback,useEffect,useState} from 'react';

const BIND='nvp.usd_film02m_h.approved_district_original_actor_camera_binding.v1';
const TICKET='nvp.usd_film02m_h.native_render_ticket.v1';
const STATUS='nvp.usd_film02m_h.native_render_status.v1';
const IMAGE='nvp.usd_film02m_h.verified_native_cycles_picture.v1';
const SHA=/^[0-9a-f]{64}$/;
const JOB=/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/;

export default function OriginalActorDistrictCyclesReview({
  projectId,nativeBridge,bindingId,bindingReceipt
}){
  const ready=Boolean(nativeBridge)&&[
    'film02mh_reopen_shot_binding','film02mh_render_begin',
    'film02mh_render_poll','film02mh_render_image'].every(
      name=>typeof nativeBridge[name]==='function');
  const [reopened,setReopened]=useState(null);
  const [ticket,setTicket]=useState(null);
  const [state,setState]=useState('');
  const [jobId,setJobId]=useState('');
  const [image,setImage]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    setReopened(null);setTicket(null);setState('');
    setImage(null);setError('');setNotice('');
  },[projectId,bindingId]);
  useEffect(()=>{
    if(bindingReceipt?.binding_id===bindingId)
      setReopened(bindingReceipt);
  },[bindingReceipt,bindingId]);
  const binding=reopened?.binding_id===bindingId?reopened:null;
  const verifyBinding=value=>{
    if(value?.format!==BIND||value.binding_id!==bindingId||
       value.native_source_reopened!==true||
       value.source_actor_takes_unchanged!==true||
       !SHA.test(value.binding_document_sha256))
      throw Error('Original source shot binding did not independently reopen');
    return value;
  };
  const guarded=async operation=>{
    if(!ready||busy)return;
    setBusy(true);setError('');
    try{await operation();}
    catch(e){setError(e?.message||String(e));}
    finally{setBusy(false);}
  };
  const reopen=()=>guarded(async()=>{
    const result=verifyBinding(
      await nativeBridge.film02mh_reopen_shot_binding({
        project_id:projectId,binding_id:bindingId}));
    setReopened(result);setTicket(null);setImage(null);
    setNotice('Approved original shot source verified. A new render needs separate OS approval.');
  });
  const verifiedImage=useCallback(async(id,sha)=>{
    const result=await nativeBridge.film02mh_render_image({
      project_id:projectId,binding_id:bindingId,
      binding_sha256:sha,job_id:id});
    if(result?.format!==IMAGE||result.binding_id!==bindingId||
       result.binding_sha256!==sha||result.job_id!==id||
       !SHA.test(result.picture_sha256)||
       result.native_worker_and_independent_reopen_verified!==true||
       result.original_actor_takes_and_pcm_unchanged!==true||
       result.director_picture_approved!==false||
       result.final_film_accepted!==false||
       typeof result.image_data_url!=='string'||
       !result.image_data_url.startsWith('data:image/png;base64,'))
      throw Error('Unverified Blender pixels cannot be displayed');
    setImage(result);setJobId(id);
    return result;
  },[nativeBridge,projectId,bindingId]);
  const begin=()=>guarded(async()=>{
    if(!binding||!SHA.test(binding.binding_document_sha256))
      throw Error('Reopen the exact source binding before requesting native Cycles');
    const received=await nativeBridge.film02mh_render_begin({
      project_id:projectId,binding_id:bindingId,
      binding_sha256:binding.binding_document_sha256});
    if(received?.format!==TICKET||
       received.state!=='PENDING_FRESH_NATIVE_APPROVAL'||
       received.binding_id!==bindingId||
       received.binding_sha256!==binding.binding_document_sha256||
       received.original_actor_takes_modified!==false||
       received.director_picture_approved!==false||
       !/^[0-9a-f]{24}$/.test(received.ticket_id))
      throw Error('Native OS render ticket is not approved-source scoped');
    setImage(null);setTicket(received.ticket_id);
    setState('NATIVE_JOB_OR_APPROVAL_PENDING');
    setNotice('Native OS review and protected Cycles pending. The original Take is unchanged.');
  });
  useEffect(()=>{
    if(!ticket||!binding||!ready)return;
    let stopped=false,handle=null;
    const poll=async()=>{
      try{
        const result=await nativeBridge.film02mh_render_poll(ticket);
        if(stopped)return;
        if(result?.format!==STATUS||result.ticket_id!==ticket||
           result.binding_id!==bindingId||
           result.binding_sha256!==binding.binding_document_sha256||
           result.original_actor_takes_modified!==false||
           result.director_picture_approved!==false)
          throw Error('Native render no longer refers to the approved shot');
        setState(result.state);
        if(result.state==='NATIVE_JOB_OR_APPROVAL_PENDING'){
          handle=setTimeout(poll,1100);
          return;
        }
        if(result.state==='SOURCE_VERIFIED_CYCLES_PICTURE'){
          if(result.native_worker_and_independent_reopen_verified!==true||
             !JOB.test(result.job_id)||
             !SHA.test(result.picture_sha256))
            throw Error('Protected Blender source receipt incomplete');
          const pixels=await verifiedImage(
            result.job_id,binding.binding_document_sha256);
          if(pixels.picture_sha256!==result.picture_sha256)
            throw Error('Readback image differs from exact native worker receipt');
          if(!stopped)setNotice('Genuine Cycles pixels independently reopened. Human shot review is still pending.');
        }else{
          setNotice('Native render: '+result.state+
            '. Historical source approval cannot authorize a new worker.');
        }
        if(!stopped)setTicket(null);
      }catch(e){
        if(!stopped){setTicket(null);setError(
          e?.message||'Native worker verification failed');}
      }
    };
    handle=setTimeout(poll,300);
    return()=>{stopped=true;clearTimeout(handle);};
  },[ticket,binding?.binding_document_sha256,bindingId,ready,nativeBridge,verifiedImage]);
  const reopenImage=()=>guarded(async()=>{
    if(!binding||!JOB.test(jobId))
      throw Error('Reopen an approved source and exact completed native job ID');
    await verifiedImage(jobId,binding.binding_document_sha256);
    setNotice('Native journal and original USD scene verified after reopen; no worker restarted.');
  });
  if(!ready)return null;
  return <section role="region" aria-label="Protected original actor district Cycles review">
    <h5>Real actor + approved district · Cycles picture review</h5>
    <p className="fineprint">This renders a genuine source-pinned OpenUSD
      shot using the protected Blender/Cycles worker. A new operating-system
      approval is required for the render, separate from approving the world.
      Neither actor Takes nor original PCM are rewritten.</p>
    <button disabled={busy||Boolean(ticket)||!bindingId} onClick={reopen}>
      Reopen existing approved actor/district shot for render</button>
    {binding&&<p role="status">Approved shot SHA:
      {' '+binding.binding_document_sha256}. The binding does not
      grant permission to execute Blender.</p>}
    <button disabled={busy||Boolean(ticket)||!binding} onClick={begin}>
      OS approve and render original actor/district Cycles frame</button>
    {state&&<p role="status">Native source render: {state}</p>}
    <label>Exact completed Cycles worker job ID
      <input aria-label="Completed actor district Cycles job ID"
        value={jobId} disabled={busy}
        onChange={e=>setJobId(e.target.value)}/></label>
    <button disabled={busy||Boolean(ticket)||!binding||!JOB.test(jobId)}
      onClick={reopenImage}>Reopen independently verified saved Cycles image</button>
    {notice&&<p role="status">{notice}</p>}
    {error&&<p role="alert">{error}</p>}
    {image&&<figure>
      <img src={image.image_data_url} width={320} height={180}
        alt="Verified original actor and modular district Cycles frame"/>
      <figcaption>Actual native image SHA: {image.picture_sha256}.
        Original actor world Take SHA: {image.world_take_sha256}.
        Approved building district SHA: {image.district_document_sha256}.
        Actor Takes and PCM remain unchanged. Human image-quality review open.
      </figcaption>
    </figure>}
  </section>;
}
