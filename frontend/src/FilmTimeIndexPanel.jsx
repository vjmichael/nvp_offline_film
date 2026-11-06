import React,{useEffect,useMemo,useRef,useState} from 'react';

// INDEX-TIME-05: a data-first FilmIndex/SQLite source-inspection pane.
// Original PTS and Film Time stay exact decimal strings, never JS Number
// approximations. No browser-side native worker launch or master approval.
const FORMAT='nvp.index_time05.editor_source_read.v1';
import FilmTimeAssemblyPanel from './FilmTimeAssemblyPanel.jsx';
import {filmTimeClock} from './filmTimeClock.js';
export {filmTimeClock} from './filmTimeClock.js';

export default function FilmTimeIndexPanel({projectId,api,nativeBridge=null}){
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
  const preferredEdit=useRef('');
  const activePreview=useRef(null);
  const [refresh,setRefresh]=useState(0);
  const [native,setNative]=useState(nativeBridge);
  const [nativeReady,setNativeReady]=useState(false);
  const [importing,setImporting]=useState(false);
  const [importResult,setImportResult]=useState(null);
  const [previewTicket,setPreviewTicket]=useState(null);
  const [rendered,setRendered]=useState(null);
  const [renderError,setRenderError]=useState('');
  const [nativeBusy,setNativeBusy]=useState(false);
  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    function detect(){
      const n=window.pywebview?.api;
      if(n&&[
        'video_import_capabilities','pick_and_import_footage',
        'request_source_frame_preview','poll_source_frame_preview',
        'cancel_source_frame_preview',
      ].every(key=>typeof n[key]==='function'))setNative(n);
    }
    detect();
    window.addEventListener('pywebviewready',detect);
    return ()=>window.removeEventListener('pywebviewready',detect);
  },[nativeBridge]);
  useEffect(()=>{
    let live=true;
    setNativeReady(false);
    if(native&&typeof native.video_import_capabilities==='function'){
      Promise.resolve(native.video_import_capabilities())
        .then(result=>{if(live)setNativeReady(
          result?.format==='nvp.index_time06.native_capability.v1' &&
          result.native_window===true && result.native_dialog===true &&
          result.video_tools_available===true);})
        .catch(()=>{if(live)setNativeReady(false);});
    }
    return ()=>{live=false;};
  },[native]);
  const selected=useMemo(
    ()=>edits.find(e=>e.edit_id===editId)||null,[edits,editId]);

  useEffect(()=>{
    let active=true;
    generation.current++;
    setEdits([]);setEditId('');setClips([]);setNext(null);
    setSelection(null);setRendered(null);setPreviewTicket(null);
    activePreview.current=null;setError('');setLoading(true);
    api('/projects/'+encodeURIComponent(projectId)+'/film-time/edits')
      .then(value=>{
        if(!active)return;
        if(value?.format!==FORMAT||value.project_id!==projectId ||
           !Array.isArray(value.edits) || value.worker_started!==false)
          throw new Error('Indexed source list failed custody checks');
        setEdits(value.edits);
        setTruncated(value.truncated===true);
        const wanted=preferredEdit.current;
        setEditId(value.edits.find(item=>item.edit_id===wanted)?.edit_id||
          value.edits[0]?.edit_id||'');
        preferredEdit.current='';
      }).catch(err=>{if(active)setError(err.message);})
      .finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;generation.current++;};
  },[api,projectId,refresh]);

  useEffect(()=>{
    const request=++generation.current;
    setClips([]);setNext(null);setSelection(null);setError('');
    setRendered(null);setRenderError('');setPreviewTicket(null);
    activePreview.current=null;
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
    const request=++generation.current;
    setTickDraft(tick.toString());setBusy(true);setError('');
    setSelection(null);setRendered(null);setPreviewTicket(null);
    activePreview.current=null;
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


  async function importFootage(){
    if(!nativeReady||importing||busy)return;
    const projectAtStart=projectId;
    setImporting(true);setError('');setImportResult(null);
    try{
      const result=await native.pick_and_import_footage(projectId);
      if(projectAtStart!==projectId)return;
      if(result?.format!=='nvp.index_time06.native_import.v1' ||
         !['IMPORTED','DENIED','CANCELLED'].includes(result.status))
        throw new Error('Native source picker returned an unverified import result');
      if(result.status==='IMPORTED'){
        if(result.project_id!==projectId||
           result.original_modified!==false||
           result.original_copied!==false||
           result.source_hash_verified_at_import!==true||
           !result.edit_id||!result.edit_document_sha256)
          throw new Error('Source import custody was not proven');
        preferredEdit.current=result.edit_id;
        setImportResult(result);
        setRefresh(count=>count+1);
      }
    }catch(err){setError(err.message);}
    finally{setImporting(false);}
  }

  async function requestPreview(){
    if(!nativeReady||!native||!selected||!selection||
       selection.status!=='INDEXED_SOURCE_FRAME_SELECTED'||
       nativeBusy||previewTicket)return;
    const request=++generation.current;
    setNativeBusy(true);setRenderError('');setRendered(null);
    const chosen={
      project_id:projectId,edit_id:selected.edit_id,
      edit_revision:selected.revision,
      edit_document_sha256:selected.edit_document_sha256,
      source_tick:selection.requested_film_tick,
      source_frame_zero:selection.source_frame_zero,
      source_pts:selection.source_pts,
    };
    try{
      const answer=await native.request_source_frame_preview(chosen);
      if(request!==generation.current)return;
      if(answer?.format!=='nvp.index_time06.preview_ticket.v1' ||
         !['QUEUED','DENIED'].includes(answer.status))
        throw new Error('Native host refused the source preview protocol');
      if(answer.status==='DENIED'){setRenderError('Preview was not approved.');return;}
      if(answer.edit_document_sha256!==chosen.edit_document_sha256||
         answer.source_frame_zero!==chosen.source_frame_zero||
         answer.source_tick!==chosen.source_tick||
         answer.project_id!==projectId || !answer.ticket_id)
        throw new Error('Native source preview ticket did not match selection');
      activePreview.current=answer.ticket_id;
      setPreviewTicket(answer.ticket_id);
    }catch(err){if(request===generation.current)setRenderError(err.message);}
    finally{if(request===generation.current)setNativeBusy(false);}
  }

  useEffect(()=>{
    if(!native||!previewTicket)return;
    let live=true,pending=false;
    const exact=selection&&selected?{
      edit:selected.edit_id,sha:selected.edit_document_sha256,
      revision:selected.revision,tick:selection.requested_film_tick,
      frame:selection.source_frame_zero,pts:selection.source_pts,
    }:null;
    async function poll(){
      if(!live||pending||!exact)return;
      pending=true;
      try{
        const reply=await native.poll_source_frame_preview(previewTicket);
        if(!live||activePreview.current!==previewTicket)return;
        if(reply?.status==='READY'){
          if(reply.format!=='nvp.index_time06.verified_png.v1' ||
             reply.edit_id!==exact.edit||
             reply.edit_revision!==exact.revision||
             reply.edit_document_sha256!==exact.sha||
             reply.source_tick!==exact.tick||
             reply.source_frame_zero!==exact.frame||
             reply.source_pts!==exact.pts||
             reply.film_master_approved!==false||
             reply.original_modified!==false||
             !reply.image_data_url?.startsWith('data:image/png;base64,')||
             reply.image_data_url.length>17*1024*1024)
            throw new Error('Native verified PNG mismatched original source selection');
          setRendered(reply);setPreviewTicket(null);
        }else if(reply?.status==='RECOVERY_REQUIRED'||reply?.status==='CANCELLED'){
          setRenderError(reply.status==='CANCELLED'
            ?'Preview cancelled without modifying the original.'
            :'Native review failed or needs fenced worker recovery.');
          setPreviewTicket(null);
        }else if(reply?.status!=='QUEUED'){
          throw new Error('Unknown native source preview state');
        }
      }catch(err){
        if(live&&activePreview.current===previewTicket){
          setRenderError(err.message);setPreviewTicket(null);
        }
      }finally{pending=false;}
    }
    poll();
    const timer=setInterval(poll,750);
    return ()=>{live=false;clearInterval(timer);};
  },[native,previewTicket,selection,selected]);

  async function cancelPreview(){
    if(!previewTicket||!native)return;
    try{
      const result=await native.cancel_source_frame_preview(previewTicket);
      if(result?.status!=='DENIED'&&result?.status!=='CANCELLATION_REQUESTED')
        throw new Error('Native source cancellation was not acknowledged');
    }catch(err){setRenderError(err.message);}
  }

  return <section className="card" aria-label="Indexed source Film Time">
    <h2>Indexed footage · Film Time</h2>
    <p className="fineprint">Inspect immutable imported-video placements,
      original timestamps, and held source frames without loading a full
      movie or rendering every timeline frame.</p>
    {nativeReady&&<div className="actions">
      <button disabled={importing} onClick={importFootage}>
        {importing?'Hashing and indexing original footage…':'Import original footage…'}
      </button>
    </div>}
    {!nativeReady&&<p className="fineprint">Footage import and approved
      source picture previews require the installed NVP desktop with
      its native video tools. Browser-only mode is read-only.</p>}
    {importResult?.status==='IMPORTED'&&<p role="status">
      Original indexed: {importResult.indexed_source_frames} measured frames.
      The initial Film Time edit holds {importResult.placed_frames} frames.
      The final source frame remains indexed but unplaced until its exact
      end boundary is known. The original stays on its selected drive.</p>}
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
      <p className="fineprint">Saved duration: {filmTimeClock(selected.duration_tick)}
        {' '}({selected.duration_tick} exact Film Time ticks).
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
          <p>Film Time {filmTimeClock(clip.film_start_tick)}
            {' '}– {filmTimeClock(clip.film_end_tick)}</p>
          <p className="fineprint">Exact ticks:
            {' '}{clip.film_start_tick}–{clip.film_end_tick}</p>
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
          {' '}{filmTimeClock(selection.requested_film_tick)}
          {' '}({selection.requested_film_tick} ticks).
          This is an intentional gap.</p>}
      {selection?.status==='INDEXED_SOURCE_FRAME_SELECTED'&&
        <section aria-label="Selected original indexed frame">
          <h3>Selected original frame</h3>
          <p>{selection.source_id} · frame {selection.source_frame_zero}
            {' '} · original PTS {selection.source_pts}</p>
          <p>Held from {filmTimeClock(selection.frame_film_start_tick)}
            {' '}to {filmTimeClock(selection.frame_film_end_tick)}
            {' '}on the film clock.</p>
          <p className="fineprint">Exact ticks:
            {' '}{selection.frame_film_start_tick}–{selection.frame_film_end_tick}</p>
          {nativeReady&&<div className="actions">
            <button disabled={nativeBusy||Boolean(previewTicket)}
              onClick={requestPreview}>Preview actual source frame</button>
            {previewTicket&&<button onClick={cancelPreview}>
              Cancel source preview</button>}
          </div>}
          {previewTicket&&<p role="status">
            Native source review queued or decoding; original unchanged.</p>}
          {rendered?.status==='READY'&&<figure
            aria-label="Verified original source frame preview">
            <img src={rendered.image_data_url}
              alt="Independently verified unapproved frame from indexed original footage"/>
            <figcaption>Verified native FFmpeg preview · original PTS
              {' '}{rendered.source_pts} · not a final approved film frame</figcaption>
          </figure>}
          {renderError&&<p role="alert">{renderError}</p>}
          <p className="fineprint">Indexed binary seek:
            {' '}{selection.frame_index_pts_reads} SQLite PTS reads.
            Source stamp checked, original bytes not SHA-reverified.
            No decoder launched, and no picture approved.</p>
        </section>}
      {nativeReady && typeof native?.preview_footage_assembly==='function' &&
        typeof native?.save_footage_assembly==='function' &&
        <FilmTimeAssemblyPanel
          key={selected.edit_id+':'+selected.revision}
          projectId={projectId}
          edit={selected} clips={clips} edits={edits} native={native} api={api}
          onSaved={(id)=>{
            preferredEdit.current=id;
            setRendered(null);
            setSelection(null);
            setPreviewTicket(null);
            activePreview.current=null;
            setRefresh(v=>v+1);
          }}/>
      }
    </>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">Imported-video indexing is separate from
      OpenUSD actor/scene events. Source import and PNG review are
      installed-desktop-only native operations with explicit human approval.
      The original is never overwritten. No review image is an approved master.</p>
  </section>;
}
