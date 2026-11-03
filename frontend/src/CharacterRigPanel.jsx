import React, { useEffect, useState } from 'react';

const roles = ['hips', 'spine', 'head', 'arm_left', 'arm_right', 'leg_left', 'leg_right'];

export default function CharacterRigPanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [library, setLibrary] = useState([]);
  const [session, setSession] = useState(null);
  const [actorId, setActorId] = useState('');
  const [assetId, setAssetId] = useState('');
  const [file, setFile] = useState(null);
  const [license, setLicense] = useState('creator_owned');
  const [attribution, setAttribution] = useState('');
  const [source, setSource] = useState('');
  const [scale, setScale] = useState('1');
  const [mapping, setMapping] = useState(Object.fromEntries(roles.map(x => [x, x])));
  const [notice, setNotice] = useState('');
  const base = `/projects/${project.id}/production/scenes/${sceneId}/rigged-characters`;
  const assets = `/projects/${project.id}/production/rigged-characters`;

  async function reload() {
    const [models, plan] = await Promise.all([
      api(assets), api(base).catch(err => {
        if (String(err.message).includes('Rigged character session does not exist')) return null;
        throw err;
      }),
    ]);
    setLibrary(models);setSession(plan);
  }
  useEffect(() => {
    let live = true;
    Promise.all([api(assets),sceneId ? api(base).catch(e =>
      String(e.message).includes('Rigged character session does not exist') ? null : Promise.reject(e)) : Promise.resolve(null)])
      .then(([models,plan]) => { if (live) { setLibrary(models);setSession(plan);setNotice(''); } })
      .catch(e => { if (live) setNotice(String(e.message)); });
    return () => { live = false; };
  }, [api, assets, base, sceneId]);

  async function perform(fn, msg) {
    await action(async () => {await fn();await reload();setNotice(msg);});
  }

  async function upload() {
    if (!file) {setNotice('Choose a rigged .glb file.');return;}
    if (file.size > 32 * 1024 * 1024) {setNotice('Maximum imported character size is 32 MiB.');return;}
    await perform(async () => {
      const qs = new URLSearchParams({license_code:license,attribution,source});
      const response = await fetch(`/api${assets}?${qs}`, {
        method:'POST',headers:{'Content-Type':'model/gltf-binary'},body:file,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Rigged character import failed');
      }
      const imported = await response.json();
      setAssetId(imported.asset_id);
      setMapping(Object.fromEntries(roles.map(x => [x,
        imported.joint_names.includes(x) ? x : (imported.joint_names[0] || '')])));
    },'Registered character geometry and declared rights. Review bone mapping before approval.');
  }

  async function downloadBundle() {
    await action(async () => {
      const response=await fetch(`/api${base}/bundle`);
      if (!response.ok) {
        const error=await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Character bundle export failed');
      }
      const url=URL.createObjectURL(await response.blob());
      const a=document.createElement('a');a.href=url;a.download=`nvp_${sceneId}_rigged_characters.zip`;
      a.click();URL.revokeObjectURL(url);
      setNotice('Downloaded approved Blender bundle. Import/deformation validation is still required for each real asset.');
    });
  }

  const selected=library.find(x => x.asset_id === assetId);
  const chosenActor=actorId || session?.actors?.[0]?.instance_id || '';
  return <div className="columns">
    <section className="card">
      <h2>Import a rigged character</h2>
      <p className="muted">PROD-06C imports local, self-contained skinned GLB assets. NVP does not download characters, infer a skeleton mapping, or certify an asset license.</p>
      <label>Character GLB file <input type="file" accept=".glb,model/gltf-binary" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <label>Declared license
        <select value={license} onChange={e => setLicense(e.target.value)}>
          {['creator_owned','CC0-1.0','CC-BY-4.0','commercial_licensed','evaluation_only'].map(x => <option key={x}>{x}</option>)}
        </select>
      </label>
      <label>Attribution <input value={attribution} onChange={e => setAttribution(e.target.value)} /></label>
      <label>Source / provenance <input value={source} onChange={e => setSource(e.target.value)} /></label>
      <button disabled={busy || !file} onClick={upload}>Validate and register GLB</button>
      <label>Active screenplay scene
        <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
          {project.scenes.map(x => <option key={x.id} value={x.id}>{x.heading}</option>)}
        </select>
      </label>
      {!session ? <button disabled={busy || !sceneId} onClick={() => perform(() => api(base,'POST'),'Created director-editable character binding plan.')}>Create character binding plan</button>
        : <p>Status: <strong>{session.status}</strong> · revision {session.revision}{session.stale ? ' · STALE SOURCE' : ''}</p>}
    </section>
    <section className="card">
      <h2>Retarget with explicit bone mapping</h2>
      {notice && <p role="status">{notice}</p>}
      <label>Registered character
        <select value={assetId} onChange={e => setAssetId(e.target.value)}>
          <option value="">Select a rigged asset</option>
          {library.map(x => <option key={x.asset_id} value={x.asset_id}>{x.asset_id.slice(0,18)} · {x.joint_count} joints · {x.license}</option>)}
        </select>
      </label>
      {selected && <p className="muted">Registered SHA {selected.sha256.slice(0,16)}… · {selected.skinned_vertices} vertices. Rights are creator-declared, not independently verified.</p>}
      <label>Approved scene actor ID <input value={chosenActor} onChange={e => setActorId(e.target.value)} placeholder="Copy an approved actor instance ID" /></label>
      <label>Character scale factor <input value={scale} onChange={e => setScale(e.target.value)} /></label>
      {roles.map(role => <label key={role}>{role}
        <select value={mapping[role]} onChange={e => setMapping(prev => ({...prev,[role]:e.target.value}))}>
          <option value="">Select a source bone</option>
          {(selected?.joint_names || []).map(name => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>)}
      <button disabled={busy || !session || session.stale || session.status !== 'draft' || !chosenActor || !assetId}
        onClick={() => perform(() => api(`${base}/bind`,'POST', {
          actor_instance_id:chosenActor,character_asset_id:assetId,role_map:mapping,
          uniform_scale:Number(scale),expected_revision:session.revision,
        }), 'Mapped rig to existing approved motion. Inspect its rest pose before final use.')}>Save explicit bone mapping</button>
      {session?.actors?.map(x => <p key={x.instance_id}>{x.instance_id} → {x.character_asset_id}</p>)}
      <button disabled={busy || !session || session.status !== 'draft' || session.stale || !session.actors.length}
        onClick={() => perform(() => api(`${base}/approve`,'POST', {expected_revision:session.revision}),
          'Approved character identity and bone mapping without changing the original performance.')}>Approve rigged character binding</button>
      <button disabled={busy || session?.status !== 'approved' || session.stale} onClick={downloadBundle}>Export Blender character bundle</button>
      <p className="muted">This is explicit bone-name remapping of approved rotations, not automatic motion capture retargeting. Different bone axes/rest poses may require a future calibrated solver.</p>
    </section>
  </div>;
}
