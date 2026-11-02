import React, { useEffect, useMemo, useState } from 'react';

// NVP-PROD-01: editable PROXY staging, not live Blender or photorealistic rendering.
const COLOR = { character: '#4ba1d2', furniture: '#ac815c', prop: '#c1a63d', set_piece: '#6baf72' };

function splitDimensions(value) {
  const numbers = value.split(',').map(v => Number(v.trim()));
  if (numbers.length !== 3 || numbers.some(n => !Number.isFinite(n) || n <= 0)) {
    throw new Error('Dimensions must be three positive numbers in metres, such as 1.8, 0.8, 0.7.');
  }
  return numbers;
}

function saveDownload(filename, text, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function SceneStagePanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [assets, setAssets] = useState([]);
  const [plan, setPlan] = useState(null);
  const [message, setMessage] = useState('');
  const [newName, setNewName] = useState('');
  const [category, setCategory] = useState('furniture');
  const [dimensions, setDimensions] = useState('2, 1, 0.75');
  const [anchors, setAnchors] = useState('{}');
  const [room, setRoom] = useState('8, 6, 3');
  const [assetId, setAssetId] = useState('');
  const [instanceId, setInstanceId] = useState('table_1');
  const [wall, setWall] = useState('');
  const [linkTarget, setLinkTarget] = useState('');
  const [selfAnchor, setSelfAnchor] = useState('');
  const [targetAnchor, setTargetAnchor] = useState('');
  const [maxGap, setMaxGap] = useState('0.5');
  const [notice, setNotice] = useState('');
  const scene = project.scenes.find(x => x.id === sceneId) || null;
  const base = `/projects/${project.id}/production`;

  useEffect(() => {
    setSceneId(project.scenes[0]?.id || '');
    setPlan(null);
  }, [project.id]);

  useEffect(() => {
    let active = true;
    api(base + '/assets')
      .then(rows => { if (active) {
        setAssets(rows);
        setAssetId(old => rows.some(a => a.asset_id === old) ? old : (rows[0]?.asset_id || ''));
      }})
      .catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, [base]);

  useEffect(() => {
    if (!sceneId) return;
    let active = true;
    setPlan(null);
    api(base + `/scenes/${encodeURIComponent(sceneId)}`)
      .then(data => { if (active) { setPlan(data); setMessage(''); }})
      .catch(error => { if (active) {
        // A new scene is expected not to have been staged yet.
        if (error.message.includes('not staged')) { setPlan(null); setMessage(''); }
        else setMessage(error.message);
      }});
    return () => { active = false; };
  }, [base, sceneId, project.revision]);

  const selectedAsset = assets.find(a => a.asset_id === assetId);
  const sceneAssets = useMemo(() => Object.fromEntries(assets.map(a => [a.asset_id, a])), [assets]);
  const poses = plan?.layout?.placements || {};
  const scenePath = base + '/scenes/' + encodeURIComponent(sceneId);
  const execute = (callback) => action(async () => {
    setMessage(''); setNotice('');
    await callback();
  });

  async function reloadAssets() {
    const rows = await api(base + '/assets');
    setAssets(rows);
    setAssetId(old => rows.some(a => a.asset_id === old) ? old : (rows[0]?.asset_id || ''));
  }

  function addAsset() {
    execute(async () => {
      const parsedAnchors = JSON.parse(anchors);
      const added = await api(base + '/assets', 'POST', { name: newName, category,
        dimensions: splitDimensions(dimensions), anchors: parsedAnchors });
      await reloadAssets();
      setAssetId(added.asset_id);
      setNewName(''); setAnchors('{}');
      setNotice('Persistent proxy asset registered. Its ID does not change when other scenes are staged.');
    });
  }

  function stage() {
    execute(async () => {
      const value = await api(scenePath + '/stage', 'POST', { room: splitDimensions(room) });
      setPlan(value);
      setNotice(value.unresolved_cast?.length
        ? 'Scene staged. Register these characters if you want 3D proxies: ' + value.unresolved_cast.join(', ')
        : 'Scene staged. Add furniture or props before solving.');
    });
  }

  function addInstance() {
    execute(async () => {
      if (!plan) throw new Error('Stage a scene first.');
      const attachment = linkTarget ? { target_instance: linkTarget, self_anchor: selfAnchor,
        target_anchor: targetAnchor, max_gap: Number(maxGap) } : null;
      const result = await api(scenePath + '/instances', 'POST', {
        asset_id: assetId, instance_id: instanceId, wall: wall || null, attachment,
        expected_plan_revision: plan.plan_revision,
      });
      setPlan(result);
      setInstanceId('item_' + (result.instances.length + 1));
      setNotice('Asset placed in the plan. Solve the layout to find actual coordinates.');
    });
  }

  function solve() {
    execute(async () => {
      const result = await api(scenePath + '/solve', 'POST', { expected_plan_revision: plan.plan_revision });
      setPlan(result);
      setNotice('Constraint-checked layout proposed. Review the top-down proxy plan before approving it.');
    });
  }

  function approve() {
    execute(async () => {
      const result = await api(scenePath + '/approve', 'POST', { expected_plan_revision: plan.plan_revision });
      setPlan(result);
      setNotice('Layout approved. Export a Blender script or machine-readable manifest.');
    });
  }

  function resync() {
    execute(async () => {
      if (!window.confirm('Resynchronize this stage with the current screenplay? Previous approved geometry is archived. You must solve and approve a new layout.')) return;
      const result = await api(scenePath + '/resync', 'POST', { expected_plan_revision: plan.plan_revision });
      setPlan(result);
      setNotice('Previous stage archived; current scene source linked. Asset choices retained.');
    });
  }

  function download(format) {
    execute(async () => {
      if (format === 'blender') {
        const result = await api(scenePath + '/blender-script');
        saveDownload('NVP_' + sceneId + '_scene.py', result.script, 'text/x-python');
        setNotice('Blender bpy script exported, not executed. Run it inside Blender to create a .blend file.');
      } else {
        const manifest = await api(scenePath + '/manifest');
        saveDownload('NVP_' + sceneId + '_scene.json', JSON.stringify(manifest, null, 2), 'application/json');
        setNotice('Validated production scene manifest exported.');
      }
    });
  }

  return <div className="columns">
    <section className="card">
      <h2>Stage a screenplay scene</h2>
      <p className="muted">This is deterministic proxy geometry, not an animated scene or a rendered film. No AI model or Blender installation is needed to plan it.</p>
      <label>Screenplay scene
        <select value={sceneId} onChange={e => { setSceneId(e.target.value); setNotice(''); }}>
          {project.scenes.map(s => <option key={s.id} value={s.id}>{s.number}. {s.heading}</option>)}
        </select>
      </label>
      {!plan && scene && <>
        <label>Room width, depth, height — metres
          <input value={room} onChange={e => setRoom(e.target.value)} placeholder="8, 6, 3" />
        </label>
        <button className="primary" disabled={busy} onClick={stage}>Create 3D stage proposal</button>
      </>}
      {plan && <>
        <p className="fineprint">Scene source revision {plan.screenplay_revision} · stage revision {plan.plan_revision} · {plan.approval_state}</p>
        <p className="fineprint">Room: {plan.room.join(' × ')} metres · {plan.instances.length} placed asset(s)</p>
        <div className="actions">
          <button className="secondary" disabled={busy} onClick={resync}>Resync source / reopen stage</button>
          {plan.approval_state !== 'approved' && <>
            <button className="secondary" disabled={busy} onClick={solve}>Solve and validate layout</button>
            <button className="primary" disabled={busy || !plan.layout} onClick={approve}>Approve validated layout</button>
          </>}
        </div>
      </>}
      <h3>Persistent asset registry</h3>
      <p className="fineprint">Each registered item is a box proxy with immutable dimensions and anchors; real Blender models are not loaded yet.</p>
      <label>Name<input value={newName} maxLength={150} onChange={e => setNewName(e.target.value)} placeholder="Dining table" /></label>
      <label>Type<select value={category} onChange={e => setCategory(e.target.value)}>
        <option value="furniture">Furniture</option><option value="character">Character</option>
        <option value="prop">Prop</option><option value="set_piece">Set piece</option>
      </select></label>
      <label>Dimensions X, Y, Z (metres)<input value={dimensions} onChange={e => setDimensions(e.target.value)} /></label>
      <label>Spatial anchors (local XYZ, JSON)<textarea rows={3} value={anchors} onChange={e => setAnchors(e.target.value)}
        placeholder='{"seat": [0, 0.2, 0.45]}' /></label>
      <button className="secondary" disabled={busy || !newName.trim()} onClick={addAsset}>Register reusable proxy asset</button>
      {plan && plan.approval_state !== 'approved' && <>
        <h3>Add an asset to this scene</h3>
        <label>Asset<select value={assetId} onChange={e => setAssetId(e.target.value)}>
          {assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.category}: {a.name}</option>)}
        </select></label>
        <label>Instance ID<input value={instanceId} onChange={e => setInstanceId(e.target.value)} maxLength={64} /></label>
        <label>Optional wall constraint<select value={wall} onChange={e => setWall(e.target.value)}>
          <option value="">No wall constraint</option>
          <option value="north">North</option><option value="south">South</option>
          <option value="east">East</option><option value="west">West</option>
        </select></label>
        <details><summary>Advanced: attach to another asset's named anchor</summary>
          <label>Existing instance<select value={linkTarget} onChange={e => setLinkTarget(e.target.value)}>
            <option value="">No anchor relationship</option>
            {plan.instances.map(i => <option key={i.instance_id} value={i.instance_id}>{i.instance_id}</option>)}
          </select></label>
          {linkTarget && <>
            <p className="fineprint">Available local anchors: {Object.keys(selectedAsset?.anchors || {}).join(', ') || '(none)'}</p>
            <label>My anchor<input value={selfAnchor} onChange={e => setSelfAnchor(e.target.value)} /></label>
            <label>Target anchor<input value={targetAnchor} onChange={e => setTargetAnchor(e.target.value)} /></label>
            <label>Maximum anchor gap, metres<input value={maxGap} onChange={e => setMaxGap(e.target.value)} /></label>
          </>}
        </details>
        <button className="secondary" disabled={busy || !assetId || !instanceId.trim()} onClick={addInstance}>Add to stage plan</button>
      </>}
    </section>
    <section className="card">
      <h2>Top-down stage preview</h2>
      {message && <p role="alert">{message}</p>}
      {notice && <p className="muted">{notice}</p>}
      {!plan?.layout && <p className="muted">Solve the stage to see a validated arrangement of proxy objects.</p>}
      {plan?.layout && <>
        <svg viewBox={`-0.5 -0.5 ${plan.room[0] + 1} ${plan.room[1] + 1}`}
          style={{ width: '100%', maxHeight: 420, background: '#1b2428', borderRadius: 8 }}
          role="img" aria-label="Top-down room layout showing generated asset footprints">
          <rect x="0" y="0" width={plan.room[0]} height={plan.room[1]} fill="#2d383b" stroke="#a1b3b8" strokeWidth=".05" />
          {plan.instances.map(item => {
            const pose = poses[item.instance_id], asset = sceneAssets[item.asset_id];
            if (!pose || !asset) return null;
            return <g key={item.instance_id}
              transform={`translate(${pose.x} ${plan.room[1] - pose.y}) rotate(${-pose.rotation})`}>
              <rect x={-asset.dimensions[0]/2} y={-asset.dimensions[1]/2}
                width={asset.dimensions[0]} height={asset.dimensions[1]}
                fill={COLOR[asset.category] || '#ddd'} stroke="#eef" strokeWidth=".035" />
              <text textAnchor="middle" dominantBaseline="middle" fontSize=".18" fill="#fff">{item.instance_id.slice(0, 20)}</text>
            </g>;
          })}
        </svg>
        <p className="fineprint">Solver: {plan.layout.solver}, {plan.layout.candidates_checked} candidate placements examined.</p>
        {plan.layout.checked.limitations.map((line, index) => <p className="fineprint" key={index}>{line}</p>)}
      </>}
      {plan && <>
        <h3>Staged objects</h3>
        {plan.instances.map(item => <p className="fineprint" key={item.instance_id}>
          <strong>{item.instance_id}</strong> · {sceneAssets[item.asset_id]?.name || item.asset_id}
          {item.wall ? ` · ${item.wall} wall` : ''}
          {poses[item.instance_id] ? ` · (${poses[item.instance_id].x}, ${poses[item.instance_id].y})` : ' · not solved'}
        </p>)}
      </>}
      {plan?.approval_state === 'approved' && <>
        <h3>Export for Blender</h3>
        <p className="fineprint">Exports geometry, spatial anchor markers, an establishing camera and a basic light as a bpy script. No Blender process runs here.</p>
        <div className="actions">
          <button className="primary" disabled={busy} onClick={() => download('blender')}>Download Blender scene script</button>
          <button className="secondary" disabled={busy} onClick={() => download('manifest')}>Download validated JSON</button>
        </div>
        <p className="fineprint">In Blender on your machine: <code>blender -b -P scene.py -- --output scene.blend</code></p>
      </>}
    </section>
  </div>;
}
