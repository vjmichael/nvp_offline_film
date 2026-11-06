import React, { useEffect, useState } from 'react';

/** NVP-PROD-02..04: auditable world edits, licensed GLB import and basic previs. */
const LICENSES = ['creator_owned', 'CC0-1.0', 'CC-BY-4.0', 'commercial_licensed', 'evaluation_only'];

function downloadText(name, value) {
  const blob = new Blob([value], { type: 'text/x-python;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

export default function ProductionAuthoringPanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [world, setWorld] = useState(null);
  const [dialogue, setDialogue] = useState(null);
  const [blocking, setBlocking] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [assets, setAssets] = useState([]);
  const [meshes, setMeshes] = useState([]);
  const [blender, setBlender] = useState(null);
  const [renderPreflight, setRenderPreflight] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [instance, setInstance] = useState('');
  const [field, setField] = useState('visible');
  const [value, setValue] = useState('false');
  const [lock, setLock] = useState(true);
  const [meshAssetId, setMeshAssetId] = useState('');
  const [license, setLicense] = useState('creator_owned');
  const [attribution, setAttribution] = useState('');
  const [source, setSource] = useState('');
  const [file, setFile] = useState(null);
  const [actor, setActor] = useState('');
  const [targetX, setTargetX] = useState('3');
  const [targetY, setTargetY] = useState('3');
  const [markStart, setMarkStart] = useState('0');
  const [markEnd, setMarkEnd] = useState('4');
  const [subjectIds, setSubjectIds] = useState([]);
  const [lens, setLens] = useState('50');
  const [shotSize, setShotSize] = useState('medium');
  const base = `/projects/${project.id}/production`;
  const path = `${base}/scenes/${encodeURIComponent(sceneId)}`;
  const people = (world?.manifest?.instances || []).filter(item => item.category === 'character');
  const room = world?.manifest?.room_m || [8, 6, 3];

  useEffect(() => { setSceneId(project.scenes[0]?.id || ''); }, [project.id]);
  useEffect(() => { setRenderPreflight(null); }, [project.id, sceneId, project.revision, world?.revision]);

  async function refresh() {
    if (!sceneId) return;
    const results = await Promise.allSettled([
      api(path + '/world'), api(path + '/dialogue'), api(path + '/blocking'),
      api(path + '/cameras'), api(base + '/assets'), api(base + '/meshes'),
      api('/production/blender-availability')
    ]);
    const values = results.map((r) => r.status === 'fulfilled' ? r.value : null);
    setWorld(values[0]); setDialogue(values[1]); setBlocking(values[2] || []);
    setCameras(values[3] || []); setAssets(values[4] || []); setMeshes(values[5] || []);
    setBlender(values[6]);
    const failed = results.find((r) => r.status === 'rejected');
    setError(failed ? failed.reason.message : '');
    const participants = values[0]?.manifest?.instances || [];
    setInstance(old => participants.some(x => x.instance_id === old) ? old : participants[0]?.instance_id || '');
    const characters = participants.filter(x => x.category === 'character');
    setActor(old => characters.some(x => x.instance_id === old) ? old : characters[0]?.instance_id || '');
    setMeshAssetId(old => (values[4] || []).some(x => x.asset_id === old) ? old : (values[4] || [])[0]?.asset_id || '');
  }

  useEffect(() => { let active = true; if (sceneId) refresh().catch(err => { if(active) setError(err.message); });
    return () => { active = false; }; }, [sceneId, project.revision]);

  const execute = (callback) => action(async () => {
    setError(''); setNotice('');
    await callback();
    await refresh();
  });

  function editWorld(human) {
    execute(async () => {
      const parsedValue = field === 'visible' ? value === 'true' :
        field === 'pose.rotation' ? Number(value) : Number(value);
      const payload = { instance_id: instance, field, value: parsedValue,
                        expected_revision: world.revision, locked: lock, rationale: 'Director-requested staging proposal' };
      if (human) {
        await api(path + '/world/human', 'POST', payload);
        setNotice('Human staging edit recorded and validated. Your field stays pinned.');
      } else {
        await api(path + '/world/proposals', 'POST', payload);
        setNotice('AI staging proposal recorded, not applied.');
      }
    });
  }

  function decideProposal(item, decision) {
    execute(async () => {
      await api(path + `/world/proposals/${encodeURIComponent(item.id)}/decision`,
        'POST', { decision, expected_revision: world.revision });
      setNotice(decision === 'accept' ? 'Proposal accepted and geometry checked.' : 'Proposal rejected.');
    });
  }

  function undo() {
    execute(async () => { await api(path + '/world/undo', 'POST', { expected_revision: world.revision });
      setNotice('Previous world edit restored from durable history.'); });
  }

  function rebase() {
    execute(async () => { await api(path + '/world/rebase', 'POST', { expected_revision: world.revision });
      setNotice('Human edits were rechecked against the newly approved scene.'); });
  }

  async function importMesh() {
    if (!file) throw new Error('Choose a self-contained .glb file.');
    if (file.size > 32 * 1024 * 1024) throw new Error('GLB exceeds the 32 MiB import limit.');
    const query = new URLSearchParams({ license_code: license, attribution, source });
    const response = await fetch(`/api${base}/assets/${encodeURIComponent(meshAssetId)}/mesh?${query}`, {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
    });
    if (!response.ok) { const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || 'Mesh import refused'); }
    return response.json();
  }

  function addBlocking() {
    execute(async () => {
      const mark = await api(path + '/blocking', 'POST', {
        actor_instance_id: actor, target_xy_m: [Number(targetX), Number(targetY)],
        start_s: Number(markStart), end_s: Number(markEnd), action: 'walk'
      });
      setNotice(`Blocking path accepted: ${mark.path.distance_m} m, ${mark.path.nodes_checked} checked nodes.`);
    });
  }

  function addCamera() {
    execute(async () => {
      const camera = await api(path + '/cameras', 'POST', {
        subjects: subjectIds, lens_mm: Number(lens), shot_size: shotSize,
      });
      setNotice(`Camera solved: maximum frame residual ${camera.solution.max_residual}.`);
    });
  }

  return <div className="columns">
    <section className="card">
      <h2>Direct the 3D scene</h2>
      <p className="muted">Persistent, deterministic scene editing. Human changes take priority; AI changes remain optional proposals.</p>
      <label>Active screenplay scene
        <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
          {project.scenes.map(s => <option key={s.id} value={s.id}>{s.number}. {s.heading}</option>)}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {world?.stale && <p role="alert">The approved base scene changed. Recheck inherited edits before exporting.</p>}
      {world?.stale && <button disabled={busy} onClick={rebase}>Review and rebase edits</button>}
      {world?.manifest && <>
        <p className="fineprint">World revision {world.revision} · Room {room.join(' × ')} m · {world.manifest.instances.length} staged objects.</p>
        <svg viewBox={`0 0 ${room[0]} ${room[1]}`} width="100%" role="img" aria-label="Top-down 3D staging and blocking preview" style={{ background: '#202935', borderRadius: '8px' }}>
          {world.manifest.instances.map(item => {
            const dims = item.dimensions; const rotated = item.pose.rotation % 180 !== 0;
            const dx = rotated ? dims[1] : dims[0]; const dy = rotated ? dims[0] : dims[1];
            return <g key={item.instance_id}>
              <rect x={item.pose.x-dx/2} y={room[1]-item.pose.y-dy/2} width={dx} height={dy}
                stroke="white" strokeWidth="0.02" fill={item.category==='character' ? '#3489c7' : '#b48b55'} opacity={item.visible === false ? .30 : .85}/>
              <text x={item.pose.x} y={room[1]-item.pose.y} fontSize=".18" textAnchor="middle" fill="white">{item.instance_id}</text>
            </g>;
          })}
          {blocking.filter(item => !item.stale).map(item => <polyline key={item.id}
            points={item.path.points.map(p => `${p[0]},${room[1]-p[1]}`).join(' ')}
            fill="none" stroke="#68df9b" strokeWidth=".05" />)}
          {cameras.filter(c => !c.stale).map(c => <circle key={c.id} cx={c.solution.position_m[0]} cy={room[1]-c.solution.position_m[1]} r=".12" fill="#f9e16b"/>)}
        </svg>
        <h3>Edit a world attribute</h3>
        <label>Object<select value={instance} onChange={e => setInstance(e.target.value)}>
          {world.manifest.instances.map(i => <option key={i.instance_id} value={i.instance_id}>{i.name} ({i.instance_id})</option>)}
        </select></label>
        <label>Attribute<select value={field} onChange={e => { setField(e.target.value); setValue(e.target.value === 'visible' ? 'true' : '0'); }}>
          <option value="visible">Visibility</option><option value="pose.x">X position (m)</option>
          <option value="pose.y">Y position (m)</option><option value="pose.rotation">Rotation (degrees)</option>
        </select></label>
        {field === 'visible' ? <select value={value} onChange={e => setValue(e.target.value)}>
          <option value="true">Visible</option><option value="false">Hidden</option></select>
          : <input type="number" step={field === 'pose.rotation' ? 90 : .25} value={value} onChange={e => setValue(e.target.value)} />}
        <label><input type="checkbox" checked={lock} onChange={e => setLock(e.target.checked)}/> Pin human change</label>
        <div className="actions">
          <button disabled={busy} onClick={() => editWorld(true)}>Apply human edit</button>
          <button disabled={busy} onClick={() => editWorld(false)}>Propose AI edit</button>
          <button disabled={busy || world.revision===0} onClick={undo}>Undo last edit</button>
        </div>
        <h3>Review proposed changes</h3>
        {world.proposals.filter(p => p.status==='proposed').map(p => <div key={p.id} className="scene-item">
          <strong>{p.instance_id}: {p.field} = {JSON.stringify(p.value)}</strong>
          <div className="actions"><button disabled={busy} onClick={() => decideProposal(p,'accept')}>Approve</button>
            <button disabled={busy} onClick={() => decideProposal(p,'reject')}>Reject</button></div>
        </div>)}
      </>}
    </section>
    <section className="card">
      <h2>Licensed 3D assets</h2>
      <p className="fineprint">Import self-contained GLB 2.0 meshes. NVP checks geometry, dimensions, immutable IDs, file digest and declared license. This is not yet a full 3D renderer.</p>
      <label>Existing persistent asset<select value={meshAssetId} onChange={e => setMeshAssetId(e.target.value)}>
        {assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.dimensions.join(' × ')} m)</option>)}
      </select></label>
      <label>GLB file<input type="file" accept=".glb,model/gltf-binary" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
      <label>Declared license<select value={license} onChange={e => setLicense(e.target.value)}>
        {LICENSES.map(l => <option key={l}>{l}</option>)}
      </select></label>
      <label>Attribution<input value={attribution} onChange={e => setAttribution(e.target.value)}/></label>
      <label>Asset source<input value={source} onChange={e => setSource(e.target.value)}/></label>
      <button disabled={busy || !file || !meshAssetId} onClick={() => execute(async () => {
        await importMesh(); setNotice('Mesh registered, validated, and content-addressed.');
      })}>Import verified mesh</button>
      {meshes.map(m => <p key={m.asset_id} className="fineprint">{m.asset_id}: {m.mesh_count} mesh(es), {m.faces} faces · {m.license}</p>)}
      <h3>Blender acceptance</h3>
      <p className="fineprint">Review the precise director-approved proxy world and Blender script hashes before a future trusted native render approval. This preview does not start Blender or reserve RAM/VRAM.</p>
      <button disabled={busy || !sceneId || !world?.manifest || world?.stale} onClick={() => execute(async () => {
        const proof = await api(path + '/render-preflight');
        setRenderPreflight(proof);
        setNotice('Render source verified. No Blender job or native approval was created.');
      })}>Inspect render preflight</button>
      {renderPreflight && <div role="status" className="scene-item">
        <strong>Source preview — Blender not started</strong>
        <p className="fineprint">Project revision {renderPreflight.project_revision} · World revision {renderPreflight.world_revision} · {renderPreflight.instance_count} proxy objects.</p>
        <p className="fineprint" style={{overflowWrap:'anywhere'}}>World SHA-256: <code>{renderPreflight.world_sha256}</code></p>
        <p className="fineprint" style={{overflowWrap:'anywhere'}}>Blender script SHA-256: <code>{renderPreflight.blender_script_sha256}</code></p>
        <p className="fineprint">Native authorization: not granted · Resource admission: not checked · Output: not rendered.</p>
      </div>}
      <p className="fineprint">{blender?.available ? blender.version + ' found' : 'Native Blender not installed here; generated scripts require Blender 5.2 LTS.'}</p>
      <button disabled={busy || !world?.manifest || world?.stale} onClick={() => execute(async () => {
        const out = await api(path + '/world/blender-script');
        downloadText('NVP_scene.py',out.script);
        setNotice('Blender exporter saved. This does not claim Blender has run.');
      })}>Export approved world as Blender script</button>
      <h2>Actor blocking</h2>
      <label>Actor<select value={actor} onChange={e => setActor(e.target.value)}>
        {people.map(i => <option key={i.instance_id} value={i.instance_id}>{i.name}</option>)}
      </select></label>
      <div className="actions">
        <label>Destination X<input type="number" step=".25" value={targetX} onChange={e => setTargetX(e.target.value)} /></label>
        <label>Destination Y<input type="number" step=".25" value={targetY} onChange={e => setTargetY(e.target.value)} /></label>
      </div>
      <div className="actions">
        <label>Start (sec)<input type="number" value={markStart} onChange={e => setMarkStart(e.target.value)} /></label>
        <label>End (sec)<input type="number" value={markEnd} onChange={e => setMarkEnd(e.target.value)} /></label>
      </div>
      <button disabled={busy || !actor} onClick={addBlocking}>Validate and save actor path</button>
      {blocking.map(b => <p key={b.id} className="fineprint">{b.mark.actor_instance_id} → {b.mark.target_xy_m.join(', ')} · {b.path.distance_m} m {b.stale ? '· Needs review' : ''}</p>)}
      <h2>Virtual camera solver</h2>
      <p className="fineprint">Select one to three actors. The camera solver measures point-framing errors and reports occlusion failures; it is not yet a Blender pixel-level test.</p>
      {people.map(i => <label key={i.instance_id}><input type="checkbox" checked={subjectIds.includes(i.instance_id)} onChange={e => setSubjectIds(old => e.target.checked ? [...old,i.instance_id] : old.filter(x => x!==i.instance_id))}/> {i.name}</label>)}
      <label>Lens (mm)<input type="number" min="18" max="135" value={lens} onChange={e => setLens(e.target.value)} /></label>
      <label>Shot size<select value={shotSize} onChange={e => setShotSize(e.target.value)}>
        <option value="wide">Wide</option><option value="full">Full</option><option value="medium">Medium</option><option value="close_up">Close-up</option>
      </select></label>
      <button disabled={busy || subjectIds.length===0 || subjectIds.length>3} onClick={addCamera}>Solve and validate camera</button>
      {cameras.map(c => <p className="fineprint" key={c.id}>{c.recipe.shot_size} at {c.solution.position_m.join(', ')} m · max residual {c.solution.max_residual} {c.stale?'· Stale':''}</p>)}
      <h2>Dialogue timing</h2>
      {(dialogue?.dialogue || []).map(l => <div key={l.id} className="scene-item">
        <strong>{l.speaker_name}:</strong> {l.text}
        <p className="fineprint">{l.duration_s === null ? 'Timing unmeasured' : `${l.duration_s} s (${l.timing_origin})`}; listeners: {l.listener_instance_ids.join(', ') || 'not assigned'}</p>
      </div>)}
    </section>
  </div>;
}
