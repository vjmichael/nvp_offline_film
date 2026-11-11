import React, {useEffect, useMemo, useState} from 'react';
import './director-scene-library.css';
import DirectorWorldStage from './DirectorWorldStage.jsx';

// Only creative details belong in a filmmaking screen. Project authorization,
// source hashes, model selection and production worker decisions belong to NVP.
const FIELDS = [
  ['description','What is this scene about?'],
  ['location','Where does it take place?'],
  ['time_of_day','Time of day'],
  ['era','Period or era'],
  ['season','Season'],
  ['weather','Weather (if it matters)'],
  ['action','What happens in the scene?'],
  ['performers','Characters or animals (optional)'],
  ['dialogue','Dialogue notes (optional)'],
  ['director_note','Other director notes'],
];
const HEADERS = {
  character:'Character',location:'Location',time_of_day:'Time of day',
  era:'Period',season:'Season',weather:'Weather',wardrobe:'Wardrobe',
  prop:'Prop',action:'Action',dialogue:'Dialogue',continuity:'Continuity',
  director_note:'Director note',
};
const DIRECTOR = {'x-nvp-director':'1'};
const emptyNotes=()=>Object.fromEntries(FIELDS.map(([key])=>[key,'']));

async function action(url,method='GET',data) {
  const response=await fetch(url,{
    method,credentials:'same-origin',
    headers:{'Content-Type':'application/json',...DIRECTOR},
    ...(data===undefined?{}:{body:JSON.stringify(data)}),
  });
  if(!response.ok) {
    const err=await response.json().catch(()=>({}));
    const detail=typeof err.detail==='string'?err.detail:
      'Your scene could not be saved. Please try again.';
    throw new Error(detail);
  }
  return response.json();
}

function People({cast}) {
  return <div className="director-scene-chips">
    {cast?.length?cast.map(person=><span key={person.actor_id||person.source_cue}>
      {person.name}{person.needs_review?' · speaker to identify':''}</span>):
      <span>No performers required</span>}
  </div>;
}

function BibleGroup({title,items,render}) {
  return <section className="director-bible-group" aria-label={title}>
    <h4>{title}</h4>
    {items.length?<ul>{items.map((item,index)=><li key={item.actor_id||item.name||index}>
      {render(item)}
    </li>)}</ul>:<p className="film-muted">Not specified yet.</p>}
  </section>;
}

export default function DirectorSceneLibrary({movie,onScript,onFilm}) {
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/preproduction';
  const [data,setData]=useState(null);
  const [current,setCurrent]=useState('');
  const [notes,setNotes]=useState(emptyNotes);
  const [quickAnswer,setQuickAnswer]=useState('');
  const [edits,setEdits]=useState({});
  const [speakerChoices,setSpeakerChoices]=useState({});
  const [speakerNames,setSpeakerNames]=useState({});
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const [aiReady,setAiReady]=useState(false);

  useEffect(()=>{
    const controller=new AbortController();
    let alive=true;
    action(base).then(value=>{
      if(alive)setData(value);
    }).catch(err=>{if(alive)setError(err.message)});
    // NVP selects the existing local model internally. The filmmaker never
    // needs to choose an endpoint, model file or generation backend.
    action('/api/creative/models').then(result=>{
      if(alive)setAiReady(result.state==='available');
    }).catch(()=>{if(alive)setAiReady(false)});
    return ()=>{alive=false;controller.abort()};
  },[base,movie.revision]);

  const selected = useMemo(()=>data?.scenes?.find(x=>x.id===current)||
    data?.scenes?.[0]||null,[data,current]);
  useEffect(()=>{
    if(!selected)return;
    setNotes({...emptyNotes(),...selected.notes});
    setQuickAnswer('');
    setEdits({});
    setSpeakerChoices({});
    setSpeakerNames({});
  },[selected?.id,selected?.notes_revision]);

  async function update(work,success) {
    if(busy)return;
    setBusy(true);setError('');setMessage('');
    try{
      const changed=await work();
      if(changed?.scenes)setData(changed);
      if(success)setMessage(success);
    }catch(err){setError(err.message)}
    finally{setBusy(false)}
  }

  function chooseScene(scene) {
    if(!selected||selected.id===scene.id)return;
    if(JSON.stringify(notes)!==JSON.stringify({...emptyNotes(),...selected.notes}) &&
        !window.confirm('This scene has unsaved details. Leave without saving?'))return;
    setCurrent(scene.id);
  }

  function saveQuestionAnswer() {
    if(!selected||!quickAnswer.trim())return;
    const prompt=selected.questions?.[0]||'';
    const field=prompt.startsWith('Where')?'location':'action';
    const updated={...notes,[field]:quickAnswer.trim()};
    update(async()=>{
      const result=await action(base+'/scenes/'+encodeURIComponent(selected.id),
        'PUT',{notes:updated,expected_notes_revision:selected.notes_revision,
          expected_screenplay_revision:data.screenplay_revision});
      setQuickAnswer('');
      return result;
    },'Your answer has been saved with this scene.');
  }
  function save() {
    if(!selected)return;
    update(()=>action(base+'/scenes/'+encodeURIComponent(selected.id),'PUT',{
      notes,expected_notes_revision:selected.notes_revision,
      expected_screenplay_revision:data.screenplay_revision,
    }),'Scene details saved. Your source and earlier choices are preserved.');
  }
  function addScene() {
    update(()=>action(base+'/scenes','POST',{
      expected_screenplay_revision:data.screenplay_revision
    }),'A new scene was added. You can decide what happens in it.');
  }
  function askAI() {
    if(!selected)return;
    update(()=>action(base+'/scenes/'+encodeURIComponent(selected.id)+'/suggestions','POST'),
      'Here are some ideas to review. Nothing has been added to your film without your approval.');
  }
  function restoreNotes(revision) {
    if(!selected)return;
    if(!window.confirm('Restore an earlier version of your scene details? Your current version will remain in the history.'))return;
    update(()=>action(base+'/scenes/'+encodeURIComponent(selected.id)+'/restore',
      'POST',{
        source_revision:revision,
        expected_notes_revision:selected.notes_revision,
        expected_screenplay_revision:data.screenplay_revision
      }),'Earlier scene details restored. Your other versions are preserved.');
  }
  function identifySpeaker(cue,defaultActorId=null) {
    const actor=speakerChoices[cue]||defaultActorId||'new';
    const payload={
      source_cue:cue,
      expected_screenplay_revision:data.screenplay_revision,
      ...(actor==='new'?{new_name:(speakerNames[cue]||'').trim()}:
        {actor_id:actor}),
    };
    update(()=>action(base+'/scenes/'+encodeURIComponent(selected.id)+'/speakers',
      'POST',payload),
      'Speaker linked to the character you chose.');
  }
  function review(proposal,decision) {
    update(()=>action(base+'/suggestions/'+proposal.id+'/decision','POST',{
      decision,expected_screenplay_revision:data.screenplay_revision,
      ...(decision==='accept'&&edits[proposal.id]!==undefined
        ?{approved_value:edits[proposal.id]}:{}),
    }),decision==='accept'?'Added to your approved scene notes.':'Suggestion declined.');
  }
  if(!data) return <section className="film-card" aria-label="Scene Library">
    <h2>Scene Library</h2>
    {error?<p role="alert" className="director-error">{error}</p>:
      <p role="status" className="film-muted">Opening your scenes…</p>}
  </section>;

  const facts=data.bible?.facts||[];
  const sceneFacts=facts.filter(item=>item.scene_id===selected?.id);
  const hasNotes=selected&&JSON.stringify(notes)!==
    JSON.stringify({...emptyNotes(),...selected.notes});

  return <section className="film-card director-library" aria-label="Scene Library">
    <div className="film-card-head">
      <div>
        <div className="film-eyebrow">YOUR SCENE LIBRARY</div>
        <h2>Set Up Scenes</h2>
        <p className="film-muted">Build your film scene by scene. You make the creative decisions.</p>
      </div>
      <button className="film-secondary" onClick={onScript}>Edit Screenplay</button>
    </div>
    {data.title_conflict&&<div className="director-review-alert" role="status">
      Your script is titled <strong>{data.title_conflict.script_title}</strong>, while your
      movie is named <strong>{data.title_conflict.movie_title}</strong>. Both are preserved.
      You can review the title when you're ready.
    </div>}
    {error&&<div className="director-error" role="alert">{error}</div>}
    {message&&<div className="director-message" role="status">{message}</div>}
    <div className="director-library-grid">
      <div className="director-library-sidebar">
        <h3>Scenes</h3>
        <div className="director-scene-buttons" role="group" aria-label="Movie scenes">
          {(data.scenes||[]).map(scene=><button
            key={scene.id} aria-pressed={selected?.id===scene.id}
            className={selected?.id===scene.id?'selected':''}
            onClick={()=>chooseScene(scene)}>
            <small>SCENE {String(scene.number).padStart(2,'0')}</small>
            <strong>{scene.heading}</strong>
            <span>{scene.location||scene.notes?.location||'Location not chosen'}</span>
          </button>)}
        </div>
        {data.mode==='idea'&&<button className="film-secondary director-add-scene"
          onClick={addScene} disabled={busy}>+ Add next scene</button>}
        <details className="director-bible">
          <summary>Production Bible</summary>
          <p className="film-muted">The creative details that guide your film.</p>
          <BibleGroup title="Characters and animals" items={data.bible.cast||[]}
            render={x=>x.name}/>
          <BibleGroup title="Locations" items={data.bible.locations||[]}
            render={x=>x.name}/>
          <BibleGroup title="Approved props" items={data.bible.props||[]}
            render={x=>x.name}/>
          <BibleGroup title="Scene settings" items={data.bible.scene_settings||[]}
            render={x=><><strong>{x.scene_name}</strong>: {[
              x.location,x.time_of_day,x.era,x.season,x.weather
            ].filter(Boolean).join(' · ')||'Not specified'}</>}/>
          <BibleGroup title="Continuity notes" items={data.bible.continuity||[]}
            render={x=><>{x.origin==='review_suggestion'?'To review: ':''}{x.note}</>}/>
          <BibleGroup title="Earlier approved story details"
            items={data.bible.approved_story||[]}
            render={x=><><strong>{x.name}</strong> · {x.kind}
              {x.facts?.length>0&&<div className="director-bible-facts">
                {x.facts.map((fact,index)=><span key={index}>
                  {fact.name.replaceAll('_',' ')}: {fact.value}
                </span>)}
              </div>}</>}/>
        </details>
      </div>
      {selected&&<div className="director-scene-workspace">
        <DirectorWorldStage
          key={movie.id+':'+selected.id+':'+selected.notes_revision+':'+movie.revision}
          movie={movie} scene={selected}/>
        <h3>{selected.heading}</h3>
        <p className="film-muted">{selected.location?
          <>From the script: <strong>{selected.location}</strong>
            {selected.time_of_day?' · '+selected.time_of_day:''}</>:
          'You can choose the location and describe the scene below.'}</p>
        <People cast={selected.cast}/>
        {selected.cast?.some(person=>person.needs_review)&&
          <section className="director-speaker-review" aria-label="Identify speakers">
            <h4>Who is speaking?</h4>
            <p className="film-muted">A script label may refer to different
              people in different scenes. Choose the correct character.</p>
            {selected.cast.filter(person=>person.needs_review).map(person=>
              <div className="director-speaker-choice" key={person.source_cue}>
                <strong>{person.source_cue}</strong>
                <label>
                  <span>Character</span>
                  <select value={speakerChoices[person.source_cue]||'new'}
                    onChange={e=>setSpeakerChoices(s=>({
                      ...s,[person.source_cue]:e.target.value}))}>
                    <option value="new">Name a new character</option>
                    {(data.bible.cast||[]).map(actor=><option
                      key={actor.actor_id} value={actor.actor_id}>{actor.name}</option>)}
                  </select>
                </label>
                {(speakerChoices[person.source_cue]||'new')==='new'&&<label>
                  <span>Character name</span>
                  <input maxLength={100} value={speakerNames[person.source_cue]||''}
                    onChange={e=>setSpeakerNames(s=>({
                      ...s,[person.source_cue]:e.target.value}))}
                    placeholder="Give this speaker a name"/>
                </label>}
                <button className="film-secondary" disabled={busy||(
                  (speakerChoices[person.source_cue]||'new')==='new'&&
                  !speakerNames[person.source_cue]?.trim())}
                  onClick={()=>identifySpeaker(person.source_cue)}>
                  Confirm Character
                </button>
              </div>)}
          </section>}
        {selected.cast?.some(person=>person.source_cue&&!person.needs_review)&&
          <details className="director-speaker-alias">
            <summary>Connect character names across scenes</summary>
            <p className="film-muted">If the screenplay uses another name for
              the same performer, you can link it here without changing the script.</p>
            {selected.cast.filter(person=>person.source_cue&&!person.needs_review)
              .map(person=><div className="director-speaker-choice" key={person.source_cue}>
              <span>{person.source_cue}</span>
              <select aria-label={'Identity for '+person.source_cue}
                value={speakerChoices[person.source_cue]||person.actor_id}
                onChange={e=>setSpeakerChoices(x=>({
                  ...x,[person.source_cue]:e.target.value}))}>
                <option value="new">Name a new character</option>
                {(data.bible.cast||[]).map(actor=><option
                  key={actor.actor_id} value={actor.actor_id}>{actor.name}</option>)}
              </select>
              {speakerChoices[person.source_cue]==='new'&&<input
                aria-label={'New name for '+person.source_cue}
                maxLength={100} value={speakerNames[person.source_cue]||''}
                onChange={e=>setSpeakerNames(x=>({
                  ...x,[person.source_cue]:e.target.value}))}/>}
              <button className="film-secondary" disabled={busy||(
                speakerChoices[person.source_cue]==='new'&&
                !speakerNames[person.source_cue]?.trim())}
                onClick={()=>identifySpeaker(person.source_cue,person.actor_id)}>
                Link Character</button>
            </div>)}
          </details>}
        {selected.script_excerpt&&<details className="director-script-source">
          <summary>Read the original scene</summary>
          <pre>{selected.script_excerpt}</pre>
        </details>}
        {selected.dialogue?.length>0&&<details className="director-dialogue">
          <summary>Dialogue from the script ({selected.dialogue.length})</summary>
          {selected.dialogue.map((line,index)=><blockquote key={index}>
            <strong>{line.speaker}</strong>: {line.line}
            <small> Script line {line.line_number}</small>
          </blockquote>)}
        </details>}
        <div className="director-scene-form">
          <h4>Your scene details</h4>
          <p className="film-muted">Fill in what matters. You can leave the rest blank.</p>
          <div className="director-note-fields">
            {FIELDS.map(([field,label])=><label key={field}>
              <span>{label}</span>
              {field==='description'||field==='action'||field==='dialogue'||
                field==='director_note'?
                <textarea rows={3} maxLength={1500} value={notes[field]||''}
                  onChange={e=>setNotes(n=>({...n,[field]:e.target.value}))}/>:
                <input maxLength={1500} value={notes[field]||''}
                  onChange={e=>setNotes(n=>({...n,[field]:e.target.value}))}/>}
            </label>)}
          </div>
          <div className="film-actions">
            <button className="film-primary" disabled={busy||!hasNotes}
              onClick={save}>Save Scene Details</button>
          </div>
          {selected.notes_history?.length>1&&<details className="director-note-history">
            <summary>Earlier scene details</summary>
            <p className="film-muted">Choose an earlier version if you want to
              revisit a creative decision. Restoring it preserves the current version.</p>
            {selected.notes_history.slice(1).map(version=><div
              className="director-history-row" key={version.revision}>
              <span>Version {version.revision}: {version.notes.description||
                version.notes.location||version.notes.action||'Scene notes'}</span>
              <button className="film-secondary" disabled={busy}
                onClick={()=>restoreNotes(version.revision)}>Restore</button>
            </div>)}
          </details>}
        </div>
        {sceneFacts.length>0&&<section className="director-approved-details">
          <h4>Approved scene details</h4>
          <ul>{sceneFacts.map((fact,index)=><li key={index}>
            <strong>{HEADERS[fact.category]||'Note'}:</strong> {fact.value}
          </li>)}</ul>
        </section>}
        <section className="director-assistant" aria-label="Scene assistant">
          <h4>Ideas for this scene</h4>
          {selected.questions?.map(question=><p key={question}
            className="director-assistant-question">{question}</p>)}
          {selected.questions?.length>0&&<div className="director-quick-answer">
            <label htmlFor="director-context-answer">Tell me about it</label>
            <textarea id="director-context-answer" rows={2} maxLength={1500}
              value={quickAnswer} placeholder="Your scene, in your own words…"
              onChange={e=>setQuickAnswer(e.target.value)}/>
            <div className="film-actions"><button className="film-secondary"
              disabled={busy||!quickAnswer.trim()} onClick={saveQuestionAnswer}>
              Save Answer</button></div>
          </div>}
          <p className="film-muted">I can suggest details based on your screenplay
            and notes. You choose what belongs in your movie.</p>
          <button className="film-secondary" onClick={askAI} disabled={busy||!aiReady}>
            {busy?'Working on your scene…':'Ask AI for ideas'}</button>
          {!aiReady&&<p className="film-hint">AI assistance is unavailable right now.
            Your scenes can still be edited manually.</p>}
          {selected.proposals?.filter(p=>!p.stale).map(p=>
            <article className="director-proposal" key={p.id}>
              <div className="director-proposal-head">
                <strong>{HEADERS[p.category]||'Scene idea'}</strong>
                <span>{p.status==='accepted'?'Approved':
                  p.status==='rejected'?'Declined':'Suggested · awaiting your decision'}</span>
              </div>
              <p>{p.approved_value||p.value}</p>
              {p.evidence_quote&&<p className="director-proposal-source">
                From script line {p.evidence_line}: “{p.evidence_quote}”</p>}
              {p.status==='proposed'&&<>
                <label className="director-adjust-label">
                  Change this idea (optional)
                  <input value={edits[p.id]===undefined?p.value:edits[p.id]}
                    maxLength={1500} onChange={e=>setEdits(s=>({...s,[p.id]:e.target.value}))}/>
                </label>
                <div className="film-actions">
                  <button className="film-secondary" disabled={busy}
                    onClick={()=>review(p,'reject')}>Decline</button>
                  <button className="film-primary" disabled={busy}
                    onClick={()=>review(p,'accept')}>Approve</button>
                </div>
              </>}
            </article>)}
          {selected.proposals?.some(p=>p.stale)&&<p className="film-hint">
            Older suggestions were set aside because this scene changed.
            Your approved earlier work is preserved in its history.</p>}
        </section>
        <div className="film-actions"><button className="film-secondary" onClick={onFilm}>
          Continue to Film Scenes →</button></div>
      </div>}
    </div>
  </section>;
}
