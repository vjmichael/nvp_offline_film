import React,{useEffect,useRef,useState} from 'react';
import './director-editorial-sections.css';

const FORMAT='nvp.g07.sections.v1';
const LIMIT=32;
const same=(a,b)=>a?.kind===b?.kind&&a?.digest===b?.digest&&a?.revision===b?.revision&&a?.section_id===b?.section_id&&a?.first===b?.first&&a?.count===b?.count&&a?.scene_id===b?.scene_id;
const refOf=x=>x.kind==='scene'?{kind:'scene',scene_id:x.scene_id,revision:x.revision,digest:x.digest}:x.kind==='section'?{kind:'section',section_id:x.section_id,digest:x.digest}:{kind:'edit',revision:x.revision,digest:x.digest,...(x.first==null?{}:{first:x.first,count:x.count})};
const sourceKey=x=>JSON.stringify(x);
function spanClock(row,item){try{return clock(row.end_tick?String(BigInt(row.end_tick)-BigInt(row.start_tick)):item.duration_tick);}catch{return '—';}}
function clock(t){try{const n=BigInt(t)/7056000000n;return `${n/3600n}:${String(n/60n%60n).padStart(2,'0')}:${String(n%60n).padStart(2,'0')}`;}catch{return '—';}}

export default function DirectorEditorialSections(props){return <Sections key={`${props.projectId}:${!!props.encrypted}`} {...props}/>;}
function Sections({projectId,encrypted=false,api,activeRevision=null,onActivated,disabled=false,beginAction,endAction,browseOnly=false}){
  const base='/api/projects/'+encodeURIComponent(projectId)+(encrypted?'/live':'')+'/edit/sections';
  const [open,setOpen]=useState(false),[family,setFamily]=useState(browseOnly?'scenes':'sections'),[cursors,setCursors]=useState([null]),[sceneCursors,setSceneCursors]=useState([null]);
  const [stack,setStack]=useState([]),[first,setFirst]=useState(0),[page,setPage]=useState(null),[loading,setLoading]=useState(false);
  const [title,setTitle]=useState(''),[chosen,setChosen]=useState([]),[preview,setPreview]=useState(null),[activation,setActivation]=useState(null);
  const [sliceFirst,setSliceFirst]=useState('1'),[sliceLast,setSliceLast]=useState('1');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[reload,setReload]=useState(0);
  const requestRef=useRef(0),mounted=useRef(true),busyRef=useRef(false);
  const selected=stack.at(-1)||null,after=cursors.at(-1);
  const revisionRef=useRef(activeRevision);revisionRef.current=activeRevision;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;requestRef.current++;};},[base]);
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController(),seq=++requestRef.current;
    setPage(null);setLoading(true);setError('');setActivation(null);
    const query=new URLSearchParams({family,limit:String(LIMIT)});if(after!==null)query.set('after',String(after));
    const valid=()=>mounted.current&&!controller.signal.aborted&&requestRef.current===seq;
    const pending=selected?api(base+'/page','POST',{selection:refOf(selected),first,limit:LIMIT,...(selected.kind==='scene'?{after:sceneCursors.at(-1)}:{})},controller.signal):api(base+'?'+query,'GET',undefined,controller.signal);
    pending.then(out=>{
      if(!valid())return;
      if(out?.format!==FORMAT||out.project_id!==projectId||out.render_approved!==false||!Array.isArray(out.items)||out.items.length>LIMIT||
        (selected?(!same(selected,out.selection)||out.first!==first):out.family!==family))throw Error('Wrong section');
      setPage(out);
    }).catch(()=>{if(valid())setError('This section could not be opened. Your saved edit is unchanged.');})
      .finally(()=>{if(valid())setLoading(false);});
    return()=>{controller.abort();};
  },[base,projectId,api,open,family,after,selected,first,reload,sceneCursors]);
  useEffect(()=>{setActivation(null);},[activeRevision]);
  function clearPage(){requestRef.current++;setPage(null);setActivation(null);}
  function select(item){if(busyRef.current)return;clearPage();setStack(s=>[...s,item]);setFirst(0);setSceneCursors([null]);setSliceFirst('1');setSliceLast(String(item.clip_count||1));}
  function switchFamily(key){if(busyRef.current||(key===family&&!selected&&after===null))return;clearPage();setFamily(key);setStack([]);setCursors([null]);setFirst(0);}
  function changeDraft(fn){setPreview(null);setChosen(fn);}
  function move(index,delta){changeDraft(old=>{const a=[...old],j=index+delta;if(j>=0&&j<a.length)[a[index],a[j]]=[a[j],a[index]];return a;});}
  function add(item,from=1,to=item.clip_count){
    if(!['edit','section'].includes(item.kind)||!Number.isInteger(from)||!Number.isInteger(to)||from<1||to<from||to>item.clip_count)return;
    const source=item.kind==='section'?refOf(item):{...refOf(item),first:(item.first||0)+from-1,count:to-from+1};
    changeDraft(old=>old.length>=64||old.some(x=>sourceKey(x.source)===sourceKey(source))?old:[...old,{source,label:item.label+(item.kind==='edit'?` · cuts ${(item.first||0)+from}–${(item.first||0)+to}`:'')}]);
  }
  async function operation(path,body,apply){
    if(busyRef.current||disabled||(beginAction&&!beginAction()))return;busyRef.current=true;setBusy(true);setError('');setNotice('');
    const seq=requestRef.current;
    try{const result=await api(base+path,'POST',body);
      if(!mounted.current||seq!==requestRef.current)return;
      if(result?.format!==FORMAT||result.project_id!==projectId||result.render_approved!==false)throw Error('Wrong film');
      await apply(result);
    }catch{if(mounted.current&&requestRef.current===seq)setError('This change could not be confirmed. Reopen the saved edit before trying again.');}
    finally{busyRef.current=false;endAction?.();if(mounted.current)setBusy(false);}
  }
  const composition=()=>({title:title.trim(),children:chosen.map(x=>x.source)});
  const activationBody=()=>({section_id:selected.section_id,digest:selected.digest,expected_revision:activeRevision});
  const usable=page&&!loading;
  const pagedActivation=selected?.kind==='section'&&(selected.clip_count>250||Number(page?.selection?.duration_tick??selected.duration_tick)>28800*7056000000);
  return <details className="film-sections" onToggle={e=>{const now=e.currentTarget.open;if(!now&&busyRef.current){e.currentTarget.open=true;return;}setOpen(now);if(!now){clearPage();setPreview(null);}}}>
    <summary onClick={e=>{if(busy)e.preventDefault();}}>{browseOnly?'Browse scenes and takes':'Organize film sections'}</summary>
    {open&&<section aria-label={browseOnly?"Browse scenes and takes":"Organize film sections"} className="film-sections-workspace">
      <p className="film-muted">{browseOnly?"Find original material from your scenes.":"Arrange saved cuts into acts or chapters. Your original footage and earlier edits stay intact."}</p>
      <div className={"film-sections-grid"+(browseOnly?" browse-only":"")}><div className="film-sections-library">
      <h4>Film material</h4>
      <div className="film-sections-tabs" role="group" aria-label="Browse saved film material">
        {(browseOnly?[['scenes','Scenes'],['takes','Recorded takes']]:[['sections','Sections'],['edits','Saved edits'],['scenes','Scenes'],['takes','Recorded takes']]).map(([key,label])=><button key={key} type="button" className="film-secondary" aria-pressed={family===key} disabled={busy} onClick={()=>switchFamily(key)}>{label}</button>)}
      </div>
      {selected&&<><button type="button" className="film-secondary" disabled={busy} onClick={()=>{clearPage();setStack(s=>s.slice(0,-1));setFirst(0);}}>Back</button><h4>{selected.label}</h4></>}
      {loading&&<p role="status">Opening your film material…</p>}
      {error&&<p role="alert">{error} <button type="button" className="film-secondary" disabled={busy} onClick={()=>setReload(x=>x+1)}>Try again</button></p>}
      {notice&&<p role="status">{notice}</p>}
      {usable&&page.active_section&&<p className="film-muted">Active edit: {page.active_section.label}</p>}
      {usable&&<>
        {!page.items.length&&<p className="film-muted">Nothing saved on this page.</p>}
        <ul className="film-sections-list" aria-label="Saved film material">{page.items.map((row,i)=>{
          const item=row.source?{...row.source,label:row.label,clip_count:row.clip_count}:row;
          const drill=item.kind==='section'||item.kind==='edit'||item.kind==='scene';
          return <li key={i}><div className="film-sections-item">
            {drill?<button type="button" className="film-sections-open" disabled={busy} onClick={()=>select(item)}>{item.label}</button>:<span>{item.label}</span>}
            <div className="film-sections-meta">{item.clip_count!=null&&<span>{item.clip_count} cuts</span>}{(row.end_tick||item.duration_tick)&&<span>{spanClock(row,item)}</span>}</div></div>
            {!browseOnly&&!selected&&drill&&item.clip_count>0&&<button type="button" className="film-secondary film-sections-add" disabled={busy||disabled||chosen.length>=64} onClick={()=>add(item)}>Add to section</button>}
          </li>;
        })}</ul>
        <div className="film-sections-pagination" role="group" aria-label="Section pages">
          <button type="button" className="film-secondary" disabled={busy||(selected?.kind==='scene'?sceneCursors.length===1:selected?first===0:cursors.length===1)} onClick={()=>{clearPage();if(selected?.kind==='scene')setSceneCursors(a=>a.slice(0,-1));else if(selected)setFirst(x=>Math.max(0,x-LIMIT));else setCursors(a=>a.slice(0,-1));}}>Previous</button>
          <button type="button" className="film-secondary" disabled={busy||(selected&&selected.kind!=='scene'?page.next_first==null:page.next_after==null)} onClick={()=>{clearPage();if(selected?.kind==='scene')setSceneCursors(a=>[...a,page.next_after].slice(-64));else if(selected)setFirst(page.next_first);else setCursors(a=>[...a,page.next_after].slice(-64));}}>Next</button>
        </div>
        {!browseOnly&&selected?.kind==='edit'&&page.selection.clip_count>0&&<div className="film-sections-range" role="group" aria-label="Choose cut range">
          <label>First cut <input type="number" min="1" max={page.selection.clip_count} value={sliceFirst} onChange={e=>setSliceFirst(e.target.value)}/></label>
          <label>Last cut <input type="number" min="1" max={page.selection.clip_count} value={sliceLast} onChange={e=>setSliceLast(e.target.value)}/></label>
          <button type="button" className="film-secondary" disabled={busy||disabled||!(Number(sliceFirst)>=1&&Number(sliceLast)>=Number(sliceFirst)&&Number(sliceLast)<=page.selection.clip_count&&Number.isInteger(Number(sliceFirst))&&Number.isInteger(Number(sliceLast)))} onClick={()=>add({...selected,clip_count:page.selection.clip_count},Number(sliceFirst),Number(sliceLast))}>Add cut range</button>
        </div>}
        {!browseOnly&&selected?.kind==='section'&&onActivated&&activeRevision!==null&&<div>
          {!activation?<button type="button" className="film-secondary" disabled={busy||disabled} onClick={()=>operation(pagedActivation?'/paged-activation-preview':'/activation-preview',activationBody(),r=>{if(r.section_id!==selected.section_id||r.section_digest!==selected.digest||r.expected_revision!==activeRevision||revisionRef.current!==activeRevision||typeof r.approval_digest!=='string')throw Error();setActivation(r);})}>Review as active edit</button>:<div className="film-sections-review" aria-label="Review grouped edit"><p>Use {selected.label} as the current edit? {activation.clip_count} cuts · {clock(activation.duration_tick)}. Previous edits are kept.{activation.paged&&' You can browse the chapter timeline. Sampled scene previews are available; final export is not yet available for this arrangement.'}</p>
            <button className="film-primary" type="button" disabled={busy||disabled||activation.expected_revision!==activeRevision} onClick={()=>operation(activation.paged?'/paged-activate':'/activate',{...activationBody(),approval_digest:activation.approval_digest},async r=>{if(r.revision!==activeRevision+1||r.original_sources_unchanged!==true)throw Error();setActivation(null);await onActivated(r.revision);setNotice('Your grouped edit is now active.');setReload(x=>x+1);})}>Use this edit</button>
            <button className="film-secondary" type="button" disabled={busy} onClick={()=>setActivation(null)}>Cancel</button></div>}
        </div>}
      </>}
      </div>{!browseOnly&&<div className="film-sections-draft"><h4>New section <span>{chosen.length} selections</span></h4>
      <label>Section name <input placeholder="e.g. Act One" value={title} maxLength={120} disabled={busy||disabled} onChange={e=>{setTitle(e.target.value);setPreview(null);}}/></label>
      {!chosen.length&&<p className="film-sections-empty">Open a saved edit or section and add the cuts you want here.</p>}
      <ol className="film-sections-order" aria-label="Section order">{chosen.map((item,i)=><li key={sourceKey(item.source)}><span>{i+1}. {item.label}</span><div className="film-sections-row-actions"><button type="button" className="film-secondary" aria-label={`Move ${i+1} up`} disabled={busy||disabled||i===0} onClick={()=>move(i,-1)}>↑</button><button type="button" className="film-secondary" aria-label={`Move ${i+1} down`} disabled={busy||disabled||i===chosen.length-1} onClick={()=>move(i,1)}>↓</button><button type="button" className="film-secondary" aria-label={`Remove ${i+1}`} disabled={busy||disabled} onClick={()=>changeDraft(old=>old.filter((_,j)=>j!==i))}>Remove</button></div></li>)}</ol>
      {!preview?<button type="button" className="film-secondary" disabled={busy||disabled||!title.trim()||!chosen.length} onClick={()=>operation('/preview',composition(),r=>{if(r.title!==title.trim()||typeof r.digest!=='string')throw Error();setPreview(r);})}>Review section</button>:<div className="film-sections-review" aria-label="Review new section"><p>{preview.title} · {preview.clip_count} cuts · {clock(preview.duration_tick)}. Saving does not change the active edit.</p><button className="film-primary" type="button" disabled={busy||disabled} onClick={()=>operation('/save',{...composition(),digest:preview.digest},r=>{if(r.selection?.label!==preview.title)throw Error();setPreview(null);setChosen([]);setTitle('');setNotice('Section saved.');clearPage();setFamily('sections');setStack([]);setCursors([null]);setFirst(0);setReload(n=>n+1);})}>Save section</button><button type="button" className="film-secondary" disabled={busy} onClick={()=>setPreview(null)}>Cancel</button></div>}
      </div>}
      </div>
    </section>}
  </details>;
}
