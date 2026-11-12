import React, {useEffect,useState} from 'react';
import './director-screenplay-assistant.css';

async function request(url,method='GET',payload) {
  const response=await fetch(url,{
    method,credentials:'same-origin',
    headers:{'Content-Type':'application/json','x-nvp-director':'1'},
    ...(payload===undefined?{}:{body:JSON.stringify(payload)}),
  });
  if(!response.ok) {
    const error=await response.json().catch(()=>({}));
    throw new Error(typeof error.detail==='string'?error.detail:
      'Writing assistance is unavailable right now.');
  }
  return response.json();
}

export default function DirectorScreenplayAssistant({movie,unsaved,onApproved}) {
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/preproduction';
  const [direction,setDirection]=useState('');
  const [draft,setDraft]=useState(null);
  const [edited,setEdited]=useState('');
  const [busy,setBusy]=useState(false);
  const [available,setAvailable]=useState(false);
  const [luState,setLuState]=useState('disconnected');
  const [luMessage,setLuMessage]=useState('Lu Workspace is not connected.');
  const [notice,setNotice]=useState('');
  const [error,setError]=useState('');

  useEffect(()=>{
    let active=true;
    request(base).then(data=>{
      if(!active)return;
      const recent=(data.screenplay_drafts||[]).find(x=>x.status==='proposed'&&!x.stale);
      if(recent){setDraft(recent);setEdited(recent.content);}
    }).catch(()=>{});
    const checkLu=()=>{
      if(movie.encrypted){
        setAvailable(false);
        setLuState('private_unavailable');
        setLuMessage('Private-film Lu integration is not yet authorized.');
        return;
      }
      request('/api/projects/'+encodeURIComponent(movie.id)+'/lu/status')
        .then(result=>{
          if(!active)return;
          setLuState(result.state);
          setLuMessage(result.message||'Lu Workspace is unavailable.');
          setAvailable(result.state==='ready');
        }).catch(()=>{
          if(!active)return;
          setAvailable(false);setLuState('disconnected');
          setLuMessage('Lu Workspace cannot be reached.');
        });
    };
    checkLu();
    const interval=window.setInterval(checkLu,15000);
    window.addEventListener('focus',checkLu);
    return ()=>{
      active=false;
      window.clearInterval(interval);
      window.removeEventListener('focus',checkLu);
    };
  },[base,movie.revision]);

  async function perform(fn) {
    if(busy)return;
    setBusy(true);setError('');setNotice('');
    try{await fn()}catch(err){setError(err.message)}
    finally{setBusy(false)}
  }
  function generate() {
    perform(async()=>{
      const library=await request(base+'/screenplay/suggestions','POST',{direction});
      const newest=library.screenplay_drafts?.find(x=>x.status==='proposed'&&!x.stale);
      if(!newest)throw new Error('No screenplay was proposed. You can keep writing manually.');
      setDraft(newest);
      setEdited(newest.content);
      setNotice('A screenplay draft is ready. Edit it, approve it or decline it.');
    });
  }
  function decide(decision) {
    if(!draft)return;
    perform(async()=>{
      await request(base+'/screenplay/'+draft.id+'/decision','POST',{
        decision,expected_screenplay_revision:movie.revision,
        ...(decision==='accept'?{edited_text:edited}:{}),
      });
      setDraft(null);setEdited('');
      if(decision==='accept'){
        const latest=await request('/api/projects/'+encodeURIComponent(movie.id)+
          (movie.encrypted?'/live':''));
        onApproved(latest);
        setNotice('Your approved screenplay is saved. You can edit it whenever you like.');
      }else{
        setNotice('Draft declined. Your movie has not changed.');
      }
    });
  }
  return <section className="director-screenplay-helper" aria-label="Screenplay writing assistant">
    <h3>Work on your screenplay together</h3>
    <p className="film-muted">You decide the story. Ask for a simple first scene,
      a revision or ideas for what comes next. Suggestions never replace your
      writing without your approval.</p>
    {error&&<p className="director-screenplay-error" role="alert">{error}</p>}
    {notice&&<p className="director-screenplay-notice" role="status">{notice}</p>}
    {busy&&luState==='ready'&&<button type="button" className="film-secondary"
      onClick={async()=>{
        try{
          const result=await request('/api/projects/'+encodeURIComponent(movie.id)+
            '/lu/cancel','POST');
          if(result.state==='cancellation_requested')
            setNotice('Cancellation requested from Lu; completion is not yet confirmed.');
        }catch(err){setError(err.message);}
      }}>Request Lu cancellation</button>}
    {!draft?<>
      <label htmlFor="director-writing-direction">What would you like help writing?</label>
      <textarea id="director-writing-direction" rows={3} maxLength={1200}
        placeholder="An opening scene in a quiet mountain valley, with no dialogue…"
        value={direction} onChange={e=>setDirection(e.target.value)}/>
      <div className="film-actions"><button className="film-secondary"
        onClick={generate} disabled={busy||!available||unsaved}>
        {busy?'Lu is writing a draft…':'Ask Lu for a screenplay draft'}
      </button></div>
      {!available&&<p className="film-hint" role="status">{luMessage}
        {' '}You can continue writing and saving your screenplay yourself.</p>}
      {unsaved&&<p className="film-hint">Save your current screenplay changes before
        requesting a new draft.</p>}
    </>:<>
      <h4>Screenplay suggestion · needs your review</h4>
      <label htmlFor="director-draft-screenplay">Review and edit this draft</label>
      <textarea id="director-draft-screenplay" rows={14} maxLength={1_000_000}
        value={edited} onChange={e=>setEdited(e.target.value)}/>
      {movie.screenplay&&<p className="film-hint">Approving this draft replaces the
        current screenplay. Your earlier screenplay version is preserved.</p>}
      <div className="film-actions">
        <button className="film-secondary" onClick={()=>decide('discard')}
          disabled={busy}>Decline Draft</button>
        <button className="film-primary" onClick={()=>decide('accept')}
          disabled={busy||!edited.trim()}>Approve and Use Screenplay</button>
      </div>
    </>}
  </section>;
}
