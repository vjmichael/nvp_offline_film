import React,{useEffect,useState} from 'react';

// A plain filmmaker scene library: SOURCE CUES are not approved casting,
// locations are screenplay headings, and props require creator-linked Bible
// entities. Local AI proposals remain unapproved and never auto-write assets.
export default function SceneLibraryPanel({
  project,api,onEditScreenplay,onOpenSceneTool,
  modelId='',modelPort='1234'
}){
  const [library,setLibrary]=useState(null);
  const [sceneId,setSceneId]=useState('');
  const [proposal,setProposal]=useState(null);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState('');

  useEffect(()=>{
    let alive=true;
    setLibrary(null);setProposal(null);setError('');
    api('/projects/'+project.id+'/scene-library').then(data=>{
      if(!alive)return;
      if(data?.format!=='nvp.plan03.scene_library.v1'||
         data.project_id!==project.id||
         data.project_revision!==project.revision)
        throw Error('Scene Library does not match the saved screenplay revision');
      setLibrary(data);
      setSceneId(previous=>data.scenes.some(s=>s.scene_id===previous)?
        previous:(data.scenes[0]?.scene_id||''));
    }).catch(err=>{if(alive)setError(err.message)});
    return()=>{alive=false};
  },[api,project.id,project.revision]);

  const scene=library?.scenes.find(s=>s.scene_id===sceneId);
  async function suggestBreakdown(){
    if(!scene||!modelId||working)return;
    setWorking(true);setError('');setProposal(null);
    try{
      const reply=await api(
        '/projects/'+project.id+'/scenes/'+encodeURIComponent(scene.scene_id)+'/ai-breakdown',
        'POST',{model_id:modelId,model_port:modelPort?Number(modelPort):null,
          expected_revision:library.project_revision});
      if(reply?.format!=='nvp.plan03.ai_scene_breakdown_proposal.v1'||
         reply.status!=='UNAPPROVED_PROPOSAL'||
         reply.creator_approval_granted!==false||
         reply.project_revision!==library.project_revision||
         reply.source_scene_sha256!==scene.source_scene_sha256)
        throw Error('Model breakdown does not match this unapproved source scene');
      setProposal(reply);
    }catch(err){setError(err.message)}
    finally{setWorking(false)}
  }

  return <section className="scene-library" aria-label="Scene Library">
    <header className="scene-library-heading">
      <div>
        <h2>Scenes in your movie</h2>
        <p className="muted">Choose a scene to see who's in it, where it happens,
          and which props you have actually assigned. Nothing here creates footage.</p>
      </div>
      <button className="secondary" onClick={onEditScreenplay}>Edit screenplay</button>
    </header>
    {error&&<p role="alert" className="alert">{error}</p>}
    {!library&&<p role="status">Reading saved screenplay scenes…</p>}
    {library&&library.scenes.length===0&&<div className="card">
      <h3>Your scene library is empty</h3>
      <p>Add a scene heading to your screenplay, such as INT. KITCHEN - DAY,
        then return here to see its characters, location and props.</p>
      <button className="primary" onClick={onEditScreenplay}>Write the first scene</button>
    </div>}
    {library?.scenes.length>0&&<div className="scene-library-layout">
      <nav className="scene-library-list" aria-label="Select a scene">
        {library.scenes.map(s=><button key={s.scene_id}
          type="button" className={'scene-library-item'+
            (s.scene_id===sceneId?' chosen':'')}
          aria-current={s.scene_id===sceneId?'true':undefined}
          onClick={()=>{setSceneId(s.scene_id);setProposal(null);setError('')}}>
          <span className="scene-number">Scene {s.number}</span>
          <strong>{s.heading}</strong>
          <span className="fineprint">{s.screenplay_character_cues.length} character cues
            · {s.props.length} assigned props</span>
        </button>)}
      </nav>
      {scene&&<div className="scene-library-detail">
        <div className="scene-library-detail-header">
          <div>
            <div className="kicker">SCENE {scene.number} · SCRIPT LINES {scene.start_line}–{scene.end_line}</div>
            <h3>{scene.heading}</h3>
          </div>
          <p className="fineprint">Saved screenplay revision {library.project_revision}</p>
        </div>
        <div className="scene-library-facts">
          <section className="card" aria-label="Scene actors">
            <h4>Actors and characters</h4>
            <p>{scene.screenplay_character_cues.join(', ')||
              'No explicit character cues yet'}</p>
            <p className="fineprint">Characters mentioned in screenplay.
              Approved casting: {scene.actors.map(a=>a.name).join(', ')||'Not assigned'}</p>
          </section>
          <section className="card" aria-label="Scene locations">
            <h4>Location</h4>
            <p>{scene.location_from_heading}</p>
            <p className="fineprint">Source: screenplay heading.
              Approved set: {scene.locations.map(x=>x.name).join(', ')||'Not assigned'}</p>
          </section>
          <section className="card" aria-label="Scene props">
            <h4>Props</h4>
            <p>{scene.props.map(x=>x.name).join(', ')||'Not yet assigned'}</p>
            <p className="fineprint">Only creator-linked, source-current Story Bible props appear here.</p>
          </section>
        </div>
        {!!scene.stale_links.length&&<p role="status" className="notice">
          {scene.stale_links.length} Story Bible scene link(s) require review
          because this scene's screenplay text changed.</p>}
        <details>
          <summary>Read this scene's screenplay</summary>
          <pre className="scene-library-script">{scene.screenplay_text}</pre>
        </details>
        <div className="actions">
          <button className="primary" onClick={()=>onOpenSceneTool('stage',scene.scene_id)}>
            Work on this scene
          </button>
          <button className="secondary" onClick={()=>onOpenSceneTool('scenes',scene.scene_id)}>
            Plan shots
          </button>
          <button className="secondary" onClick={()=>onOpenSceneTool('bible',scene.scene_id)}>
            Assign actors, locations and props
          </button>
        </div>
        <details className="scene-ai-breakdown">
          <summary>Ask a local AI for scene breakdown ideas (optional)</summary>
          <p className="muted">AI suggestions are not production facts.
            Review them before manually assigning actors, locations or props.</p>
          {!modelId?<p className="fineprint">
            No local model selected. You can still plan the movie manually;
            connect a model under Advanced Studio → Writing assistant.</p>:
          <button disabled={working} onClick={suggestBreakdown}>
            {working?'Generating proposal…':'Suggest actors, locations and props'}
          </button>}
          {proposal?.scene_id===scene.scene_id&&<div className="scene-ai-proposal"
            aria-label="Unapproved AI scene suggestions">
            <h4>Unapproved suggestions — nothing has been changed</h4>
            {['actors','locations','props'].map(category=>
              <div key={category}><strong>{category[0].toUpperCase()+category.slice(1)}</strong>
                <p>{proposal.suggestions[category].join(', ')||'No suggestions'}</p>
              </div>)}
            <p className="fineprint">Add any accurate suggestions through
              the Story Bible. Generating this proposal never grants permission
              to publish a Digital Take or launch a renderer.</p>
          </div>}
        </details>
      </div>}
    </div>}
  </section>;
}
