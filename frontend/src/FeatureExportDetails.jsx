import React,{useEffect,useState} from 'react';

const labels={QUEUED:'Waiting to export',STAGING:'Preparing cinema files',PUBLISHED_PENDING_INDEX:'Files saved · checking',INDEXED:'Ready for review',REVIEW_REQUIRED:'Review needed',CANCELLED:'Cancelled'};

// Read-only native journal details. Hashes are recorded evidence, not a new
// playback, certification or independent disk audit. Never show paths or leases.
export default function FeatureExportDetails({projectId,features,api}){
  const [open,setOpen]=useState(false),[choice,setChoice]=useState('');
  const [kind,setKind]=useState('source'),[first,setFirst]=useState(0);
  const [page,setPage]=useState(null),[failed,setFailed]=useState(false),[retry,setRetry]=useState(0);
  const selected=features.find(x=>x.feature_id===choice)||features[0];
  const featureId=selected?.feature_id;
  // Key the visible response to the current selection before the effect runs.
  const current=page?.project_id===projectId&&page?.feature_id===featureId&&page?.kind===kind&&page?.first===first?page:null;
  useEffect(()=>{
    let live=true;setPage(null);setFailed(false);
    if(open&&featureId&&typeof api?.wo5_review_feature_page==='function'){
      Promise.resolve().then(()=>api.wo5_review_feature_page(projectId,featureId,first,kind)).then(result=>{
        if(!live)return;
        if(result?.project_id!==projectId||result?.feature_id!==featureId||result?.kind!==kind||result?.first!==first||!Array.isArray(result.entries)||result.entries.length>32)throw Error('Invalid page');
        setPage(result);
      }).catch(()=>{if(live)setFailed(true);});
    }
    return()=>{live=false;};
  },[open,featureId,projectId,first,kind,api,retry]);
  if(!selected||typeof api?.wo5_review_feature_page!=='function')return null;
  return <details className="film-card" onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>Export details <span className="film-muted">· {labels[selected.state]||'Unavailable'}</span></summary>
    <p className="film-muted">Recorded picture, sound and file checks. This does not certify a cinema package.</p>
    <label>Export <select value={featureId} onChange={e=>{setChoice(e.target.value);setFirst(0);}}>{features.map((x,i)=><option key={x.feature_id} value={x.feature_id}>{x.assembly_id||`Export ${i+1}`}</option>)}</select></label>
    <div role="group" aria-label="Export detail type">
      <button aria-pressed={kind==='source'} onClick={()=>{setKind('source');setFirst(0);}}>Reels</button>{' '}
      <button aria-pressed={kind==='output'} onClick={()=>{setKind('output');setFirst(0);}}>Output files</button>
    </div>
    {failed?<p role="alert">Export details are unavailable. <button onClick={()=>setRetry(n=>n+1)}>Retry</button></p>:!current?<p role="status">{open?'Loading export details…':'Open to view details.'}</p>:<>
      <p role="status">{labels[current.state]||'Unavailable'} · {current.total} {kind==='source'?'reels':'recorded files'}</p>
      {!current.entries.length?<p>No files have been recorded yet.</p>:<ol start={first+1}>
        {current.entries.map((entry,i)=><li key={first+i}>
          {kind==='source'?`Reel ${entry.reel} · ${entry.frames} frames`:entry.name}
          <details><summary>Recorded checksums</summary>{kind==='source'?<><p>Picture <code style={{overflowWrap:'anywhere'}}>{entry.picture_sha256}</code></p><p>Sound <code style={{overflowWrap:'anywhere'}}>{entry.sound_sha256}</code></p></>:<code style={{overflowWrap:'anywhere'}}>{entry.sha256}</code>}</details>
        </li>)}
      </ol>}
      <div role="group" aria-label="Export detail pages"><button disabled={first===0} onClick={()=>setFirst(Math.max(0,first-32))}>Previous</button>{' '}<button disabled={current.next_first==null} onClick={()=>setFirst(current.next_first)}>Next</button></div>
    </>}
  </details>;
}
