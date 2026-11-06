import React, { useEffect, useMemo, useState } from 'react';

/**
 * NVP-only developer interface for explicit story event ordering. It never
 * grants approvals automatically, infers time from screenplay scene numbers,
 * or delegates film logic to Lu.
 */
export default function StoryTimeline({ project, api }) {
  const [timeline, setTimeline] = useState(null);
  const [bible, setBible] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [before, setBefore] = useState('');
  const [after, setAfter] = useState('');
  const [sceneId, setSceneId] = useState('');
  const [eventId, setEventId] = useState('');
  const [phase, setPhase] = useState('before');
  const [characterId, setCharacterId] = useState('');
  const [factId, setFactId] = useState('');
  const [learnedAt, setLearnedAt] = useState('');
  const [knowledgeNote, setKnowledgeNote] = useState('');
  const [inspectScene, setInspectScene] = useState('');
  const [sceneKnowledge, setSceneKnowledge] = useState(null);

  const root = '/projects/' + project.id + '/timeline';
  const events = timeline?.events || [];
  const entities = bible?.entities || [];
  const characters = entities.filter((entry) => entry.kind === 'character');
  const facts = entities.flatMap((entry) => entry.facts
    .filter((f) => f.status === 'accepted')
    .map((f) => ({ ...f, subject: entry.name })));
  const byId = useMemo(() => Object.fromEntries(
    [...events, ...entities].map((item) => [item.id, item.name])
  ), [timeline, bible]);

  async function refresh() {
    const [t, b] = await Promise.all([
      api(root),
      api('/projects/' + project.id + '/story-bible'),
    ]);
    setTimeline(t);
    setBible(b);
    setError('');
    return t;
  }

  useEffect(() => {
    let mounted = true;
    Promise.all([api(root), api('/projects/' + project.id + '/story-bible')])
      .then(([t, b]) => { if (mounted) { setTimeline(t); setBible(b); setError(''); } })
      .catch((err) => { if (mounted) setError(err.message); });
    return () => { mounted = false; };
  }, [project.id, project.revision]);

  async function action(callback, message) {
    setBusy(true);
    setError('');
    try {
      await callback();
      await refresh();
      setSceneKnowledge(null);
      setNotice(message || 'Timeline saved.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function selectEvent(value) {
    return <option key={value.id} value={value.id}>{value.name}</option>;
  }

  const selectedFacts = facts;
  return <div className="columns">
    <section className="card">
      <h2>Story chronology</h2>
      <p className="muted">Define what happens before what. Events not connected by the approved order
        remain unordered, even if their scenes appear earlier or later in the screenplay.</p>
      <p className="fineprint">Create or rename events in the Story Bible first. All changes require
        a current project timeline revision, not a model's permission.</p>
      <div className="actions">
        <button className="secondary" disabled={busy} onClick={() => action(async () => {}, 'Timeline refreshed.')}>Refresh timeline</button>
      </div>
      <p className="fineprint">{events.length} story events · {timeline?.edges?.length || 0} explicit order relations · revision {timeline?.revision ?? '—'}</p>
      {events.length === 0 && <p className="muted">No story events yet. Add an Event in the Story Bible tab to begin.</p>}
      <label>Event happening first
        <select value={before} onChange={(e) => setBefore(e.target.value)}>
          <option value="">Choose first event</option>{events.map(selectEvent)}
        </select>
      </label>
      <label>Event happening later
        <select value={after} onChange={(e) => setAfter(e.target.value)}>
          <option value="">Choose later event</option>{events.map(selectEvent)}
        </select>
      </label>
      <button className="secondary" disabled={busy || !before || !after || before === after || !timeline}
        onClick={() => action(() => api(root + '/precedence', 'POST', {
          before_id: before, after_id: after, expected_revision: timeline.revision,
        }), 'Event order approved. Unconnected events remain unordered.')}>Add event order</button>
      <h3>Recorded event relationships</h3>
      {(timeline?.edges || []).map((edge) => <div className="scene-item" key={edge.before_id + edge.after_id}>
        <strong>{byId[edge.before_id] || edge.before_id} → {byId[edge.after_id] || edge.after_id}</strong>
        <small>Creator-authored BEFORE relationship</small>
        <button className="secondary" disabled={busy}
          onClick={() => action(() => api(root + '/precedence/remove', 'POST', {
            before_id: edge.before_id, after_id: edge.after_id,
            expected_revision: timeline.revision,
          }), 'Event ordering removed; any newly ambiguous character knowledge requires review.')}>
          Remove relationship
        </button>
      </div>)}
      <h3>Place a screenplay scene in story time</h3>
      <p className="fineprint">Select a point BEFORE or AFTER a named event. This is an explicit
        scene reference, not a claim that a scene itself happens entirely before or after the event.</p>
      <label>Scene
        <select value={sceneId} onChange={(e) => setSceneId(e.target.value)}>
          <option value="">Choose screenplay scene</option>
          {project.scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.number}. {scene.heading}</option>)}
        </select>
      </label>
      <label>Anchor event
        <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
          <option value="">Choose event</option>{events.map(selectEvent)}
        </select>
      </label>
      <label>Scene story-time point
        <select value={phase} onChange={(e) => setPhase(e.target.value)}>
          <option value="before">Before the anchor event</option>
          <option value="after">After the anchor event</option>
        </select>
      </label>
      <button className="secondary" disabled={busy || !sceneId || !eventId || !timeline}
        onClick={() => action(() => api(root + '/scenes/' + encodeURIComponent(sceneId), 'PUT', {
          event_id: eventId, phase, expected_revision: timeline.revision,
        }), 'Scene time anchor recorded. Knowledge can now be checked at this explicit point.')}>
        Save scene anchor
      </button>
      {(timeline?.scene_marks || []).map((mark) => <div className="scene-item" key={mark.scene_id}>
        <strong>{project.scenes.find((s) => s.id === mark.scene_id)?.heading || 'Archived scene'}</strong>
        <span>{mark.phase.toUpperCase()} {byId[mark.anchor_event_id] || mark.anchor_event_id}</span>
        <small>Anchored to screenplay revision {mark.screenplay_revision}</small>
        <button className="secondary" disabled={busy}
          onClick={() => action(() => api(root + '/scenes/' + encodeURIComponent(mark.scene_id)
            + '?expected_revision=' + timeline.revision, 'DELETE'), 'Scene time anchor removed.')}>Remove anchor</button>
      </div>)}
    </section>
    <section className="card">
      <h2>What does each character know?</h2>
      <p className="muted">Approval ties a character's knowledge to an already-approved Story Bible fact
        and a named learning event. Without such a record, NVP will not invent what someone knows.</p>
      <label>Character
        <select value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
          <option value="">Choose a character</option>
          {characters.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
        </select>
      </label>
      <label>Approved fact they discover
        <select value={factId} onChange={(e) => setFactId(e.target.value)}>
          <option value="">Choose an approved fact</option>
          {selectedFacts.map((f) => <option key={f.id} value={f.id}>
            {f.subject} · {f.fact_key}: {f.fact_value.slice(0,75)}
          </option>)}
        </select>
      </label>
      <label>When they learn it
        <select value={learnedAt} onChange={(e) => setLearnedAt(e.target.value)}>
          <option value="">Already known at story start</option>{events.map(selectEvent)}
        </select>
      </label>
      <label>Creator's evidence or note
        <textarea rows={2} maxLength={1000} value={knowledgeNote}
          onChange={(e) => setKnowledgeNote(e.target.value)}
          placeholder="Mara discovers this in the evidence room..." />
      </label>
      <button className="secondary" disabled={busy || !characterId || !factId}
        onClick={() => action(() => api(root + '/knowledge', 'POST', {
          character_id: characterId, fact_id: factId,
          learned_at_event_id: learnedAt || null, source_note: knowledgeNote,
        }), 'Knowledge proposed. Explicit approval is required before the writer uses it.')}>
        Propose knowledge
      </button>
      <h3>Knowledge approvals</h3>
      {(timeline?.knowledge_proposals || []).map((claim) => <div className="scene-item" key={claim.id}>
        <small>{claim.status}</small>
        <strong>{byId[claim.character_id] || claim.character_id}</strong>
        <span>{facts.find((f) => f.id === claim.fact_id)?.fact_value || 'Source fact changed'}</span>
        <span>{claim.learned_at_event_id
          ? 'Learned at: ' + (byId[claim.learned_at_event_id] || claim.learned_at_event_id)
          : 'Known before story begins'}</span>
        {claim.status === 'proposed' && <div className="actions">
          {['accept', 'reject'].map((decision) => <button className="secondary" key={decision}
            disabled={busy} onClick={() => action(() => api(root + '/knowledge/' + claim.id + '/decision', 'POST', {
              decision, expected_revision: timeline.revision,
            }), 'Knowledge review recorded.')}>{decision === 'accept' ? 'Approve' : 'Reject'}</button>)}
        </div>}
      </div>)}
      <h3>Preview character knowledge at a scene point</h3>
      <label>Scene to inspect
        <select value={inspectScene} onChange={(e) => { setInspectScene(e.target.value); setSceneKnowledge(null); }}>
          <option value="">Choose a scene</option>
          {project.scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.number}. {scene.heading}</option>)}
        </select>
      </label>
      <button className="secondary" disabled={busy || !inspectScene}
        onClick={() => {
          setBusy(true);
          setError('');
          api(root + '?scene_id=' + encodeURIComponent(inspectScene))
            .then((snapshot) => { setSceneKnowledge(snapshot); setNotice('Knowledge evaluated at the selected point.'); })
            .catch((err) => { setSceneKnowledge(null); setError(err.message); })
            .finally(() => setBusy(false));
        }}>Inspect knowledge state</button>
      {sceneKnowledge && <div>
        <p className="fineprint">{sceneKnowledge.scene_marker
          ? 'Explicit point: ' + sceneKnowledge.scene_marker.phase.toUpperCase()
            + ' ' + (byId[sceneKnowledge.scene_marker.anchor_event_id] || 'event')
          : 'Unanchored scene: event-specific knowledge is unresolved'}</p>
        {sceneKnowledge.knowledge.map((claim) => <p className="fineprint" key={claim.id}>
          <strong>{claim.character_name}: {claim.state.replaceAll('_', ' ')}</strong>
          {claim.state === 'source_fact_changed'
            ? ' — previously approved fact was superseded; do not reuse'
            : ' — ' + claim.fact_key + ': ' + claim.fact_value}
        </p>)}
        <p className="fineprint">{sceneKnowledge.limitations}</p>
      </div>}
      {error && <p role="alert">{error}</p>}
      {notice && <p className="fineprint">{notice}</p>}
    </section>
  </div>;
}
