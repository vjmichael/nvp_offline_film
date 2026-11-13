import React,{useEffect,useMemo,useState} from 'react';

// P1-B/C: no browser ActorID authority, voice generator, raw source file path,
// invented transcripts, or glTF executable. Native OS prompts own both writes.
const CAST='nvp.p1bc.native_actor_cast.v1';
const IDENT=/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/;

export default function ActorPerformancePanel({projectId,native,sourceRevision=0}){
  const [cast,setCast]=useState(null);
  const [actorId,setActorId]=useState('ActorLead');
  const [displayName,setDisplayName]=useState('');
  const [takeId,setTakeId]=useState('');
  const [cueId,setCueId]=useState('');
  const [dialogueId,setDialogueId]=useState('ActorLine001');
  const [tick,setTick]=useState('0');
  const [verified,setVerified]=useState(null);
  const [registered,setRegistered]=useState(null);
  const [bound,setBound]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const ready=Boolean(native&&[
    'data_av_actor_cast','data_av_actor_register',
    'data_av_actor_dialogue_bind','data_av_actor_dialogue_at',
  ].every(k=>typeof native[k]==='function'));
  const take=useMemo(()=>(cast?.takes||[]).find(x=>x.take_id===takeId),
    [cast,takeId]);
  const cue=(take?.original_dialogue||[]).find(x=>x.event_id===cueId);

  async function refresh(){
    if(!ready||!projectId)return;
    const result=await native.data_av_actor_cast(projectId);
    if(result?.format!==CAST||result.project_id!==projectId||
       !Array.isArray(result.actors)||!Array.isArray(result.takes)||
       result.sources_immutable!==true||result.voices_synthesized!==false)
      throw Error('Native cast did not independently verify original sources');
    setCast(result);
    setTakeId(old=>result.takes.some(x=>x.take_id===old)
      ?old:(result.takes[0]?.take_id||''));
    return result;
  }

  useEffect(()=>{
    let active=true;
    setCast(null);setTakeId('');setCueId('');setVerified(null);
    setBound(null);setRegistered(null);setError('');
    if(!ready||!projectId)return;
    Promise.resolve(native.data_av_actor_cast(projectId)).then(result=>{
      if(!active)return;
      if(result?.format!==CAST||result.project_id!==projectId||
         !Array.isArray(result.actors)||!Array.isArray(result.takes)||
         result.sources_immutable!==true||result.voices_synthesized!==false)
        throw Error('Original native cast is not verified');
      setCast(result);setTakeId(result.takes[0]?.take_id||'');
    }).catch(e=>{if(active)setError(e.message)});
    return ()=>{active=false};
  },[ready,native,projectId,sourceRevision]);

  useEffect(()=>{
    if(!take){setCueId('');return;}
    setCueId(old=>take.original_dialogue?.some(x=>x.event_id===old)
      ?old:(take.original_dialogue?.[0]?.event_id||''));
  },[take]);

  async function registerActor(){
    if(!IDENT.test(actorId)||!displayName.trim()||busy)return;
    setBusy(true);setError('');setRegistered(null);
    try{
      const result=await native.data_av_actor_register({
        project_id:projectId,actor_id:actorId,display_name:displayName.trim(),
      });
      if(result?.format!=='nvp.p1bc.native_actor_registration.v1'||
         result.status!=='ACTOR_ID_REGISTERED'||result.actor_id!==actorId||
         result.source_modified!==false||result.voice_synthesized!==false)
        throw Error('ActorID registration does not match native authority');
      setRegistered(result);
      await refresh();
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  async function bindLine(){
    if(!IDENT.test(dialogueId)||!take||!cue||busy)return;
    setBusy(true);setError('');setBound(null);setVerified(null);
    try{
      const result=await native.data_av_actor_dialogue_bind({
        project_id:projectId,dialogue_id:dialogueId,
        actor_id:cue.actor_id,take_id:take.take_id,event_id:cue.event_id,
      });
      if(result?.format!=='nvp.p1bc.native_original_dialogue.v1'||
         result.status!=='ORIGINAL_DIALOGUE_BOUND'||
         result.dialogue_id!==dialogueId||result.take_modified!==false||
         result.voice_synthesized!==false)
        throw Error('Original ActorID speaker attribution was not verified');
      setBound(result);
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  async function sample(){
    if(!bound||busy||!/^\d{1,19}$/.test(tick))return;
    setBusy(true);setError('');setVerified(null);
    try{
      const reply=await native.data_av_actor_dialogue_at({
        project_id:projectId,dialogue_id:bound.dialogue_id,
        revision:1,tick,
      });
      if(reply?.format!=='nvp.p1bc.native_original_dialogue_tick.v1'||
         reply.source_modified!==false||reply.film_master_approved!==false||
         reply.result?.actor_id!==cue?.actor_id||
         reply.result?.native_scene_rig_binding_verified!==true||
         reply.result?.native_skin_deformation_evaluated!==true||
         reply.result?.voice_synthesized!==false||
         reply.result?.lip_sync_generated!==false)
        throw Error('Native original dialogue Film Time result is unverified');
      setVerified(reply.result);
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  return <section className="card" aria-label="Original ActorID and dialogue">
    <h3>Original actor, rig and dialogue</h3>
    <p className="fineprint">Register a durable ActorID, then attribute only
      an existing recorded dialogue event from a frozen OpenUSD Take. Actor
      identity must be attached to actual skinned USD geometry in the
      source scene before dialogue appears here. Native confirmation is
      required for every new identity or attribution.</p>
    {!ready&&<p role="status">Requires trusted desktop actor/voice bridge.</p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">
      {cast?.actors?.length||0} original ActorIDs · {cast?.takes?.length||0}
      {' '}rigged USD Takes with checked ActorID bindings.
    </p>
    <label>New permanent ActorID
      <input value={actorId} disabled={!ready||busy} maxLength={80}
        onChange={e=>setActorId(e.target.value)}/>
    </label>
    <label>Character name
      <input value={displayName} disabled={!ready||busy} maxLength={120}
        onChange={e=>setDisplayName(e.target.value)}/>
    </label>
    <button disabled={!ready||busy||!IDENT.test(actorId)||!displayName.trim()}
      onClick={registerActor}>Ask native director to register ActorID</button>
    {registered&&<p role="status">Actor {registered.actor_id} registered,
      SHA {registered.actor_sha256.slice(0,16)}…</p>}
    <label>Original rigged Digital Take
      <select value={takeId} disabled={!ready||busy}
        onChange={e=>{setTakeId(e.target.value);setBound(null);}}>
        {!cast?.takes?.length&&<option value="">No ActorID-bound original rigged Takes</option>}
        {(cast?.takes||[]).map(x=><option key={x.take_id} value={x.take_id}>
          {x.take_id}</option>)}
      </select>
    </label>
    {take&&<p className="fineprint">{take.cast.map(x=>x.actor_id)
      .join(', ')} · scene rig/skin verified · original Take SHA
      {' '}{take.take_sha256.slice(0,16)}…</p>}
    <label>Recorded actor dialogue (not synthesized)
      <select value={cueId} disabled={!take||busy}
        onChange={e=>{setCueId(e.target.value);setBound(null);}}>
        {!take?.original_dialogue?.length&&
          <option value="">No original actor-matched dialogue sources</option>}
        {(take?.original_dialogue||[]).map(x=>
          <option key={x.event_id} value={x.event_id}>
            {x.actor_id} · {x.event_id} · ticks {x.start_tick}–{x.end_tick}
          </option>)}
      </select>
    </label>
    <label>New unique dialogue attribution identity
      <input maxLength={80} value={dialogueId} disabled={busy}
        onChange={e=>setDialogueId(e.target.value)}/>
    </label>
    <button disabled={!ready||!cue||busy||!IDENT.test(dialogueId)}
      onClick={bindLine}>Ask native director to bind original speaker</button>
    {bound&&<p role="status">Original voice event bound to {cue?.actor_id},
      SHA {bound.dialogue_sha256.slice(0,16)}…</p>}
    {bound&&<>
      <label>Read exact Film Time tick
        <input value={tick} inputMode="numeric" maxLength={19}
          disabled={busy} onChange={e=>setTick(e.target.value)}/>
      </label>
      <button disabled={busy||!/^\d{1,19}$/.test(tick)}
        onClick={sample}>Verify ActorID, original voice and rig at tick</button>
      {verified&&<p role="status">Actor {verified.actor_id} at tick
        {' '}{verified.time_tick}: {verified.dialogue_active?'original dialogue active':
        'original dialogue inactive'} · USD {verified.usd_prim_path}
        {' '}· {verified.source_skin_vertex_count} evaluated source skin vertices</p>
    </>}
    <p className="fineprint">No voice cloned or generated, no automatic
      dialogue text, lip-sync, facial performance or film master approved.
      Scene source, original sound and Digital Takes are immutable.</p>
  </section>;
}
