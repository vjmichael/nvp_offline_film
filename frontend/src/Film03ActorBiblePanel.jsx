import React, {useEffect, useMemo, useState} from 'react';
import Film03ActorVoicePanel from './Film03ActorVoicePanel.jsx';

const FAMILIES = {
  scene: ['screenplay_scene', 'filmindex'],
  dialogue: ['filmindex'], performance: ['filmindex'],
  voice: ['filmindex'], wardrobe: ['bible_prop', 'filmindex', 'mesh_glb', 'rigged_glb'],
  prop: ['bible_prop', 'filmindex', 'mesh_glb'], model: ['filmindex', 'mesh_glb', 'rigged_glb'],
  mesh: ['filmindex', 'mesh_glb', 'rigged_glb'], texture: ['filmindex', 'texture_blob'], rig: ['filmindex', 'rigged_glb'],
  take: ['filmindex'], actor_prim: ['filmindex'],
};
const KINDS = {
  scene: ['scene'], dialogue: ['dialogue'], performance: ['performance'],
  voice: ['audio'], wardrobe: ['asset', 'prop'], prop: ['asset', 'prop'],
  model: ['asset'], mesh: ['asset'], texture: ['asset'], rig: ['asset'],
  take: ['take'], actor_prim: ['take'],
};

/** Object, human, robot and virtual actors all have a single canonical StoryBible ActorID. */
export default function Film03ActorBiblePanel({project, actor, api, action, busy, refreshBible}) {
  const [catalog, setCatalog] = useState(null);
  const [detail, setDetail] = useState(null);
  const [role, setRole] = useState('scene');
  const [family, setFamily] = useState('screenplay_scene');
  const [target, setTarget] = useState('');
  const [scope, setScope] = useState('global');
  const [note, setNote] = useState('');
  const [prim, setPrim] = useState('/World/Engineer');
  const [textureSha, setTextureSha] = useState('');
  const [editing, setEditing] = useState(null);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const [castTake, setCastTake] = useState('');
  const [castReport, setCastReport] = useState(null);
  const [error, setError] = useState('');

  const pid = project.id;
  const actorId = actor?.actor_id;
  const root = '/projects/' + pid + '/production-bible';
  useEffect(() => {
    let live = true;
    setDetail(null); setCatalog(null); setError(''); setNotice(''); setEditing(null);
    if (!actorId) return;
    Promise.all([
      api(root + '/actor-catalog'),
      api(root + '/actors/' + encodeURIComponent(actorId)),
    ]).then(([cat, result]) => {
      if (!live) return;
      if (cat?.format !== 'nvp.film03.production_bible_actor_links.v1' ||
          result?.actor_id !== actorId || result?.project_id !== pid)
        throw new Error('A different production ActorID was returned');
      setCatalog(cat); setDetail(result);
    }).catch(e => {if (live) setError(e.message);});
    return () => { live = false; };
  }, [pid, actorId, actor?.revision, project.revision, api]);

  const choices = useMemo(() => (catalog?.sources || []).filter(row =>
    row.family === family &&
    (family !== 'filmindex' || (KINDS[role] || []).includes(row.kind)) &&
    (family !== 'bible_prop' || (role === 'wardrobe' || role === 'prop'))
  ), [catalog, family, role]);

  useEffect(() => {
    if (!choices.some(row => key(row) === target))
      setTarget(choices.length ? key(choices[0]) : '');
  }, [choices, target]);

  function key(entry) {
    return entry.family + '|' + entry.target_id + '|' + entry.target_revision;
  }
  const selected = family === 'texture_blob'
    ? (/^[a-f0-9]{64}$/.test(textureSha)
       ? {family:'texture_blob', target_id:textureSha, target_revision:1, kind:'texture'} : null)
    : choices.find(row => key(row) === target);

  function chooseRole(next) {
    setRole(next); setFamily(FAMILIES[next][0]); setEditing(null);
  }
  function editExisting(entry) {
    setEditing(entry);
    setRole(entry.role); setFamily(entry.source_family);
    setTarget(entry.source_family + '|' + entry.target_id + '|' + entry.target_revision);
    setScope(entry.production_scope);
    setNote(entry.director_note || '');
    setPrim(entry.actor_prim_path || '/World/Engineer');
    if (entry.source_family === 'texture_blob') setTextureSha(entry.target_id);
    setNotice('Editing creates another relationship revision. Historical bindings remain intact.');
  }
  function reviewCastCoverage() {
    if (!castTake) return;
    action(async()=>{
      const report = await api(root + '/takes/' + encodeURIComponent(castTake) +
        '/cast-coverage');
      if (report?.format !== 'nvp.film03.production_bible_actor_cast_coverage.v1')
        throw new Error('Unverified native cast-coverage report');
      setCastReport(report);
    });
  }
  function submit() {
    if (!actorId || !detail || !selected) return;
    action(async () => {
      const result = await api(root + '/actors/' + encodeURIComponent(actorId) + '/links',
        'POST', {
          role, source_family: family, target_id: selected.target_id,
          target_revision: selected.target_revision,
          actor_prim_path: role === 'actor_prim' ? prim : null,
          production_scope: scope, director_note: note,
          expected_actor_revision: detail.bible_revision,
          link_id: editing?.link_id || null,
          expected_link_revision: editing?.link_revision || 0,
        });
      if (result.actor_id !== actorId) throw new Error('ActorID changed during link');
      setDetail(result); setEditing(null); setNotice('Linked at a new durable production-bible revision.');
      await refreshBible(pid);
    });
  }
  function retire(entry) {
    if (!reason.trim()) {setError('Explain why this link is being retired. Old versions remain saved.');return;}
    action(async () => {
      const result = await api(root + '/actors/' + encodeURIComponent(actorId) +
        '/links/' + encodeURIComponent(entry.link_id) + '/retire', 'POST', {
          expected_actor_revision: detail.bible_revision,
          expected_link_revision: entry.link_revision,
          director_reason: reason,
        });
      setDetail(result); setReason('');
      setNotice('Link retired without deleting any original model, asset, or Take.');
      await refreshBible(pid);
    });
  }

  if (!actorId) return null;
  return <section className="card" aria-label="Actor production bible">
    <h3>ActorID · production source registry</h3>
    <p className="fineprint">
      Canonical immutable identity: <code>{actorId}</code>.
      This is the existing StoryBible character ID, not a new duplicate identity.
      Dialogue, voice, outfits, props, 3D meshes and scene references are versioned independently.
    </p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!detail ? <p className="muted">Loading exact ActorID and original assets…</p> : <>
      <p className="fineprint">Bible revision {detail.bible_revision} · {detail.active_links.length} active links · {detail.history.length} historical link versions</p>
      <h4>Active production associations</h4>
      {!detail.active_links.length && <p className="muted">No relationships linked yet. Every character already has an ActorID; add approved sources below.</p>}
      {detail.active_links.map(entry => <div key={entry.link_id} className="scene-item">
        <strong>{entry.role} · {entry.source_family}</strong>
        <small>{entry.target_id} · revision {entry.target_revision} · link version {entry.link_revision}</small>
        <p className="fineprint">Source SHA: <code>{entry.source_sha256}</code> · scope {entry.production_scope}</p>
        {entry.needs_director_source_review && <p role="alert">
          Source changed since this association: review original versus current screenplay, prop or asset before using the linked performance.
        </p>}
        {entry.actor_prim_path && <p className="fineprint">OpenUSD actor: {entry.actor_prim_path}</p>}
        {entry.director_note && <p>{entry.director_note}</p>}
        <button className="secondary" disabled={busy} onClick={() => editExisting(entry)}>Revise link without deleting</button>
        <label>Reason to retire this link
          <input value={reason} maxLength={1200} onChange={e=>setReason(e.target.value)}
            placeholder="Replaced costume or scene; preserve old source" />
        </label>
        <button className="secondary" disabled={busy || !reason.trim()} onClick={() => retire(entry)}>
          Retire link, keep history
        </button>
      </div>)}
      <h4>{editing ? 'Revise existing source link' : 'Link original production resource'}</h4>
      <label>Production relationship type
        <select aria-label="Actor resource role" value={role} onChange={e=>chooseRole(e.target.value)}>
          {Object.keys(FAMILIES).map(name=><option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label>Authoritative source family
        <select aria-label="Actor source family" value={family} onChange={e=>{setFamily(e.target.value);setEditing(null);}}>
          {FAMILIES[role].map(name=><option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label>Existing verified resource (not a file path)
        <select aria-label="Actor source resource" value={target} onChange={e=>setTarget(e.target.value)}>
          {!choices.length && <option value="">No existing compatible original resource</option>}
          {choices.map(row=><option key={key(row)} value={key(row)}>
            {row.name || row.target_id} · {row.kind} · rev {row.target_revision}
          </option>)}
        </select>
      </label>
      {family === 'texture_blob' && <label>Existing original FilmIndex PNG texture SHA-256
        <input aria-label="Texture source SHA-256" value={textureSha} maxLength={64}
          placeholder="64-character source SHA-256" onChange={e=>setTextureSha(e.target.value)} />
      </label>}
      {role === 'actor_prim' && <label>Real OpenUSD actor prim path
        <input aria-label="OpenUSD actor prim path" value={prim} maxLength={240}
          onChange={e=>setPrim(e.target.value)} />
      </label>}
      <label>Scene/time/wardrobe scope
        <input aria-label="Actor production scope" value={scope} maxLength={120}
          onChange={e=>setScope(e.target.value)} />
      </label>
      <label>Director/source relationship note
        <textarea aria-label="Actor resource note" value={note} rows={2} maxLength={1200}
          onChange={e=>setNote(e.target.value)} />
      </label>
      <div className="actions">
        <button disabled={busy || !selected || !scope.trim()} onClick={submit}>
          {editing ? 'Publish revised link' : 'Link verified source'}
        </button>
        {editing && <button className="secondary" onClick={()=>setEditing(null)}>Cancel revision</button>}
      </div>
      {!choices.length && family !== 'texture_blob' && <p className="fineprint">Register a source asset, StoryBible prop or script scene first. NVP refuses invented resource IDs.</p>}
      {family === 'texture_blob' && <p className="fineprint">A texture SHA must already exist in this project's immutable PNG source blob store. NVP verifies its original bytes; pasted unrecognized hashes are refused.</p>}
      <h4>Original OpenUSD actor cast completeness</h4>
      <p className="fineprint">An actor in a frozen source Take must be tied to exactly one existing ActorID. Missing or ambiguous identity blocks complete-cast acceptance; no automatic recasting is permitted.</p>
      <label>Source frozen Take
        <select aria-label="Cast coverage source Take" value={castTake}
          onChange={e=>{setCastTake(e.target.value);setCastReport(null);}}>
          <option value="">Choose a Take to audit</option>
          {(catalog?.sources || []).filter(x=>x.family==='filmindex'&&x.kind==='take')
            .map(x=><option key={x.target_id} value={x.target_id}>{x.target_id}</option>)}
        </select>
      </label>
      <button className="secondary" disabled={busy || !castTake}
        onClick={reviewCastCoverage}>Check every source actor has an ActorID</button>
      {castReport && <>
        <p role="status">{castReport.complete ? 'Full original cast identified'
          : 'Cast incomplete — cannot accept all actor identities'}</p>
        {castReport.authored_actor_prims.map(path=><p key={path} className="fineprint">
          {path} → {castReport.actor_id_by_prim[path] || 'UNCast / multiple ActorIDs'}
        </p>)}
        {!!castReport.uncast_prim_paths.length && <p role="alert">
          Uncast OpenUSD actor prims: {castReport.uncast_prim_paths.join(', ')}.
          Select each StoryBible character and link its real actor prim before acceptance.
        </p>}
      </>}
      <Film03ActorVoicePanel project={project} actorId={actorId}
        detail={detail} catalog={catalog} api={api} action={action} busy={busy}
        onUpdated={async()=>{
          const latest=await api(root + '/actors/' + encodeURIComponent(actorId));
          if(latest?.actor_id!==actorId)
            throw new Error('Voice cast update returned wrong ActorID');
          setDetail(latest);
          await refreshBible(pid);
        }} />
      <h4>Immutable relationship history</h4>
      <details>
        <summary>Show all {detail.history.length} saved relationship revisions</summary>
        {detail.history.map(entry=><p key={entry.link_id + ':' + entry.link_revision} className="fineprint">
          {entry.role} · {entry.status} · {entry.link_id} rev {entry.link_revision} ·
          {entry.target_id} @ {entry.target_revision} · SHA {entry.source_sha256}
        </p>)}
      </details>
      <p className="fineprint">Links describe traceable production sources. A mesh or texture association does not imply redistribution rights, rendered correctness, or director approval.</p>
    </>}
  </section>;
}
