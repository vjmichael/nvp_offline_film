import React, { useCallback, useEffect, useState } from 'react';
import { formatNumberedSource } from './lineNumbers.js';

/** Conservative film-only reviewer: no automatic changes to scripts or canon. */
export default function ScreenplayReviewPanel({ project, api, action, busy }) {
  const scenes = project.scenes || [];
  const [sceneId, setSceneId] = useState(scenes[0]?.id || '');
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [notes, setNotes] = useState({});
  const [resolutions, setResolutions] = useState({});
  const root = '/projects/' + project.id + '/screenplay-review/scenes/';
  const currentScene = scenes.find(s => s.id === sceneId);

  const refresh = useCallback(async () => {
    if (!sceneId) { setReport(null); return; }
    const data = await api(root + encodeURIComponent(sceneId));
    setReport(data);
    setError('');
  }, [project.id, sceneId, root, api]);

  useEffect(() => {
    if (!scenes.some(s => s.id === sceneId)) {
      setSceneId(scenes[0]?.id || '');
      return;
    }
    let active = true;
    refresh().catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [project.id, project.revision, sceneId]);

  function decide(item, decision) {
    const resolution = decision === 'accept' ? (resolutions[item.id] || 'intentional') : '';
    const note = notes[item.id] || '';
    action(async () => {
      if (!report || report.scene_id !== sceneId) throw new Error('Refresh the report before reviewing.');
      const result = await api(root + encodeURIComponent(sceneId) +
        '/suggestions/' + encodeURIComponent(item.id) + '/decision', 'POST', {
        decision, resolution, note, expected_review_revision: report.review_revision,
        expected_screenplay_revision: report.screenplay_revision,
      });
      setReport(result);
    });
  }

  if (!scenes.length) return <section className="card">
    <h2>Screenplay continuity review</h2>
    <p className="muted">Write or import a screenplay scene to review it.</p>
  </section>;

  return <div className="columns">
    <section className="card">
      <h2>Screenplay continuity review</h2>
      <p className="muted">NVP finds a small set of explicit wording conflicts. Dialogue may reflect a lie, mistake or bluff. Every item is a suggestion—not a confirmed error.</p>
      <label>Scene
        <select value={sceneId} onChange={e => { setSceneId(e.target.value); setReport(null); }}>
          {scenes.map(s => <option key={s.id} value={s.id}>{s.number}. {s.heading}</option>)}
        </select>
      </label>
      <button className="secondary" disabled={busy} onClick={() => action(refresh)}>
        Refresh continuity review
      </button>
      {error && <p role="alert">{error}</p>}
      <p className="fineprint">{report?.limitations || 'Checking current screenplay against creator-approved global facts.'}</p>
      {report && <p>{report.counts.unreviewed} unreviewed potential issue(s) across {report.counts.candidate_count} evidence matches.</p>}
      {currentScene && <details>
        <summary>Show original screenplay scene</summary>
        <pre className="screenplay-numbered-preview">{formatNumberedSource(currentScene.text, currentScene.start_line || 1)}</pre>
      </details>}
    </section>
    <section className="card">
      <h2>Evidence and director decisions</h2>
      {report && report.suggestions.length === 0 && <p className="muted">No matches in the supported patterns. This is not proof that the screenplay has no continuity errors.</p>}
      {(report?.suggestions || []).map(s => <div className="scene-item" key={s.id}>
        <small>{s.kind.replaceAll('_', ' ')} · {s.confidence.replaceAll('_', ' ')} · {s.status}</small>
        <strong>{s.title}</strong>
        {s.evidence.map((e, i) => <div key={i}>
          <p className="fineprint">Scene line {e.scene_line}, screenplay line {e.screenplay_line} · {e.source_kind}</p>
          <blockquote>{e.quote}</blockquote>
          <p className="fineprint">Matched wording: {e.matched_phrase}</p>
        </div>)}
        {s.canon && <p className="fineprint">
          <strong>Approved canon:</strong> {s.canon.fact_key} = {s.canon.fact_value} (scope: {s.canon.story_scope})
        </p>}
        <p className="fineprint">{s.explanation}</p>
        {s.status === 'proposed' ? <>
          <label>My interpretation
            <select value={resolutions[s.id] || 'intentional'}
              onChange={e => setResolutions(current => ({ ...current, [s.id]: e.target.value }))}>
              <option value="intentional">Intentional (e.g. dream, deception, unreliable narrator)</option>
              <option value="fix_later">Issue to fix later</option>
            </select>
          </label>
          <label>Optional director note
            <textarea maxLength={1200} rows={2} value={notes[s.id] || ''}
              onChange={e => setNotes(current => ({ ...current, [s.id]: e.target.value }))}
              placeholder="Explain why this wording is intentional or what needs revision" />
          </label>
          <div className="actions">
            <button className="secondary" disabled={busy} onClick={() => decide(s, 'accept')}>Accept for review</button>
            <button className="secondary" disabled={busy} onClick={() => decide(s, 'reject')}>Reject suggestion</button>
          </div>
        </> : <p className="fineprint">Director decision: {s.status}
          {s.resolution ? ' · ' + s.resolution : ''}
          {s.review_note ? ' · ' + s.review_note : ''}
        </p>}
      </div>)}
      <p className="fineprint">Review decisions never change the screenplay, scene plans, character beliefs or Story Bible automatically. Changes to the evidence create a new review suggestion.</p>
    </section>
  </div>;
}
