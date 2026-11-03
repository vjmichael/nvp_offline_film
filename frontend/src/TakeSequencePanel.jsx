import React, { useCallback, useEffect, useMemo, useState } from 'react';

// PROD-05 proxy filmmaking: timed shots and blocking, not rigged animation or TTS.
const PATTERNS = ['master', 'single', 'two_shot', 'over_shoulder', 'reaction', 'insert', 'tracking'];

function downloadScript(script, scene) {
  const file = new Blob([script], { type: 'text/x-python;charset=utf-8' });
  const url = URL.createObjectURL(file);
  const a = document.createElement('a');
  a.href = url;
  a.download = `nvp_${scene}_timed_scene.py`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function TakeSequencePanel({ project, api, action, busy }) {
  const [sceneId, setSceneId] = useState(project.scenes[0]?.id || '');
  const [sequence, setSequence] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [dialogue, setDialogue] = useState([]);
  const [chosenCamera, setChosenCamera] = useState('');
  const [pattern, setPattern] = useState('single');
  const [frames, setFrames] = useState('72');
  const [cueStarts, setCueStarts] = useState({});
  const [message, setMessage] = useState('');

  const prefix = `/projects/${project.id}/production/scenes/${sceneId}`;
  const takeApi = `${prefix}/sequence`;
  const refresh = useCallback(async () => {
    if (!sceneId) return;
    const [cam, script] = await Promise.all([api(`${prefix}/cameras`), api(`${prefix}/dialogue`)]);
    setCameras(cam.filter(x => !x.stale));
    setDialogue(script.dialogue);
    try {
      const next = await api(takeApi);
      setSequence(next);
    } catch (err) {
      if (String(err.message).includes('Shot sequence does not exist')) setSequence(null);
      else throw err;
    }
  }, [api, prefix, takeApi, sceneId]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        if (!sceneId) { setSequence(null); return; }
        const [cam, dialog, seq] = await Promise.all([
          api(`${prefix}/cameras`),
          api(`${prefix}/dialogue`),
          api(takeApi).catch(err => {
            if (String(err.message).includes('Shot sequence does not exist')) return null;
            throw err;
          }),
        ]);
        if (alive) {
          setCameras(cam.filter(x => !x.stale));
          setDialogue(dialog.dialogue);
          setSequence(seq);
          setMessage('');
        }
      } catch (err) {
        if (alive) setMessage(err.message);
      }
    };
    load();
    return () => { alive = false; };
  }, [api, prefix, sceneId, takeApi]);

  const cameraOptions = useMemo(() => cameras.map(c => ({
    id: c.id,
    label: `${c.recipe.shot_size} · ${c.recipe.subjects.join(', ')} · ${c.solution.lens_mm}mm`,
  })), [cameras]);
  const selectedCamera = chosenCamera || cameraOptions[0]?.id || '';
  const editable = Boolean(sequence && sequence.status === 'draft' && !sequence.stale);
  const warnings = sequence?.review?.warnings || [];
  const errors = sequence?.review?.errors || [];
  const acknowledgements = new Set(sequence?.plan?.acknowledged_warnings || []);

  async function perform(fn, notice) {
    await action(async () => {
      const updated = await fn();
      if (updated?.plan) setSequence(updated);
      setMessage(notice);
      await refresh();
    });
  }

  async function exportBlender() {
    await action(async () => {
      const result = await api(`${takeApi}/blender-script`);
      downloadScript(result.script, sceneId);
      setMessage('Saved a Blender bpy script. Run in Blender 5.2+ with -- --output scene.blend.');
    });
  }

  return <div className="columns">
    <section className="card">
      <h2>Direct the sequence</h2>
      <p className="muted">Arrange shots in exact 24 fps frames. Camera placements and actor paths come from the approved 3D scene; dialogue timing must be supplied by the director or measured from audio.</p>
      <label>Screenplay scene
        <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
          {project.scenes.map(s => <option key={s.id} value={s.id}>{s.heading}</option>)}
        </select>
      </label>
      {!sequence && <button disabled={busy || !sceneId} onClick={() => perform(() => api(takeApi, 'POST'), 'Sequence draft created.')}>Create shot sequence</button>}
      {sequence && <p><strong>Sequence:</strong> {sequence.status} · revision {sequence.revision} · {sequence.review?.duration_s ?? '—'} sec {sequence.stale && <strong> (Stale: reset/review before continuing)</strong>}</p>}
      {sequence && <>
        <h3>Camera coverage</h3>
        <label>Solved camera
          <select value={selectedCamera} onChange={e => setChosenCamera(e.target.value)}>
            {cameraOptions.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </label>
        <label>Coverage pattern
          <select value={pattern} onChange={e => setPattern(e.target.value)}>
            {PATTERNS.map(p => <option key={p} value={p}>{p.replaceAll('_', ' ')}</option>)}
          </select>
        </label>
        <label>Shot length (frames at 24 fps)
          <input type="number" min="1" max="14400" step="1" value={frames} onChange={e => setFrames(e.target.value)} />
        </label>
        <button disabled={busy || !editable || !selectedCamera} onClick={() => perform(
          () => api(`${takeApi}/shots`, 'POST', {
            camera_id: selectedCamera, frames: Number(frames), pattern, expected_revision: sequence.revision,
          }), 'Shot appended; review its continuity warnings.')}>Append shot</button>
        <button disabled={busy || !editable || !sequence.plan.shots.length} onClick={() => perform(
          () => api(`${takeApi}/shots/pop`, 'POST', { expected_revision: sequence.revision }), 'Last shot removed.')}>Remove last shot</button>
        <div>{sequence.plan.shots.map(s => <p key={s.id}><strong>{s.pattern.replaceAll('_', ' ')}</strong> · frames {s.start_frame}–{s.stop_frame - 1} · {s.camera_id.slice(0, 12)}</p>)}</div>
        <h3>Dialogue starts</h3>
        {dialogue.map(line => {
          const existing = sequence.plan.cues.find(c => c.line_id === line.id);
          return <div key={line.id} style={{ marginBottom: 12 }}>
            <p><strong>{line.speaker_name}</strong>: {line.text}</p>
            <p className="muted">Duration: {line.duration_s === null ? 'Not measured (required)' : `${line.duration_s}s`}. {existing ? `Scheduled at frame ${existing.start_frame}.` : 'Unscheduled.'}</p>
            <label>Start frame
              <input type="number" min="1" step="1" placeholder="e.g. 1"
                value={cueStarts[line.id] ?? existing?.start_frame ?? ''}
                onChange={e => setCueStarts(v => ({ ...v, [line.id]: e.target.value }))}/>
            </label>
            <button disabled={busy || !editable || line.duration_s === null} onClick={() => perform(
              () => api(`${takeApi}/cues/${encodeURIComponent(line.id)}`, 'POST', {
                start_frame: Number(cueStarts[line.id] ?? existing?.start_frame ?? 1),
                expected_revision: sequence.revision,
              }), 'Dialogue cue updated.')}>Set cue</button>
            <button disabled={busy || !editable || !existing} onClick={() => perform(
              () => api(`${takeApi}/cues/${encodeURIComponent(line.id)}/clear`, 'POST', {
                expected_revision: sequence.revision,
              }), 'Dialogue cue removed.')}>Clear cue</button>
          </div>;
        })}
      </>}
    </section>
    <section className="card">
      <h2>Continuity and approval</h2>
      <p className="muted">Warnings are suggestions that a filmmaker may intentionally override. Hard errors prevent exporting. A generated take only moves approved proxy characters and switches cameras—no voices, rigs, or lip sync yet.</p>
      {!sequence && <p>Create a sequence on the left to begin.</p>}
      {sequence && <>
        {sequence.stale && <p><strong>Scene dependencies changed.</strong> You must explicitly reset or begin a new revision; NVP will not use old approved cameras silently.</p>}
        <h3>Blocking, timing and cut validation</h3>
        {errors.length === 0 && <p>No blocking or timing errors detected.</p>}
        {errors.map((e, i) => <p key={`error_${i}`}><strong>Error:</strong> {e}</p>)}
        {warnings.map(w => <p key={w.code}><strong>{acknowledgements.has(w.code) ? 'Acknowledged' : 'Review'}:</strong> {w.description}<span className="muted"> ({w.code})</span></p>)}
        {sequence.review && <p className="muted">{sequence.review.total_frames} total frames; {warnings.length} potential creative continuity issues.</p>}
        <button disabled={busy || !editable || !warnings.length} onClick={() => perform(
          () => api(`${takeApi}/warnings/acknowledge`, 'POST', {
            expected_revision: sequence.revision, codes: warnings.map(w => w.code),
          }), 'Director acknowledged these exact continuity warnings.')}>Acknowledge all shown warnings</button>
        <button disabled={busy || !editable || errors.length > 0 || (sequence.review?.unacknowledged_warnings?.length ?? 0) > 0}
          onClick={() => perform(() => api(`${takeApi}/approve`, 'POST', { expected_revision: sequence.revision }),
            'Sequence approved. The approved timing and source state are pinned.')}>Approve sequence</button>
        <button disabled={busy || !sequence || sequence.status !== 'approved'} onClick={() => perform(
          () => api(`${takeApi}/revision`, 'POST', { expected_revision: sequence.revision }),
          'New editable revision created from approved sequence.')}>Begin new revision</button>
        <button disabled={busy || !sequence || sequence.status !== 'draft'} onClick={() => perform(
          () => api(`${takeApi}/reset`, 'POST', { expected_revision: sequence.revision }),
          'Shot and dialogue draft reset. Previous revisions are retained in history.')}>Reset draft and dependencies</button>
        <button disabled={busy || sequence.status !== 'approved' || sequence.stale} onClick={exportBlender}>Export timed Blender scene script</button>
      </>}
      {message && <p className="muted">{message}</p>}
    </section>
  </div>;
}
