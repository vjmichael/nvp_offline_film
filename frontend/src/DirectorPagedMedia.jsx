import DirectorWorkingMovie from './DirectorWorkingMovie.jsx';
import React,{useEffect,useRef,useState} from 'react';
const TPS=7056000000n,SAMPLE=147000n;
const baseFor=(pid,encrypted)=>'/api/projects/'+encodeURIComponent(pid)+(encrypted?'/live':'')+'/edit/sections';

export function DirectorPagedMedia({projectId,encrypted,edit,selection,api,renderPicture}){
  const [picture,setPicture]=useState(null),[working,setWorking]=useState(false),[notice,setNotice]=useState(''),[audio,setAudio]=useState(''),[listening,setListening]=useState(false);
  const soundRequest=useRef(null);
  const base=baseFor(projectId,encrypted);
  const tick=selection?.start_tick;
  const scope={revision:edit.revision,digest:edit.active_digest};
  useEffect(()=>{
    const controller=new AbortController();setPicture(null);setNotice('');setAudio('');setListening(false);soundRequest.current?.abort();
    if(tick===undefined){setWorking(false);return()=>controller.abort();}
    setWorking(true);
    api(base+'/picture','POST',{...scope,tick},controller.signal).then(out=>{
      if(controller.signal.aborted)return;
      if(out?.format!=='nvp.g07.picture_preview.v1'||out.project_id!==projectId||out.revision!==edit.revision||out.active_digest!==edit.active_digest||out.position_tick!==tick||out.preview_is_sampled_native_openusd!==true||out.final_video_rendered!==false||!Array.isArray(out.shots)||out.shots.length<1||out.shots.length>2)throw Error('Changed picture');
      setPicture(out);
    }).catch(()=>{if(!controller.signal.aborted)setNotice('This picture could not be reopened from the original recording.');}).finally(()=>{if(!controller.signal.aborted)setWorking(false);});
    return()=>{controller.abort();soundRequest.current?.abort();};
  },[base,projectId,edit.revision,edit.active_digest,tick,api]);
  useEffect(()=>()=>{if(audio)URL.revokeObjectURL(audio);},[audio]);
  async function listen(){
    let start,duration;
    try{start=(BigInt(tick)+SAMPLE-1n)/SAMPLE*SAMPLE;let remaining=BigInt(edit.duration_tick)-start;duration=(remaining<3n*TPS?remaining:3n*TPS)/SAMPLE*SAMPLE;if(duration<=0n)throw Error('No samples');}catch{setNotice('There is no complete sound sample at this moment.');return;}
    soundRequest.current?.abort();const controller=new AbortController();soundRequest.current=controller;setListening(true);setAudio('');setNotice('');
    try{
      const response=await fetch(base+'/sound',{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'x-nvp-director':'1','Content-Type':'application/json'},body:JSON.stringify({...scope,start_tick:String(start),duration_tick:String(duration)})});
      if(!response.ok)throw Error('Sound unavailable');const blob=await response.blob();if(blob.type!=='audio/wav')throw Error('Invalid sound');
      if(!controller.signal.aborted)setAudio(URL.createObjectURL(blob));
    }catch{if(!controller.signal.aborted)setNotice('The original sound could not be reopened.');}finally{if(!controller.signal.aborted)setListening(false);}
  }
  if(!selection)return null;
  return <section className="film-page-preview" aria-label="Selected cut preview" data-source-sample={picture?'verified':undefined}>
    <div className="film-editor-section-heading"><h3>Cut {selection.index+1} · Preview</h3><button className="film-secondary" disabled={listening} onClick={listen}>{listening?'Opening sound…':'Listen to sound'}</button></div>
    {renderPicture({sample:picture,working,position:Number(BigInt(tick))/Number(TPS)})}
    {notice&&<p role="alert">{notice}</p>}{audio&&<audio controls className="film-editor-listen-player" src={audio} aria-label="Original sound preview"/>}
    <p className="film-muted">A sampled view of your recorded scene and a short listening preview. Your originals stay unchanged.</p>
    {encrypted&&<DirectorReviewClip projectId={projectId} edit={edit} selection={selection} api={api}/>}
  </section>;
}

export function DirectorDeliveryReview({projectId,encrypted,edit,api}){
  const [result,setResult]=useState(''),[busy,setBusy]=useState(false);const request=useRef(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function review(){request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setResult('');try{
    const out=await api(baseFor(projectId,encrypted)+'/delivery-review','POST',{revision:edit.revision,digest:edit.active_digest},c.signal);
    if(c.signal.aborted)return;
    if(out?.format!=='nvp.g07.paged_delivery_source.v1'||out.project_id!==projectId||out.revision!==edit.revision||out.active_digest!==edit.active_digest||out.clip_count!==edit.clip_count||out.render_approved!==false||out.media_verified!==false||out.final_movie_exported!==false)throw Error('Changed source');
    setResult('Cut order and timing checked. Final picture, sound and export still need verification.');
  }catch{if(!c.signal.aborted)setResult('Some cuts need review before delivery. Your current edit is unchanged.');}finally{if(!c.signal.aborted)setBusy(false);}}
  return <div className="film-delivery-review"><button className="film-secondary" onClick={review} disabled={busy}>{busy?'Checking cut timing…':'Check cut timing'}</button>{result&&<p role="status">{result}</p>}{encrypted&&<><DirectorSavedReviewClips projectId={projectId} edit={edit} api={api}/><DirectorWorkingMovie key={`${projectId}:${edit.revision}:${edit.active_digest}`} projectId={projectId} edit={edit} api={api}/></>}</div>;
}

export function DirectorStorageReview({projectId,api}){
  const [page,setPage]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(false),[notice,setNotice]=useState(''),[cursor,setCursor]=useState(null);const request=useRef(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function check(after=null,message=''){request.current?.abort();const c=new AbortController();request.current=c;setPage(null);setBusy(true);setError(false);setNotice(message);setCursor(after);try{
    const url=baseFor(projectId,true)+'/storage-review'+(after?'?after='+encodeURIComponent(after):'');const out=await api(url,'GET',undefined,c.signal);
    if(c.signal.aborted)return;
    if(out?.format!=='nvp.g07.storage_status.v1'||out.project_id!==projectId||!Number.isSafeInteger(out.revision)||out.render_approved!==false||!Array.isArray(out.items)||out.items.length>32||out.items.some(x=>!['available','legacy_available','missing','needs_review'].includes(x.status)||!/^[a-f0-9]{32}$/.test(x.section_id)))throw Error('Changed report');
    setPage(out);
  }catch{if(!c.signal.aborted)setError(true);}finally{if(!c.signal.aborted)setBusy(false);}}
  async function recover(item){
    if(!page||item.status!=='missing'||busy||page.revision<1)return;
    request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setError(false);setNotice('Choose the complete movie backup in the native window.');
    try{
      const out=await api(baseFor(projectId,true)+'/recover','POST',{section_id:item.section_id,revision:page.revision},c.signal);
      if(c.signal.aborted)return;
      if(out?.revision!==page.revision||out.render_approved!==false)throw Error('Changed recovery');
      if(out.cancelled===true&&out.restored===false){setNotice('Recovery cancelled. Your saved material is unchanged.');return;}
      if(out.restored!==true||out.cancelled!==false||out.section_id!==item.section_id)throw Error('Unverified recovery');
      await check(cursor,'The saved section was recovered. Your current edit and originals are unchanged. Reopen the edit to see the restored arrangement.');
    }catch{if(!c.signal.aborted){setError(true);setNotice('This section could not be recovered. Check your backup or recover other missing sections first.');}}finally{if(!c.signal.aborted)setBusy(false);}
  }
  async function wholeMovie(action){
    request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setError(false);setNotice('Follow the native window to continue.');
    try{const out=await api(baseFor(projectId,true)+'/'+action,'POST',{},c.signal);if(c.signal.aborted)return;
      if(out?.project_id!==projectId)throw Error('Changed movie');
      if(out.cancelled===true){setNotice('Cancelled. Your movie is unchanged.');return;}
      if(action==='optimize-edits'||action==='optimize-scenes'){if(out.original_unchanged!==true||!Number.isInteger(out.migrated)||out.migrated<0||out.migrated>8||typeof out.complete!=='boolean')throw Error('Unverified storage');const label=action==='optimize-edits'?'saved edits':'filmed scenes';setNotice(out.complete?`All ${label} are optimized. Your movie and history are unchanged.`:`${out.migrated} ${label} optimized. Choose the action again for more.`);return;}
      if(action==='optimize-recording'){if(out.migrated!==true&&out.complete!==true)throw Error('Unverified storage');setNotice(out.complete?'All recordings are already in protected storage.':'One recording optimized. Your original sound and saved edits are unchanged.');return;}
      if(out.format!=='nvp.g03.live_movie_backup.v1'||out.original_unchanged!==true)throw Error('Unverified backup');
      if(action==='create-backup'&&out.backup_created===true)setNotice('Verified encrypted movie backup saved. Keep your movie passphrase and Windows account.');
      else if(action==='restore-copy'&&out.restored_copy===true&&out.active_movie_replaced===false)setNotice('Verified separate movie copy recovered. The current movie has not been replaced.');
      else throw Error('Unverified backup');
    }catch{if(!c.signal.aborted){setError(true);setNotice('This action could not be completed. Your original movie is unchanged.');}}finally{if(!c.signal.aborted)setBusy(false);}
  }
  const issue=page?.items.filter(x=>!['available','legacy_available'].includes(x.status)).length||0;
  return <details className="film-sections"><summary>Movie recovery</summary><div className="film-sections-workspace"><p className="film-muted">Keep a protected backup of your complete movie and its original material. Recovery makes a separate copy without replacing your current movie.</p><div className="film-sections-pagination"><button className="film-secondary" onClick={()=>wholeMovie('create-backup')} disabled={busy}>Create movie backup</button><button className="film-secondary" onClick={()=>wholeMovie('restore-copy')} disabled={busy}>Recover movie copy</button></div><button className="film-secondary" onClick={()=>wholeMovie('optimize-recording')} disabled={busy}>Optimize recording storage</button><button className="film-secondary" onClick={()=>wholeMovie('optimize-edits')} disabled={busy}>Optimize saved edits</button><button className="film-secondary" onClick={()=>wholeMovie('optimize-scenes')} disabled={busy}>Optimize filmed scenes</button><button className="film-secondary" onClick={()=>check()} disabled={busy}>{busy?'Checking saved sections…':'Check saved sections'}</button>{error&&<p role="alert">Keep the original movie and backup unchanged.</p>}{notice&&<p role="status">{notice}</p>}{page&&<div><p role="status">{page.items.length} saved sections checked in this group. {issue?`${issue} need recovery or review.`:'All checked sections are available.'}</p>{page.items.filter(x=>x.status==='missing').map((item,i)=><div className="film-recovery-row" key={item.section_id}><span>Missing saved section {i+1}</span><button className="film-secondary" disabled={busy||page.revision<1} onClick={()=>recover(item)}>Choose backup</button></div>)}{page.items.some(x=>x.status==='needs_review')&&<p className="film-muted">Existing damaged material needs review and will not be overwritten.</p>}{page.next_after&&<button className="film-secondary" disabled={busy} onClick={()=>check(page.next_after)}>Check next sections</button>}</div>}</div></details>;
}


function DirectorReviewClip({projectId,edit,selection,api}){
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[saved,setSaved]=useState(null);const request=useRef(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  const format='nvp.g07.protected_review_reel.v1';let first=0,count=0;
  try{const frame=TPS/24n;let from=(BigInt(selection.start_tick)+frame-1n)/frame;let to=BigInt(selection.end_tick||edit.duration_tick)/frame;first=Number(from);count=Number(to-from<240n?to-from:240n);if(!Number.isSafeInteger(first)||first<0||first+count>259200||count<1)count=0;}catch{count=0;}
  async function action(copy=false){request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setNotice(copy?'Choose a folder in the native window.':'Review the clip in the native window.');
    try{const out=await api(baseFor(projectId,true)+(copy?'/copy-review-clip':'/review-clip'),'POST',copy?{revision:edit.revision,digest:edit.active_digest,reel_id:saved}:{revision:edit.revision,digest:edit.active_digest,first_frame:first,frame_count:count},c.signal);
      if(c.signal.aborted)return;if(out?.format!==format||out.project_id!==projectId||out.revision!==edit.revision)throw Error('Changed clip');
      if(out.cancelled===true){setNotice('Cancelled. Your originals are unchanged.');return;}
      if(copy){if(out.copy_saved!==true||out.reel_id!==saved)throw Error('Unverified copy');setNotice('Review clip copy saved outside the protected movie.');}
      else{if(out.verified!==true||out.protected!==true||out.whole_movie_exported!==false||out.start_frame!==first||out.frame_count!==count||! /^[a-f0-9]{32}$/.test(out.reel_id))throw Error('Unverified clip');setSaved(out.reel_id);setNotice('Review clip saved inside your protected movie. This is not a final movie export.');}
    }catch{if(!c.signal.aborted)setNotice('The review clip could not be completed. Your current edit is unchanged.');}finally{if(!c.signal.aborted)setBusy(false);}}
  return <details className="film-sections"><summary>Review clip</summary><p className="film-muted">Save up to ten seconds of working picture and sound from this cut. Final movie export is a separate step.</p><div className="film-sections-pagination"><button className="film-secondary" disabled={busy||!count} onClick={()=>action(false)}>Save review clip</button>{saved&&<button className="film-secondary" disabled={busy} onClick={()=>action(true)}>Save review copy</button>}</div>{notice&&<p role="status">{notice}</p>}{!count&&<p className="film-muted">This cut is outside the current review clip profile.</p>}</details>;
}


function DirectorSavedReviewClips({projectId,edit,api}){
 const [page,setPage]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');const request=useRef(null);const format='nvp.g07.protected_review_reel.v1';
 useEffect(()=>()=>request.current?.abort(),[]);
 async function run(after=null,reel=null){request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setNotice('');try{
   const path=reel?'/copy-review-clip':'/review-clips'+(after?'?after='+encodeURIComponent(after):'');const scope={revision:edit.revision,digest:edit.active_digest};
   const out=await api(baseFor(projectId,true)+path,'POST',reel?{...scope,reel_id:reel}:scope,c.signal);if(c.signal.aborted)return;
   if(out?.format!==format||out.project_id!==projectId||out.revision!==edit.revision)throw Error('Changed edit');
   if(reel){if(out.cancelled===true)setNotice('Copy cancelled.');else if(out.copy_saved===true&&out.reel_id===reel)setNotice('Review copy saved.');else throw Error('Unverified copy');}
   else {if(out.whole_movie_exported!==false||out.reopened!==false||!Array.isArray(out.items)||out.items.length>32||out.items.some(x=>! /^[a-f0-9]{32}$/.test(x.reel_id)||!['saved','needs_review'].includes(x.state)||!Number.isSafeInteger(x.start_frame)||!Number.isSafeInteger(x.frame_count)))throw Error('Invalid clips');setPage(out);}
 }catch{if(!c.signal.aborted)setNotice('Saved review clips could not be reopened.');}finally{if(!c.signal.aborted)setBusy(false);}}
 return <details className="film-sections"><summary>Saved review clips</summary><p className="film-muted">Review copies remain separate from your finished film.</p><button className="film-secondary" onClick={()=>run()} disabled={busy}>Show saved clips</button>{page&&<div>{!page.items.length&&<p>No saved clips for this edit.</p>}{page.items.map((clip,i)=><div className="film-recovery-row" key={clip.reel_id}><span>{(clip.start_frame/24).toFixed(1)}s · {(clip.frame_count/24).toFixed(1)}s clip {clip.state==='needs_review'?'· Needs review':''}</span>{clip.state==='saved'&&<button className="film-secondary" onClick={()=>run(null,clip.reel_id)} disabled={busy}>Save copy</button>}</div>)}{page.next_after&&<button className="film-secondary" disabled={busy} onClick={()=>run(page.next_after)}>More clips</button>}</div>}{notice&&<p role="status">{notice}</p>}</details>;
}
