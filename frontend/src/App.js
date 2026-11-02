import React, { useEffect, useState } from 'react';

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

  function create() {
    action(async () => {
      const result = await api('/projects', 'POST', { title, idea });
      accept(result);
      setProjects(await api('/projects'));
      setNotice('Your movie is saved on this computer.');
      setTab('story');
    });
  }

  function open(id) {
    action(async () => {
      accept(await api('/projects/' + id));
      setTab('story');
    });
  }

  function saveScript() {
    action(async () => {
      const result = await api('/projects/' + project.id + '/screenplay', 'PUT', {
        screenplay: script, expected_revision: project.revision,
      });
      accept(result);
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
        <p className="lead">You don't need a screenplay, a camera or filmmaking experience. Tell NVP what you have in mind.</p>
        <section className="card">
          <label>A name for your movie<input value={title} maxLength={150} placeholder="The long way home" onChange={(e) => setTitle(e.target.value)}/></label>
          <label>Your idea, in your words<textarea rows={6} maxLength={10000} value={idea} placeholder="A person returns home and discovers..." onChange={(e) => setIdea(e.target.value)}/></label>
          <div className="actions"><button className="primary" disabled={busy || !title.trim()} onClick={create}>Create my movie →</button></div>
        </section>
        <p className="fineprint">This foundation build organizes your story and camera ideas. AI writing, actors and film rendering are not connected yet.</p>
      </div> : <div className="page">
        <div className="kicker">YOUR MOVIE</div><h1>{project.title}</h1><p className="lead">{project.idea || 'Every story starts somewhere.'}</p>
        <nav className="tabs">
          <button className={tab === 'story' ? 'active' : ''} onClick={() => setTab('story')}>1 · Tell your story</button>
          <button className={tab === 'scenes' ? 'active' : ''} onClick={() => setTab('scenes')}>2 · Plan your scenes</button>
          <button className={tab === 'make' ? 'active' : ''} onClick={() => setTab('make')}>3 · Make your movie</button>
        </nav>
        {tab === 'story' && <div className="columns">
          <section className="card">
            <h2>Your screenplay</h2><p className="muted">Paste or write a scene. Use headings like INT. KITCHEN - NIGHT and character names above dialogue.</p>
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
