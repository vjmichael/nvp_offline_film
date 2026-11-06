import React,{useEffect,useMemo,useRef,useState} from 'react';

// INDEX-TIME-05: a data-first FilmIndex/SQLite source-inspection pane.
// Original PTS and Film Time stay exact decimal strings, never JS Number
// approximations. No browser-side native worker launch or master approval.
const FORMAT='nvp.index_time05.editor_source_read.v1';

export default function FilmTimeIndexPanel({projectId,api}){
  const [edits,setEdits]=useState([]);
  const [editId,setEditId]=useState('');
  const [clips,setClips]=useState([]);
  const [next,setNext]=useState(null);
  const [tickDraft,setTickDraft]=useState('0');
  const [selection,setSelection]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(false);
  const [truncated,setTruncated]=useState(false);
  const generation=useRef(0);
  const selected=useMemo(
    ()=>edits.find(e=>e.edit_id===editId)||null,[edits,editId]);

  useEffect(()=>{
    let active=true;
    generation.current++;
    setEdits([]);setEditId('');setClips([]);setNext(null);
    setSelection(null);setError('');setLoading(true);
    api('/projects/'+encodeURIComponent(projectId)+'/film-time/edits')
      .then(value=>{
        if(!active)return;
        if(value?.format!==FORMAT||value.project_id!==projectId ||
           !Array.isArray(value.edits) || value.worker_started!==false)
          throw new Error('Indexed source list failed custody checks');
        setEdits(value.edits);
        setTruncated(value.truncated===true);
        setEditId(value.edits[0]?.edit_id||'');
      }).catch(err=>{if(active)setError(err.message);})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;generation.current++;};
  },[api,projectId]);

  useEffect(()=>{
    const request=++generation.current;
    setClips([]);setNext(null);setSelection(null);setError('');
    if(!selected)return;
    setTickDraft('0');setLoading(true);
    const params=new URLSearchParams({
      revision:String(selected.revision),
      expected_edit_sha256:selected.edit_document_sha256,
      after_ordinal:'-1',limit:'40',
    });
    api('/projects/'+encodeURIComponent(projectId)+'/film-time/edits/'+
      encodeURIComponent(selected.edit_id)+'/clips?'+params)
      .then(page=>{
        if(generation.current!==request)return;
        if(page?.format!==FORMAT||page.status!=='INDEXED_EDIT_CLIPS' ||
           page.project_id!==projectId||
           page.edit_id!==selected.edit_id||
           page.edit_revision!==selected.revision||
           page.edit_document_sha256!==selected.edit_document_sha256||
           page.original_media_read!==false||!Array.isArray(page.clips))
          throw new Error('Indexed edit page changed source version');
        setClips(page.clips);setNext(page.next_after_ordinal);
        setTickDraft(page.clips[0]?.film_start_tick||'0');
      }).catch(err=>{if(generation.current===request)setError(err.message);})
      .finally(()=>{if(generation.current===request)setLoading(false);});
  },[api,projectId,selected]);

  async function more(){
    if(!selected||next===null||busy)return;
    const request=generation.current;
    setBusy(true);setError('');
    try{
      const params=new URLSearchParams({
        revision:String(selected.revision),
        expected_edit_sha256:selected.edit_document_sha256,
        after_ordinal:String(next),limit:'40',
      });
      const page=await api('/projects/'+encodeURIComponent(projectId)+
        '/film-time/edits/'+encodeURIComponent(selected.edit_id)+
        '/clips?'+params);
      if(request!==generation.current)return;
      if(page?.format!==FORMAT||page.status!=='INDEXED_EDIT_CLIPS' ||
         page.edit_document_sha256!==selected.edit_document_sha256 ||
         page.edit_id!==selected.edit_id||!Array.isArray(page.clips) ||
         page.clips.some(c=>c.ordinal<=next))
        throw new Error('Indexed next page was stale or did not advance');
      setClips(rows=>[...rows,...page.clips]);
      setNext(page.next_after_ordinal);
    }catch(err){if(request===generation.current)setError(err.message);}
    finally{if(request===generation.current)setBusy(false);}
  }

  async function seekAt(text){
    if(!selected||busy)return;
    const value=String(text).trim();
    if(!/^\d{1,20}$/.test(value)){
      setError('Film Time must be a nonnegative exact integer tick.');
      return;
    }
    let tick;
    try{tick=BigInt(value);}catch{
      setError('Invalid exact Film Time tick.');return;
    }
    if(tick>BigInt(selected.duration_tick)){
      setError('Selected Film Time is beyond the indexed edit duration.');
      return;
    }
    const request=generation.current;
    setTickDraft(tick.toString());setBusy(true);setError('');
    setSelection(null);
    try{
      const params=new URLSearchParams({
        revision:String(selected.revision),
        expected_edit_sha256:selected.edit_document_sha256,
        tick:tick.toString(),
      });
      const result=await api('/projects/'+encodeURIComponent(projectId)+
        '/film-time/edits/'+encodeURIComponent(selected.edit_id)+
        '/seek?'+params);
      if(request!==generation.current)return;
      if(result?.format!==FORMAT||
         result.project_id!==projectId||
         result.edit_document_sha256!==selected.edit_document_sha256||
         result.edit_id!==selected.edit_id||
         result.edit_revision!==selected.revision||
         result.requested_film_tick!==tick.toString()||
         result.original_source_path_disclosed!==false||
         result.native_worker_started!==false||
         result.film_master_approved!==false||
         !['EMPTY_IMPORTED_VIDEO_GAP','INDEXED_SOURCE_FRAME_SELECTED']
           .includes(result.status))
        throw new Error('Native index seek returned a stale or unauthorized source');
      setSelection(result);
    }catch(err){if(request===generation.current)setError(err.message);}
    finally{if(request===generation.current)setBusy(false);}
  }

  return <section className="card" aria-label="Indexed source Film Time">
    <h2>Indexed footage · Film Time</h2>
    <p className="fineprint">Inspect immutable imported-video placements,
      original timestamps, and held source frames without loading a full
      movie or rendering every timeline frame.</p>
    {loading&&<p role="status">Opening indexed source metadata…</p>}
    {!loading&&edits.length===0&&
      <p>No indexed imported-video edit is published in this film yet.
        Source footage must be registered and placed on a Film Time edit first.</p>}
    {truncated&&<p>Showing the first bounded set of imported-video edits.</p>}
    {selected&&<>
      <label>Indexed edit
        <select aria-label="Indexed Film Time edit" value={editId}
          onChange={e=>setEditId(e.target.value)}>
          {edits.map(e=><option key={e.edit_id} value={e.edit_id}>
            {e.edit_id} · revision {e.revision} · {e.clip_count} clips
          </option>)}
        </select>
      </label>
      <p className="fineprint">Saved duration: {selected.duration_tick} Film Time ticks.
        Original media bytes are not rehashed during metadata browsing.
        An indexed lookup is not final-media approval.</p>
      <form onSubmit={e=>{e.preventDefault();seekAt(tickDraft);}}>
        <label>Film Time tick (exact integer)
          <input aria-label="Indexed Film Time tick" inputMode="numeric"
            value={tickDraft} onChange={e=>setTickDraft(e.target.value)}
            placeholder="0"/>
        </label>
        <button type="submit" disabled={busy||loading}>Seek indexed source</button>
      </form>
      <h3>Source placements</h3>
      {clips.length===0&&!loading&&<p>No imported clips in this edit.</p>}
      <div className="nvp-film-index-placements">
        {clips.map(clip=><div key={clip.ordinal} className="card">
          <strong>Clip {clip.ordinal+1} · {clip.source_id}</strong>
          <p>Film Time {clip.film_start_tick}–{clip.film_end_tick} ticks</p>
          <p className="fineprint">Original frame ordinals
            {' '}{clip.source_in_frame_zero}–{clip.source_out_frame_zero}
            {' '} (out-exclusive) · source PTS
            {' '}{clip.source_in_pts}–{clip.source_out_pts}</p>
          <button disabled={busy} onClick={()=>
            seekAt(clip.film_start_tick)}>Inspect clip beginning</button>
        </div>)}
      </div>
      {next!==null&&<button disabled={busy||loading}
        onClick={more}>Load next indexed clips</button>}
      {selection?.status==='EMPTY_IMPORTED_VIDEO_GAP'&&
        <p role="status">No imported video is placed at Film Time
          {' '}{selection.requested_film_tick}. This is an intentional gap.</p>}
      {selection?.status==='INDEXED_SOURCE_FRAME_SELECTED'&&
        <section aria-label="Selected original indexed frame">
          <h3>Selected original frame</h3>
          <p>{selection.source_id} · frame {selection.source_frame_zero}
            {' '} · original PTS {selection.source_pts}</p>
          <p>Held for Film Time {selection.frame_film_start_tick}
            {' '}–{selection.frame_film_end_tick} ticks</p>
          <p className="fineprint">Indexed binary seek:
            {' '}{selection.frame_index_pts_reads} SQLite PTS reads.
            Source stamp checked, original bytes not SHA-reverified.
            No decoder launched, and no picture approved.</p>
        </section>}
    </>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">Imported-video indexing is separate from
      OpenUSD actor/scene events. This pane is read-only.
      Native preview/conform requires the existing separately authorized
      source-window worker.</p>
  </section>;
}
