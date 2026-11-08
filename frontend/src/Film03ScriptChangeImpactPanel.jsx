import React, {useEffect, useState} from 'react';

/** Read-only exact Studio screenplay -> FilmIndex dialogue -> Bible retake impact. */
export default function Film03ScriptChangeImpactPanel({project, api}) {
  const [sources, setSources] = useState([]);
  const [scriptId, setScriptId] = useState('');
  const [impact, setImpact] = useState(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const root = '/projects/' + project.id + '/film03';

  useEffect(() => {
    let active = true;
    setSources([]); setScriptId(''); setImpact(null); setError('');
    api(root + '/script-sources').then(result => {
      if (!active) return;
      const items = result?.sources || [];
      setSources(items);
      setScriptId(items[0]?.script_id || '');
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [project.id, root, api]);

  async function preview() {
    if (!scriptId) return;
    setWorking(true); setError(''); setImpact(null);
    try {
      const result = await api(root + '/script-impact/' + encodeURIComponent(scriptId));
      if (result?.format !== 'nvp.film03.readonly_script_dialogue_impact.v1' ||
          result?.retakes_performed_automatically !== false ||
          result?.old_audio_takes_modified !== false)
        throw new Error('Unexpected executable or mutating script-impact response');
      setImpact(result);
    } catch(e) { setError(e.message); }
    finally {setWorking(false);}
  }

  return <section className="card" aria-label="Screenplay dialogue source impact">
    <h3>Script changes → dialogue and production bible</h3>
    <p className="fineprint">Compare your current screenplay to an exact saved FILM03 script snapshot. Earlier actor recordings, wardrobe links, OpenUSD Takes, editorial selections and source revisions are never silently replaced.</p>
    {error && <p role="alert">{error}</p>}
    {!sources.length ? <p className="muted">
      No creator-approved FILM03 script snapshot exists for this project yet.
      Original Studio screenplay versions remain saved. A source-authorized
      script snapshot must be captured before a historical performance comparison.
      This panel never fabricates approval.
    </p> : <>
      <label>Original script snapshot
        <select aria-label="Original dialogue source" value={scriptId}
          onChange={e=>{setScriptId(e.target.value);setImpact(null);}}>
          {sources.map(s=><option key={s.script_id} value={s.script_id}>
            {s.script_id} · source rev {s.revision} · screenplay rev {s.screenplay_revision}
          </option>)}
        </select>
      </label>
      <button className="secondary" disabled={working || !scriptId}
        onClick={preview}>Review source impacts (read only)</button>
    </>}
    {impact && <>
      <p><strong>Latest screenplay revision:</strong> {impact.screenplay_revision} ·
        Last captured dialogue snapshot: {impact.last_published_script_snapshot_revision}</p>
      <p>{impact.new_or_changed_script_lines.length} line source change(s) ·
        {impact.impacted_historical_performances.length} earlier performance(s) potentially affected</p>
      {impact.requires_manual_lineage_review && <p role="alert">
        Ambiguous dialogue ancestry: creator must explicitly reconcile old/new line identities.
      </p>}
      {impact.new_or_changed_script_lines.map((entry,i)=><div className="scene-item"
          key={entry.line_id + ':' + i}>
        <strong>{entry.speaker} · {entry.kind}</strong>
        <p className="fineprint">Scene {entry.scene_id} · stable line {entry.line_id}</p>
        {entry.old_text && <blockquote>Previous: {entry.old_text}</blockquote>}
        {entry.new_text && <blockquote>Current: {entry.new_text}</blockquote>}
      </div>)}
      {impact.impacted_historical_performances.map(item=><div className="scene-item"
          key={item.performance_id}>
        <strong>Historical performance: {item.performance_id}</strong>
        <p>Old script revision {item.old_script_revision} ·
          {item.current_text ? 'Current dialogue: ' + item.current_text
            : 'Original line removed or unmatched'}</p>
        <p className="fineprint">Director must choose: retain the original delivery,
          or record/select a new Take. Existing source audio is preserved.</p>
      </div>)}
      <h4>Versioned downstream consumers</h4>
      {(impact.previous_revision_indexed_production_dependents || []).map((item,i)=>
        <p className="fineprint" key={item.object_id + ':' + item.revision + ':' + i}>
          {item.object_id} · revision {item.revision}
        </p>)}
      <h4>Production Bible continuity warnings</h4>
      {(impact.production_bible?.issues || []).map((item,i)=><div className="scene-item"
          key={item.entity_id + ':' + i}>
        <strong>{item.entity_name || 'Source continuity'} · {item.type}</strong>
        <p>{item.scene_id || (item.affected_scenes || []).map(s=>s.scene_id).join(', ')}</p>
      </div>)}
      {!impact.new_or_changed_script_lines.length && !impact.production_bible?.issues?.length &&
        <p className="muted">No indexed script/continuity changes detected in this snapshot; not proof of semantic story consistency.</p>}
      <p className="fineprint">This report never saves a new scene, approves a line, changes production assets or launches an AI worker. Retake selection requires separate creator authority.</p>
    </>}
  </section>;
}
