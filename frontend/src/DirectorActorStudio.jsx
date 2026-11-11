import React,{useEffect,useRef,useState} from 'react';
import './director-actor-studio.css';

const fmt=n=>Number(n||0).toFixed(2);
const movements={
  neutral:'Still and composed',
  natural:'Natural movement',
  restrained:'Restrained, subtle movement',
  energetic:'Energetic performance',
  heavy:'Slow, weighted movement'};
const emotions={neutral:'Neutral',joy:'Joy',sadness:'Sadness',
  anger:'Anger',fear:'Fear',surprise:'Surprise',focus:'Focused'};
const hairStyles={bald:'No hair',short:'Short',medium:'Medium',long:'Long'};
const voiceStates={unreviewed:'Needs your review',
  approved:'Approved original performance',
  rejected:'Do not use this delivery for facial animation'};

async function perform(url,method='GET',data,signal){
  const response=await fetch(url,{
    method,signal,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(data===undefined?{}:{body:JSON.stringify(data)})});
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw new Error(typeof error.detail==='string'?error.detail:
      'That acting change could not be saved. Your earlier directions remain.');
  }
  return response.json();
}

function PanelColor({label,value,onChange}){
  return <label className="director-actor-color">{label}
    <input type="color" value={value} onChange={e=>onChange(e.target.value)}/>
  </label>;
}

export default function DirectorActorStudio({movie,takeId}){
  const base='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/production/actors/'+encodeURIComponent(takeId||'');
  const [data,setData]=useState(null);
  const [actorId,setActorId]=useState('');
  const [acting,setActing]=useState(null);
  const [appearance,setAppearance]=useState(null);
  const [voiceClip,setVoiceClip]=useState('');
  const [delivery,setDelivery]=useState('');
  const [dialogueNote,setDialogueNote]=useState('');
  const [voiceUrl,setVoiceUrl]=useState('');
  const [previewUrl,setPreviewUrl]=useState('');
  const [sceneTime,setSceneTime]=useState('0');
  const [busy,setBusy]=useState(false);
  const [previewBusy,setPreviewBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [showHistory,setShowHistory]=useState(false);
  const alive=useRef(true);
  const requestRef=useRef(0);
  const voiceRequest=useRef(null);

  useEffect(()=>{
    let on=true;alive.current=true;
    setData(null);setActorId('');setError('');setNotice('');
    setVoiceUrl('');setPreviewUrl('');
    if(!takeId)return()=>{on=false;alive.current=false};
    perform(base).then(result=>{if(on)setData(result)})
      .catch(e=>{if(on)setError(e.message)});
    return()=>{on=false;alive.current=false;
      requestRef.current++;
      voiceRequest.current?.abort();
    };
  },[base,takeId]);

  useEffect(()=>{
    if(!data)return;
    const cast=data.draft.actors||[];
    if(!cast.some(a=>a.actor_id===actorId)){
      setActorId(cast[0]?.actor_id||'');
    }
  },[data?.revision,takeId]);

  const performer=(data?.draft?.actors||[]).find(a=>a.actor_id===actorId)||null;
  useEffect(()=>{
    if(!performer)return;
    setActing({movement:performer.movement,emotion:performer.emotion,
      expression_strength:performer.expression_strength,
      gait_strength:performer.gait_strength,blink_rate:performer.blink_rate,
      director_note:performer.director_note});
    setAppearance({skin_color:performer.skin_color,
      hair_color:performer.hair_color,
      hair:performer.hair,wardrobe_color:performer.wardrobe_color,
      eye_color:performer.eye_color,
      height_scale:performer.height_scale,
      shoulder_width:performer.shoulder_width});
    const clip=performer.voice_clips?.[0];
    setVoiceClip(clip?.clip_id||'');
  },[data?.revision,actorId]);

  const selectedVoice=performer?.voice_clips?.find(
    v=>v.clip_id===voiceClip)||null;
  useEffect(()=>{
    setDelivery(selectedVoice?.delivery||'');
    setDialogueNote(selectedVoice?.dialogue_note||'');
  },[selectedVoice?.clip_id,data?.revision]);

  // Object URL lifecycle: user-supplied native recordings stay in memory
  // only while this film and selected speaker are visible.
  useEffect(()=>()=>{if(voiceUrl)URL.revokeObjectURL(voiceUrl)},[voiceUrl]);
  useEffect(()=>()=>{if(previewUrl)URL.revokeObjectURL(previewUrl)},[previewUrl]);

  useEffect(()=>{
    if(!data)return;
    let cancelled=false;
    const id=++requestRef.current;
    const handler=window.setTimeout(async()=>{
      setPreviewBusy(true);
      try{
        const response=await fetch(base+'/preview?seconds='+
          encodeURIComponent(sceneTime),{
            credentials:'same-origin',headers:{'x-nvp-director':'1'}});
        if(!response.ok)throw new Error('Actor preview could not be prepared');
        const blob=await response.blob();
        if(cancelled||id!==requestRef.current)return;
        setPreviewUrl(URL.createObjectURL(blob));
      }catch(_){
        if(!cancelled&&id===requestRef.current)setPreviewUrl('');
      }finally{
        if(!cancelled&&id===requestRef.current)setPreviewBusy(false);
      }
    },160);
    return()=>{cancelled=true;window.clearTimeout(handler)};
  },[base,data?.revision,sceneTime]);

  async function save(operation,details,success){
    if(busy||!actorId||!data)return;
    setBusy(true);setError('');setNotice('');
    try{
      const result=await perform(base+'/change','POST',{
        expected_revision:data.revision,actor_id:actorId,operation,details});
      if(alive.current){setData(result);setNotice(success)}
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  async function approve(){
    if(!data||busy||data.revision===0)return;
    if(!window.confirm('Approve this performance for the film? Your recorded Take and original voices remain unchanged.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const result=await perform(base+'/approve','POST',{
        expected_revision:data.revision});
      if(alive.current){setData(result);setNotice(
        'Your character performance is approved for the finished movie.')}
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  async function restore(version){
    if(!data||busy||!window.confirm(
      'Restore these earlier acting directions? Your current version and original Takes will be preserved.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const result=await perform(base+'/restore','POST',{
        source_revision:version,expected_revision:data.revision});
      if(alive.current){setData(result);
        setNotice('Earlier acting directions restored as a new version.')}
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  async function listen(){
    if(!voiceClip||!data)return;
    voiceRequest.current?.abort();
    const controller=new AbortController();
    voiceRequest.current=controller;
    setError('');setNotice('');
    try{
      const response=await fetch(base+'/voice/'+encodeURIComponent(voiceClip),{
        credentials:'same-origin',signal:controller.signal,
        headers:{'x-nvp-director':'1'}});
      if(!response.ok)throw new Error('The original voice recording is unavailable');
      const content=await response.blob();
      if(controller.signal.aborted)return;
      setVoiceUrl(URL.createObjectURL(content));
      setNotice('Listening to the original microphone recording.');
    }catch(e){if(e.name!=='AbortError')setError(e.message)}
  }

  if(!takeId)return null;
  const approved=data&&data.revision>0&&
    data.approved_revision===data.revision;
  const sceneDuration=data?.duration_seconds||30;
  const originals=data?.available_recorded_voices||[];

  return <section className="director-actor-room" aria-label="Direct the performers">
    <div className="director-actor-heading">
      <div>
        <h3>Direct the performers</h3>
        <p className="film-muted">Shape how characters move, express themselves
          and appear on screen. Listen to their original performances before
          choosing what is right for your film.</p>
      </div>
      <span className="director-actor-approval-status">
        {approved?'Approved performance':
          data?'Awaiting your performance approval':'Opening the acting room…'}
      </span>
    </div>
    {error&&<div className="director-actor-error" role="alert">{error}</div>}
    {notice&&<div className="director-actor-notice" role="status">{notice}</div>}
    {data&&data.draft.actors.length===0&&
      <p className="film-muted">This scene has no recorded characters. That is
        fine—landscapes and other performer-free scenes need no acting directions.</p>}
    {data&&data.draft.actors.length>0&&<>
      <label className="director-actor-choose">
        Character
        <select value={actorId} onChange={e=>{
          setActorId(e.target.value);setVoiceUrl('');}}>
          {data.draft.actors.map(actor=><option
            key={actor.actor_id} value={actor.actor_id}>{actor.name}</option>)}
        </select>
      </label>
      <div className="director-actor-preview">
        {previewUrl?<img src={previewUrl}
          alt={'Animated preview of '+(performer?.name||'the actor')+
             ' in the original recorded scene'}/>:
          <div className="director-actor-no-preview">
            {previewBusy?'Preparing your actor preview…':
              'Character picture preview is currently unavailable.'}
          </div>}
        <div className="director-actor-preview-controls">
          <label>Scene moment
            <input type="range" min="0"
              max={Math.max(0,sceneDuration-.05)} step=".05"
              value={sceneTime} onChange={e=>setSceneTime(e.target.value)}/>
            <small>{fmt(sceneTime)} seconds</small>
          </label>
        </div>
        <p className="film-hint">This is an editable rehearsal-quality preview,
          not captured facial motion or a final human-surface render.</p>
      </div>
      <div className="director-actor-layout">
        <section className="director-actor-panel">
          <h4>Acting and movement</h4>
          {acting&&<>
            <label>Movement style<select value={acting.movement}
              onChange={e=>setActing(a=>({...a,movement:e.target.value}))}>
              {Object.entries(movements).map(([key,label])=>
                <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Expression<select value={acting.emotion}
              onChange={e=>setActing(a=>({...a,emotion:e.target.value}))}>
              {Object.entries(emotions).map(([key,label])=>
                <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Expression strength
              <input type="range" min="0" max="1" step=".05"
                value={acting.expression_strength}
                onChange={e=>setActing(a=>({...a,
                  expression_strength:Number(e.target.value)}))}/>
            </label>
            <label>Physical movement energy
              <input type="range" min="0" max="2" step=".05"
                value={acting.gait_strength}
                onChange={e=>setActing(a=>({...a,
                  gait_strength:Number(e.target.value)}))}/>
            </label>
            <label>Natural blink rate
              <input type="range" min="0" max="40" step="1"
                value={acting.blink_rate}
                onChange={e=>setActing(a=>({...a,
                  blink_rate:Number(e.target.value)}))}/>
            </label>
            <label>Direction for this performer
              <textarea rows={3} maxLength={1000}
                placeholder="More tentative at the beginning; more certain toward the end…"
                value={acting.director_note}
                onChange={e=>setActing(a=>({...a,director_note:e.target.value}))}/>
            </label>
            <button className="film-secondary" disabled={busy}
              onClick={()=>save('acting',acting,
                'Acting directions saved. Review and approve this character performance.')}>
              Save Acting Directions</button>
          </>}
        </section>
        <section className="director-actor-panel">
          <h4>Character appearance</h4>
          {appearance&&<>
            <div className="director-actor-colors">
              {[
                ['skin_color','Skin tone'],['hair_color','Hair color'],
                ['eye_color','Eye color'],['wardrobe_color','Wardrobe']
              ].map(([key,label])=><PanelColor key={key} label={label}
                value={appearance[key]}
                onChange={v=>setAppearance(a=>({...a,[key]:v}))}/>)}
            </div>
            <label>Hair style<select value={appearance.hair}
              onChange={e=>setAppearance(a=>({...a,hair:e.target.value}))}>
              {Object.entries(hairStyles).map(([key,label])=>
                <option key={key} value={key}>{label}</option>)}
            </select></label>
            <label>Character height
              <input type="range" min=".65" max="1.45" step=".01"
                value={appearance.height_scale}
                onChange={e=>setAppearance(a=>({...a,
                  height_scale:Number(e.target.value)}))}/>
            </label>
            <label>Shoulder proportions
              <input type="range" min=".55" max="1.55" step=".01"
                value={appearance.shoulder_width}
                onChange={e=>setAppearance(a=>({...a,
                  shoulder_width:Number(e.target.value)}))}/>
            </label>
            <button className="film-secondary" disabled={busy}
              onClick={()=>save('appearance',appearance,
                'Character appearance saved without changing the filmed Take.')}>
              Save Appearance</button>
          </>}
        </section>
      </div>
      <section className="director-actor-voice">
        <h4>Original voice and dialogue delivery</h4>
        <p className="film-muted">Use the actual recorded performance and
          listen before choosing it. NVP will not pretend an unrecorded line
          was spoken, or invent a professional actor voice.</p>
        {!performer?.voice_clips?.length&&<p className="film-muted">
          This performer has no original voice recording in this Take.
          Record a performance in Film Scenes to add real dialogue.</p>}
        {!!performer?.voice_clips?.length&&<>
          <label>Recorded delivery
            <select value={voiceClip} onChange={e=>{
              setVoiceClip(e.target.value);setVoiceUrl('');}}>
              {performer.voice_clips.map((v,index)=>
                <option key={v.clip_id} value={v.clip_id}>
                  Original voice {index+1} · {voiceStates[v.review]}
                </option>)}
            </select>
          </label>
          <button className="film-secondary" disabled={busy||!voiceClip}
            onClick={listen}>Listen to Original</button>
          {voiceUrl&&<audio controls autoPlay preload="none" src={voiceUrl}>
            Your device cannot audition this recording.
          </audio>}
          {selectedVoice&&<>
            <label>Acting / vocal delivery notes
              <input maxLength={140} value={delivery}
                placeholder="Quietly, with growing anger; warm and restrained…"
                onChange={e=>setDelivery(e.target.value)}/>
            </label>
            <label>Dialogue continuity note
              <textarea rows={2} maxLength={600}
                placeholder="Optional reference to the spoken line; NVP does not verify the words here."
                value={dialogueNote}
                onChange={e=>setDialogueNote(e.target.value)}/>
            </label>
            <div className="director-actor-review-buttons">
              <button className="film-secondary" disabled={busy}
                onClick={()=>save('review_voice',{
                  clip_id:voiceClip,review:'rejected',
                  delivery,dialogue_note:dialogueNote
                },'This delivery was declined for facial animation. Its original recording is safe.')}>
                Decline Delivery</button>
              <button className="film-primary" disabled={busy}
                onClick={()=>save('review_voice',{
                  clip_id:voiceClip,review:'approved',
                  delivery,dialogue_note:dialogueNote
                },'This original voice was approved for this character.')}>
                Approve Original Voice</button>
            </div>
          </>}
        </>}
        <p className="film-hint">Facial timing follows energy in the recorded
          voice. Precise speech sounds, phonemes and full facial-capture
          realism are not yet generated automatically.</p>
      </section>
      <section className="director-actor-approve">
        <div><strong>{approved?'This performance is approved':
            'Review your character direction'}</strong>
          <p className="film-muted">Approval applies these character
            decisions to the finished film. Changes made afterward
            require approval again. The original recording never changes.</p>
        </div>
        <button className="film-primary"
          disabled={busy||approved||data.revision===0}
          onClick={approve}>{approved?'Approved':'Approve Performance'}</button>
      </section>
      {data.history.length>1&&<details
        className="director-actor-history" open={showHistory}
        onToggle={e=>setShowHistory(e.currentTarget.open)}>
        <summary>Earlier acting directions</summary>
        <p className="film-muted">Restore an earlier set of creative
          decisions as a new version. All original Takes are preserved.</p>
        {data.history.filter(h=>h.revision!==data.revision).map(h=>
          <div key={h.revision}>
            <span>Acting version {h.revision}</span>
            <button className="film-secondary" disabled={busy}
              onClick={()=>restore(h.revision)}>Restore Version</button>
          </div>)}
      </details>}
    </>}
  </section>;
}
