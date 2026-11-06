import React, {useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import './SlateBranchTimelinePane.css';

/* Preview does not commit. Host supplies explicit approval-gated callbacks.
   Browser popout is implemented; native desktop window manager still requires
   installed-app integration, not claimed by this component. */
const ROW=62, WINDOW_ROWS=12;

export default function SlateBranchTimelinePane({
  graphView,activeView=null,onMakeActive,onInsertBefore,onInsertAfter,
  onReplace,onPreviewTake
}) {
  const [group,setGroup]=useState('');
  const [inspection,setInspection]=useState('');
  const [target,setTarget]=useState('');
  const [scrollTop,setScrollTop]=useState(0);
  const [popRoot,setPopRoot]=useState(null);
  const popup=useRef(null);
  const groups=graphView?.parallel_groups || {};
  const groupIds=useMemo(()=>Object.keys(groups),[groups]);
  const current=groupIds.includes(group)?group:(groupIds[0]||'');
  const takes=groups[current]||[];
  const sequences=activeView?.sequence||[];
  const hasCut=Boolean(activeView?.edit_document_sha256);
  const active=new Set(hasCut
    ? sequences.map(s=>s.branch_id)
    : takes.filter(t=>t.selected).map(t=>t.branch_id));
  const limit=Math.min(WINDOW_ROWS,Math.max(takes.length,1));
  const first=Math.max(0,Math.min(
    Math.floor(scrollTop/ROW),Math.max(0,takes.length-limit)));
  const visible=takes.slice(first,first+limit+2);

  function inspect(take) {
    setInspection(take.branch_id);
    onPreviewTake?.(take); // inspect only; active edit remains unchanged
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
    const stylesheet=document.createElement('link');
    stylesheet.rel='stylesheet';
    stylesheet.href=new URL('./SlateBranchTimelinePane.css',import.meta.url).href;
    w.document.head.appendChild(stylesheet);
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
        </select></label><span>{takes.length} takes and camera views</span></div>
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
              <i className={'nvp-slate-line '+(isActive?'green':'gray')}/>
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
      <div className="nvp-slate-legend">
        <span><i className="nvp-slate-swatch green"/>Committed</span>
        <span><i className="nvp-slate-swatch gray"/>Available</span>
        <span><i className="nvp-slate-swatch focus"/>Inspecting only</span>
        <span><i className="nvp-slate-swatch dashed"/>Straight dashed parent line</span>
      </div>
      <h3>Active assembled cut</h3>
      {hasCut?<div className="nvp-slate-segments">
        {sequences.map(segment=><button key={segment.segment_id}
          className={target===segment.segment_id?'target':''}
          onClick={()=>setTarget(segment.segment_id)}>
          {segment.branch_id}<small>{segment.segment_id}</small></button>)}
      </div>:<p className="nvp-slate-info">No assembled cut is committed in this viewer.</p>}
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
