import React, { useEffect, useState } from 'react';

// PROD-06A: creator-reviewed motion, not automatic motion retargeting or final acting.
export default function MotionRigPanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [session, setSession] = useState(null);
  const [clips, setClips] = useState([]);
  const [chosenActor, setChosenActor] = useState('');
  const [chosenClip, setChosenClip] = useState('');
  const [startFrame, setStartFrame] = useState('1');
  const [bvh, setBvh] = useState('');
  const [clipName, setClipName] = useState('Motion clip');
  const [license, setLicense] = useState('creator_owned');
  const [mapping, setMapping] = useState('{"hips":"Hips","arm_left":"LeftArm"}');
  const [notice, setNotice] = useState('');
  const root = `/projects/${project.id}/production/scenes/${sceneId}/rig-motion`;

  async function reload() {
    if (!sceneId) return;
    const [available, rig] = await Promise.all([
      api(`/projects/${project.id}/production/motion-clips`),
      api(root).catch(error => {
        if (String(error.message).includes('Motion session does not exist')) return null;
        throw error;
      }),
    ]);
    setClips(available); setSession(rig);
  }
  useEffect(() => {
    let active = true;
    setSession(null);setNotice('');
    Promise.all([
      api(`/projects/${project.id}/production/motion-clips`),
      sceneId ? api(root).catch(e => String(e.message).includes('Motion session does not exist') ? null : Promise.reject(e)) : Promise.resolve(null),
    ]).then(([available, rig]) => { if (active) { setClips(available);setSession(rig); } })
      .catch(e => { if (active) setNotice(e.message); });
    return () => { active = false; };
  }, [project.id, sceneId, root, api]);

  async function perform(fn, message) {
    await action(async () => { await fn(); await reload(); setNotice(message); });
  }
  async function importBvh() {
    await perform(async () => {
      const map = JSON.parse(mapping);
      if (typeof map !== 'object' || !map || Array.isArray(map)) throw Error('Joint mapping must be a JSON object.');
      const result = await api(`/projects/${project.id}/production/motion-clips/bvh`, 'POST', {
        name: clipName, license, bvh, mapping: map,
      });
      setChosenClip(result.clip_id);
      setNotice(`Registered ${result.clip_id}; BVH root translation is ignored.`);
    }, 'Motion source registered. Check the declared license and joint mapping before approval.');
  }
  async function downloadScript() {
    await action(async () => {
      const result = await api(`${root}/blender-script`);
      const file = new Blob([result.script], { type: 'text/x-python;charset=utf-8' });
      const url = URL.createObjectURL(file);const anchor=document.createElement('a');
      anchor.href=url;anchor.download=`nvp_${sceneId}_rigged_preview.py`;
      document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setNotice('Saved a Blender 5.2+ script. This is a basic armature preview, not automatically calibrated retargeting.');
    });
  }
  const actorId = chosenActor || session?.actors?.[0]?.instance_id || '';
  const clipId = chosenClip || clips?.[0]?.id || '';
  return <div className="columns">
    <section className="card">
      <h2>Character motion library</h2>
      <p className="muted">Import local BVH clips with an explicit map to seven humanoid preview bones. No remote downloads, automatic license verification, or model-generated Blender code.</p>
      <label>Scene
        <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
          {project.scenes.map(s => <option key={s.id} value={s.id}>{s.heading}</option>)}
        </select>
      </label>
      <label>Motion name <input value={clipName} onChange={e => setClipName(e.target.value)} /></label>
      <label>Declared license / ownership <input value={license} onChange={e => setLicense(e.target.value)} /></label>
      <label>BVH source (local file)
        <input type="file" accept=".bvh,text/plain" onChange={async e => {
          const file = e.target.files?.[0];if (!file) return;
          if (file.size > 1000000) { setNotice('BVH must not exceed 1 MB.');return; }
          setBvh(await file.text());setClipName(file.name.replace(/\.bvh$/i, ''));
        }} />
      </label>
      <label>Explicit BVH joint mapping (JSON)
        <textarea rows={3} value={mapping} onChange={e => setMapping(e.target.value)} />
      </label>
      <button disabled={busy || !bvh.trim()} onClick={importBvh}>Register motion clip</button>
      <p className="muted">Clip IDs and source hashes remain permanent. License text is a declaration to be verified before using external motion commercially.</p>
    </section>
    <section className="card">
      <h2>Direct a rigged performance</h2>
      {notice && <p role="status">{notice}</p>}
      {!session ? <>
        <p className="muted">Approve a PROD-05 filmed sequence before creating its rig-motion layer.</p>
        <button disabled={busy || !sceneId} onClick={() => perform(() => api(root, 'POST'), 'Created an editable motion layer.')}>Create motion layer</button>
      </> : <>
        <p><strong>Status:</strong> {session.status}{session.stale ? ' · previous shot take changed' : ''} · revision {session.revision}</p>
        <p className="muted">Preview rig: humanoid_v1. Root movement remains controlled by approved actor blocking.</p>
        <label>Character
          <select value={actorId} onChange={e => setChosenActor(e.target.value)}>
            {session.actors.map(a => <option key={a.instance_id} value={a.instance_id}>{a.instance_id}</option>)}
          </select>
        </label>
        <label>Reusable motion clip
          <select value={clipId} onChange={e => setChosenClip(e.target.value)}>
            {clips.map(c => <option key={c.id} value={c.id}>{c.name} ({c.license})</option>)}
          </select>
        </label>
        <label>Start frame (24 fps) <input type="number" min="1" max={session.end_frame} value={startFrame} onChange={e => setStartFrame(e.target.value)} /></label>
        <button disabled={busy || session.status !== 'draft' || session.stale || !clipId || !actorId}
          onClick={() => perform(() => api(`${root}/attach`, 'POST', {
            actor_instance_id: actorId,clip_id: clipId,start_frame: Number(startFrame),expected_revision: session.revision,
          }), 'Clip assigned. Preview and verify orientation before approving.')}>Attach clip</button>
        <button disabled={busy || session.status !== 'draft' || session.stale || !actorId}
          onClick={() => perform(() => api(`${root}/clear`, 'POST', {
            actor_instance_id: actorId,expected_revision: session.revision,
          }), 'Cleared this actor’s clip assignments.')}>Clear actor clips</button>
        {session.actors.map(a => <div key={a.instance_id}>
          <strong>{a.instance_id}</strong>
          <ul>{a.segments.map(seg => <li key={`${seg.clip_id}-${seg.start_frame}`}>{seg.clip_id}: frames {seg.start_frame}–{seg.stop_frame - 1}</li>)}</ul>
        </div>)}
        <button disabled={busy || session.status !== 'draft' || session.stale}
          onClick={() => perform(() => api(`${root}/approve`, 'POST', { expected_revision: session.revision }),
            'Approved the current rig-motion layer.')}>Approve motion</button>
        <button disabled={busy || session.status !== 'approved' || session.stale} onClick={downloadScript}>Export rigged Blender scene</button>
      </>}
    </section>
  </div>;
}
