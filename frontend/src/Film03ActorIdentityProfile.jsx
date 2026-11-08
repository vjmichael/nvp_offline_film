import React, {useEffect, useState} from 'react';

// Every field belongs to ONE existing StoryBible character ActorID.
// No second character/persona database and no model-generated defaults.
const initial = {
  appearance: {
    silhouette:'', palette:'', surface:'', signature_marks:'',
    visual_expression:'',
  },
  behavior: {
    personality_traits:'', habits:'', emotional_rules:'', speech_style:'',
  },
  movement: {
    gait:'', posture:'', signature_gestures:'', movement_peculiarities:'',
  },
  voice_type: {
    voice_type_id:'', register:'', pitch:'', timbre:'', accent:'',
    cadence:'', articulation:'', signature_quirks:'',
  },
  voice_generation: {
    engine_id:'', model_id:'', model_revision:'', engine_voice_id:'',
    seed:0,rate:1,pitch_shift:0,stability:1,language:'en',
  },
  director_notes:'',
};
const titles = {
  appearance:'Appearance and visual continuity',
  behavior:'Personality and behavioral continuity',
  movement:'Physical performance, gait and movement quirks',
  voice_type:'The canonical ActorID VoiceType',
  voice_generation:'AI voice provider and generation identity',
};
const descriptions = {
  voice_type:'This describes the character’s voice. VoiceType is not interchangeable with another actor’s VoiceID.',
  voice_generation:'NVP locks engine, model revision, provider voice selector, seed and settings to this ActorID. This does not execute AI or authorize a generated Take.',
  movement:'Record distinctive habits such as an uneven step, slow turn, persistent limp or odd gesture. Later animation and AI camera work should use the same source.',
};
const settings = new Set(['seed','rate','pitch_shift','stability']);

export default function Film03ActorIdentityProfile({
  project, actorId, detail, action, busy, onUpdated,
}) {
  const [profile,setProfile] = useState(initial);
  const [approvalNote,setApprovalNote] = useState('');
  const [feedback,setFeedback] = useState('');
  const [error,setError] = useState('');
  const current = detail?.current_identity_profile;
  const native = typeof window === 'undefined' ? {} : (window.pywebview?.api || {});
  useEffect(()=>{
    setProfile(current?.profile ?
      JSON.parse(JSON.stringify(current.profile)) :
      JSON.parse(JSON.stringify(initial)));
    setFeedback('');setError('');setApprovalNote('');
  },[actorId,current?.profile_revision]);

  function field(section,key,value) {
    setProfile(p=>({...p,[section]:{...p[section],
      [key]:settings.has(key) ? Number(value) : value,
    }}));
  }
  function publish(){
    if (typeof native.film03_publish_actor_identity_profile !== 'function') {
      setError('Installed NVP director confirmation is required to publish an ActorID profile.');
      return;
    }
    if(approvalNote.trim().length<12) {
      setError('Director must explain this character identity revision.');return;
    }
    action(async()=>{
      const result=await native.film03_publish_actor_identity_profile({
        project_id:project.id,actor_id:actorId,profile,
        expected_profile_revision:current?.profile_revision || 0,
        expected_bible_revision:detail.bible_revision,
        director_note:approvalNote,
      });
      if(result?.format!=='nvp.film03.actor_identity_profile.v1' ||
          result.actor_id!==actorId ||
          result.host_native_director_confirmation!==true ||
          result.original_actor_assets_modified!==false ||
          result.original_voice_recordings_modified!==false ||
          result.tts_or_animation_worker_invoked!==false) {
        throw new Error('Unverified immutable ActorID profile operation');
      }
      await onUpdated();
      setFeedback('ActorID profile revision ' + result.current.profile_revision +
        ' published; previous appearance, behavior, gait and VoiceType remain in history.');
    });
  }
  return <section className="card" aria-label="Canonical ActorID character identity profile">
    <h3>ActorID — the complete character identity</h3>
    <p className="fineprint">ActorID <code>{actorId}</code> is the source of identity
      for every actor asset, trait, physical movement and voice generation instruction.
      Changing a costume or mesh cannot change the actor’s persona or VoiceID.</p>
    <p className="fineprint">Current character profile: {current ?
      'revision ' + current.profile_revision : 'not yet director-authored'} ·
      current VoiceID: {detail.current_voice_identity?.voice_id ||
        'none (AI voice generation blocked)'}</p>
    {current && (
      current.voice_id !== (detail.current_voice_identity?.voice_id || null) ||
      current.voice_cast_revision !== (
        detail.current_voice_identity?.cast_revision || null)
    ) && <p role="alert">
      VoiceID changed since this ActorID profile was published.
      AI-generated speech is blocked until the director reviews and
      republishes a profile bound to the CURRENT approved voice.
    </p>}
    {!!detail.immutable_identity_profile_history?.length && <details>
      <summary>View all historical ActorID identity profiles</summary>
      {detail.immutable_identity_profile_history.map(x=>
        <p className="fineprint" key={x.profile_revision}>
          Revision {x.profile_revision} · source SHA {x.document_sha256} ·
          VoiceID {x.voice_id || 'not yet cast'}
        </p>)}
    </details>}
    {Object.entries(titles).map(([section,title])=><fieldset key={section}
      className="scene-item">
      <legend><strong>{title}</strong></legend>
      {descriptions[section] && <p className="fineprint">{descriptions[section]}</p>}
      {Object.entries(profile[section]).map(([name,value])=>
        <label key={name}>{name.replaceAll('_',' ')}
          <input aria-label={'Actor '+section+'.'+name}
            type={settings.has(name) ? 'number' : 'text'}
            min={name==='seed'?0:name==='rate'?0.5:name==='stability'?0:
              name==='pitch_shift'?-12:undefined}
            max={name==='seed'?4294967295:name==='rate'?2:
              name==='stability'?1:name==='pitch_shift'?12:undefined}
            step={name==='seed'?1:settings.has(name)?0.1:undefined}
            maxLength={settings.has(name)?undefined:350}
            value={value} onChange={e=>field(section,name,e.target.value)}/>
        </label>)}
    </fieldset>)}
    <label>Director identity continuity notes
      <textarea aria-label="Actor identity director notes" rows={2}
        maxLength={1500} value={profile.director_notes}
        onChange={e=>setProfile(p=>({...p,director_notes:e.target.value}))} />
    </label>
    <label>Approval reason for exact new character revision
      <textarea aria-label="Actor identity approval reason" rows={2}
        maxLength={1500} value={approvalNote}
        onChange={e=>setApprovalNote(e.target.value)} />
    </label>
    {error && <p role="alert">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    <button disabled={busy || approvalNote.trim().length<12 ||
        typeof native.film03_publish_actor_identity_profile!=='function'}
      onClick={publish}>
      Publish immutable ActorID identity (native director approval)
    </button>
    <p className="fineprint">The AI voice engine selector and voice type
      are pinned to this ActorID, but NVP still requires approved VoiceID,
      script-line validation, a supervised real TTS provider,
      verified output provenance and separate director audition before
      any generated speech enters a Take.</p>
  </section>;
}
