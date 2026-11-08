import React,{useEffect,useState} from 'react';

// WO6-07E: original OpenUSD pose + actual source PCM for ONE
// source-projected 24fps frame; no rendered picture or finished film.
const KIND='nvp.wo6_07e.exact_edited_source_pcm_review.v1';
const CAT='nvp.wo6_07e.original_source_review_catalog.v1';

export default function WO6DirectorSourceReview({projectId}){
  const [catalog,setCatalog]=useState(null);
  const [editId,setEditId]=useState('');
  const [timelineId,setTimelineId]=useState('');
  const [frameText,setFrameText]=useState('0');
  const [review,setReview]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const native=()=>window.pywebview?.api;
  const selectedEdit=catalog?.edits?.find(x=>x.edit_id===editId)||null;
  const selectedTimeline=catalog?.timelines?.find(
    x=>x.timeline_id===timelineId)||null;

  useEffect(()=>{
    let active=true;
    const refresh=async()=>{
      try{
        const api=native();
        if(typeof api?.wo6_07e_source_review_catalog!=='function')
          throw new Error('Source review requires the installed NVP native host');
        const data=await api.wo6_07e_source_review_catalog(projectId);
        if(!active)return;
        if(data?.format!==CAT||data.project_id!==projectId||
            data.native_worker_authorized!==false)
          throw new Error('Untrusted original source catalog');
        setCatalog(data);
        setEditId(old=>data.edits.some(e=>e.edit_id===old)?
          old:(data.edits[0]?.edit_id||''));
        setTimelineId('');
        setReview(null);
        setError('');
      }catch(e){if(active)setError(String(e?.message||e))}
    };
    void refresh();
    window.addEventListener('pywebviewready',refresh);
    return ()=>{active=false;window.removeEventListener('pywebviewready',refresh)};
  },[projectId]);
  const selectEdit=(id)=>{setEditId(id);setReview(null);setFrameText('0')};
  const selectTimeline=(id)=>{setTimelineId(id);setReview(null)};
  const selectFrame=(str)=>{setFrameText(str);setReview(null)};
  const inspect=async()=>{
    if(!selectedEdit)return;
    setError('');setBusy(true);setReview(null);
    try{
      if(!/^(0|[1-9][0-9]{0,6})$/.test(frameText))
        throw new Error('Choose an exact bounded 24 fps zero-based frame');
      const num=Number(frameText);
      const max=Math.ceil(Number(selectedEdit.duration_tick)*24/7056000000);
      if(!Number.isSafeInteger(num)||!Number.isFinite(max)||num>=max)
        throw new Error('Source frame exceeds the selected native edit');
      const request={
        project_id:projectId,
        edit_id:selectedEdit.edit_id,
        edit_revision:selectedEdit.edit_revision,
        edit_sha256:selectedEdit.edit_sha256,
        frame_zero:num,
        sound_timeline_id:selectedTimeline?.timeline_id||null,
        sound_timeline_revision:selectedTimeline?.revision||null,
        sound_timeline_sha256:selectedTimeline?.sha256||null,
      };
      const data=await native().wo6_07e_review_source_frame(request);
      if(data?.format!==KIND||data.project_id!==projectId||
          data.edit_document_sha256!==request.edit_sha256||
          data.output_frame_zero!==num||
          data.native_worker_authorized!==false||
          data.original_source_modified!==false||
          data.frame_pixels_rendered!==false||
          data.finished_film_mastered_audio!==false)
        throw new Error('Original source frame / PCM provenance could not be verified');
      setReview(data);
    }catch(e){setError(String(e?.message||e))}
    finally{setBusy(false)}
  };
  return <section aria-label="WO6 exact original editorial and PCM director review">
    <h3>Original edit + recorded sound, exact Film Time</h3>
    <p>This is a source-level director audition. It displays the real
      OpenUSD actor, camera and lighting state and lets you hear a bounded
      original PCM excerpt starting at the same editorial frame. It is not rendered
      film picture or a mastered soundtrack.</p>
    {!catalog&&<p>Reading trusted original editorial sources…</p>}
    <label>Approved immutable editorial cut
      <select value={editId} disabled={busy} onChange={e=>selectEdit(e.target.value)}>
        {catalog?.edits?.map(x=><option key={x.edit_id} value={x.edit_id}>
          {x.edit_id} · rev {x.edit_revision} · {x.segment_count} source segments
        </option>)}
      </select>
    </label>
    <label>Recorded sound timeline
      <select value={timelineId} disabled={busy}
        onChange={e=>selectTimeline(e.target.value)}>
        <option value="">Use exact frozen Take original soundtrack</option>
        {catalog?.timelines?.map(x=><option key={x.timeline_id}
          value={x.timeline_id}>
          {x.timeline_id} · rev {x.revision} · {x.event_count} native events
        </option>)}
      </select>
    </label>
    <label>Output frame at 24 fps (zero-based)
      <input inputMode="numeric" value={frameText} disabled={busy}
        onChange={e=>selectFrame(e.target.value)}/>
    </label>
    <div className="actions">
      <button type="button" disabled={busy||!selectedEdit||frameText==='0'}
        onClick={()=>selectFrame(String(Math.max(0,Number(frameText)-1)))}>
        Previous frame</button>
      <button type="button" disabled={busy||!selectedEdit}
        onClick={()=>selectFrame(String(Number(frameText)+1))}>
        Next frame</button>
      <button type="button" disabled={busy||!selectedEdit} onClick={inspect}>
        Inspect exact original frame and PCM</button>
    </div>
    {review&&<div aria-label="Verified native source-frame review">
      <p>Source Take: {review.source_take_id}. Source tick:
        {review.source_film_time_tick}. Output frame: {review.output_frame_zero}.</p>
      <p>Editorial segment: {review.source_projection.segment_id}.
        Original Take SHA: {review.source_take_sha256}</p>
      <p>Source review SHA: {review.source_review_sha256}</p>
      <p>Native verified scene positions (not rendered pixels):</p>
      <ul>{review.scene_poses.map(p=><li key={p.prim_path}>
        {p.role} {p.prim_path} — XYZ {p.world_translation.join(', ')}
        {p.native_schema?.schema?' ('+p.native_schema.schema+')':''}
      </li>)}</ul>
      <p>PCM source tracks: {review.source_pcm_tracks.length}.
        Exact samples in this excerpt: {review.source_pcm_samples} at
        {review.source_pcm_sample_rate} Hz.</p>
      {review.audio_data_url&&<audio key={review.source_review_sha256}
        controls preload="none" src={review.audio_data_url}>
        Original PCM review requires a browser with WAV audio support.
      </audio>}
      {!review.audio_data_url&&<p>No authenticated recorded PCM is audible
        at this chosen original source frame.</p>}
      {review.source_pcm_omissions.length>0&&<p>
        Incomplete or non-recorded original sound sources:
        {review.source_pcm_omissions.map(x=>x.event_id+' ('+x.reason+')').join(', ')}
      </p>}
      {review.frame_spans_edit_boundary&&<p>Clip boundary: this window
        is shorter than the usual 0.5-second source excerpt. Next frame maps
        to its own original source Take.</p>}
      <p>Audio begins only when you press play. There are no picture
        pixels here, no continuous 24 fps playback verification,
        no model execution, no worker permission and no final mix approval.</p>
    </div>}
    {busy&&<p role="status">Verifying native source frame and original PCM…</p>}
    {error&&<p role="status">{error}</p>}
  </section>;
}
