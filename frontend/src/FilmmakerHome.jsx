import React, {useEffect, useRef, useState} from 'react';
import LineNumberedTextarea from './LineNumberedTextarea.jsx';
import './filmmaker-home.css';

const PHASES = [
  {id:'script', label:'Script', detail:'Optional'},
  {id:'scenes', label:'Set Up Scenes'},
  {id:'film', label:'Film Scenes'},
  {id:'edit', label:'Edit Film'},
  {id:'export', label:'Export Film'},
];
const DIRECTOR = {'x-nvp-director':'1'};
async function request(path, method='GET', data) {
  const response=await fetch('/api'+path,{
    method, credentials:'same-origin',
    headers:{'Content-Type':'application/json',...DIRECTOR},
    ...(data===undefined?{}:{body:JSON.stringify(data)}),
  });
  if (!response.ok) {
    const err=await response.json().catch(()=>({detail:'Film service unavailable'}));
    const error=new Error(typeof err.detail==='string'?err.detail:'Film service unavailable');
    error.status=response.status;
    throw error;
  }
  return response.json();
}
function restorePhase(id) {
  try {
    const p=window.localStorage.getItem('nvp-film-phase-'+id);
    return PHASES.some(x=>x.id===p)?p:'scenes';
  } catch {return 'scenes';}
}
function useDialogFocus(isOpen) {
  const ref=useRef(null);
  useEffect(()=>{if(isOpen) ref.current?.focus();},[isOpen]);
  return ref;
}
function keepDialogFocus(event) {
  if(event.key!=='Tab')return;
  const items=[...event.currentTarget.querySelectorAll(
    'button:not(:disabled),input:not(:disabled),a[href],textarea:not(:disabled)'
  )].filter(element=>element.getClientRects().length||element.offsetParent!==null);
  // Headless jsdom may not compute rectangles; the actual installed browser does.
  const all=items.length?items:[...event.currentTarget.querySelectorAll(
    'button:not(:disabled),input:not(:disabled),a[href],textarea:not(:disabled)'
  )];
  if(!all.length)return;
  if(event.shiftKey&&document.activeElement===all[0]){
    event.preventDefault();all[all.length-1].focus();
  }else if(!event.shiftKey&&document.activeElement===all[all.length-1]){
    event.preventDefault();all[0].focus();
  }
}
function DisplayMessage({children,kind='assistant'}) {
  return <div className={'film-message film-message-'+kind}>{children}</div>;
}

export default function FilmmakerHome() {
  const [projects,setProjects]=useState([]);
  const [project,setProject]=useState(null);
  const [flow,setFlow]=useState('welcome');
  const [phase,setPhase]=useState('scenes');
  const [mode,setMode]=useState('idea');
  const [askMode,setAskMode]=useState(true);
  const [title,setTitle]=useState('');
  const [idea,setIdea]=useState('');
  const [script,setScript]=useState('');
  const [selectedScene,setSelectedScene]=useState('');
  const [lockTarget,setLockTarget]=useState(null);
  const [lockAction,setLockAction]=useState('unlock');
  const [passphrase,setPassphrase]=useState('');
  const [confirmPhrase,setConfirmPhrase]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [serviceAvailable,setServiceAvailable]=useState(false);
  const [canEncrypt,setCanEncrypt]=useState(false);
  const [encryptMovie,setEncryptMovie]=useState(false);
  const [moviePassphrase,setMoviePassphrase]=useState('');
  const [moviePassphraseAgain,setMoviePassphraseAgain]=useState('');
  const dialogFocus=useDialogFocus(flow==='welcome');
  const lockFocus=useDialogFocus(!!lockTarget);

  async function refreshProjects() {
    const list=await request('/projects');
    setProjects(list);
    return list;
  }
  useEffect(()=>{
    let mounted=true;
    Promise.all([request('/status'),request('/projects')])
      .then(([status,list])=>{
        if (!mounted) return;
        setServiceAvailable(status.status==='ready');
        setCanEncrypt(status.capabilities?.project_file_encryption==='new_windows_movies_only');
        setProjects(list);
      }).catch(()=>{if(mounted)setError('NVP is not connected. Your saved movie remains on this computer.');});
    return ()=>{mounted=false};
  },[]);
  // WebView2 may leave a screenplay partially edited while the director
  // selects another movie. Never discard that source silently.
  function confirmLeavingUnsaved() {
    return !project || script===project.screenplay ||
      window.confirm('This screenplay has unsaved edits. Leave without saving?');
  }
  useEffect(()=>{
    if(!project?.id)return;
    let active=true;
    const id=project.id;
    const revoke=()=>{
      if(!active)return;
      active=false;
      setProject(null);
      setScript('');
      setSelectedScene('');
      setFlow('resume');
      setError('This movie was locked or is no longer available. Unlock it to continue.');
      request('/projects').then(list=>setProjects(list)).catch(()=>{});
    };
    const verify=()=>{
      request('/projects/'+id+(project.encrypted?'/live':'')).catch(error=>{
        if(active&&(error.status===423||error.status===404))revoke();
      });
    };
    const onStorage=(event)=>{
      if(event.key==='nvp-film-lock-'+id)revoke();
    };
    window.addEventListener('storage',onStorage);
    window.addEventListener('focus',verify);
    const poll=window.setInterval(verify,15000);
    return ()=>{
      active=false;
      window.removeEventListener('storage',onStorage);
      window.removeEventListener('focus',verify);
      window.clearInterval(poll);
    };
  },[project?.id,project?.encrypted]);
  async function perform(fn) {
    if(busy)return;
    setBusy(true);setError('');setNotice('');
    try{await fn()}catch(err){setError(err.message)}
    finally{setBusy(false)}
  }
  function showWelcome(force=false) {
    if(!force&&!confirmLeavingUnsaved())return;
    setProject(null);setFlow('welcome');setError('');setNotice('');
  }
  function beginMovie() {
    if(!confirmLeavingUnsaved())return;
    setProject(null);setFlow('new');setAskMode(true);setError('');setNotice('');
    setEncryptMovie(false);setMoviePassphrase('');setMoviePassphraseAgain('');
  }
  function goPhase(next, movieId=project?.id) {
    setPhase(next);
    if(movieId)try{window.localStorage.setItem('nvp-film-phase-'+movieId,next)}catch{}
  }
  function attachMovie(movie) {
    setProject(movie);
    setScript(movie.screenplay||'');
    let remembered='';
    try{remembered=window.localStorage.getItem('nvp-film-scene-'+movie.id)||''}catch{}
    setSelectedScene(movie.scenes?.some(s=>s.id===remembered)
      ?remembered:(movie.scenes?.[0]?.id||''));
    setPhase(restorePhase(movie.id));
    setFlow('working');
  }
  async function openMovie(id) {
    if(id===project?.id)return;
    if(!confirmLeavingUnsaved())return;
    const record=projects.find(x=>x.id===id);
    if(record?.locked&&!record.unlocked) {
      setLockTarget(record);setLockAction('unlock');setPassphrase('');setConfirmPhrase('');
      return;
    }
    await perform(async()=>{attachMovie(await request(
      '/projects/'+id+(record?.encrypted?'/live':'')))});
  }
  async function unlockMovie(event) {
    event.preventDefault();
    await perform(async()=>{
      await request('/projects/'+lockTarget.id+'/unlock','POST',{passphrase});
      const id=lockTarget.id;
      setLockTarget(null);setPassphrase('');
      await refreshProjects();
      attachMovie(await request(
        '/projects/'+id+(lockTarget.encrypted?'/live':'')));
    });
  }
  async function protectOrRelock(event) {
    event.preventDefault();
    await perform(async()=>{
      if(lockAction==='protect'){
        if(passphrase!==confirmPhrase)throw new Error('The two passphrases do not match.');
        await request('/projects/'+lockTarget.id+'/protect','POST',{passphrase});
      }else{
        await request('/projects/'+lockTarget.id+'/lock','POST');
      }
      try{window.localStorage.setItem('nvp-film-lock-'+lockTarget.id,String(Date.now()))}catch{}
      setLockTarget(null);setPassphrase('');setConfirmPhrase('');
      await refreshProjects();showWelcome(true);
      setNotice('Movie locked. Its scenes and screenplay require unlocking again.');
    });
  }
  async function createMovie() {
    await perform(async()=>{
      const name=title.trim();
      if (!name)throw new Error('Give your movie a title.');
      if(mode==='script'&&!script.trim())throw new Error('Upload or paste your script.');
      if(encryptMovie&&(!canEncrypt||moviePassphrase.length<12||
          moviePassphrase!==moviePassphraseAgain)){
        throw new Error('Enter and confirm a movie passphrase of at least 12 characters.');
      }
      const movie=await request(encryptMovie?'/projects/encrypted':'/projects','POST',{
        title:name,idea:idea.trim(),screenplay:mode==='script'?script:'',
        ...(encryptMovie?{passphrase:moviePassphrase}:{})
      });
      setMoviePassphrase('');setMoviePassphraseAgain('');
      await refreshProjects();
      attachMovie(movie);
      goPhase('scenes',movie.id);
      setNotice(mode==='script'
        ? 'Script saved and its scenes listed. You decide how the scenes are performed.'
        : 'Idea saved. Set up your first scene when you are ready.');
    });
  }
  async function saveScript() {
    await perform(async()=>{
      const next=await request('/projects/'+project.id+
        (project.encrypted?'/live/screenplay':'/screenplay'),'PUT',{
        screenplay:script,expected_revision:project.revision
      });
      attachMovie(next);
      goPhase('scenes');
      setNotice('Screenplay saved. Review its scenes and missing details.');
    });
  }
  async function chooseScene(id) {
    setSelectedScene(id);
    if(project?.id)try{window.localStorage.setItem('nvp-film-scene-'+project.id,id)}catch{}
  }
  async function suggestShots(scene) {
    await perform(async()=>{
      if(project.encrypted)throw new Error(
        'Protected filming workers remain disabled until host authorization is connected.');
      const next=await request('/projects/'+project.id+'/scenes/'+scene.id+'/shot-plan','POST');
      attachMovie(next);setSelectedScene(scene.id);goPhase('film');
      setNotice('Shot suggestions saved. No performance has been filmed.');
    });
  }
  function startLock(nextAction, record) {
    setPassphrase('');setConfirmPhrase('');setError('');
    setLockAction(nextAction);setLockTarget(record);
  }
  const scene=project?.scenes?.find(x=>x.id===selectedScene)||project?.scenes?.[0]||null;
  const dirty=project&&script!==project.screenplay;
  const targetProject=projects.find(p=>p.id===project?.id);
  const postUrl=project?'/postproduction.html?project='+encodeURIComponent(project.id)+
    (project.encrypted?'&encrypted=1':''):'#';

  return <div className="film-shell">
    <aside className="film-sidebar" aria-label="Your movie projects">
      <button className="film-brand" onClick={()=>showWelcome()} aria-label="NVP home">NVP <span>FILM</span></button>
      <button className="film-new" onClick={beginMovie} disabled={busy}>+ New Movie</button>
      <div className="film-sidebar-label">YOUR MOVIES</div>
      <div className="film-project-list">
        {projects.length===0&&<p className="film-muted">No movies yet.</p>}
        {projects.map(p=><div className="film-project-row" key={p.id}>
          <button className={'film-project '+(project?.id===p.id?'selected':'')}
            onClick={()=>openMovie(p.id)} title={p.locked&&!p.unlocked?'Unlock to resume':'Resume movie'}
            aria-label={(p.locked&&!p.unlocked?'Locked movie: ':'Resume movie: ')+p.title}>
            <span aria-hidden="true">{p.encrypted?'🔐':p.locked&&!p.unlocked?'🔒':p.locked?'🔓':'🎬'}</span>
            <span>{p.title}</span>
          </button>
          {p.locked&&p.unlocked&&<button className="film-mini" title={'Lock '+p.title}
            aria-label={'Lock '+p.title} onClick={()=>startLock('lock',p)}>Lock</button>}
        </div>)}
      </div>
      <div className="film-sidebar-footer">
        <span className="film-status-dot" aria-hidden="true"></span>
        {serviceAvailable?'Movies saved locally':'Film service unavailable'}
        <p>Make a movie, not a technical project.</p>
      </div>
    </aside>
    <main className="film-main">
      <header className="film-topbar">
        <span>{project?'MAKING '+project.title.toUpperCase():'YOUR FILM STUDIO'}</span>
        <span className="film-ai-state" aria-label="AI connection status">AI assistance not connected</span>
      </header>
      {error&&<div role="alert" className="film-error">{error}</div>}
      {notice&&<div role="status" className="film-notice">{notice}</div>}

      {flow==='welcome'&&<section className="film-home" aria-label="Chat home">
        <div className="film-home-heading"><div className="film-eyebrow">YOUR CREATIVE SPACE</div>
          <h1>What movie are you imagining?</h1>
          <p>Your film starts with an idea. We can shape it scene by scene.</p>
        </div>
        <div className="film-conversation" role="log" aria-label="Filmmaking conversation">
          <DisplayMessage>Welcome to NVP. Would you like to make a new movie or resume working on a movie?</DisplayMessage>
          {idea.trim()&&<DisplayMessage kind="user">{idea}</DisplayMessage>}
        </div>
        <div className="film-home-compose">
          <label htmlFor="film-home-idea">Describe your film idea (optional)</label>
          <textarea id="film-home-idea" rows={3} value={idea} maxLength={10000}
            onChange={e=>setIdea(e.target.value)} placeholder="A quiet story about a family returning home..."/>
          <div className="film-actions">
            <button className="film-secondary" onClick={()=>setFlow('resume')}>Resume Working</button>
            <button className="film-primary" onClick={beginMovie}>New Movie →</button>
          </div>
          <p className="film-hint">Your idea is not sent to an AI until a model is connected. You can work manually now.</p>
        </div>
        <div role="dialog" aria-modal="true" aria-labelledby="film-welcome-title" className="film-modal-backdrop" onKeyDown={keepDialogFocus}>
          <section className="film-modal">
            <div className="film-eyebrow">WELCOME TO NVP</div>
            <h2 id="film-welcome-title">Would you like to make a new movie or resume working on a movie?</h2>
            <div className="film-modal-actions">
              <button ref={dialogFocus} className="film-primary" onClick={beginMovie}>New Movie</button>
              <button className="film-secondary" onClick={()=>setFlow('resume')}>Resume Working</button>
            </div>
          </section>
        </div>
      </section>}

      {flow==='resume'&&<section className="film-page">
        <div className="film-eyebrow">YOUR MOVIES</div><h1>Resume Working</h1>
        <p className="film-muted">Choose a film to continue where you left off. Protected films require their passphrase.</p>
        <div className="film-movie-grid">{projects.map(p=><button className="film-movie-card" key={p.id}
          onClick={()=>openMovie(p.id)}><strong>{p.title}</strong><span>{p.locked&&!p.unlocked?'Locked · Unlock to continue':'Resume movie'}</span></button>)}</div>
        <button className="film-secondary" onClick={showWelcome}>Back</button>
      </section>}

      {flow==='new'&&<section className="film-page film-wizard">
        <div className="film-eyebrow">NEW MOVIE · STEP 1</div>
        <h1>Start with a script or just an idea.</h1>
        {askMode&&<div role="group" aria-label="Optional screenplay question" className="film-choice">
          <div><strong>Do you have a script or just an idea?</strong>
            <p className="film-muted">You can ignore this question and continue.</p></div>
          <button className="film-secondary" onClick={()=>{setMode('script');setAskMode(false)}}>I have a script</button>
          <button className="film-secondary" onClick={()=>{setMode('idea');setAskMode(false)}}>Just an idea</button>
          <button className="film-link" onClick={()=>setAskMode(false)}>Skip</button>
        </div>}
        <div className="film-card">
          <label htmlFor="new-film-title">Movie title</label>
          <input id="new-film-title" value={title} maxLength={150} onChange={e=>setTitle(e.target.value)}
            placeholder="Untitled movie"/>
          <div className="film-switch" role="group" aria-label="Starting material">
            <button className={mode==='idea'?'active':''} onClick={()=>setMode('idea')}>Just an idea</button>
            <button className={mode==='script'?'active':''} onClick={()=>setMode('script')}>I have a script</button>
          </div>
          {mode==='idea'?<>
            <label htmlFor="new-film-idea">Tell us what your movie is about</label>
            <textarea id="new-film-idea" rows={8} maxLength={10000} value={idea}
              onChange={e=>setIdea(e.target.value)}
              placeholder="Describe the setting, characters or what you want to happen..."/>
          </>:<>
            <label htmlFor="new-film-upload">Upload a screenplay (.txt or .fountain)</label>
            <input id="new-film-upload" type="file" accept=".txt,.fountain,text/plain"
              onChange={async e=>{
                const file=e.target.files?.[0];if(!file)return;
                if(file.size>1000000){setError('Screenplay must be under 1 MB.');return}
                setScript(await file.text());
              }}/>
            <label htmlFor="new-film-script">Or paste your screenplay</label>
            <textarea id="new-film-script" rows={10} maxLength={1000000} value={script}
              onChange={e=>setScript(e.target.value)} placeholder="INT. KITCHEN - NIGHT..."/>
            <label htmlFor="new-film-context">Story idea or notes (optional)</label>
            <textarea id="new-film-context" rows={3} maxLength={10000} value={idea}
              onChange={e=>setIdea(e.target.value)}/>
          </>}
          {canEncrypt&&<div className="film-encryption-choice">
            <label htmlFor="new-film-encrypted" className="film-encryption-label">
              <input type="checkbox" id="new-film-encrypted" checked={encryptMovie}
                onChange={e=>setEncryptMovie(e.target.checked)}/>
              Encrypt this new movie on this Windows account
            </label>
            <p className="film-hint">Encrypts this movie's screenplay and imported sources.
              The movie title remains visible. Keep your passphrase and Windows account
              credentials: both are needed for recovery.</p>
            {encryptMovie&&<>
              <label htmlFor="new-film-password">Movie passphrase</label>
              <input id="new-film-password" type="password" autoComplete="new-password"
                value={moviePassphrase} minLength={12} maxLength={256}
                onChange={e=>setMoviePassphrase(e.target.value)}/>
              <label htmlFor="new-film-password-confirm">Confirm movie passphrase</label>
              <input id="new-film-password-confirm" type="password" autoComplete="new-password"
                value={moviePassphraseAgain} minLength={12} maxLength={256}
                onChange={e=>setMoviePassphraseAgain(e.target.value)}/>
            </>}
          </div>}
          <div className="film-actions"><button className="film-secondary" onClick={()=>showWelcome()}>Back</button>
            <button className="film-primary" onClick={createMovie} disabled={busy||!title.trim()||(mode==='script'&&!script.trim())}>
              Next →</button></div>
        </div>
      </section>}

      {flow==='working'&&project&&<div className="film-page">
        <div className="film-film-head">
          <div><div className="film-eyebrow">YOUR MOVIE</div><h1>{project.title}</h1>
            <p className="film-muted">{project.idea||'Develop your story one scene at a time.'}</p>
            {project.encrypted&&<p className="film-hint" role="status">Encrypted movie.
              Film and rendering workers are unavailable until protected production is connected.</p>}</div>
          <div>
            {targetProject?.locked?<button className="film-secondary" onClick={()=>startLock('lock',targetProject)}>Lock Movie</button>
              :<button className="film-secondary" onClick={()=>startLock('protect',{id:project.id,title:project.title})}>Lock in NVP</button>}
          </div>
        </div>
        <nav className="film-steps" aria-label="Filmmaking steps">
          {PHASES.map((x,i)=><button key={x.id} onClick={()=>goPhase(x.id)}
            className={phase===x.id?'active':''} aria-current={phase===x.id?'step':undefined}>
            <span className="film-step-num">{i+1}</span>{x.label}</button>)}
        </nav>
        {phase==='script'&&<section className="film-card">
          <h2>Your screenplay (optional)</h2>
          <p className="film-muted">You do not need a script to build and film scenes. Imported dialogue and characters are planning details, not recorded performances.</p>
          <LineNumberedTextarea label="Edit screenplay" value={script} rows={19}
            maxLength={1000000} onChange={event=>setScript(event.target.value)}/>
          <div className="film-actions"><button className="film-primary" disabled={busy||!dirty}
            onClick={saveScript}>Save Screenplay</button><button className="film-secondary"
              onClick={()=>goPhase('scenes')}>Set Up Scenes →</button></div>
          {dirty&&<p className="film-hint">Unsaved screenplay changes are not part of the scene inventory yet.</p>}
        </section>}
        {phase==='scenes'&&<section className="film-card">
          <div className="film-card-head"><div><h2>Set Up Scenes</h2>
            <p className="film-muted">Choose a scene, review the setting and decide what should happen.</p></div>
            <button className="film-secondary" onClick={()=>goPhase('script')}>Edit Screenplay</button>
          </div>
          {!project.scenes?.length?<div className="film-blank-stage">
            <div className="film-stage-placeholder" aria-hidden="true">◫</div>
            <h3>Your first scene starts here</h3>
            <p>Describe a location and what happens there. Creating the editable 3D scene is a later milestone; none has been generated yet.</p>
            <button className="film-primary" onClick={()=>goPhase('script')}>Write a scene →</button>
          </div>:<div className="film-scene-layout">
            <div className="film-scene-list">
              {project.scenes.map(s=><button key={s.id}
                className={s.id===scene?.id?'selected':''} onClick={()=>chooseScene(s.id)}>
                <small>SCENE {s.number}</small><strong>{s.heading}</strong>
                <span>{s.characters.length?s.characters.join(', '):'No characters required'}</span>
              </button>)}
            </div>
            <div className="film-scene-details">
              <div className="film-stage-placeholder" aria-label="3D scene not generated">Scene preview not generated</div>
              <h3>{scene?.heading}</h3>
              <p className="film-muted">Location and time come from the script header. Confirm season, weather, props and what moves or happens.</p>
              <div className="film-script-excerpt">{scene?.text}</div>
              <div className="film-chip-row">{scene?.characters.map(c=><span key={c}>{c}</span>)}
                {!scene?.characters.length&&<span>Actor-free scenes welcome</span>}</div>
              <button className="film-secondary" onClick={()=>goPhase('film')}>Go to Filming →</button>
            </div>
          </div>}
        </section>}
        {phase==='film'&&<section className="film-card">
          <h2>Film Scenes</h2>
          <p className="film-muted">Direct what happens. Three familiar views are suggested, but filming should preserve the full performance data so you can change framing later.</p>
          <div className="film-coverage">{['Wide shot','Medium shot','Close-up'].map(v=><div key={v}>
            <div className="film-coverage-preview">No footage recorded</div><strong>{v}</strong>
          </div>)}</div>
          {scene&&<div className="film-actions"><button className="film-secondary" disabled={busy||project.encrypted}
            title={project.encrypted?'Protected workers not yet integrated':undefined}
            onClick={()=>suggestShots(scene)}>Save Shot Suggestions</button></div>}
          <p role="status" className="film-hint">Production capture is not connected to this filmmaker screen yet. These are suggestions, not recorded film.</p>
        </section>}
        {phase==='edit'&&<section className="film-card">
          <h2>Edit Film</h2>
          <p className="film-muted">Editing opens in a separate Post-Production window so the scene workspace stays dedicated to directing.</p>
          <a className="film-primary film-open-editor" href={postUrl} target="_blank" rel="noopener noreferrer">Open Post-Production Window ↗</a>
          <p className="film-hint">The editorial timeline will be integrated in G07. Existing original Takes are never edited by opening this window.</p>
        </section>}
        {phase==='export'&&<section className="film-card">
          <h2>Export Film</h2>
          <p className="film-muted">A finished presentation will be generated here from approved Takes and editing decisions.</p>
          <button className="film-primary" disabled>Export unavailable until filming and editing are connected</button>
          <p className="film-hint">No render, movie, or Presentation Package has been created by this screen.</p>
        </section>}
      </div>}
      {lockTarget&&<div className="film-modal-backdrop" role="dialog" aria-modal="true"
        aria-labelledby="film-lock-title" onKeyDown={keepDialogFocus}>
        <form className="film-modal" onSubmit={lockAction==='unlock'?unlockMovie:protectOrRelock}>
          <h2 id="film-lock-title">{lockAction==='unlock'?'Unlock Movie':lockAction==='protect'?'Lock in NVP':'Lock Movie'}</h2>
          <p className="film-muted">{lockTarget.title}</p>
          {lockAction!=='lock'&&<>
            <label htmlFor="film-passphrase">Movie passphrase (at least 12 characters)</label>
            <input ref={lockFocus} id="film-passphrase" type="password" minLength={12} maxLength={256}
              autoComplete="off" value={passphrase} onChange={e=>setPassphrase(e.target.value)} required/>
            {lockAction==='protect'&&<>
              <label htmlFor="film-passphrase-again">Confirm passphrase</label>
              <input id="film-passphrase-again" type="password" minLength={12} maxLength={256}
                autoComplete="off" value={confirmPhrase} onChange={e=>setConfirmPhrase(e.target.value)} required/>
            </>}
          </>}
          <p className="film-hint">This only restricts opening the movie in NVP. It does not encrypt its SQLite data, OpenUSD, original audio or backups. Other software under your Windows account can still read the files. There is no passphrase recovery.</p>
          <div className="film-actions">
            <button type="button" ref={lockAction==='lock'?lockFocus:null} className="film-secondary" onClick={()=>{setLockTarget(null);setPassphrase('');setError('')}}>Cancel</button>
            <button className="film-primary" disabled={busy} type="submit">
              {lockAction==='unlock'?'Unlock':lockAction==='protect'?'Protect':'Lock Now'}</button>
          </div>
          {error&&<p role="alert">{error}</p>}
        </form>
      </div>}
    </main>
  </div>;
}
