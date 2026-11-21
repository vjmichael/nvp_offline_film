import React,{useEffect,useRef,useState} from 'react';
import './director-editorial-sections.css';
import {DirectorPagedMedia,DirectorDeliveryReview} from './DirectorPagedMedia.jsx';
const FORMAT='nvp.g07.paged_active_edit.v1', LIMIT=32;
function clock(t){try{const n=BigInt(t)/7056000000n;return `${n/3600n}:${String(n/60n%60n).padStart(2,'0')}:${String(n%60n).padStart(2,'0')}`;}catch{return '—';}}
export default function DirectorPagedTimeline(props){
  return <Timeline key={`${props.projectId}:${props.encrypted}:${props.edit.revision}:${props.edit.active_digest}`} {...props}/>;
}
function Timeline({projectId,encrypted,edit,api,sceneTitles={},disabled=false,renderPicture}){
  const [first,setFirst]=useState(0),[page,setPage]=useState(null),[error,setError]=useState(false),[reload,setReload]=useState(0),[jump,setJump]=useState(''),[target,setTarget]=useState(null);
  const [selection,setSelection]=useState(null);
  const listRef=useRef(null);
  const base='/api/projects/'+encodeURIComponent(projectId)+(encrypted?'/live':'')+'/edit/sections/active-page';
  useEffect(()=>{
    const controller=new AbortController();let live=true;setPage(null);setError(false);
    api(base,'POST',{revision:edit.revision,digest:edit.active_digest,first,limit:LIMIT},controller.signal).then(out=>{
      if(!live||controller.signal.aborted)return;
      if(out?.format!==FORMAT||out.project_id!==projectId||out.revision!==edit.revision||out.active_digest!==edit.active_digest||out.first!==first||out.total!==edit.clip_count||out.render_approved!==false||!Array.isArray(out.items)||out.items.length!==Math.min(LIMIT,edit.clip_count-first)||out.items.some((x,i)=>x.index!==first+i||typeof x.start_tick!=='string'||typeof x.end_tick!=='string'||!/^(0|[1-9][0-9]{0,18})$/.test(x.start_tick)||!/^[1-9][0-9]{0,18}$/.test(x.end_tick)||BigInt(x.start_tick)>=BigInt(x.end_tick)||BigInt(x.end_tick)>BigInt(edit.duration_tick))||out.next_first!==(first+LIMIT<edit.clip_count?first+LIMIT:null))throw Error('Changed edit');
      setPage(out);
    }).catch(()=>{if(live&&!controller.signal.aborted)setError(true);});
    return()=>{live=false;controller.abort();};
  },[base,projectId,edit.revision,edit.active_digest,edit.clip_count,first,reload,api]);
  useEffect(()=>{
    const list=listRef.current;if(!page||!list)return;
    const row=target===null?null:list.querySelector(`[data-cut-index="${target}"]`);
    list.scrollTop=row?Math.max(0,row.offsetTop-(list.clientHeight-row.offsetHeight)/2):0;
  },[page,target]);
  const validJump=/^[0-9]+$/.test(jump)&&Number.isSafeInteger(Number(jump))&&Number(jump)>=1&&Number(jump)<=edit.clip_count;
  function go(n,selected=null){setSelection(null);setTarget(selected);setPage(null);setFirst(n);setReload(r=>r+1);}
  return <section className="film-sections-workspace film-active-timeline" aria-label="Chapter timeline">
    <div className="film-editor-section-heading"><div><h3>{edit.title}</h3><p className="film-muted">{edit.clip_count.toLocaleString()} cuts · {clock(edit.duration_tick)}</p></div><span>Current edit</span></div>
    <p className="film-muted">Browse the chapter timeline or organize a new arrangement below. {renderPicture?'Choose a cut to preview its recorded scene. Individual shot changes and final export are not yet available.':'Picture preview, individual shot changes and export are not yet available for this edit.'}</p>
    {error?<p role="alert">This part of the edit could not be reopened. <button className="film-secondary" disabled={disabled} onClick={()=>go(first,target)}>Try again</button></p>:!page?<p role="status">Opening cuts…</p>:<ol ref={listRef} className="film-active-cut-list" aria-label="Current edit cuts" start={first+1}>{page.items.map(row=><li key={row.index} data-cut-index={row.index} className={row.index===target?'film-active-cut-target':undefined} aria-current={row.index===target?'true':undefined}><span className="film-active-cut-number">{row.index+1}</span><div>{renderPicture?<button type="button" className="film-cut-preview-button" aria-label={`Preview cut ${row.index+1}`} disabled={disabled} onClick={()=>{setSelection(row);setTarget(row.index);}}>{sceneTitles[row.scene_id]||'Recorded scene'}</button>:<strong>{sceneTitles[row.scene_id]||'Recorded scene'}</strong>}<small>{row.transition==='dissolve'?'Soft transition':'Straight cut'}</small></div><span className="film-active-cut-time">{clock(row.start_tick)} – {clock(row.end_tick)}</span></li>)}</ol>}
    {renderPicture&&<DirectorPagedMedia key={selection?String(selection.index):'none'} projectId={projectId} encrypted={encrypted} edit={edit} selection={selection} api={api} renderPicture={renderPicture}/>}
    <div className="film-sections-pagination"><button className="film-secondary" disabled={disabled||first===0} onClick={()=>go(Math.max(0,first-LIMIT))}>Previous</button><span aria-live="polite">Cuts {first+1}–{Math.min(first+LIMIT,edit.clip_count)} of {edit.clip_count}</span><button className="film-secondary" disabled={disabled||!page||page.next_first==null} onClick={()=>go(page.next_first)}>Next</button></div>
    <form className="film-active-jump" onSubmit={e=>{e.preventDefault();if(validJump&&!disabled)go(Math.floor((Number(jump)-1)/LIMIT)*LIMIT,Number(jump)-1);}}><label>Go to cut <input inputMode="numeric" value={jump} onChange={e=>setJump(e.target.value)} disabled={disabled}/></label><button className="film-secondary" disabled={disabled||!validJump}>Go</button></form>
    {renderPicture&&<DirectorDeliveryReview projectId={projectId} encrypted={encrypted} edit={edit} api={api}/>}
  </section>;
}
