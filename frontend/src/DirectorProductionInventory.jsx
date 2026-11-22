import React,{useEffect,useRef,useState} from 'react';

// Metadata only. Page through originals, never fetch all media into the UI.
export default function DirectorProductionInventory({projectId,api}){
  const [page,setPage]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const request=useRef(null);
  useEffect(()=>{setPage(null);setBusy(false);setNotice('');return()=>request.current?.abort();},[projectId]);
  async function load(family,after=null){
    request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setNotice('');setPage(null);
    try{
      const out=await api(`/api/projects/${projectId}/live/edit/sections/media-inventory?family=${family}&limit=32${after?'&after='+encodeURIComponent(after):''}`,'GET',undefined,c.signal);
      if(c.signal.aborted)return;
      if(out?.project_id!==projectId||out.family!==family||out.media_authenticated!==false||!Array.isArray(out.items)||out.items.length>32||out.items.some(x=>!/^[a-f0-9]{32}$/.test(x.id)||!Number.isSafeInteger(x.source_bytes)||x.source_bytes<0)||!(out.next_after===null||/^[a-f0-9]{32}$/.test(out.next_after)))throw Error('Inventory changed');
      setPage(out);
    }catch{if(!c.signal.aborted)setNotice('Saved material could not be listed.');}finally{if(!c.signal.aborted)setBusy(false);}
  }
  return <details className="film-sections"><summary>Production material</summary><p className="film-muted">Browse saved originals. Sizes refer to original payloads, not storage used on disk.</p><button className="film-secondary" disabled={busy} onClick={()=>load('takes')}>Filmed takes</button> <button className="film-secondary" disabled={busy} onClick={()=>load('recordings')}>Recordings</button>{busy&&<p role="status">Opening saved material…</p>}{page&&<><ul>{page.items.map((x,i)=><li key={x.id}>{x.scene_id} · {page.family==='takes'?'Take':'Recording'} {x.id.slice(0,8)} · {(x.source_bytes/1024/1024).toFixed(2)} MiB{x.sample_count?` · ${(x.sample_count/48000).toFixed(1)} s`:''}</li>)}</ul>{!page.items.length&&<p>No saved material on this page.</p>}{page.next_after&&<button className="film-secondary" onClick={()=>load(page.family,page.next_after)}>Next page</button>}</>}{notice&&<p role="alert">{notice}</p>}</details>;
}
