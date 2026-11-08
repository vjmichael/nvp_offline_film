import React, {useEffect, useMemo, useState} from 'react';

/**
 * Production Bible: the actor's VoiceID is immutable identity, not the
 * last recorded file. Audition exact original PCM BEFORE native approval.
 * Browser cannot create a voice cast or approve a take through HTTP.
 */
export default function Film03ActorVoicePanel({
  project, actorId, detail, catalog, api, action, busy, onUpdated,
}) {
  const [candidates, setCandidates] = useState([]);
  const [reference, setReference] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [recastReason, setRecastReason] = useState('');
  const [performance, setPerformance] = useState('');
  const [deliveryNote, setDeliveryNote] = useState('');
  const [auditions, setAuditions] = useState({});
  const [listened, setListened] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const current = detail.current_voice_identity;
  const root = '/projects/' + project.id + '/production-bible/actors/' +
    encodeURIComponent(actorId);
  const native = typeof window === 'undefined' ? {} : (window.pywebview?.api || {});
  const original = useMemo(() =>
    (catalog?.sources || []).filter(s => s.family === 'filmindex' &&
      s.kind === 'audio' && Number.isInteger(s.sample_count) &&
      s.sample_count > 0), [catalog]);
  const sourceKey = s => s.target_id + ':' + s.target_revision;
  const refEntry = original.find(s => sourceKey(s) === reference);
  const selectedCandidate = candidates.find(x=>x.performance_id===performance);

  useEffect(() => {
    let live = true;
    setCandidates([]); setPerformance(''); setAuditions({}); setListened(false);
    setError(''); setMessage('');
    api(root + '/voice-candidates').then(result => {
      if (!live) return;
      if (result?.format !== 'nvp.film03.voice_candidate_audition_catalog.v1' ||
          result.actor_id !== actorId || result.project_id !== project.id)
        throw new Error('Voice candidates are not for this ActorID');
      setCandidates(result.candidates);
    }).catch(e=>{if(live)setError(e.message);});
    return () => { live = false; };
  }, [actorId, project.id, detail.bible_revision, root, api]);

  useEffect(() => {
    if (!current && !refEntry && original.length && !reference)
      setReference(sourceKey(original[0]));
  }, [original, reference, current]);

  async function audition(audioId, revision, expectedSha, sampleCount, kind) {
    setError(''); setMessage('');
    if(typeof native.film03_audition_original_voice !== 'function') {
      setError('A real installed NVP desktop host is required to audition original source voice.');
      return;
    }
    const clip = await native.film03_audition_original_voice({
      project_id:project.id,source_audio_id:audioId,
      source_audio_revision:revision,first_sample:0,
      sample_count:Math.min(144000,sampleCount),
    });
    if (clip?.format !== 'nvp.film03.original_actor_voice_audition.v1' ||
        clip.source_audio_id !== audioId || clip.source_audio_sha256 !== expectedSha ||
        clip.source_audio_revision !== revision ||
        clip.original_recording_not_tts !== true ||
        clip.audition_not_voice_identity_approval !== true)
      throw new Error('Original voice audition SHA, identity or provenance differs');
    setAuditions(old=>({...old,[kind]:{
      sha256:clip.source_audio_sha256,
      audioSrc:'data:audio/wav;base64,' + clip.wav_data_base64,
      sampleCount:clip.sample_count,
    }}));
    setListened(false);
  }

  function enrollVoice() {
    if (!refEntry || !auditions.newReference ||
        auditions.newReference.sha256 !== refEntry.sha256 || !listened ||
        !voiceId.startsWith('Voice_') || reviewNote.trim().length < 12) return;
    action(async()=>{
      const invoke = native.film03_cast_actor_voice;
      if(typeof invoke !== 'function') throw new Error('Trusted NVP native voice consent unavailable');
      const outcome=await invoke({
        project_id:project.id,actor_id:actorId,voice_id:voiceId,
        reference_audio_id:refEntry.target_id,
        reference_audio_revision:refEntry.target_revision,
        expected_cast_revision:current?.cast_revision || 0,
        director_review_note:reviewNote,
        voice_recast_reason:current ? recastReason : '',
      });
      if (outcome?.format !== 'nvp.film03.production_bible_voice_identity.v1' ||
          outcome.actor_id !== actorId ||
          outcome.current?.voice_id !== voiceId ||
          outcome.host_native_director_confirmation !== true ||
          outcome.source_voice_performance_generated !== false ||
          outcome.audio_take_overwritten !== false)
        throw new Error('Unverified native voice identity casting response');
      await onUpdated();
      setAuditions({}); setListened(false);
      setMessage('VoiceID source enrolled at immutable revision ' +
        outcome.current.cast_revision + '. Earlier voice remains preserved.');
    });
  }

  function approveTake() {
    if (!current || !selectedCandidate || !auditions.currentReference ||
        !auditions.candidate || !listened || deliveryNote.trim().length < 12 ||
        auditions.currentReference.sha256 !== current.reference_audio_sha256 ||
        auditions.candidate.sha256 !== selectedCandidate.source_audio_sha256) return;
    action(async()=>{
      const invoke = native.film03_approve_actor_voice_take;
      if(typeof invoke !== 'function') throw new Error('Native actor voice review approval unavailable');
      const outcome=await invoke({
        project_id:project.id,actor_id:actorId,
        performance_id:selectedCandidate.performance_id,
        voice_id:current.voice_id,
        expected_cast_revision:current.cast_revision,
        expected_approval_revision:selectedCandidate.latest_approval_revision,
        reference_audio_sha256:current.reference_audio_sha256,
        director_comparison_note:deliveryNote,
      });
      if (outcome?.format !== 'nvp.film03.voice_performance_review.v1' ||
          outcome.actor_id !== actorId || outcome.voice_id !== current.voice_id ||
          outcome.host_native_director_confirmation !== true ||
          outcome.original_recording_overwritten !== false ||
          outcome.audio_voice_model_invoked !== false)
        throw new Error('VoiceID and original voice approval mismatch');
      setMessage('Original dialogue Take approved for ' +
        current.voice_id + ' at review ' + outcome.approval_revision);
      setAuditions({}); setListened(false);
      await onUpdated();
    });
  }

  const canCast = typeof native.film03_cast_actor_voice === 'function' &&
    !busy && !!refEntry && !!auditions.newReference &&
    auditions.newReference.sha256 === refEntry.sha256 &&
    voiceId.trim().startsWith('Voice_') && reviewNote.trim().length >= 12 &&
    (!current || (voiceId !== current.voice_id &&
      recastReason.trim().length >= 12)) && listened;
  const canApprove = typeof native.film03_approve_actor_voice_take === 'function' &&
    !busy && !!current && !!selectedCandidate && !!auditions.currentReference &&
    !!auditions.candidate && listened && deliveryNote.trim().length >= 12 &&
    auditions.currentReference.sha256 === current.reference_audio_sha256 &&
    auditions.candidate.sha256 === selectedCandidate.source_audio_sha256;

  return <section className="card" aria-label="ActorID voice continuity">
    <h3>VoiceID · authoritative character voice</h3>
    <p className="fineprint">ActorID <code>{actorId}</code> keeps the same approved
      VoiceID across script, wardrobe, camera, model and mesh changes.
      Matching a dialogue line is NOT proof that the voice is correct.
      Every different recording must be compared with this character’s
      original voice reference.</p>
    {current ? <div className="scene-item">
      <strong>Approved current VoiceID: <code>{current.voice_id}</code></strong>
      <p className="fineprint">Voice cast version {current.cast_revision} ·
        original reference {current.reference_audio_id} @ {current.reference_audio_revision}</p>
      <p className="fineprint">Reference SHA: <code>{current.reference_audio_sha256}</code></p>
      <p>Voice changes require another VoiceID, another original reference recording,
        an explicit director reason and a separate native confirmation.</p>
    </div> : <p className="muted">
      This actor has no approved VoiceID. NVP must not automatically invent a
      speaking voice or use a recorded clip merely because its filename matches.
    </p>}
    {!!detail.immutable_voice_cast_history?.length && <details>
      <summary>All {detail.immutable_voice_cast_history.length} original voice casting decisions</summary>
      {detail.immutable_voice_cast_history.map(x=><p className="fineprint"
        key={x.cast_revision}>{x.cast_revision} · {x.voice_id} ·
        {x.reference_audio_id} · source SHA {x.reference_audio_sha256}</p>)}
    </details>}
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {typeof native.film03_audition_original_voice !== 'function' &&
      <p className="fineprint">Voice approval and actual PCM auditions only run inside the
        trusted installed NVP desktop, not an ordinary browser or AI model session.</p>}

    <h4>{current ? 'Explicit character-voice recast' : 'Enroll approved reference voice'}</h4>
    <label>New canonical VoiceID (for example Voice_Donut_Original)
      <input aria-label="Canonical VoiceID" value={voiceId} maxLength={80}
        onChange={e=>setVoiceId(e.target.value)} />
    </label>
    <label>Existing original recorded PCM reference
      <select aria-label="Voice reference recording" value={reference}
        onChange={e=>{setReference(e.target.value);setAuditions({});setListened(false);}}>
        <option value="">Select original source recording</option>
        {original.map(s=><option key={sourceKey(s)} value={sourceKey(s)}>
          {s.target_id} · rev {s.target_revision} · {s.sample_count} samples
        </option>)}
      </select>
    </label>
    <button className="secondary" disabled={busy || !refEntry} onClick={()=>
      action(()=>audition(refEntry.target_id,refEntry.target_revision,refEntry.sha256,
                         refEntry.sample_count,'newReference'))}>
      Audition this original VoiceID reference
    </button>
    {auditions.newReference && <audio controls preload="none"
      aria-label="Proposed ActorID VoiceID reference audition"
      src={auditions.newReference.audioSrc} />}
    <label>Director’s reference audition notes
      <textarea aria-label="Reference voice audition notes" rows={2}
        value={reviewNote} maxLength={1200}
        onChange={e=>setReviewNote(e.target.value)} />
    </label>
    {current && <label>Why is the character’s voice being recast?
      <textarea aria-label="Voice recast reason" rows={2}
        maxLength={1200} value={recastReason}
        onChange={e=>setRecastReason(e.target.value)} />
    </label>}
    <label><input type="checkbox" checked={listened}
      onChange={e=>setListened(e.target.checked)} />
      I listened to the original source recording and reviewed its identity
      for this ActorID.</label>
    <button disabled={!canCast} onClick={enrollVoice}>
      {current ? 'Approve a NEW VoiceID (preserve old voice)' :
        'Enroll first ActorID VoiceID (native approval)'}
    </button>

    <h4>Compare exact dialogue Take against approved VoiceID</h4>
    <p className="fineprint">Every new spoken Take needs separate approval.
      AI or audio filenames cannot declare voice continuity.</p>
    <label>ActorID-linked recorded performance
      <select aria-label="Actor recorded dialogue Take" value={performance}
        onChange={e=>{setPerformance(e.target.value);setAuditions({});setListened(false);}}>
        <option value="">Select a recorded performance</option>
        {candidates.map(x=><option key={x.performance_id} value={x.performance_id}>
          {x.performance_id} · {x.script_line_text}
          {x.approved_voice_id ? ' · reviewed for ' + x.approved_voice_id : ' · unreviewed'}
        </option>)}
      </select>
    </label>
    {current && <>
      <button className="secondary" disabled={busy} onClick={()=>
        action(()=>audition(current.reference_audio_id,current.reference_audio_revision,
          current.reference_audio_sha256,current.reference_sample_count,
          'currentReference'))}>
        Audition current ActorID VoiceID reference
      </button>
      {auditions.currentReference && <audio controls preload="none"
        aria-label="Current approved ActorID voice reference"
        src={auditions.currentReference.audioSrc} />}
    </>}
    {selectedCandidate && <button className="secondary" disabled={busy} onClick={()=>
      action(()=>audition(selectedCandidate.source_audio_id,
                         selectedCandidate.source_audio_revision,
                         selectedCandidate.source_audio_sha256,144000,
                         'candidate'))}>
      Audition this exact recorded dialogue Take
    </button>}
    {auditions.candidate && <audio controls preload="none"
      aria-label="Actor candidate original spoken Take"
      src={auditions.candidate.audioSrc} />}
    <label>Director’s comparison of the audible VoiceID reference and Take
      <textarea aria-label="Actor voice consistency comparison notes" rows={3}
        maxLength={1200} value={deliveryNote}
        onChange={e=>setDeliveryNote(e.target.value)} />
    </label>
    <p className="fineprint">This is an explicit human audition decision,
      not an automatic acoustic/speaker-recognition result. If the timbre
      differs, reject or record a new performance rather than relabel it.</p>
    <button disabled={!canApprove} onClick={approveTake}>
      Approve this VoiceID for the exact recorded Take
    </button>
  </section>;
}
