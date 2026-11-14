import React,{useEffect,useState} from 'react';

// This advanced director panel uses only the installed pywebview host. It has
// no HTTP substitute, no browser-minted consent, and no original-Take mutation.
const goodId=value=>/^[A-Za-z][A-Za-z0-9_-]{2,63}$/.test(value);
const goodSha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
export default function DirectorCameraActorContinuity({movie}){
  const [native,setNative]=useState(()=>typeof window==='undefined'?
    null:window.pywebview?.api||null);
  const [sources,setSources]=useState([]);
  const [drafts,setDrafts]=useState([]);
  const [actors,setActors]=useState([]);
  const [picked,setPicked]=useState(0);
  const [railId,setRailId]=useState('DirectorRail001');
  const [draft,setDraft]=useState(null);
  const [actorId,setActorId]=useState('');
  const [actor,setActor]=useState(null);
  const [profileText,setProfileText]=useState('');
  const [directorNote,setDirectorNote]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const pid=movie?.id;
  useEffect(()=>{
    if(typeof window==='undefined')return;
    const ready=()=>setNative(window.pywebview?.api||null);
    window.addEventListener('pywebviewready',ready);
    ready();
    return()=>window.removeEventListener('pywebviewready',ready);
  },[]);
  async function refresh(){
    if(!native||!pid)return;
    const [camera,catalog,cast]=await Promise.all([
      native.camfx03_camera_sources(pid),
      native.camfx03_draft_catalog(pid),
      native.film03_actor_catalog(pid)
    ]);
    if(camera?.format!=='nvp.conv06.original_camera_bank_sources.v1'||
       camera.project_id!==pid||camera.unapproved_source_only!==true||
       camera.actor_take_pcm_modified!==false||!Array.isArray(camera.sources)||
       catalog?.format!=='nvp.cam_fx03.original_camera_draft_catalog.v1'||
       catalog.project_id!==pid||!Array.isArray(catalog.drafts)||
       cast?.format!=='nvp.conv06.story_bible_actorid_catalog.v1'||
       cast.project_id!==pid||!Array.isArray(cast.actors))
      throw Error('Trusted original camera/ActorID source was not verified');
    setSources(camera.sources);setDrafts(catalog.drafts);setActors(cast.actors);
  }
  useEffect(()=>{
    let active=true;
    setSources([]);setDrafts([]);setActors([]);setDraft(null);
    setActor(null);setActorId('');setError('');setNotice('');
    if(!native||!pid||movie.encrypted)return()=>{active=false;};
    Promise.all([
      native.camfx03_camera_sources(pid),
      native.camfx03_draft_catalog(pid),
      native.film03_actor_catalog(pid)
    ]).then(([camera,catalog,cast])=>{
      if(!active)return;
      if(camera?.format!=='nvp.conv06.original_camera_bank_sources.v1'||
         camera.project_id!==pid||camera.actor_take_pcm_modified!==false||
         !Array.isArray(camera.sources)||
         catalog?.format!=='nvp.cam_fx03.original_camera_draft_catalog.v1'||
         catalog.project_id!==pid||!Array.isArray(catalog.drafts)||
         cast?.format!=='nvp.conv06.story_bible_actorid_catalog.v1'||
         cast.project_id!==pid||!Array.isArray(cast.actors))
        throw Error('Original NVP source contract is not available');
      setSources(camera.sources);setDrafts(catalog.drafts);setActors(cast.actors);
    }).catch(e=>{if(active)setError(e.message)});
    return()=>{active=false;};
  },[pid,movie.encrypted,native]);
  async function action(work){
    if(busy)return;
    setBusy(true);setError('');setNotice('');
    try{await work();await refresh();}
    catch(e){setError(e.message||'Director action was not accepted');}
    finally{setBusy(false);}
  }
  function chooseActor(id){
    setActorId(id);setActor(null);setProfileText('');
    if(!id)return;
    action(async()=>{
      const next=await native.film03_actor_profile(pid,id);
      if(next.actor_id!==id||next.project_id!==pid||
         next.identity_is_story_bible_character_id!==true)
        throw Error('Selected ActorID did not match the original StoryBible');
      setActor(next);
      setProfileText(next.current?.profile?
        JSON.stringify(next.current.profile,null,2):'');
      setDirectorNote(next.current?.director_note||'');
    });
  }
  const editNode=(index,field,value)=>{
    if(!draft||draft.state!=='DRAFT')return;
    const nodes=draft.rail_spec.nodes.map((node,i)=>
      i===index?{...node,[field]:Number(value)}:node);
    setDraft({...draft,rail_spec:{...draft.rail_spec,nodes},dirty:true});
  };
  if(!native||!pid||movie.encrypted)return null;
  return <details className="film-card" aria-label="Advanced original camera and actor direction">
    <summary>Advanced direction: camera drafts &amp; actor continuity</summary>
    <p className="film-muted">Work with original scene cameras and the StoryBible cast.
      Saved drafts can be reopened after a restart. Publishing requires a fresh native confirmation.</p>
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    <section aria-label="Director camera drafts">
      <h3>Camera drafts</h3>
      {sources.length===0?<p className="film-muted">No approved original director camera bank yet. Set up a source world Take and director camera bank first.</p>:
      <label>Original source camera
        <select value={picked} onChange={e=>setPicked(Number(e.target.value))}>
          {sources.map((s,i)=><option key={s.camera_bank_id+':'+s.camera_id} value={i}>
            {s.camera_id}</option>)}
        </select>
      </label>}
      <label>New camera draft ID <input value={railId}
        onChange={e=>setRailId(e.target.value)} maxLength={64}/></label>
      <button type="button" disabled={busy||!sources.length||!goodId(railId)}
        onClick={()=>action(async()=>{
          const s=sources[picked];
          const result=await native.camfx03_draft_create({
            project_id:pid,rail_id:railId,expected_revision:0,
            rail_spec:s.rail_spec});
          if(result?.format!=='nvp.cam_fx03.durable_original_camera_rail_draft.v1'||
             result.state!=='DRAFT')throw Error('Camera draft was not persisted');
          setDraft(result);setNotice('Saved a new original camera draft.');
        })}>Create draft</button>
      <label>Reopen a saved draft
        <select value="" onChange={e=>action(async()=>{
          if(!e.target.value)return;
          const result=await native.camfx03_draft_reopen({
            project_id:pid,draft_id:e.target.value});
          if(result.project_id!==pid)throw Error('Unexpected camera draft');
          setDraft(result);
        })}>
          <option value="">Select a camera draft</option>
          {drafts.map(d=><option key={d.draft_id} value={d.draft_id}>
            {d.rail_id} — {d.state} (v{d.version})</option>)}
        </select>
      </label>
      {draft&&<div>
        <p>Camera: {draft.rail_spec.camera_id} · version {draft.version} · {draft.state}</p>
        {draft.state==='DRAFT'&&<>
          <label>Shot style <select value={draft.rail_spec.technique}
            onChange={e=>setDraft({...draft,dirty:true,rail_spec:{
              ...draft.rail_spec,technique:e.target.value}})}>
            {['static','dolly','truck','crane','orbit','track','pan_tilt',
               'reaction','two_shot','establishing','custom'].map(t=>
                 <option value={t} key={t}>{t}</option>)}
          </select></label>
          {draft.rail_spec.nodes.map((node,i)=><div key={node.tick}>
            <label>Key {i+1} focal length (mm)
              <input type="number" min="8" max="300" step="1"
                value={node.focal_length_mm}
                onChange={e=>editNode(i,'focal_length_mm',e.target.value)}/>
            </label>
            <label>Key {i+1} focus (m)
              <input type="number" min="0.05" max="10000" step="0.05"
                value={node.focus_distance_m}
                onChange={e=>editNode(i,'focus_distance_m',e.target.value)}/>
            </label>
          </div>)}
          <button disabled={busy||!draft.dirty} onClick={()=>action(async()=>{
            const saved=await native.camfx03_draft_save({
              project_id:pid,draft_id:draft.draft_id,
              version:draft.version,rail_spec:draft.rail_spec});
            if(saved.state!=='DRAFT'||saved.version!==draft.version+1)
              throw Error('Stale draft version; re-open to reconcile');
            setDraft(saved);setNotice('Saved and source-verified camera edit.');
          })}>Save edit</button>
          <button disabled={busy||draft.undo_depth===0} onClick={()=>action(async()=>{
            const item=await native.camfx03_draft_undo({
              project_id:pid,draft_id:draft.draft_id,version:draft.version});
            setDraft(item);setNotice('Restored previous camera draft.');
          })}>Undo</button>
          <button disabled={busy||draft.dirty||!goodSha(draft.proposal_sha256)}
            onClick={()=>action(async()=>{
              const item=await native.camfx03_draft_publish({
                project_id:pid,draft_id:draft.draft_id,version:draft.version,
                preview_sha256:draft.proposal_sha256});
              if(item?.draft?.state!=='PUBLISHED')
                throw Error('Original camera layer publication not confirmed');
              setDraft(item.draft);
              setNotice('Director-approved USD rail published; original actors and sound are intact.');
            })}>Review &amp; approve rail in native window</button>
          <button disabled={busy} onClick={()=>action(async()=>{
            const item=await native.camfx03_draft_discard({
              project_id:pid,draft_id:draft.draft_id,version:draft.version});
            setDraft(item);setNotice('Unapproved camera draft discarded.');
          })}>Discard draft</button>
        </>}
        {draft.state==='INTERRUPTED_REQUIRES_NEW_APPROVAL'&&
          <button disabled={busy} onClick={()=>action(async()=>{
            const result=await native.camfx03_draft_recover_publish({
              project_id:pid,draft_id:draft.draft_id});
            setDraft(result);setNotice('Reconciled committed source without replaying approval.');
          })}>Reconcile interrupted approval (read-only)</button>}
      </div>}
    </section>
    <section aria-label="ActorID identity continuity">
      <h3>Actor continuity</h3>
      <label>Original StoryBible ActorID
        <select value={actorId} onChange={e=>chooseActor(e.target.value)}>
          <option value="">Select a character</option>
          {actors.map(a=><option value={a.actor_id} key={a.actor_id}>
            {a.name}</option>)}
        </select>
      </label>
      {actor&&<div>
        <p>{actor.actor_name} · Identity revision {actor.current?.profile_revision||0}
          {actor.profile_voice_cast_stale?' · voice casting changed':''}</p>
        <p className="film-muted">Changes to identity, gait or voice selectors are reviewed as one versioned
          original record. This advanced editor requires the exact typed profile; it never generates a voice.</p>
        <details><summary>Review/edit exact actor identity record</summary>
          <label>Typed actor identity (JSON)
            <textarea rows={12} value={profileText}
              onChange={e=>setProfileText(e.target.value)}
              placeholder="Supply the complete actor appearance, behavior, movement, voice type and generator identity."/>
          </label>
          <label>Director approval note
            <input value={directorNote} maxLength={1500}
              onChange={e=>setDirectorNote(e.target.value)}/>
          </label>
          <button disabled={busy||!profileText.trim()||!directorNote.trim()}
            onClick={()=>action(async()=>{
              const parsed=JSON.parse(profileText);
              const result=await native.film03_actor_profile_publish({
                project_id:pid,actor_id:actorId,profile:parsed,
                expected_profile_revision:actor.current?.profile_revision||0,
                expected_bible_revision:actor.bible_revision,
                director_note:directorNote});
              if(result.actor_id!==actorId||
                 result.native_director_identity_approved!==true)
                throw Error('Native ActorID revision was not confirmed');
              setActor(result);
              setProfileText(JSON.stringify(result.current.profile,null,2));
              setNotice('Director-approved ActorID identity recorded.');
            })}>Review &amp; approve ActorID profile in native window</button>
        </details>
      </div>}
    </section>
  </details>;
}
