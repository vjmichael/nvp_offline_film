import React, {useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import './SlateBranchTimelinePane.css';

/* Preview does not commit. Host supplies explicit approval-gated callbacks.
   Browser popout is implemented; native desktop window manager still requires
   installed-app integration, not claimed by this component. */
const ROW=62, WINDOW_ROWS=12;

export default function SlateBranchTimelinePane({
  graphView,activeView=null,draftView=null,catalogPage=null,onLoadMore=null,
  onMakeActive,onInsertBefore,onInsertAfter,onReplace,onPreviewTake,
  onDraftCut,onDraftPaste,onCommitDraft,onRequestDataPreview,
  onRequestGeometryPreview=null,cameraChoices=[],previewPane=null
}) {
  const [group,setGroup]=useState('');
  const [inspection,setInspection]=useState('');
  const [target,setTarget]=useState('');
  const [geometryCamera,setGeometryCamera]=useState('');
  // Film Time is integer source data, not an output-frame index.
  // This local pose cursor cannot mutate a frozen Take or activate a draft.
  const [poseTick,setPoseTick]=useState(null);
  // This clipboard contains only source interval IDs/ticks, never 3D source
  // data, assets, geometry, picture frames or an approved editorial decision.
  const [sourceClipboard,setSourceClipboard]=useState(null);
  const [scrollTop,setScrollTop]=useState(0);
  const [popRoot,setPopRoot]=useState(null);
  const popup=useRef(null);
  const groups=useMemo(()=>{
    if(graphView?.parallel_groups)return graphView.parallel_groups;
    if(!catalogPage?.items)return {};
    const result={};
    for(const node of catalogPage.items){
      (result[node.group_id]??=[]).push(node);
    }
    return result;
  },[graphView,catalogPage]);
  const branchInfo=useMemo(()=>Object.fromEntries(
    Object.values(groups).flat().map(node=>[node.branch_id,node])),[groups]);
  const groupIds=useMemo(()=>Object.keys(groups),[groups]);
  const current=groupIds.includes(group)?group:(groupIds[0]||'');
  const takes=groups[current]||[];
  const sequences=activeView?.sequence||[];
  const draftSegments=draftView?.segments||null;
  const shownSegments=draftSegments||sequences;
  const chosenSegment=shownSegments.find(s=>s.segment_id===target)||null;
  const hasDraft=Boolean(draftSegments);
  const hasCut=Boolean(activeView?.edit_document_sha256);
  const active=new Set(hasCut
    ? sequences.map(s=>s.branch_id)
    : takes.filter(t=>t.selected).map(t=>t.branch_id));
  // In an assembled cut the source take may be used for only a small
  // interval. Paint ONLY those ranges green; the rest stays gray.
  function activeRanges(node) {
    if(!hasCut)return node.selected?[{source_in_tick:node.source_start_tick,
                                     source_out_tick:node.source_end_tick}]:[];
    return sequences.filter(s=>s.branch_id===node.branch_id);
  }
  function rangeStyle(node,segment) {
    const start=node.source_start_tick,end=node.source_end_tick;
    const denom=end-start;
    if(!(Number.isFinite(denom)&&denom>0))return {display:'none'};
    const left=Math.max(0,Math.min(100,100*(segment.source_in_tick-start)/denom));
    const right=Math.max(0,Math.min(100,100*(segment.source_out_tick-start)/denom));
    return {left:left+'%',width:Math.max(0,right-left)+'%'};
  }
  const limit=Math.min(WINDOW_ROWS,Math.max(takes.length,1));
  const first=Math.max(0,Math.min(
    Math.floor(scrollTop/ROW),Math.max(0,takes.length-limit)));
  const visible=takes.slice(first,first+limit+2);

  function inspect(take) {
    setInspection(take.branch_id);
    onPreviewTake?.(take); // inspect only; active edit remains unchanged
  }
  function copySelected() {
    if(!chosenSegment)return;
    const {branch_id,source_in_tick,source_out_tick}=chosenSegment;
    setSourceClipboard({branch_id,source_in_tick,source_out_tick});
  }
  function cutSelected() {
    if(!hasDraft || !chosenSegment || !onDraftCut)return;
    copySelected();
    // A CUT removes a reference from the temporary draft only. It never
    // deletes a frozen Take, nor modifies the active green committed path.
    onDraftCut(chosenSegment.segment_id);
  }
  function pasteAt(side) {
    if(!hasDraft || !chosenSegment || !sourceClipboard || !onDraftPaste)return;
    // Host provides a NEW unique segment ID and checks exact source bounds.
    onDraftPaste(sourceClipboard,chosenSegment.segment_id,side);
  }
  function dock() {
    const w=popup.current; popup.current=null; setPopRoot(null);
    if(w&&!w.closed)w.close();
  }
  function popOut() {
    if(popup.current&&!popup.current.closed){popup.current.focus();return;}
    const w=window.open('','nvp_slate_'+(graphView?.project_id||'project'),
                        'popup=yes,width=1240,height=820,resizable=yes,scrollbars=yes');
    if(!w)return; // blocked; keep embedded
    w.document.title='NVP · Parallel Takes';
    w.document.body.style.margin='0';
    w.document.body.style.background='#14161e';
    // A same-origin detached window must receive the current Vite/bundled
    // stylesheets. This also handles CSS injected as <style> in dev mode.
    document.querySelectorAll('link[rel="stylesheet"],style').forEach(source=>{
      const copy=source.cloneNode(true);
      if(copy.tagName==='LINK'&&source.href)copy.href=source.href;
      w.document.head.appendChild(copy);
    });
    const root=w.document.createElement('div');
    w.document.body.appendChild(root);
    w.addEventListener('pagehide',()=>{popup.current=null;setPopRoot(null);});
    popup.current=w;setPopRoot(root);
  }
  useEffect(()=>()=>{if(popup.current&&!popup.current.closed)popup.current.close();},[]);
  function pane() {
    return <section className="nvp-slate-pane" aria-label="Branching take timeline">
      <div className="nvp-slate-heading">
        <div><strong>{graphView?.scene_label||'Scene'} · Branching take timeline</strong>
          <p>Inspecting a take does not make it active.</p></div>
        <button onClick={popRoot?dock:popOut}>
          {popRoot?'Dock timeline':'Detach window'}</button>
      </div>
      <div className="nvp-slate-toolbar"><label>Parallel group
        <select value={current} onChange={e=>{
          setGroup(e.target.value);setScrollTop(0);setInspection('');
        }}>
          {groupIds.map(g=><option key={g} value={g}>{g}</option>)}
        </select></label><span>{takes.length} shown
          {catalogPage?.branch_count!=null?' of '+catalogPage.branch_count:''} takes and camera views</span></div>
      <div className="nvp-slate-gridhead">
        <span>Digital slate / take</span>
        <span>Parent-child lineage</span><span>Actions</span></div>
      <div className="nvp-slate-scroll" onScroll={e=>setScrollTop(e.currentTarget.scrollTop)}
           style={{height:Math.min(ROW*limit,744)}}>
        <div className="nvp-slate-vertical-dashes" aria-hidden="true"/>
        <div style={{height:ROW*first}}/>
        {visible.map(t=>{
          const isActive=active.has(t.branch_id);
          const isFocus=inspection===t.branch_id;
          return <div className={'nvp-slate-entry'+(isFocus?' inspected':'')}
                      style={{height:ROW}} key={t.branch_id}>
            <button className="nvp-slate-name" onClick={()=>inspect(t)}
                    aria-pressed={isFocus}>
              <strong>{t.slate?.shot||'Shot'} · Take {t.slate?.take_number||'?'}</strong>
              <small>{t.slate?.wild?'Wild take · ':''}Camera {t.slate?.camera||'—'} · {t.kind}</small>
            </button>
            <div className="nvp-slate-track"
                 aria-label={isActive?'Active source':'Available alternative'}>
              <i className="nvp-slate-line gray"/>
              {activeRanges(t).map((range,i)=><i key={i}
                  className="nvp-slate-range green"
                  style={rangeStyle(t,range)}/>)}
              {t.parent_id&&<i className="nvp-slate-dash-marker" title={'Parent '+t.parent_id}/>}
              {isFocus&&<span>Inspecting</span>}
            </div>
            <div className="nvp-slate-actions">
              <button onClick={()=>inspect(t)}>Inspect</button>
              <button disabled={!onMakeActive||isActive}
                      onClick={()=>onMakeActive(t)}>Make Active</button>
              <button disabled={!onInsertBefore||!target}
                      onClick={()=>onInsertBefore(t,target)}>Before</button>
              <button disabled={!onInsertAfter||!target}
                      onClick={()=>onInsertAfter(t,target)}>After</button>
              <button disabled={!onReplace||!target}
                      onClick={()=>onReplace(t,target)}>Replace</button>
            </div>
          </div>;
        })}
        <div style={{height:Math.max(0,takes.length-first-visible.length)*ROW}}/>
      </div>
      {catalogPage?.next_after_index!=null&&
        <button className="nvp-slate-more" disabled={!onLoadMore}
          onClick={()=>onLoadMore(catalogPage.next_after_index)}>
          Load more takes
        </button>}
      <div className="nvp-slate-legend">
        <span><i className="nvp-slate-swatch green"/>Committed</span>
        <span><i className="nvp-slate-swatch gray"/>Available</span>
        <span><i className="nvp-slate-swatch focus"/>Inspecting only</span>
        <span><i className="nvp-slate-swatch dashed"/>Straight dashed parent line</span>
      </div>
      <h3>{hasDraft?'Uncommitted draft assembly':'Active assembled cut'}</h3>
      {hasDraft&&<p className="nvp-slate-info">
        Draft changes are not active. The committed source ranges above
        remain green until the director authorizes the new cut.
      </p>}
      {(hasDraft||hasCut)?<div className="nvp-slate-segments">
        {shownSegments.map(segment=>{
          const node=branchInfo[segment.branch_id];
          const semantic=node?.semantic||{};
          const slate=node?.slate||{};
          const cues=(semantic.moment_cues||[]).filter(cue=>
            cue.source_out_tick>segment.source_in_tick &&
            cue.source_in_tick<segment.source_out_tick);
          const observedBeats=[...new Set([
            ...(semantic.beat_ids||[]),
            ...cues.flatMap(cue=>cue.beat_ids||[])])];
          const observedEmotions=[...new Set([
            ...(semantic.emotion_tags||[]),
            ...cues.flatMap(cue=>cue.emotion_tags||[])])];
          const dialogueIds=[...new Set([
            ...(semantic.dialogue_ids||[]),
            ...cues.flatMap(cue=>cue.dialogue_ids||[])])];
          const observations=(semantic.ai_observations||[])
            .filter(obs=>obs.status==='UNREVIEWED_AI_PROPOSAL' &&
              obs.source_out_tick>segment.source_in_tick &&
              obs.source_in_tick<segment.source_out_tick);
          return <button key={segment.segment_id}
            className={'nvp-slate-assembly-card'+(target===segment.segment_id?' target':'')}
            onClick={()=>{setTarget(segment.segment_id);setPoseTick(null);}}>
            <span className="nvp-slate-card-label">Scene {slate.scene||graphView?.scene_label||'—'} · Shot {slate.shot||'—'}</span>
            <strong>{slate.wild?'Wild · ':''}Take {slate.take_number||'?'} · Camera {slate.camera||'—'}</strong>
            <span className="nvp-slate-card-sub">{semantic.shot_type||node?.kind||'Source Take'} · {segment.branch_id}</span>
            <span className="nvp-slate-card-time">Edit {segment.timeline_start_tick}–{segment.timeline_end_tick} ticks</span>
            <span className="nvp-slate-card-time">Source {segment.source_in_tick}–{segment.source_out_tick} ticks</span>
            {(observedBeats.length>0||observedEmotions.length>0)&&
              <span className="nvp-slate-card-tags">
                {[...observedBeats,...observedEmotions].slice(0,4).join(' · ')}
              </span>}
            {dialogueIds.length>0&&
              <span className="nvp-slate-card-notes">
                Dialogue cues: {dialogueIds.slice(0,3).join(', ')}
              </span>}
            {semantic.director_rating!=null&&
              <span>Director rating {semantic.director_rating}/5</span>}
            {semantic.technical_status&&semantic.technical_status!=='unknown'&&
              <span>Technical: {semantic.technical_status}</span>}
            {semantic.director_notes&&
              <span className="nvp-slate-card-notes" title={semantic.director_notes}>
                Director: {semantic.director_notes}
              </span>}
            {segment.incoming_transition?.requires_continuity_review&&
              <span className="nvp-slate-card-warning">Continuity review at incoming cut</span>}
            {observations.length>0&&
              <span className="nvp-slate-card-ai" title={observations[0].summary}>
                AI suggestion · unreviewed: {observations[0].summary}
              </span>}
            <span className="nvp-slate-card-id">Segment {segment.segment_id}</span>
          </button>;
        })}
      </div>:<p className="nvp-slate-info">No assembled cut is committed in this viewer.</p>}
      <div className="nvp-slate-draft-tools" aria-label="Reference-only draft editing">
        <button disabled={!chosenSegment} onClick={copySelected}>Copy reference</button>
        <button disabled={!hasDraft||!chosenSegment||!onDraftCut}
                onClick={cutSelected}>Cut draft reference</button>
        <button disabled={!hasDraft||!chosenSegment||!sourceClipboard||!onDraftPaste}
                onClick={()=>pasteAt('before')}>Paste before</button>
        <button disabled={!hasDraft||!chosenSegment||!sourceClipboard||!onDraftPaste}
                onClick={()=>pasteAt('after')}>Paste after</button>
        <button disabled={!hasCut||hasDraft||!chosenSegment||!onRequestDataPreview}
                onClick={()=>onRequestDataPreview(chosenSegment.timeline_start_tick)}>
          Preview source data</button>
        {onRequestGeometryPreview && <>
          {chosenSegment && !hasDraft &&
            <label className="nvp-slate-pose-time">
              Performance time · {Math.min(
                chosenSegment.timeline_end_tick-1,
                Math.max(chosenSegment.timeline_start_tick,
                  poseTick??chosenSegment.timeline_start_tick))} ticks
              <input type="range" aria-label="Performance time"
                min={chosenSegment.timeline_start_tick}
                max={chosenSegment.timeline_end_tick-1}
                step={1}
                value={Math.min(
                  chosenSegment.timeline_end_tick-1,
                  Math.max(chosenSegment.timeline_start_tick,
                    poseTick??chosenSegment.timeline_start_tick))}
                onChange={event=>setPoseTick(Number(event.target.value))}/>
            </label>}
          <label className="nvp-slate-camera-choice">
            Authored camera
            <select aria-label="Authored camera" value={geometryCamera}
              onChange={e=>setGeometryCamera(e.target.value)}>
              <option value="">Use sole native camera</option>
              {cameraChoices.map(camera=>
                <option key={camera.path} value={camera.path}>
                  {camera.label||camera.path}
                </option>)}
            </select>
          </label>
          <button className="nvp-slate-render-geometry"
            disabled={!hasCut||hasDraft||!chosenSegment||
              cameraChoices.length>1&&!geometryCamera}
            onClick={()=>onRequestGeometryPreview({
              presentation:'geometry',
              film_tick:Math.min(chosenSegment.timeline_end_tick-1,
                Math.max(chosenSegment.timeline_start_tick,
                  poseTick??chosenSegment.timeline_start_tick)),
              segment_id:chosenSegment.segment_id,
              edit_document_sha256:activeView.edit_document_sha256,
              camera_path:geometryCamera||null,
            })}>
            Render authored 3D preview
          </button>
        </>}
        <button className="nvp-slate-commit" disabled={!hasDraft||!onCommitDraft}
                onClick={()=>onCommitDraft(draftView)}>
          Make draft active
        </button>
      </div>
      {previewPane && <aside className="nvp-slate-proxy-preview"
        aria-label="On-demand low-resolution preview">
        <strong>{previewPane.presentation==='geometry'
          ? 'Authored OpenUSD geometry preview'
          : 'Low-fi blocking preview'}</strong>
        {previewPane.status==='QUEUED' &&
          <p>Preview queued. The frozen 3D source is unchanged.</p>}
        {previewPane.status==='FAILED' &&
          <p>Preview unavailable; original source data are untouched.</p>}
        {(previewPane.status==='READY'||previewPane.status==='CACHE_HIT') &&
         previewPane.edit_document_sha256===activeView?.edit_document_sha256 &&
         previewPane.segment_id===target &&
         typeof previewPane.image_data_url==='string' &&
         previewPane.image_data_url.startsWith('data:image/png;base64,') &&
         previewPane.image_data_url.length<=12*1024*1024
          ? <img src={previewPane.image_data_url}
                 alt={previewPane.presentation==='geometry'
                   ? "Authored OpenUSD camera and geometry preview; weighted body skinning is shown when sourced, not final film"
                   : "Director's low-resolution geometry-proxy composition, not final film picture"}
                 loading="lazy"/>
          : <p>Preview not ready for this selected committed segment.</p>}
        <small>{previewPane.presentation==='geometry'
          ? 'Authored geometry · native camera · supported weighted skinning · no final master approval'
          : 'Proxy geometry only · SHA-pinned frozen Take · no master approval'}</small>
        {previewPane.presentation==='geometry' &&
         (previewPane.unmeshed_actors?.length>0) &&
          <p className="nvp-slate-fidelity-notice">
            Incomplete source presentation: at least one actor lacks supported
            mesh geometry. Review source coverage before approval.
          </p>}
      </aside>}
      <p className="nvp-slate-info">{inspection
          ? 'Inspecting '+inspection+'. Active source colors have not changed.'
          : 'Click a take to inspect; Make Active is an explicit editor decision.'}</p>
      <p className="nvp-slate-info">The host must supply authorized commit and splice operations. This view itself cannot publish a FilmIndex revision.</p>
    </section>;
  }
  return popRoot?<><div className="nvp-slate-placeholder">
      Timeline open in separate window.
      <button onClick={()=>popup.current?.focus()}>Show window</button>
      <button onClick={dock}>Dock</button>
    </div>{createPortal(pane(),popRoot)}</>:pane();
}
