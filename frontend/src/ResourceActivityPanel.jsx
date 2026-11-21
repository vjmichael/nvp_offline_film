import React, { useEffect, useState } from 'react';
import './ResourceActivityPanel.css';

const names = {
  waiting_for_resources:'Waiting for available memory',
  checking_memory:'Checking RAM and GPU headroom',
  starting:'Starting the worker',
  loading_model:'Loading AI model', warming_model:'Warming AI model',
  processing_prompt:'Processing the prompt',
  generating:'Generating AI response',
  offloading_model:'Offloading AI model',
  external_model_wait:'Waiting on the connected AI server',
  preparing_scene:'Preparing 3D scene', building_scene:'Building 3D scene',
  rendering:'Rendering frames',saving_output:'Saving output',
  verifying_output:'Verifying output and source',cooling_down:'Releasing memory',
  recovering:'Recovering interrupted work',finished:'Finished',
  failed:'Stopped with an error',cancelled:'Cancelled',
};
const terminal=new Set(['SUCCEEDED','FAILED','CANCELLED','INTERRUPTED']);

function Meter({ label, total, available, hint }) {
  if (total == null || available == null || total <= 0) {
    return <div className="ra-metric"><strong>{label}</strong>
      <div className="ra-unknown" aria-label={label + ' unavailable'} />
      <p>Measurement unavailable · {hint}</p></div>;
  }
  const busy=Math.max(0,Math.min(total,total-available));
  return <div className="ra-metric">
    <div className="ra-between"><strong>{label}</strong><span>{(busy/1024).toFixed(1)} / {(total/1024).toFixed(1)} GiB used</span></div>
    <progress aria-label={label + ' used'} max={total} value={busy}/>
    <p>{(available/1024).toFixed(1)} GiB measured headroom · {hint}</p>
  </div>;
}

function Task({ item }) {
  const active=!terminal.has(item.state) && item.state!=='QUEUED' && item.state!=='STALE_UNVERIFIED';
  const measured=typeof item.completed_fraction==='number' &&
    Number.isFinite(item.completed_fraction) && item.completed_fraction>=0 &&
    item.completed_fraction<=1;
  return <div className={'ra-task ra-'+item.state.toLowerCase()} data-testid={'task-'+item.id}>
    <div className="ra-between"><strong>{item.title}</strong>
      <span>{item.state==='QUEUED'?'Queued':item.state==='STALE_UNVERIFIED'?'Recovery needed':measured?String(Math.round(item.completed_fraction*100))+'%':active?'Working':item.state}</span></div>
    <small>{item.kind==='external_ai'?'Externally managed AI server':item.kind.replaceAll('_',' ')}</small>
    <p className="ra-phase">{names[item.phase]||item.phase.replaceAll('_',' ')}</p>
    {active && (measured
      ? <progress aria-label={item.title+' measured progress'} max="100" value={Math.round(item.completed_fraction*100)}/>
      : <progress aria-label={item.title+' working; percent unknown'}/>)}
    {item.state==='QUEUED' && <p className="ra-wait">Not started. NVP is preserving computer memory headroom.{item.queue_lane ? ' Priority: '+item.queue_lane+'.' : ''}</p>}
    {item.state==='STALE_UNVERIFIED' && <p className="ra-wait">No recent worker heartbeat. NVP is holding the reservation until safe recovery is verified.</p>}
    {item.detail && <p>{item.detail}</p>}
  </div>;
}

export default function ResourceActivityPanel({endpoint='/api/system/activity',pollMs=1800}) {
  const [report,setReport]=useState(null);
  const [error,setError]=useState('');
  const [open,setOpen]=useState(false);
  useEffect(()=>{
    let live=true,controller=null,busy=false;
    async function poll(){
      if(busy)return;
      busy=true;controller=new AbortController();
      try{
        const response=await fetch(endpoint,{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error('Resource monitor returned '+response.status);
        const payload=await response.json();
        if(live){setReport(payload);setError('');}
      }catch(err){if(live && err.name!=='AbortError')setError('Resource monitor not available');}
      finally{busy=false;}
    }
    poll();
    const clock=setInterval(poll,Math.max(500,pollMs));
    return ()=>{live=false;clearInterval(clock);controller?.abort();};
  },[endpoint,pollMs]);

  const tasks=report?.tasks||[];
  const active=tasks.filter(t=>!terminal.has(t.state));
  const recent=tasks.filter(t=>terminal.has(t.state)).slice(0,4);
  const waiting=active.filter(t=>t.state==='QUEUED').length;
  const sample=report?.sample;

  return <section className="ra-panel" aria-label="Computer resources and production activity">
    <button type="button" className="ra-toggle" aria-expanded={open} onClick={()=>setOpen(!open)}>
      <span className="ra-led" aria-hidden="true">●</span>
      <span className="ra-summary"><strong>Computer & production activity</strong>
        <small>{error||(report?String(active.length-waiting)+' working · '+String(waiting)+' waiting':'Checking computer memory…')}</small></span>
      <span aria-hidden="true">{open?'▴':'▾'}</span>
    </button>
    {open && <div className="ra-details" role="region" aria-label="Resource activity details">
      <p className="ra-desc">NVP keeps memory in reserve. Heavy work can wait rather than freezing your PC.</p>
      {sample ? <>
        <Meter label="System RAM" total={sample.ram_total_mb} available={sample.ram_available_mb}
          hint="Measured by the OS; safety reserve stays free."/>
        {(sample.gpus||[]).length ? sample.gpus.map(g=><Meter key={g.device_id}
          label={'GPU VRAM · '+g.name} total={g.budget_mb} available={g.free_mb}
          hint={g.globally_measured?'Driver-reported GPU usage':'DXGI budget for NVP process—not global free VRAM'}/>)
          : <Meter label="GPU VRAM" total={null} available={null}
              hint="Unknown VRAM budget. NVP queues GPU-heavy work."/>}
        {sample.memory_psi_full10!=null && <p className="ra-desc">Linux memory stall pressure (10 seconds): {sample.memory_psi_full10.toFixed(1)}%</p>}
      </>:<p className="ra-desc">Checking hardware telemetry…</p>}
      <div className="ra-reservations" role="status">
        <strong>NVP task reservations:</strong> {((report?.reservations?.ram_mb||0)/1024).toFixed(1)} GiB RAM · {((report?.reservations?.gpu_mb||0)/1024).toFixed(1)} GiB VRAM
      </div>
      <div className="ra-section"><strong>Production tasks</strong><span>{active.length} active or queued</span></div>
      {!active.length && <p className="ra-desc">No heavy NVP tasks running. Model load/unload activity requires a connected provider adapter.</p>}
      {active.map(t=><Task key={t.id} item={t}/>)}
      {!!recent.length && <details className="ra-history"><summary>Recent completed and interrupted tasks</summary>
        {recent.map(t=><Task key={t.id} item={t}/>)}</details>}
      <p className="ra-disclaimer">Percentages are shown only when the engine provides measured progress. Current external AI models are observed, not loaded or offloaded by NVP. No ETA is invented.</p>
    </div>}
  </section>;
}
