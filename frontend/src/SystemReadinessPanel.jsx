import React,{useEffect,useState} from 'react';

// NVP's installer bundles the Python runtime, FFmpeg and FFprobe. This
// screen discovers machine prerequisites WITHOUT installing anything by
// itself; an OS package manager runs only after separate explicit native
// confirmation, and only for a fixed trusted component ID.
const FORMAT='nvp.system_ready.native_packages.v1';

export default function SystemReadinessPanel({nativeBridge=null}){
  const [native,setNative]=useState(nativeBridge);
  const [report,setReport]=useState(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  useEffect(()=>{
    if(nativeBridge){setNative(nativeBridge);return;}
    let active=true;
    let count=0;
    const poll=setInterval(()=>{
      if(++count>25)clearInterval(poll);
      const host=window.pywebview?.api;
      if(host&&active){
        setNative(host);clearInterval(poll);
      }
    },200);
    return ()=>{active=false;clearInterval(poll);};
  },[nativeBridge]);
  useEffect(()=>{
    let live=true;
    if(!native?.system_package_inventory)return;
    native.system_package_inventory().then(result=>{
      if(live&&result?.format===FORMAT)setReport(result);
    }).catch(()=>{if(live)setError('Native package scan could not complete.');});
    return ()=>{live=false;};
  },[native]);
  async function refresh(){
    if(!native?.system_package_inventory)return;
    setBusy(true);setError('');
    try{
      const result=await native.system_package_inventory();
      if(result?.format!==FORMAT)throw Error('Trusted package scan unavailable');
      setReport(result);
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  async function repair(component){
    if(!native?.repair_system_package)return;
    setBusy(true);setError('');setMessage('');
    try{
      const receipt=await native.repair_system_package(component);
      if(receipt?.format!==FORMAT||receipt.source_media_modified!==false)
        throw Error('Unverified package operation; no changes accepted');
      if(receipt.status==='INSTALLED'){
        setMessage('Operating-system package installed. NVP has rechecked the requirement.');
      }else if(receipt.status==='DECLINED'){
        setMessage('Installation was cancelled. Nothing in NVP was changed.');
      }else if(receipt.status==='RESTART_OR_RECHECK'){
        setMessage('Installer completed. Restart NVP and check the runtime again.');
      }else{
        setMessage('NVP could not repair this dependency automatically. Check your OS package manager.');
      }
      const updated=await native.system_package_inventory();
      if(updated?.format===FORMAT)setReport(updated);
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }
  return <div className="page" aria-label="System readiness">
    <div className="kicker">NVP SYSTEM CHECK</div>
    <h1>Ready to make your movie?</h1>
    <p className="lead">NVP checks the components needed by this computer.
      The Windows installer brings its own video tools and Python runtime.
      NVP only requests missing operating-system components when needed,
      and asks before making system changes.</p>
    <section className="card">
      <h2>System packages</h2>
      {!report&&<p role="status">Inspecting local runtime requirements…</p>}
      {report?.components?.map(item=><div key={item.id}
        className="scene-item" style={{marginBottom:'0.65rem',padding:'0.75rem'}}>
        <strong>{item.name}</strong>
        <span>{item.status==='ready'?'Ready':item.status==='low_space'?
          'Free some local disk space':item.status==='missing'?
          'Installation needed':item.status==='unsupported'?
          'This runtime is not supported here':'Verification needed'}</span>
        <small>Provided by: {item.supplied_by}
          {typeof item.free_mb==='number'?(' · '+item.free_mb+' MB free'):''}
        </small>
        {item.status!=='ready'&&item.repair&&
          <button disabled={busy||!native?.repair_system_package}
            onClick={()=>repair(item.repair)}>
            Ask to install {item.name}
          </button>}
        {item.status!=='ready'&&!item.repair&&
          <p className="fineprint">This requirement cannot be installed
            automatically by this NVP build. Please use the official
            NVP installer or your operating system's package manager.</p>}
      </div>)}
      <div className="actions">
        <button disabled={busy||!native?.system_package_inventory}
          onClick={refresh}>Check again</button>
      </div>
      <p className="fineprint">Only supported, known components can be
        installed. An installation requires a separate native NVP approval
        and any operating-system authorization. NVP never runs arbitrary
        commands supplied by a movie project or AI model.</p>
      {message&&<p role="status">{message}</p>}
      {error&&<p role="alert">{error}</p>}
    </section>
  </div>;
}
