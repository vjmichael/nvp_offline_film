import React,{useEffect,useState} from 'react';

const CATALOG='nvp.plan02c.canonical_camera_source_catalog.v1';
const PREVIEW='nvp.cam_fx01.verified_director_rail_proposal.v1';
const PREVIEW_CANONICAL='nvp.plan02c.camera_rail_preview.v1';
const MODEL='nvp.plan02c.unapproved_verified_source_gguf_advice.v1';
const TECHNIQUES=['static','dolly','truck','crane','orbit','track','pan_tilt',
  'reveal','reaction','two_shot','establishing','custom'];
const safeTick=n=>Number.isSafeInteger(n)&&n>=0;
const sha=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);

export default function NativeCameraRailPanel({projectId,native=null,sourceRevision=0,onPreviewChange=null}){
  const [sources,setSources]=useState([]);
  const [choice,setChoice]=useState(0);
  const [railId,setRailId]=useState('DirectorRail001');
  const [spec,setSpec]=useState(null);
  const [expectedRevision,setExpectedRevision]=useState(0);
  const [preview,setPreview]=useState(null);
  const [models,setModels]=useState([]);
  const [modelId,setModelId]=useState('');
  const [direction,setDirection]=useState('Frame the original scene with a gentle dolly.');
  const [candidate,setCandidate]=useState(null);
  const [receipt,setReceipt]=useState(null);
  const [raster,setRaster]=useState(null);
  const [protectedRaster,setProtectedRaster]=useState(null);
  const [cyclesPreview,setCyclesPreview]=useState(null);
  const [rasterName,setRasterName]=useState('DirectorStill001');
  const [error,setError]=useState('');
  const [note,setNote]=useState('');
  const [busy,setBusy]=useState(false);
  const [sourceReady,setSourceReady]=useState(false);

  useEffect(()=>{
    let alive=true;
    setSpec(null);setSources([]);setPreview(null);setCandidate(null);
    onPreviewChange?.(null);
    setSourceReady(false);setError('');
    if(!native||!projectId||typeof native.plan02c_catalog!=='function')
      return ()=>{alive=false;};
    Promise.resolve(native.plan02c_catalog(projectId)).then(data=>{
      if(!alive)return;
      if(data?.format!==CATALOG||data.project_id!==projectId||
         data.original_modified!==false||!Array.isArray(data.sources))
        throw Error('Authoritative camera source catalog was not verified');
      setSources(data.sources);
      setChoice(0);
      setSpec(data.sources[0]?.suggested_unapproved_rail_spec||null);
      setSourceReady(true);
    }).catch(e=>{if(alive)setError(e.message)});
    return ()=>{alive=false;};
  },[projectId,native,sourceRevision]);

  useEffect(()=>{
    let alive=true;
    if(!native||typeof native.plan02c_models!=='function')
      return ()=>{alive=false};
    Promise.resolve(native.plan02c_models()).then(result=>{
      if(!alive)return;
      if(result?.format!=='nvp.plan02c.available_loopback_gguf_models.v1'||
         !Array.isArray(result.models))
        throw Error('Local model inventory could not be source verified');
      setModels(result.models);
      setModelId(result.models[0]?.id||'');
    }).catch(e=>{if(alive)setNote('Local model unavailable: '+e.message)});
    return ()=>{alive=false;};
  },[native]);

  function changeSpec(next){
    setSpec(next);setPreview(null);setCandidate(null);setReceipt(null);
    setRaster(null);setProtectedRaster(null);setCyclesPreview(null);
    onPreviewChange?.(null);
    setNote('');
  }
  function updateNode(i,key,value){
    if(!spec)return;
    const parsed=key==='tick'?Number(value):Number(value);
    if(!Number.isFinite(parsed)||(key==='tick'&&!safeTick(parsed))){
      setError('Use finite original Film Time or physical camera values.');return;
    }
    const nodes=spec.nodes.map((n,j)=>{
      if(j!==i)return n;
      if(key.includes('.')){
        const [field,axis]=key.split('.');
        const v=n[field].slice();v[Number(axis)]=parsed;
        return {...n,[field]:v};
      }
      return {...n,[key]:parsed};
    });
    setError('');changeSpec({...spec,nodes});
  }
  function addMidpoint(){
    if(!spec||spec.nodes.length>=4)return;
    const nodes=spec.nodes.slice();
    const a=nodes[0],b=nodes[1];
    const mid=Math.floor((a.tick+b.tick)/2);
    if(mid===a.tick||mid===b.tick)return;
    const point={...a,tick:mid,
      position_m:a.position_m.map((v,i)=>(v+b.position_m[i])/2),
      target_m:a.target_m.map((v,i)=>(v+b.target_m[i])/2)};
    nodes.splice(1,0,point);
    changeSpec({...spec,nodes});
  }
  async function action(task){
    if(!spec||busy||!native)return;
    setError('');setNote('');setBusy(true);
    try{
      const common={project_id:projectId,rail_id:railId,
        expected_revision:expectedRevision,rail_spec:spec};
      if(task==='preview'){
        const result=await native.plan02c_preview(common);
        if(result?.format!==PREVIEW_CANONICAL||
           !sha(result.proposal_sha256)||
           result.take_document_sha256!==spec.take_document_sha256||
           result.director_approved!==false||
           result.native_worker_authorized!==false)
          throw Error('Source camera proposal was not independently verified');
        setPreview(result);
        onPreviewChange?.(result);
        setNote('Exact Film Time rail preview verified. No authorizations granted.');
      }else if(task==='model'){
        if(!modelId||direction.length>1200||!direction.trim())
          throw Error('Select a real local model and bounded director direction');
        const result=await native.plan02c_model_candidate({
          ...common,model_id:modelId,direction});
        if(result?.format!==MODEL||
           result.status!=='UNAPPROVED_SOURCE_CAMERA_ADVICE'||
           result.rail_published!==false||
           result.human_authorization_granted!==false||
           result.original_pcm_and_take_modified!==false||
           result.source_take_sha256!==spec.take_document_sha256||
           !sha(result.provider_completion_receipt?.response_sha256))
          throw Error('Model did not deliver verifiable unapproved source advice');
        setCandidate(result);
        setSpec(result.proposed_rail_spec);
        setPreview(null);
        onPreviewChange?.(null);
        setNote('Real model response received (provider-reported tokens). Review changed nodes; then preview and separately approve a rail. GGUF weight attestation is an independent gate.');
      }else if(task==='publish'){
        if(!preview||!sha(preview.proposal_sha256))
          throw Error('Preview the current unchanged rail before approval');
        const result=await native.plan02c_publish({
          ...common,preview_sha256:preview.proposal_sha256});
        if(result?.format!=='nvp.plan02c.director_approved_rail_receipt.v1'||
           result.original_modified!==false||
           result.renderer_worker_authorized!==false||
           !sha(result.rail_document_sha256))
          throw Error('Native rail publication receipt is missing');
        setReceipt(result);
        setPreview(null);
        onPreviewChange?.(null);
        setNote('Director-approved camera layer published; original Take, sound, actor motion and rendering permission remain unchanged.');
      }
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }
  async function rasterAction(publish=false){
    if(!spec||busy||!native)return;
    setBusy(true);setError('');setNote('');
    try{
      if(publish){
        if(!raster||!sha(raster.png_sha256)||
           typeof native.plan02d_raster_publish!=='function')
          throw Error('Generate an unchanged genuine native PNG first');
        const saved=await native.plan02d_raster_publish({
          project_id:projectId,presentation_id:rasterName,
          selection:raster.selection,
          selection_sha256:raster.source_selection_sha256,
          tick:raster.film_tick,
          expected_png_sha256:raster.png_sha256});
        if(saved.status!=='VERIFIED_DERIVED_OPENUSD_PNG'||
           saved.source_modified!==false||!sha(saved.png_sha256))
          throw Error('Native OS-approved picture publication was not verified');
        setNote('Independent native PNG persisted with SHA receipt. No original changes or film mastering authorization.');
        return;
      }
      if(typeof native.plan02d_preview!=='function'||
         typeof native.plan02d_raster_preview!=='function')
        throw Error('Native source-selected OpenUSD raster adapter unavailable');
      const first=spec.film_start_tick;
      const last=spec.film_end_tick;
      if(!safeTick(first)||!safeTick(last)||last<=first)
        throw Error('Original camera source Film Time cannot be represented exactly');
      const selected={
        take_id:spec.take_id,take_document_sha256:spec.take_document_sha256,
        camera_timeline_id:spec.camera_timeline_id,
        camera_timeline_revision:spec.camera_timeline_revision,
        camera_timeline_sha256:spec.camera_timeline_sha256,
        first_tick:first,last_tick_exclusive:last,
        camera_mode:receipt?'approved_rail':'original',
        rail_id:receipt?railId:null,
        rail_revision:receipt?receipt.revision:null,
        rail_document_sha256:receipt?receipt.rail_document_sha256:null
      };
      const tick=first+Math.floor((last-first)/2);
      const opened=await native.plan02d_preview({
        project_id:projectId,selection:selected});
      if(!sha(opened.selection_sha256)||
         opened.renderer_worker_authorized!==false||
         opened.take_document_sha256!==spec.take_document_sha256)
        throw Error('Source-selected camera scope was rejected');
      const picture=await native.plan02d_raster_preview({
        project_id:projectId,selection:selected,
        selection_sha256:opened.selection_sha256,tick});
      if(picture.format!=='nvp.plan02d.native_source_selected_png.v1'||
         picture.status!=='DERIVED_MEMORY_PREVIEW_NOT_PUBLISHED'||
         picture.source_modified!==false||picture.ffmpeg_used!==false||
         !sha(picture.png_sha256)||
         typeof picture.png_base64!=='string'||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(picture.png_base64))
        throw Error('Native OpenUSD PNG receipt did not verify');
      setRaster({...picture,selection:selected});
      setNote('Real bounded native source image evaluated at exact Film Time. This is not an approved cinematic master.');
    }catch(e){setRaster(null);setError(e.message)}
    finally{setBusy(false)}
  }

  async function renderWithNativeCustody(){
    if(!raster||busy||typeof native?.plan03_render_original_once!=='function')return;
    setBusy(true);setError('');setNote('');setProtectedRaster(null);
    try{
      const result=await native.plan03_render_original_once({
        project_id:projectId,
        selection:raster.selection,
        selection_sha256:raster.source_selection_sha256,
        tick:raster.film_tick,
      });
      if(result?.status==='NATIVE_SOURCE_REVIEW_REFUSED'){
        setNote('Native source review was refused; no worker started.');
        return;
      }
      if(result?.format!=='nvp.plan03.trusted_original_scene_render_result.v1'||
         result.status!=='VERIFIED_DERIVED_OS_CONTAINED_PNG'||
         result.original_source_modified!==false||
         result.film_master_approved!==false||
         result.source_take_sha256!==spec.take_document_sha256||
         result.source_tick!==raster.film_tick||
         !sha(result.png_sha256)||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(result.png_base64||''))
        throw Error('OS-supervised source renderer returned an invalid receipt');
      setProtectedRaster(result);
      setNote('OS-contained native source render verified with independent PNG SHA. No original source, sound or cinema master changed.');
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  async function renderBlenderCycles(){
    if(!raster||busy||typeof native?.plan04_render_cycles_once!=='function')return;
    setBusy(true);setError('');setNote('');setCyclesPreview(null);
    try{
      const result=await native.plan04_render_cycles_once({
        project_id:projectId,
        selection:raster.selection,
        selection_sha256:raster.source_selection_sha256,
        tick:raster.film_tick,
      });
      if(result?.status==='NATIVE_SOURCE_REVIEW_REFUSED'){
        setNote('Original source review refused. No Blender process started.');
        return;
      }
      if(result?.format!=='nvp.plan04.trusted_os_blender_cycles_result.v1'||
         result.status!=='REAL_BLENDER_CYCLES_AND_INDEPENDENT_REOPEN_VERIFIED'||
         result.engine!=='CYCLES_CPU'||result.original_source_modified!==false||
         result.final_film_published!==false||!result.independently_reopened||
         result.source_tick!==raster.film_tick||
         result.take_sha256!==spec.take_document_sha256||
         !sha(result.png_sha256)||!/^[A-Za-z0-9+/]+={0,2}$/.test(result.png_base64||''))
        throw Error('Blender renderer failed independent original source verification');
      setCyclesPreview(result);
      setNote('Blender/Cycles source render verified in a second native worker. This image is a derivative; no movie master was published.');
    }catch(e){setError(e.message)}
    finally{setBusy(false)}
  }

  function pick(index){
    const entry=sources[index];if(!entry)return;
    setChoice(index);setExpectedRevision(0);setRailId('DirectorRail001');
    setSpec(entry.suggested_unapproved_rail_spec);
    setReceipt(null);setPreview(null);setCandidate(null);
    setRaster(null);setProtectedRaster(null);setCyclesPreview(null);
    onPreviewChange?.(null);
  }

  return <section className="card" aria-label="Exact Film Time director camera rails">
    <h3>Director camera rails and local-model shot advice</h3>
    <p className="fineprint">A separate virtual camera layer over an immutable
      original Digital Take. The source performance and audio never become
      frame-based edits. Model advice is unapproved until you preview it and
      confirm a separate native OS publication dialog.</p>
    {!native&&<p role="status">The NVP desktop is required for original camera authorization.</p>}
    {error&&<p role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    <label>Frozen Take and authored source camera
      <select aria-label="Original frozen source camera" value={choice}
        disabled={busy||!sourceReady} onChange={e=>pick(Number(e.target.value))}>
        {!sources.length&&<option value={0}>No compatible frozen original camera Takes</option>}
        {sources.map((x,i)=><option value={i} key={x.source_take_id+':'+x.camera_timeline_id+':'+i}>
          {x.source_take_id} · {x.source_camera_path} · ticks {x.source_film_start_tick}–{x.source_film_end_tick}
        </option>)}
      </select>
    </label>
    {spec&&<>
      <label>New virtual camera rail identity
        <input aria-label="New director rail ID" value={railId}
          disabled={busy} onChange={e=>{setRailId(e.target.value);setPreview(null);onPreviewChange?.(null);}}/>
      </label>
      <label>Technique
        <select aria-label="Director shot technique" value={spec.technique}
          disabled={busy} onChange={e=>changeSpec({...spec,technique:e.target.value})}>
          {TECHNIQUES.map(t=><option key={t}>{t}</option>)}
        </select>
      </label>
      <p className="fineprint">Original source Take SHA:
        <code>{spec.take_document_sha256.slice(0,16)}…</code>.
        Exact interval: {spec.film_start_tick} through {spec.film_end_tick} ticks.
      </p>
      {spec.nodes.map((node,i)=><section key={i} aria-label={'Director rail control point '+(i+1)}>
        <h4>Control point {i+1}</h4>
        <p>Film Time: <code>{node.tick}</code> (exact source tick)</p>
        {['position_m','target_m'].map(field=>
          <div className="actions" key={field}>
            {['X','Y','Z'].map((axis,j)=>
              <label key={axis}>{field==='position_m'?'Position':'Target'} {axis} (m)
                <input type="number" aria-label={field+' '+axis+' point '+(i+1)}
                  value={node[field][j]} step="0.1" disabled={busy}
                  onChange={e=>updateNode(i,field+'.'+j,e.target.value)}/>
              </label>)}
          </div>)}
        <div className="actions">
          {['focal_length_mm','focus_distance_m','roll_deg'].map(field=>
            <label key={field}>{field.replaceAll('_',' ')}
              <input type="number" aria-label={field+' point '+(i+1)}
                step="0.1" value={node[field]} disabled={busy}
                onChange={e=>updateNode(i,field,e.target.value)}/>
            </label>)}
        </div>
      </section>)}
      <div className="actions">
        <button disabled={busy||spec.nodes.length>=4} onClick={addMidpoint}>
          Insert timed control point
        </button>
        <button disabled={busy||typeof native?.plan02c_preview!=='function'}
          onClick={()=>action('preview')}>Verify original Film Time rail</button>
      </div>
      {preview&&<p role="status">Verified virtual rail SHA:
        <code>{preview.proposal_sha256.slice(0,20)}…</code>.
        {preview.source_film_time_samples.length} source-tick samples; no
        picture frames or renderer worker created.</p>}
      <label>Local GGUF model (from NVP loopback server)
        <select aria-label="Local director GGUF model" value={modelId}
          disabled={busy} onChange={e=>setModelId(e.target.value)}>
          {!models.length&&<option value="">No loaded local model reported</option>}
          {models.map(x=><option value={x.id} key={x.id}>{x.id}</option>)}
        </select>
      </label>
      <label>Director's shot instruction
        <textarea aria-label="Director's camera direction" maxLength={1200}
          value={direction} rows={2} disabled={busy}
          onChange={e=>setDirection(e.target.value)}/>
      </label>
      <div className="actions">
        <button disabled={busy||!modelId||typeof native?.plan02c_model_candidate!=='function'}
          onClick={()=>action('model')}>Ask real local GGUF for unapproved advice (OS approval)</button>
        <button disabled={busy||!preview||typeof native?.plan02c_publish!=='function'}
          onClick={()=>action('publish')}>Approve this exact rail in OS dialog</button>
      </div>
      {candidate&&<p role="status">Model response recorded:
        {candidate.provider_completion_receipt.provider_reported_completion_tokens}
        provider-reported generated tokens. This is NOT model-weight attestation
        or human approval; inspect and preview the new controls.</p>}
      {receipt&&<p role="status">Approved derivative rail revision
        {receipt.revision}, SHA {receipt.rail_document_sha256.slice(0,16)}…;
        no original change.</p>}
    </>}
    {spec&&<section aria-label="Native source-selected camera PNG">
      <h4>Actual OpenUSD camera picture (source-selected)</h4>
      <div className="actions">
        <button disabled={busy||typeof native?.plan02d_raster_preview!=='function'}
          onClick={()=>rasterAction(false)}>
          Render one genuine source-time PNG (no worker)
        </button>
      </div>
      {raster&&<>
        <img src={'data:image/png;base64,'+raster.png_base64}
          alt="Native source-selected OpenUSD procedural-geometry picture"
          style={{maxWidth:'100%',height:'auto'}}/>
        <p className="fineprint">Exact Film Time tick {raster.film_tick}; derived PNG
          SHA <code>{raster.png_sha256.slice(0,20)}…</code>. This raster does
          not assert cinema-quality actor meshes, Hydra, Cycles or DCP compliance.</p>
        <label>New derivative presentation ID
          <input aria-label="Native PNG presentation identity"
            value={rasterName} disabled={busy}
            onChange={e=>setRasterName(e.target.value)}/>
        </label>
        <button disabled={busy||typeof native?.plan02d_raster_publish!=='function'}
          onClick={()=>rasterAction(true)}>
          Publish this exact PNG with new OS approval
        </button>
        <div className="scene-library-protected-render">
          <button disabled={busy||typeof native?.plan03_render_original_once!=='function'}
            onClick={renderWithNativeCustody}>
            Render with protected native worker (two OS approvals)
          </button>
          <p className="fineprint">Launches NVP's source-bound renderer
            under Windows Job Object or Linux delegated cgroup-v2 with
            separate source and execution approvals; no movie export.</p>
          <button disabled={busy||typeof native?.plan04_render_cycles_once!=='function'}
            onClick={renderBlenderCycles}>
            Render approved scene with Blender/Cycles (two OS approvals)
          </button>
          <p className="fineprint">Requires a separately checksum-pinned local
            Blender installation. The real native host must ask twice:
            source review, then execution/reopen permission. No flattened
            movie is created as authoritative source.</p>
          {cyclesPreview&&<>
            <img src={'data:image/png;base64,'+cyclesPreview.png_base64}
              alt="Independently reopened and verified Blender Cycles scene image"
              style={{maxWidth:'100%',height:'auto'}}/>
            <p role="status">Real Blender/Cycles verified.
              Derived SHA: {cyclesPreview.png_sha256.slice(0,20)}…</p>
          </>}
          {protectedRaster&&<>
            <img src={'data:image/png;base64,'+protectedRaster.png_base64}
              alt="Independently verified native OpenUSD source rendering"
              style={{maxWidth:'100%',height:'auto'}}/>
            <p role="status">Protected native renderer:
              {' '+protectedRaster.native_worker_custody}.
              PNG SHA {protectedRaster.png_sha256.slice(0,20)}…
            </p>
          </>}
        </div>
      </>}
    </section>}
    <p className="fineprint">Camera rails never retime an original actor or
      sound recording. This view does not grant Blender/Cycles execution,
      FFmpeg, film export, full GGUF model attestation or theatrical approval.</p>
  </section>;
}
