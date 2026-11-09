import React,{useState} from 'react';

// USD-FILM-01S: director can control batch GROUP SIZE, never bypass native
// RAM/VRAM/CPU admission or silently authorize a Blender worker.
export default function AdaptiveShotBatchPanel({api}){
  const [viewpoints,setViewpoints]=useState('9');
  const [selected,setSelected]=useState('3');
  const [groupSize,setGroupSize]=useState('auto');
  const [parallel,setParallel]=useState('auto');
  const [renderBackend,setRenderBackend]=useState('cpu');
  const [report,setReport]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);

  async function estimate(event){
    event.preventDefault();
    const count=Number(viewpoints), final=Number(selected);
    if(!Number.isInteger(count)||count<1||count>96||
       !Number.isInteger(final)||final<0||final>count){
      setError('Choose 1–96 viewpoints and a final-shot count no greater than that.');
      setReport(null);
      return;
    }
    setBusy(true);
    setError('');
    setReport(null);
    try{
      const received=await api('/system/shot-batch-estimate','POST',{
        viewpoint_count:count, selected_final_shots:final,
        shots_per_batch:groupSize==='auto'?null:Number(groupSize),
        parallel_worker_limit:parallel==='auto'?null:Number(parallel),
        renderer:renderBackend,gpu_device_id:renderBackend==='gpu'
          ? 'unverified-gpu' : null,
      });
      if(received?.format!=='nvp.film01s.read_only_batch_capacity_preview.v1'||
         received.render_jobs_started!==0||
         received.browser_has_no_native_render_authority!==true||
         received.source_film_index_take_verified!==false)
        throw Error('Untrusted resource estimate or native execution status');
      setReport(received);
    }catch(err){setError(err.message);}
    finally{setBusy(false);}
  }

  return <section className="card" aria-label="Adaptive camera shot batching">
    <h2>Batch virtual camera shots</h2>
    <p className="fineprint">
      Every camera is a viewpoint into the same frozen performance.
      Preview the views at low quality; render only selected final shots at high quality.
      NVP estimates how much your PC can safely handle before starting any work.
    </p>
    <form onSubmit={estimate}>
      <div className="actions">
        <label>Virtual viewpoints to preview
          <input aria-label="Virtual viewpoint count" type="number" min="1"
            max="96" step="1" value={viewpoints}
            onChange={event=>setViewpoints(event.target.value)}/>
        </label>
        <label>Shots selected for high quality
          <input aria-label="Final selected shot count" type="number" min="0"
            max="96" step="1" value={selected}
            onChange={event=>setSelected(event.target.value)}/>
        </label>
        <label>Shots per batch
          <select aria-label="Shots per batch" value={groupSize}
            onChange={event=>setGroupSize(event.target.value)}>
            <option value="auto">Auto · follow hardware</option>
            {[1,2,3,4,6,8,12,16,24,32,48,64].map(n=>
              <option key={n} value={String(n)}>{n} shots</option>)}
          </select>
        </label>
        <label>Maximum simultaneous render workers
          <select aria-label="Maximum concurrent render workers" value={parallel}
            onChange={event=>setParallel(event.target.value)}>
            <option value="auto">Auto · safe capacity</option>
            {[1,2,3,4,6,8,12,16,24,32].map(n=>
              <option key={n} value={String(n)}>{n} max</option>)}
          </select>
        </label>
        <label>Preferred render backend
          <select aria-label="Preferred render backend" value={renderBackend}
            onChange={event=>setRenderBackend(event.target.value)}>
            <option value="cpu">CPU · available when headroom permits</option>
            <option value="gpu">GPU · only after native device verification</option>
          </select>
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy?'Checking measured hardware…':'Estimate shot batches'}
        </button>
      </div>
    </form>
    {error&&<p role="alert">{error}</p>}
    {report&&<div role="status" aria-label="Measured camera batch estimate">
      <h3>{report.batch_size_mode==='AUTO'?'Automatic':'Director-selected'} grouping: {report.shots_per_batch} shots per batch</h3>
      <p><strong>Low-fi:</strong> {report.lowfi_preview_batches.length} batches for {report.available_source_viewpoints} virtual views.{' '}
        <strong>Hi-fi:</strong> {report.hifi_selected_shot_batches.length} batches for {report.selected_final_shots} selected shots.</p>
      {['lofi','hifi'].map(stage=>{
        const cap=report.safe_parallel_workers?.[stage];
        return <p key={stage}><strong>{stage==='lofi'?'Preview':'Final'} safe parallel capacity:</strong>{' '}
          {cap?.safe_workers??'unavailable'} native workers.
          {cap?.reason?' '+cap.reason:''}
        </p>;
      })}
      <p className="fineprint">
        Batch size controls grouping and queue order, not simultaneous execution.
        On a low-powered PC, 12 shots can belong to one batch while only one
        renders at a time. Last batches can contain fewer shots.
      </p>
    </div>}
    <p className="fineprint">
      This is a resource estimate, not an accepted camera-roll source or a running
      render queue. Scheduling actual original FilmIndex shots requires the
      installed NVP execution broker, source identity and a separate director
      authorization. Lu may read resource status; it cannot grant those permissions.
    </p>
  </section>;
}
