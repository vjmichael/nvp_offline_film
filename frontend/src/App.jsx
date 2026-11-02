import React, { useEffect, useState } from 'react';

const STORY_STAGE_ORDER = ['logline', 'synopsis', 'beat_sheet', 'treatment', 'screenplay'];

const SAMPLE = "INT. KITCHEN - NIGHT\n\nSomeone waits at the table.\n\nALEX\nI didn't think you would come.\n\nSAM\nNeither did I.";

async function api(path, method = 'GET', data) {
  const response = await fetch('/api' + path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
  if (!response.ok) {
    const message = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof message.detail === 'string' ? message.detail : JSON.stringify(message.detail));
  }
  return response.json();
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [title, setTitle] = useState('');
  const [idea, setIdea] = useState('');
  const [startMode, setStartMode] = useState('idea');
  const [openingScript, setOpeningScript] = useState('');
  const [creativeStatus, setCreativeStatus] = useState(null);
  const [localModelStatus, setLocalModelStatus] = useState(null);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [modelServerPort, setModelServerPort] = useState('1234');
  const [drafts, setDrafts] = useState([]);
  const [scriptHistory, setScriptHistory] = useState([]);
  const [writingStage, setWritingStage] = useState('logline');
  const approvedForStage = STORY_STAGE_ORDER.slice(0, STORY_STAGE_ORDER.indexOf(writingStage))
    .map((stage) => drafts.filter((d) => d.stage === stage && d.status === 'accepted')
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '') || b.id.localeCompare(a.id))[0])
    .filter(Boolean);
  const storyNeedsReview = approvedForStage.some((draft) => draft.context_status === 'needs_review');
  const [writingNotes, setWritingNotes] = useState('');
  const [writingSceneId, setWritingSceneId] = useState('');
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [draftText, setDraftText] = useState('');
  const [script, setScript] = useState('');
  const [selectedScene, setSelectedScene] = useState(null);
  const [selectedShot, setSelectedShot] = useState(null);
  const [shotEdit, setShotEdit] = useState(null);
  const [tab, setTab] = useState('story');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    Promise.all([api('/status'), api('/projects')])
      .then(([status, list]) => { setHealth(status); setProjects(list); })
      .catch((err) => setError('Local NVP server not available: ' + err.message));
  }, []);

  async function action(fn) {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  function accept(data) {
    setProject(data);
    setScript(data.screenplay);
    setSelectedScene(data.scenes[0]?.id || null);
    setSelectedShot(null);
    setShotEdit(null);
  }

  async function refreshCreative(projectId) {
    const [status, list, modelInfo] = await Promise.all([
      api('/creative/status'),
      api('/projects/' + projectId + '/creative-drafts'),
      api('/creative/models' + (modelServerPort ? '?port=' + modelServerPort : ''))
    ]);
    setCreativeStatus(status);
    setLocalModelStatus(modelInfo);
    setSelectedModelId((prior) => modelInfo.models.some((item) => item.id === prior)
      ? prior : (modelInfo.models[0]?.id || ''));
    setDrafts(list);
    setScriptHistory(await api('/projects/' + projectId + '/screenplay-history'));
  }

  async function importScript(event, setter) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!/\.(fountain|txt)$/i.test(file.name) || file.size > 1000000) {
      setError('Choose a .fountain or .txt script smaller than 1 MB. FDX and PDF import are not available yet.');
      return;
    }
    setError('');
    setter(await file.text());
  }

  function selectDraft(item) {
    setSelectedDraft(item);
    setDraftText(item.content);
    setWritingStage(item.stage);
  }

  function generateWriting() {
    action(async () => {
      if (!selectedModelId) throw new Error('Load a local model and refresh the list first.');
      const draft = await api('/projects/' + project.id + '/creative-drafts/generate', 'POST', {
        model_id: selectedModelId,
        model_port: modelServerPort ? Number(modelServerPort) : null,
        stage: writingStage, instructions: writingNotes, scene_id: writingSceneId || null
      });
      await refreshCreative(project.id);
      selectDraft(draft);
      setNotice('Local AI produced a proposal. Review and edit before approving it.');
    });
  }

  function saveWriting() {
    action(async () => {
      let draft;
      if (selectedDraft?.status === 'proposed') {
        draft = await api('/projects/' + project.id + '/creative-drafts/' + selectedDraft.id,
          'PUT', { content: draftText, expected_edit_revision: selectedDraft.edit_revision });
      } else {
        draft = await api('/projects/' + project.id + '/creative-drafts', 'POST', {
          stage: writingStage, content: draftText, instructions: writingNotes
        });
      }
      await refreshCreative(project.id);
      selectDraft(draft);
      setNotice('Your draft is saved separately from the screenplay.');
    });
  }

  function decideWriting(decision) {
    action(async () => {
      if (!selectedDraft) throw Error('Choose a saved draft first.');
      if (selectedDraft.content !== draftText) throw Error('Save your draft changes before approval.');
      if (decision === 'use_as_screenplay' && project.screenplay.trim() &&
          !window.confirm('Replace your current screenplay with this draft? The previous script will be kept in revision history.')) return;
      const changed = await api('/projects/' + project.id + '/creative-drafts/' + selectedDraft.id +
        '/decision', 'POST', { decision, expected_project_revision: project.revision });
      accept(changed);
      await refreshCreative(project.id);
      setSelectedDraft(null);
      setDraftText('');
      if (decision === 'use_as_screenplay') {
        setTab('story');
        setNotice('Approved screenplay applied. Check any affected scene and shot plans.');
      } else {
        setNotice(decision === 'discard' ? 'Proposal discarded.' : 'Creative draft approved.');
      }
    });
  }

  function create() {
    action(async () => {
      let result = await api('/projects', 'POST', { title, idea });
      if (startMode === 'script' && openingScript.trim()) {
        result = await api('/projects/' + result.id + '/screenplay', 'PUT', {
          screenplay: openingScript, expected_revision: result.revision
        });
      }
      accept(result);
      setProjects(await api('/projects'));
      await refreshCreative(result.id);
      setNotice('Your movie is saved on this computer.');
      setTab(startMode === 'script' ? 'story' : 'develop');
    });
  }

  function open(id) {
    action(async () => {
      accept(await api('/projects/' + id));
      await refreshCreative(id);
      setTab('develop');
    });
  }

  function restoreScriptRevision(revision) {
    action(async () => {
      if (!window.confirm('Restore this earlier screenplay? Your current screenplay will be kept in history.')) return;
      const restored = await api('/projects/' + project.id + '/screenplay-history/' + revision + '/restore',
        'POST', { expected_revision: project.revision });
      accept(restored);
      await refreshCreative(project.id);
      setNotice('An earlier screenplay has been restored. Review the affected scene plans.');
    });
  }

  function saveScript() {
    action(async () => {
      const result = await api('/projects/' + project.id + '/screenplay', 'PUT', {
        screenplay: script, expected_revision: project.revision,
      });
      accept(result);
      await refreshCreative(project.id);
      setNotice('Screenplay saved. Review the extracted scenes.');
    });
  }

  function plan(scene) {
    action(async () => {
      const result = await api('/projects/' + project.id + '/scenes/' + scene.id + '/shot-plan', 'POST');
      accept(result);
      setSelectedScene(scene.id);
      setTab('scenes');
      setNotice('Editable shot suggestions were saved. No footage was generated.');
    });
  }

  function chooseShot(shot) {
    setSelectedShot(shot.shot_id);
    setShotEdit({ ...shot });
  }

  function saveShot(approved) {
    const sceneId = selectedScene;
    const shotId = selectedShot;
    action(async () => {
      const result = await api('/projects/' + project.id + '/scenes/' + sceneId + '/shots/' + shotId, 'PUT', {
        framing: shotEdit.framing, subject: shotEdit.subject, intent: shotEdit.intent,
        notes: shotEdit.notes, approved,
      });
      accept(result);
      setSelectedScene(sceneId);
      setSelectedShot(shotId);
      setShotEdit({ ...result.scenes.find((scene) => scene.id === sceneId).shots.find((shot) => shot.shot_id === shotId) });
      setNotice(approved ? 'You approved this shot. Replanning will preserve it.' : 'Shot idea saved.');
    });
  }

  function field(name, value) {
    setShotEdit((old) => ({ ...old, [name]: value }));
  }

  const current = project?.scenes.find((scene) => scene.id === selectedScene);
  const unsaved = project && script !== project.screenplay;

  return <div className="layout">
    <aside>
      <div className="brand">NVP<span>✦</span></div>
      <p className="muted">A movie starts with you.</p>
      <div className="small-title">YOUR MOVIES</div>
      <button className="side-button" onClick={() => { setProject(null); setError(''); setNotice(''); }}>+ Make a movie</button>
      {projects.map((p) => <button key={p.id} className={'side-button ' + (p.id === project?.id ? 'chosen' : '')} onClick={() => open(p.id)}>{p.title}</button>)}
      <div className="sidebar-bottom">● Offline-first planning<br/><span className="muted">No cloud account required</span></div>
    </aside>
    <main>
      <header><span>YOUR PERSONAL FILM STUDIO</span><span>{health ? 'Planning tools ready' : 'Server disconnected'}</span></header>
      {error && <p role="alert" className="alert">{error}</p>}
      {notice && <p role="status" className="notice">{notice}</p>}
      {!project ? <div className="page introduction">
        <div className="kicker">START HERE</div>
        <h1>What's the movie you've been imagining?</h1>
        <p className="lead">Start with a sentence or bring the script you've already written. NVP helps you develop the story and plan how it looks on screen.</p>
        <section className="card">
          <div className="mode-choices">
            <button className={startMode === 'idea' ? 'active' : ''} onClick={() => setStartMode('idea')}>I have an idea</button>
            <button className={startMode === 'script' ? 'active' : ''} onClick={() => setStartMode('script')}>I have a script</button>
          </div>
          <label>A name for your movie<input value={title} maxLength={150} placeholder="The long way home" onChange={(e) => setTitle(e.target.value)}/></label>
          {startMode === 'idea'
            ? <label>What's your idea? Write it however you like.<textarea rows={6} maxLength={10000} value={idea} placeholder="A person returns home and discovers..." onChange={(e) => setIdea(e.target.value)}/></label>
            : <><label>Bring your existing script (.fountain or .txt)<input type="file" accept=".fountain,.txt" onChange={(e) => importScript(e, setOpeningScript)}/></label>
                <label>Or paste it here<textarea rows={9} value={openingScript} maxLength={1000000} onChange={(e) => setOpeningScript(e.target.value)} placeholder="INT. APARTMENT - NIGHT..."/></label></>}
          <div className="actions"><button className="primary" disabled={busy || !title.trim() || (startMode === 'script' && !openingScript.trim())} onClick={create}>Start making my movie →</button></div>
        </section>
        <p className="fineprint">Your ideas stay on this computer. This is a working planning prototype; actual film rendering is not connected yet.</p>
      </div> : <div className="page">
        <div className="kicker">YOUR MOVIE</div><h1>{project.title}</h1><p className="lead">{project.idea || 'Every story starts somewhere.'}</p>
        <nav className="tabs">
          <button className={tab === 'develop' ? 'active' : ''} onClick={() => setTab('develop')}>1 · Develop the idea</button>
          <button className={tab === 'story' ? 'active' : ''} onClick={() => setTab('story')}>2 · Screenplay</button>
          <button className={tab === 'scenes' ? 'active' : ''} onClick={() => setTab('scenes')}>3 · Plan scenes</button>
          <button className={tab === 'make' ? 'active' : ''} onClick={() => setTab('make')}>4 · Make the film</button>
        </nav>
        {tab === 'develop' && <div className="columns">
          <section className="card">
            <h2>Develop your story</h2>
            <p className="muted">Work on as much or as little of the script as you want. Every AI suggestion is editable and waits for your approval.</p>
            <label>Local AI server
              <select value={modelServerPort} onChange={(e) => {
                setModelServerPort(e.target.value);
                setLocalModelStatus(null);
                setSelectedModelId('');
              }}>
                <option value="1234">LM Studio — port 1234</option>
                <option value="8080">llama.cpp server — port 8080</option>
                <option value="">Developer-configured local server</option>
              </select>
            </label>
            <label>Local writing model
              <select value={selectedModelId} disabled={!localModelStatus?.models?.length}
                onChange={(e) => setSelectedModelId(e.target.value)}>
                {(!localModelStatus?.models?.length) && <option value="">No local model reported</option>}
                {(localModelStatus?.models || []).map((model) => <option key={model.id} value={model.id}>
                  {model.family_hint} — {model.id}
                </option>)}
              </select>
            </label>
            <div className="actions">
              <button className="secondary" disabled={busy}
                onClick={() => action(async () => {
                  await refreshCreative(project.id);
                  setNotice('Local model list refreshed. The server may still need to load the weights.');
                })}>Refresh local models</button>
            </div>
            <p className="fineprint">{localModelStatus?.message || 'Checking for a local model server...'}</p>
            <label>What are we working on?
              <select value={writingStage} onChange={(e) => { setWritingStage(e.target.value); setSelectedDraft(null); setDraftText(''); }}>
                <option value="logline">One-sentence movie idea</option>
                <option value="synopsis">Story summary</option>
                <option value="beat_sheet">Story beats</option>
                <option value="treatment">Detailed story treatment</option>
                <option value="screenplay">Actual screenplay scene(s)</option>
              </select>
            </label>
            {approvedForStage.length > 0 && <div className="context-panel">
              <h3>Approved story decisions used for this stage</h3>
              <p className="fineprint">Only your approved earlier stages become story context. AI proposals remain suggestions.</p>
              {approvedForStage.map((draft) => <p key={draft.id} className="fineprint">
                <strong>{draft.stage.replaceAll('_', ' ')}</strong>
                {draft.context_status === 'needs_review'
                  ? ' — Needs review: ' + (draft.changed_upstream_stages || []).join(', ')
                  : draft.context_status === 'legacy_untracked' ? ' — Older decision: lineage not recorded' : ' — Current'}
                <span> · {draft.content.slice(0,160)}{draft.content.length > 160 ? '…' : ''}</span>
              </p>)}
            </div>}
            {storyNeedsReview && <p role="alert" className="fineprint">
              An earlier approved decision has changed. Revisit the affected story stage before asking AI to write later stages.
            </p>}
            {writingStage === 'screenplay' && project.scenes.length > 0 &&
              <label>Focus on a scene, or leave blank for a new scene
                <select value={writingSceneId} onChange={(e) => setWritingSceneId(e.target.value)}>
                  <option value="">New scene / overall story</option>
                  {project.scenes.map((s) => <option value={s.id} key={s.id}>{s.number}. {s.heading}</option>)}
                </select>
              </label>}
            <label>What would you like the writing assistant to do?
              <textarea rows={4} maxLength={5000} value={writingNotes} onChange={(e) => setWritingNotes(e.target.value)}
                placeholder="Make the conversation tense but keep both characters sympathetic."/>
            </label>
            <div className="actions">
              <button className="secondary" disabled={busy || storyNeedsReview || !selectedModelId || localModelStatus?.state !== 'available'} onClick={generateWriting}>Ask selected local AI to draft</button>
            </div>
            <p className="fineprint">NVP uses only the local model server. A model listed above is not necessarily loaded or tested. Drafts remain proposals until you approve them.</p>
            <label>Draft (write it yourself, edit AI output, or paste an existing draft)
              <textarea className="script" rows={16} value={draftText} maxLength={120000} onChange={(e) => setDraftText(e.target.value)}
                placeholder={writingStage === 'screenplay' ? 'INT. HOME - NIGHT\n\nA door opens...' : 'Write your story idea here...'}/>
            </label>
            <div className="actions">
              <button className="secondary" disabled={busy || !draftText.trim() || (selectedDraft && selectedDraft.status !== 'proposed')} onClick={saveWriting}>
                {selectedDraft ? 'Save revised draft' : 'Save my draft'}
              </button>
              {selectedDraft?.status === 'proposed' && <>
                <button className="secondary" disabled={busy || draftText !== selectedDraft.content} onClick={() => decideWriting('accept')}>Approve as story note</button>
                {selectedDraft.stage === 'screenplay' && <button className="primary" disabled={busy || draftText !== selectedDraft.content} onClick={() => decideWriting('use_as_screenplay')}>Use as screenplay</button>}
              </>}
            </div>
            <p className="fineprint">Using a draft as the screenplay replaces its current text with your explicit approval. Non-screenplay drafts are stored as approved story notes.</p>
          </section>
          <section className="card"><h2>Your creative drafts</h2>
            {drafts.length === 0 && <p className="muted">No writing proposals yet. Your original idea remains saved.</p>}
            {drafts.map((d) => <button className={'scene-item ' + (selectedDraft?.id === d.id ? 'active' : '')}
                key={d.id} onClick={() => selectDraft(d)}>
              <small>{d.stage.replaceAll('_', ' ')} · {d.origin === 'local_ai' ? 'Local AI proposal' : 'Written by you'}</small>
              <strong>{d.content.slice(0,110)}{d.content.length > 110 ? '…' : ''}</strong>
              <span>{d.status} · revision {d.edit_revision}
                {d.context_status === 'needs_review'
                  ? ' · Needs review (' + (d.changed_upstream_stages || []).join(', ') + ')' : ''}
              </span>
            </button>)}
            {selectedDraft?.status === 'proposed' && <div className="actions">
              <button className="secondary" disabled={busy} onClick={() => decideWriting('discard')}>Discard this draft</button>
            </div>}
          </section>
        </div>}
        {tab === 'story' && <div className="columns">
          <section className="card">
            <h2>Your screenplay</h2><p className="muted">Write or edit any scene directly, or develop it collaboratively in the previous tab. Use headings such as INT. KITCHEN - NIGHT.</p>
            <label>Import a .fountain or .txt screenplay<input type="file" accept=".fountain,.txt" onChange={(e) => importScript(e, setScript)} /></label>
            <textarea className="script" rows={18} value={script} onChange={(e) => setScript(e.target.value)} placeholder="INT. BEDROOM - NIGHT&#10;&#10;A character opens a letter..." />
            <div className="actions">
              <button className="secondary" disabled={busy || script.trim().length > 0} onClick={() => setScript(SAMPLE)}>Try a sample</button>
              <button className="primary" disabled={busy || !unsaved} onClick={saveScript}>Save and find scenes</button>
            </div>
            {unsaved && <p className="fineprint">Unsaved screenplay edits.</p>}
          </section>
          <section className="card"><h2>Your story so far</h2>
            <p>{project.scenes.length} scenes found · {project.bible.characters.length} speaking characters</p>
            <h3>Characters</h3>{project.bible.characters.length
              ? <div className="chips">{project.bible.characters.map((c) => <span key={c}>{c}</span>)}</div>
              : <p className="muted">Character names appear after you save dialogue.</p>}
            <h3>Locations</h3>{project.bible.locations.map((name) => <p key={name}>{name}</p>)}
            {project.archived_shots > 0 && <p className="warning">{project.archived_shots} old shot plans are preserved after scene-heading changes. Reconciliation is a future feature.</p>}
            <h3>Earlier screenplay versions</h3>
            {scriptHistory.length === 0 && <p className="muted">No earlier versions yet.</p>}
            {scriptHistory.map((version) => <div className="history-item" key={version.revision}>
              <span>Revision {version.revision} · {version.reason.replaceAll('_', ' ')}</span>
              <button className="secondary" disabled={busy || !!unsaved} onClick={() => restoreScriptRevision(version.revision)}>Restore</button>
            </div>)}
            {unsaved && <p className="fineprint">Save or discard your unsaved screenplay edits before restoring a version.</p>}
            <p className="fineprint">This is simple screenplay extraction, not AI understanding of your story.</p>
          </section>
        </div>}
        {tab === 'scenes' && <div className="columns">
          <section className="card"><h2>Your scenes</h2><p className="muted">Choose a scene to plan camera views.</p>
            {project.scenes.length === 0 && <p>Write your first scene under “Tell your story.”</p>}
            {project.scenes.map((s) => <button key={s.id} className={'scene-item ' + (selectedScene === s.id ? 'active' : '')} onClick={() => { setSelectedScene(s.id); setSelectedShot(null); setShotEdit(null); }}>
              <small>SCENE {s.number}</small><strong>{s.heading}</strong><span>{s.characters.join(', ') || 'No dialogue found'} · {s.shots.length} shot plans</span>
            </button>)}
          </section>
          <section className="card">{current ? <>
            <h2>{current.heading}</h2><pre className="excerpt">{current.text}</pre>
            <div className="actions"><button className="secondary" disabled={busy} onClick={() => plan(current)}>Suggest camera views</button></div>
            {current.shots.map((shot) => <button key={shot.shot_id} className={'shot-item ' + (selectedShot === shot.shot_id ? 'active' : '')} onClick={() => chooseShot(shot)}>
              {shot.shot_id} · {shot.framing.replaceAll('_', ' ')} <span>{shot.status}</span>
            </button>)}
            {shotEdit && <div className="shot-edit">
              <h3>Change this camera idea</h3>
              <label>View<select value={shotEdit.framing} onChange={(e) => field('framing', e.target.value)}>
                <option value="wide">Whole space</option><option value="two_shot">Two people</option>
                <option value="medium">A person</option><option value="close_up">Close up</option><option value="insert">Important object</option>
              </select></label>
              <label>What we see<input value={shotEdit.subject} onChange={(e) => field('subject', e.target.value)}/></label>
              <label>Why we see it<input value={shotEdit.intent} onChange={(e) => field('intent', e.target.value)}/></label>
              <label>Your notes<textarea rows={3} value={shotEdit.notes} onChange={(e) => field('notes', e.target.value)}/></label>
              <div className="actions"><button className="secondary" disabled={busy} onClick={() => saveShot(false)}>Save idea</button><button className="primary" disabled={busy} onClick={() => saveShot(true)}>Approve this shot</button></div>
            </div>}
          </> : <p>Choose a scene on the left.</p>}</section>
        </div>}
        {tab === 'make' && <section className="card make"><div className="kicker">FUTURE MILESTONE</div>
          <h2>Bring your movie to life</h2><p>NVP will eventually build 3D sets, animate characters, film camera shots, edit scenes, mix audio and export the movie. This is not implemented in this foundation build.</p>
          <div className="future"><span>Build a location — planned</span><span>Animate characters — planned</span><span>Film a scene — planned</span><span>Edit and export — planned</span></div>
          <p className="fineprint">AMD, NVIDIA and CPU backends will be supported by capability, without requiring CUDA just to launch NVP.</p>
        </section>}
      </div>}
    </main>
  </div>;
}
