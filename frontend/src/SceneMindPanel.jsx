import React, { useCallback, useEffect, useMemo, useState } from 'react';

/** NVP-only developer UI. All approvals are explicit server-side decisions. */
export default function SceneMindPanel({ project, api, action, busy }) {
  const scenes = project.scenes || [];
  const [sceneId, setSceneId] = useState(scenes[0]?.id || '');
  const [beatId, setBeatId] = useState('');
  const [beatLine, setBeatLine] = useState('1');
  const [beatLabel, setBeatLabel] = useState('');
  const [mind, setMind] = useState(null);
  const [bible, setBible] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [before, setBefore] = useState(null);
  const [after, setAfter] = useState(null);
  const [error, setError] = useState('');
  const [characterId, setCharacterId] = useState('');
  const [factId, setFactId] = useState('');
  const [mode, setMode] = useState('believe');
  const [believed, setBelieved] = useState('');
  const [speakerId, setSpeakerId] = useState('');
  const [audienceId, setAudienceId] = useState('');
  const [said, setSaid] = useState('');
  const [intent, setIntent] = useState('deliberate_deception');
  const [reviewResolution, setReviewResolution] = useState('intentional');
  const [reviewNote, setReviewNote] = useState('');

  const scene = scenes.find((item) => item.id === sceneId);
  const root = '/projects/' + project.id + '/scene-mind';
  const characters = (bible?.entities || []).filter((entry) => entry.kind === 'character');
  const acceptedFacts = (bible?.entities || []).flatMap((entry) =>
    entry.facts.filter((fact) => fact.status === 'accepted').map((fact) => ({
      ...fact, owner: entry.name,
    })));
  const scopedBeats = (mind?.beats || []).filter((beat) => beat.scene_id === sceneId);
  const currentBeat = scopedBeats.find((beat) => beat.id === beatId);
  const originalLines = useMemo(() => (scene?.text || '').split('\n'), [scene?.text]);

  const refresh = useCallback(async () => {
    if (!sceneId) return;
    const [bibleData, mindData, issueData] = await Promise.all([
      api('/projects/' + project.id + '/story-bible'),
      api(root + '?scene_id=' + encodeURIComponent(sceneId)).catch(async () =>
        // An edited scene may leave old beat markers needing re-anchoring.
        api(root)),
      api(root + '/scenes/' + encodeURIComponent(sceneId) + '/suggestions'),
    ]);
    setBible(bibleData);
    setMind(mindData);
    setSuggestions(issueData);
    const visible = (mindData.beats || []).filter((beat) => beat.scene_id === sceneId);
    setBeatId((old) => visible.some((beat) => beat.id === old) ? old : (visible[0]?.id || ''));
    const freshCharacters = bibleData.entities.filter((entry) => entry.kind === 'character');
    const freshFacts = bibleData.entities.flatMap((entry) => entry.facts)
      .filter((fact) => fact.status === 'accepted');
    setCharacterId((old) => freshCharacters.some((entry) => entry.id === old)
      ? old : (freshCharacters[0]?.id || ''));
    setFactId((old) => freshFacts.some((fact) => fact.id === old)
      ? old : (freshFacts[0]?.id || ''));
    setSpeakerId((old) => freshCharacters.some((entry) => entry.id === old) ? old : (freshCharacters[0]?.id || ''));
    setAudienceId((old) => freshCharacters.some((entry) => entry.id === old) ? old : (freshCharacters[1]?.id || ''));
    setError('');
  }, [sceneId, project.id, api, root]);

  useEffect(() => {
    let live = true;
    if (sceneId && !scenes.some((item) => item.id === sceneId)) {
      setSceneId(scenes[0]?.id || '');
      return undefined;
    }
    if (sceneId) refresh().catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [sceneId, project.id, project.revision]);

  useEffect(() => {
    let live = true;
    setBefore(null);
    setAfter(null);
    if (!sceneId || !beatId) return undefined;
    const query = '?scene_id=' + encodeURIComponent(sceneId)
      + '&at_beat_id=' + encodeURIComponent(beatId);
    Promise.all([
      api(root + query + '&phase=before'), api(root + query + '&phase=after'),
    ]).then(([earlier, later]) => {
      if (live) { setBefore(earlier); setAfter(later); }
    }).catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [sceneId, beatId, mind?.revision]);

  function execute(work) {
    action(async () => {
      await work();
      await refresh();
    });
  }

  if (scenes.length === 0) return <section className="card">
    <h2>Scene knowledge</h2><p className="muted">Write at least one screenplay scene first.</p>
  </section>;

  return <div className="columns">
    <section className="card">
      <h2>What happens inside this scene?</h2>
      <p className="muted">Anchor the moment a character learns something, starts believing an untrue claim, or deliberately misleads someone. None of these actions is inferred from dialogue.</p>
      {error && <p role="alert">{error}</p>}
      <label>Scene
        <select value={sceneId} onChange={(e) => { setSceneId(e.target.value); setBeatId(''); }}>
          {scenes.map((item) => <option key={item.id} value={item.id}>{item.number}. {item.heading}</option>)}
        </select>
      </label>
      <label>Where in the scene? (line relative to this scene)
        <select value={beatLine} onChange={(e) => setBeatLine(e.target.value)}>
          {originalLines.map((line, i) => <option key={i} value={String(i + 1)}>
            {i + 1}: {line.trim() || '[blank line]'}
          </option>)}
        </select>
      </label>
      <label>Moment label<input value={beatLabel} maxLength={150}
        onChange={(e) => setBeatLabel(e.target.value)} placeholder="Mara believes Bob's explanation" /></label>
      <button className="secondary" disabled={busy || !beatLabel.trim()}
        onClick={() => execute(() => api(root + '/beats', 'POST', {
          scene_id: sceneId, line_number: Number(beatLine), label: beatLabel,
          expected_revision: mind?.revision ?? 0,
        }).then(() => setBeatLabel('')))}>Add explicit beat</button>
      <h3>Recorded beats</h3>
      {scopedBeats.length === 0 && <p className="fineprint">No within-scene knowledge moments have been recorded.</p>}
      {scopedBeats.map((beat) => <button className={'scene-item ' + (beatId === beat.id ? 'active' : '')}
        key={beat.id} onClick={() => setBeatId(beat.id)}>
        <small>Line {beat.line_number}</small><strong>{beat.label}</strong>
      </button>)}
      {currentBeat && <>
        <h3>Character state at the selected beat</h3>
        <div className="columns">
          <div><strong>Before</strong>
            {(before?.states || []).map((entry) => <p key={entry.character_id + entry.fact_id} className="fineprint">
              {characters.find((item) => item.id === entry.character_id)?.name || entry.character_id} · {entry.fact_key}: {entry.state}
            </p>)}
            {!before?.states?.length && <p className="fineprint">No established state (not proof of ignorance)</p>}
          </div>
          <div><strong>After</strong>
            {(after?.states || []).map((entry) => <p key={entry.character_id + entry.fact_id} className="fineprint">
              {characters.find((item) => item.id === entry.character_id)?.name || entry.character_id} · {entry.fact_key}: {entry.state}
            </p>)}
            {!after?.states?.length && <p className="fineprint">No established state</p>}
          </div>
        </div>
      </>}
    </section>
    <section className="card">
      <h2>Beliefs and deceptive statements</h2>
      <p className="fineprint">Approved Story Bible facts are objective canon; subjective beliefs and dialogue assertions never overwrite them.</p>
      <label>Character
        <select value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
          {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label>Fact being perceived
        <select value={factId} onChange={(e) => setFactId(e.target.value)}>
          {acceptedFacts.map((fact) => <option key={fact.id} value={fact.id}>
            {fact.owner} · {fact.fact_key}: {fact.fact_value}
          </option>)}
        </select>
      </label>
      <label>What changes in the character's mind?
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="believe">Believes a claim (possibly mistaken)</option>
          <option value="learn_truth">Learns the objective truth</option>
          <option value="doubt">Becomes uncertain</option>
          <option value="forget">Does not recall</option>
        </select>
      </label>
      {mode === 'believe' && <label>What does the character believe?
        <textarea rows={2} value={believed} maxLength={2000} onChange={(e) => setBelieved(e.target.value)} />
      </label>}
      <button className="secondary" disabled={busy || !beatId || !characterId || !factId || (mode === 'believe' && !believed.trim())}
        onClick={() => execute(() => api(root + '/changes', 'POST', {
          beat_id: beatId, character_id: characterId, fact_id: factId,
          mode, belief_value: mode === 'believe' ? believed : null,
        }))}>Propose a knowledge change</button>
      {(mind?.changes || []).filter((r) => r.scene_id === sceneId).map((record) => <div className="scene-item" key={record.id}>
        <small>{record.status} · {record.mode} · {record.fact_key || 'fact changed'}</small>
        <strong>{characters.find((c) => c.id === record.character_id)?.name || 'Character'}:</strong>
        <span>{record.belief_value || '[no asserted belief value]'}</span>
        {record.status === 'proposed' && <div className="actions">
          <button disabled={busy} className="secondary" onClick={() => execute(() => api(
            root + '/changes/' + record.id + '/decision', 'POST',
            {decision:'accept', expected_revision: mind?.revision ?? 0}))}>Approve</button>
          <button disabled={busy} className="secondary" onClick={() => execute(() => api(
            root + '/changes/' + record.id + '/decision', 'POST',
            {decision:'reject', expected_revision: mind?.revision ?? 0}))}>Reject</button>
        </div>}
      </div>)}
      <h3>Spoken claim or deceptive statement</h3>
      <label>Speaker<select value={speakerId} onChange={(e) => setSpeakerId(e.target.value)}>
        {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select></label>
      <label>Listener<select value={audienceId} onChange={(e) => setAudienceId(e.target.value)}>
        {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select></label>
      <label>What did they claim?<textarea rows={2} maxLength={2000} value={said} onChange={(e) => setSaid(e.target.value)} /></label>
      <label>Creator-specified intention<select value={intent} onChange={(e) => setIntent(e.target.value)}>
        <option value="deliberate_deception">Deliberate deception</option>
        <option value="mistake">Unintentional mistake</option>
        <option value="bluff">Bluff</option>
        <option value="truthful_claim">Claims to tell the truth</option>
      </select></label>
      <button className="secondary" disabled={busy || !beatId || !speakerId || !audienceId || !factId || !said.trim()}
        onClick={() => execute(() => api(root + '/statements', 'POST', {
          beat_id: beatId, speaker_id: speakerId, audience_id: audienceId,
          fact_id: factId, claimed_value: said, intent,
        }))}>Propose statement</button>
      {(mind?.statements || []).filter((r) => r.scene_id === sceneId).map((record) => <div key={record.id} className="scene-item">
        <small>{record.status} · {record.intent}</small>
        <strong>{record.claimed_value}</strong>
        {record.status === 'proposed' && <div className="actions">
          <button className="secondary" disabled={busy} onClick={() => execute(() => api(
            root + '/statements/' + record.id + '/decision', 'POST',
            {decision:'accept', expected_revision: mind?.revision ?? 0}))}>Approve</button>
          <button className="secondary" disabled={busy} onClick={() => execute(() => api(
            root + '/statements/' + record.id + '/decision', 'POST',
            {decision:'reject', expected_revision: mind?.revision ?? 0}))}>Reject</button>
        </div>}
      </div>)}
      <h3>Continuity review suggestions</h3>
      <p className="fineprint">Suggestions are grounded in structured canon and explicitly recorded scene beats. Accepting or rejecting a suggestion saves your review decision; it does not edit your screenplay or automatically fix character knowledge.</p>
      <label>If accepting a suggestion
        <select value={reviewResolution} onChange={(e) => setReviewResolution(e.target.value)}>
          <option value="intentional">This is intentional</option>
          <option value="fix_later">Needs later correction</option>
        </select>
      </label>
      <label>Director's review note<textarea rows={2} value={reviewNote} maxLength={1000}
        onChange={(e) => setReviewNote(e.target.value)} placeholder="Why this is deliberate, or what needs correction" /></label>
      {(suggestions?.suggestions || []).length === 0 && <p className="fineprint">No structured continuity suggestions for this scene.</p>}
      {(suggestions?.suggestions || []).map((issue) => <div key={issue.id} className="scene-item">
        <small>{issue.kind.replaceAll('_', ' ')} · {issue.status}</small>
        <strong>{issue.message}</strong><span>{issue.suggested_action}</span>
        {issue.status !== 'proposed' ? <p className="fineprint">{issue.resolution || 'Dismissed'} · {issue.review_note}</p> :
          <div className="actions">
            <button className="secondary" disabled={busy} onClick={() => execute(() => api(
              root + '/scenes/' + sceneId + '/suggestions/' + issue.id + '/decision', 'POST',
              {decision:'accept', resolution:reviewResolution, review_note:reviewNote,
               expected_revision:suggestions?.revision ?? 0}))}>Accept review</button>
            <button className="secondary" disabled={busy} onClick={() => execute(() => api(
              root + '/scenes/' + sceneId + '/suggestions/' + issue.id + '/decision', 'POST',
              {decision:'reject', review_note:reviewNote,
               expected_revision:suggestions?.revision ?? 0}))}>Reject suggestion</button>
          </div>}
      </div>)}
    </section>
  </div>;
}
