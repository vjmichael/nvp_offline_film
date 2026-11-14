import React, { useEffect, useState } from 'react';

const FALLBACK_LIMITS = {
  hips:90,spine:85,head:80,arm_left:160,arm_right:160,leg_left:150,leg_right:150,
};

export default function RetargetPanel({project,api,action,busy}) {
  const [sceneId,setSceneId] = useState(project.scenes[0]?.id || '');
  const [session,setSession] = useState(null);
  const [actorId,setActorId] = useState('');
  const [limits,setLimits] = useState({...FALLBACK_LIMITS});
  const [contactFrames,setContactFrames] = useState('1');
  const [contactTolerance,setContactTolerance] = useState('0.08');
  const [maxPenetration,setMaxPenetration] = useState('0.04');
  const [message,setMessage] = useState('');
  const base = `/projects/${project.id}/production/scenes/${sceneId}/retarget`;

  async function reload() {
    try {
      const state=await api(base);
      setSession(state);
      if (state.actors?.length && !state.actors.some(a => a.instance_id === actorId)) {
        setActorId(state.actors[0].instance_id);
      }
    } catch (e) {
      if (String(e.message).includes('Retarget calibration does not exist')) setSession(null);
      else throw e;
    }
  }

  useEffect(() => {
    let active=true;
    if (!sceneId) return;
    api(base).then(state => {
      if (!active) return;
      setSession(state);
      setActorId(state.actors?.[0]?.instance_id || '');
      setMessage('');
    }).catch(err => {
      if (!active) return;
      if (String(err.message).includes('Retarget calibration does not exist')) {
        setSession(null);
      } else setMessage(String(err.message));
    });
    return () => {active=false;};
  },[base,api,sceneId]);

  useEffect(() => {
    const actor=session?.actors?.find(x => x.instance_id === actorId);
    if (!actor) return;
    setLimits({...actor.joint_limits_deg});
    setContactFrames(actor.contact_frames.join(','));
    setContactTolerance(String(actor.contact_tolerance_m));
    setMaxPenetration(String(actor.max_ground_penetration_m));
  },[session,actorId]);

  async function perform(actionFn,success) {
    await action(async () => {
      await actionFn();
      await reload();
      setMessage(success);
    });
  }

  async function exportBundle() {
    await action(async () => {
      const response=await fetch(`/api${base}/bundle`);
      if (!response.ok) throw new Error((await response.json().catch(()=>({}))).detail || 'Calibration export failed');
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');link.href=url;
      link.download=`nvp_${sceneId}_retarget_calibration.zip`;link.click();
      URL.revokeObjectURL(url);
      setMessage('Exported immutable, approved calibration. Real Blender validation is still required for every imported rig.');
    });
  }

  return <div className="columns">
    <section className="card">
      <h2>Calibrate an imported actor</h2>
      <p className="muted">PROD-06D changes orientation in the imported skeleton's rest basis; it does not alter your approved actor path, camera cuts, or underlying character asset.</p>
      <label>Scene <select value={sceneId} onChange={event=>setSceneId(event.target.value)}>
        {project.scenes.map(scene=><option key={scene.id} value={scene.id}>{scene.heading}</option>)}
      </select></label>
      {!session ? <button disabled={busy||!sceneId} onClick={()=>perform(()=>api(base,'POST'),'Created calibration plan from approved rig bindings.')}>Create calibration plan</button>
        : <><p>Status: <strong>{session.status}</strong> · revision {session.revision}{session.stale?' · STALE DEPENDENCY':''}</p>
          <label>Actor <select value={actorId} onChange={event=>setActorId(event.target.value)}>
            {session.actors.map(actor=><option key={actor.instance_id} value={actor.instance_id}>{actor.instance_id}</option>)}
          </select></label></>}
      {message && <p role="status">{message}</p>}
      <p className="muted">The source character must already have a director-approved seven-bone mapping. Joint limits are hard validation ceilings: violations fail rather than silently clamp the motion.</p>
    </section>
    <section className="card">
      <h2>Joint limits and floor contacts</h2>
      {Object.entries(limits).map(([role,limit])=><label key={role}>{role} maximum rotation (degrees)
        <input type="number" min="1" max="180" step="1" value={limit} onChange={event=>setLimits(x=>({...x,[role]:Number(event.target.value)}))}/>
      </label>)}
      <label>Frames where feet should contact ground (comma-separated)
        <input value={contactFrames} onChange={event=>setContactFrames(event.target.value)}/>
      </label>
      <label>Maximum contact error (metres)
        <input type="number" min="0" max="0.5" step="0.01" value={contactTolerance} onChange={event=>setContactTolerance(event.target.value)}/>
      </label>
      <label>Maximum floor penetration (metres)
        <input type="number" min="0" max="0.25" step="0.01" value={maxPenetration} onChange={event=>setMaxPenetration(event.target.value)}/>
      </label>
      <button disabled={busy||!session||session.status!=='draft'||session.stale||!actorId}
        onClick={()=>perform(()=>api(`${base}/configure`,'POST',{
          actor_instance_id:actorId, expected_revision:session.revision,
          joint_limits_deg:limits, contact_frames:contactFrames.split(',').map(x=>Number(x.trim())),
          contact_tolerance_m:Number(contactTolerance),max_ground_penetration_m:Number(maxPenetration),
        }),'Saved director-authored calibration limits.')}>Save calibration settings</button>
      <button disabled={busy||!session||session.status!=='draft'||session.stale}
        onClick={()=>perform(()=>api(`${base}/approve`,'POST',{expected_revision:session.revision}),
          'Approved calibration manifest. Native scene measurements can still fail.')}>Approve calibration</button>
      <button disabled={busy||session?.status!=='approved'||session.stale} onClick={exportBundle}>Export Blender calibration bundle</button>
      <p className="muted">The exported scene includes a reproducible Blender audit for rest-basis transforms, body proportions, joint ceilings, mesh deformation and floor contacts. No AI changes are auto-applied.</p>
    </section>
  </div>;
}
