import React, {useEffect, useState} from 'react';

/** Read-only exact Studio screenplay -> FilmIndex dialogue -> Bible retake impact. */
export default function Film03ScriptChangeImpactPanel({project, api}) {
  const [sources, setSources] = useState([]);
  const [scriptId, setScriptId] = useState('');
  const [impact, setImpact] = useState(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [snapshotNotice, setSnapshotNotice] = useState('');
  const [newScriptId, setNewScriptId] = useState('NvpFilm03MainDialogue');
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

  async function publishSnapshot() {
    const native = window.pywebview?.api?.film03_publish_script_snapshot;
    if (typeof native !== 'function') {
      setError('New authoritative script snapshots require the installed NVP desktop native approval.');
      return;
    }
    const chosen = sources.find(s=>s.script_id===scriptId);
    const id = chosen?.script_id || newScriptId.trim();
    if (!/^[A-Za-z][A-Za-z0-9_.:-]{0,79}$/.test(id)) {
      setError('Enter a stable source identity, beginning with a letter.');
      return;
    }
    if (!window.confirm('Capture this screenplay as a NEW immutable source revision? Previous script, dialogue, voices and Takes remain preserved. The desktop host will separately request permission.')) return;
    setWorking(true); setError(''); setSnapshotNotice('');
    try {
      const result = await native({
        project_id: project.id, script_id:id,
        expected_screenplay_revision:project.revision,
        expected_manifest_revision:chosen?.revision || 0,
      });
      if (result?.format !== 'nvp.film03.native_director_script_snapshot_result.v1' ||
          result?.host_native_director_confirmation !== true ||
          result?.original_spoken_voice_mutated !== false ||
          result?.original_visual_take_mutated !== false ||
          result?.film_or_native_worker_execution_authorized !== false)
        throw new Error('Unverified native creator source result');
      const updated = await api(root + '/script-sources');
      setSources(updated.sources || []);
      setScriptId(id); setImpact(null);
      setSnapshotNotice('New script source revision ' + result.revision +
        ' captured under desktop director confirmation; old work remains intact.');
    } catch(e){setError(e.message);}
    finally {setWorking(false);}
  }

  return <section className="card" aria-label="Screenplay dialogue source impact">
    <h3>Script changes → dialogue and production bible</h3>
    <p className="fineprint">Compare your current screenplay to an exact saved FILM03 script snapshot. Earlier actor recordings, wardrobe links, OpenUSD Takes, editorial selections and source revisions are never silently replaced.</p>
    {error && <p role="alert">{error}</p>}
    {snapshotNotice && <p role="status">{snapshotNotice}</p>}
    <h4>Capture original screenplay as an immutable line source</h4>
    {!sources.length && <label>New script source ID
      <input aria-label="New script source ID" value={newScriptId} maxLength={80}
        onChange={e=>setNewScriptId(e.target.value)} />
    </label>}
    <button className="secondary" disabled={working || !project.screenplay?.trim() ||
      typeof window.pywebview?.api?.film03_publish_script_snapshot !== 'function'}
      onClick={publishSnapshot}>Capture script revision (native director approval)</button>
    {typeof window.pywebview?.api?.film03_publish_script_snapshot !== 'function' &&
      <p className="fineprint">Available only inside installed NVP with real native director confirmation. Ordinary browser/API access cannot publish a script source or voice Take.</p>}
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
