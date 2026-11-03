import React, { useEffect, useState } from 'react';

// PROD-06B: a creator-reviewed geometry + rest-pose calibration layer.
// This controls a procedural weighted preview, not an imported hero mesh.
const roles = ['hips', 'spine', 'head', 'arm_left', 'arm_right', 'leg_left', 'leg_right'];

function triplet(value) {
  const values = value.split(',').map(x => Number(x.trim()));
  if (values.length !== 3 || values.some(x => !Number.isFinite(x) || Math.abs(x) > 180)) {
    throw new Error('Enter three angles between -180 and 180 degrees, separated by commas.');
  }
  return values;
}

export default function SkinningPanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [session, setSession] = useState(null);
  const [actorId, setActorId] = useState('');
  const [role, setRole] = useState('arm_left');
  const [sourceRest, setSourceRest] = useState('0, 0, 0');
  const [targetRest, setTargetRest] = useState('0, 0, 0');
  const [notice, setNotice] = useState('');
  const root = `/projects/${project.id}/production/scenes/${sceneId}/skinning`;

  async function reload() {
    if (!sceneId) return;
    const result = await api(root).catch(e => {
      if (String(e.message).includes('Skinning session does not exist')) return null;
      throw e;
    });
    setSession(result);
  }
  useEffect(() => {
    let active = true;
    setSession(null);setNotice('');
    if (sceneId) api(root).catch(e => String(e.message).includes('Skinning session does not exist') ? null : Promise.reject(e))
      .then(result => { if (active) setSession(result); })
      .catch(e => { if (active) setNotice(e.message); });
    return () => { active = false; };
  }, [project.id, sceneId, root, api]);

  async function perform(fn, message) {
    await action(async () => { await fn(); await reload(); setNotice(message); });
  }
  async function exportBlender() {
    await action(async () => {
      const result = await api(`${root}/blender-script`);
      const blob = new Blob([result.script], { type: 'text/x-python;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;anchor.download = `nvp_${sceneId}_weighted_skin.py`;
      document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setNotice('Exported a Blender 5.2+ weighted skin scene. Check the rest pose and bone deformation before final approval of a performance.');
    });
  }
  const selectedActor = actorId || session?.actors?.[0]?.instance_id || '';
  return <div className="columns">
    <section className="card">
      <h2>Weighted character preview</h2>
      <p className="muted">Attach a procedural, seven-bone skinned silhouette to an approved PROD-06A performance. Motion remains connected to the original actor’s position and timing.</p>
      <label>Scene
        <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
          {project.scenes.map(s => <option key={s.id} value={s.id}>{s.heading}</option>)}
        </select>
      </label>
      {!session ? <button disabled={busy || !sceneId}
        onClick={() => perform(() => api(root, 'POST'), 'Started a new skinning proposal.')}>
        Create skinning layer
      </button> : <>
        <p><strong>Status:</strong> {session.status}{session.stale ? ' · motion package changed' : ''} · revision {session.revision}</p>
        <label>Character
          <select value={selectedActor} onChange={e => setActorId(e.target.value)}>
            {session.actors.map(a => <option key={a.instance_id} value={a.instance_id}>{a.instance_id}</option>)}
          </select>
        </label>
        <label>Preview joint
          <select value={role} onChange={e => setRole(e.target.value)}>
            {roles.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label>Source clip neutral pose — X,Y,Z degrees
          <input value={sourceRest} onChange={e => setSourceRest(e.target.value)} placeholder="0, 0, 0" />
        </label>
        <label>Target preview neutral pose — X,Y,Z degrees
          <input value={targetRest} onChange={e => setTargetRest(e.target.value)} placeholder="0, 0, 0" />
        </label>
        <button disabled={busy || session.stale || session.status !== 'draft' || !selectedActor}
          onClick={() => perform(() => api(`${root}/calibrate`, 'POST', {
            actor_instance_id:selectedActor,role,
            source_neutral_deg:triplet(sourceRest),target_neutral_deg:triplet(targetRest),
            expected_revision:session.revision,
          }), 'Saved director-authored neutral-pose correction; no approved animation was overwritten.')}>
          Save joint calibration
        </button>
        <p className="muted">The source and target rest angles are explicit; NVP does not infer them from the character’s shape. A calibration is a proposal until you approve it.</p>
      </>}
    </section>
    <section className="card">
      <h2>Review and export</h2>
      {notice && <p role="status">{notice}</p>}
      {session?.actors?.map(a => <div key={a.instance_id}>
        <strong>{a.instance_id}</strong> · {a.style}
        <ul>{Object.entries(a.calibrations).map(([bone,c]) =>
          <li key={bone}>{bone}: source [{c.source_neutral_deg.join(', ')}] → target [{c.target_neutral_deg.join(', ')}]</li>
        )}</ul>
      </div>)}
      {session && <>
        <button disabled={busy || session.status !== 'draft' || session.stale}
          onClick={() => perform(() => api(`${root}/approve`, 'POST', {expected_revision:session.revision}),
            'Weighted preview skin approved for the current motion take.')}>
          Approve weighted skin
        </button>
        <button disabled={busy || session.status !== 'approved' || session.stale} onClick={exportBlender}>
          Export weighted Blender scene
        </button>
      </>}
      <p className="muted">This is a genuine ARMATURE-deformed mesh, but still a seven-part procedural preview. Real licensed characters, smooth production skinning, facial acting and lipsync are later milestones.</p>
    </section>
  </div>;
}
