import React,{useEffect,useState} from 'react';

const FORMAT='nvp.slate.filmmaker_navigation.v1';
const choices=[['scenes','Scenes'],['takes','Takes'],['edit','Edit sections']];
const pageSize=32;
const same=(a,b)=>a?.object_id===b?.object_id&&a?.revision===b?.revision&&a?.document_sha256===b?.document_sha256;
function time(tick,rate){
  try{const n=BigInt(tick)/BigInt(rate);return `${n/3600n}:${String(n/60n%60n).padStart(2,'0')}:${String(n%60n).padStart(2,'0')}`;}
  catch{return '';}
}
export default function DirectorOriginalSections({projectId,api}){
  const [opened,setOpened]=useState(false);
  const [family,setFamily]=useState('scenes');
  const [selection,setSelection]=useState([]);
  const [cursor,setCursor]=useState([null]);
  const [first,setFirst]=useState(0);
  const [page,setPage]=useState(null);
  const [error,setError]=useState('');
  const [attempt,setAttempt]=useState(0);
  const [loading,setLoading]=useState(false);
  const selected=selection.at(-1)||null;
  const after=cursor.at(-1);
  useEffect(()=>{
    if(!opened)return;
    let active=true;const controller=new AbortController();
    setLoading(true);setPage(null);setError('');
    const params=new URLSearchParams({family,limit:String(pageSize)});
    let url='/api/projects/'+encodeURIComponent(projectId)+'/film/sections';
    if(selected){url+='/'+encodeURIComponent(selected.object_id);params.set('revision',String(selected.revision));params.set('digest',selected.document_sha256);params.set('first',String(first));}
    else if(after!==null)params.set('after',after);
    api(url+'?'+params,'GET',undefined,controller.signal).then(result=>{
      if(!active)return;
      if(result?.format!==FORMAT||result.project_id!==projectId||result.family!==family||result.source_modified!==false||!Array.isArray(result.items)||result.items.length>pageSize||
          (selected&&(!same(selected,result.selection)||result.first!==first)))throw Error('The selected section no longer matches your film.');
      setPage(result);
    }).catch(()=>{if(active)setError('This section could not be opened. Your edit has not changed.');})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;controller.abort();};
  },[opened,family,projectId,selected,after,first,api,attempt]);
  function chooseFamily(value){if(value===family&&!selected&&after===null)return;setFamily(value);setSelection([]);setCursor([null]);setFirst(0);setPage(null);}
  function select(item){setSelection(old=>[...old,item]);setFirst(0);setPage(null);}
  function back(){setSelection(old=>old.slice(0,-1));setFirst(0);setPage(null);}
  const usable=page&&!loading;
  return <details className="film-card" onToggle={e=>setOpened(e.currentTarget.open)}>
    <summary>Browse scenes, takes and edits</summary>
    {opened&&<section aria-label="Film sections">
      <p className="film-muted">Find a scene or review an existing section of your film. Browsing does not change your edit.</p>
      <div role="group" aria-label="Browse film by">
        {choices.map(([key,label])=><button type="button" key={key} className="film-secondary" aria-pressed={family===key} onClick={()=>chooseFamily(key)}>{label}</button>)}
      </div>
      {selected&&<><button type="button" className="film-secondary" onClick={back}>Back to {selection.length>1?'section':'list'}</button><h4>{selected.label}</h4></>}
      {loading&&<p role="status">Opening your film sections…</p>}
      {error&&<><p role="alert">{error}</p><button type="button" className="film-secondary" onClick={()=>setAttempt(x=>x+1)}>Try again</button></>}
      {usable&&<>
        {page.items.length===0&&<p className="film-muted">Nothing to show on this page.{page.next_after!=null?' More sections are available on the next page.':''}</p>}
        <ul aria-label="Current film section page">{page.items.map((item,i)=><li key={item.object_id?`${item.object_id}:${item.revision}:${i}`:`${item.branch_id||item.label}:${i}`}>
          {item.object_id?<button type="button" className="film-secondary" onClick={()=>select(item)}>{item.label}</button>:<strong>{item.label}</strong>}
          {item.item_count!=null&&<span> · {item.item_count} {family==='takes'?'takes and camera views':item.view==='source_sections'?'sections':'cuts'}</span>}
          {item.camera&&<span> · {item.camera}</span>}{item.wild&&<span> · Alternate take</span>}
          {item.take&&<span> · {item.take}</span>}
          {item.end_tick&&page.ticks_per_second&&<span> · {time(item.start_tick,page.ticks_per_second)}–{time(item.end_tick,page.ticks_per_second)}</span>}
        </li>)}</ul>
        <div role="group" aria-label="Film section pages">
          <button type="button" className="film-secondary" disabled={selected?first===0:cursor.length===1} onClick={()=>{setPage(null);if(selected)setFirst(Math.max(0,first-pageSize));else setCursor(old=>old.slice(0,-1));}}>Previous page</button>
          {selected?<span>Page {Math.floor(first/pageSize)+1}</span>:<button type="button" className="film-secondary" disabled={after===null} onClick={()=>{setCursor([null]);setPage(null);}}>First page</button>}
          <button type="button" className="film-secondary" disabled={selected?page.next_first==null:page.next_after==null} onClick={()=>{if(selected)setFirst(page.next_first);else setCursor(old=>[...old,page.next_after].slice(-64));setPage(null);}}>Next page</button>
        </div>
      </>}
    </section>}
  </details>;
}
