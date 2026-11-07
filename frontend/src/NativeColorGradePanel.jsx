import React,{useEffect,useState} from 'react';

// DA-06: versioned COLOR DECISIONS about a 3D source, not a grade baked into
// photographed/output frames. Old fixed-frame EXR and codec tools are retired.
// A real 3D/hardware renderer applies a chosen presentation grade later.
const DEFAULTS={
  exposure_stops:0,contrast:1,saturation:1,
  temperature_kelvin:6500,tint_magenta_green:0,
};
const CONTROLS=[
  ['exposure_stops','Exposure (stops)',-6,6,.05],
  ['contrast','Contrast',.1,3,.05],
  ['saturation','Saturation',0,3,.05],
  ['temperature_kelvin','Color temperature (K)',2500,12000,50],
  ['tint_magenta_green','Tint',-1,1,.01],
];

export default function NativeColorGradePanel({project,api,action,busy}){
  const [native,setNative]=useState(null);
  const [takes,setTakes]=useState([]);
  const [takeId,setTakeId]=useState('');
  const [gradeId,setGradeId]=useState('Color001');
  const [params,setParams]=useState(DEFAULTS);
  const [revision,setRevision]=useState(0);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [savedDirty,setSavedDirty]=useState(false);
  const [acesPolicy,setAcesPolicy]=useState(null);
  const [reviewTick,setReviewTick]=useState('0');
  const [preview,setPreview]=useState(null);
  const [reviewBusy,setReviewBusy]=useState(false);
  const [exportBusy,setExportBusy]=useState(false);
  const [presentationId,setPresentationId]=useState('ACESPresentation001');
  const [outputFps,setOutputFps]=useState('24');
  const [outputCamera,setOutputCamera]=useState('');
  const [packageReceipt,setPackageReceipt]=useState(null);
  const take=takes.find(t=>t.take_id===takeId);

  useEffect(()=>{
    const check=()=>{
      const bridge=window.pywebview?.api;
      if(bridge?.data_av_catalog)setNative(bridge);
    };
    check();window.addEventListener('pywebviewready',check);
    return ()=>window.removeEventListener('pywebviewready',check);
  },[]);

  useEffect(()=>{
    if(!native||typeof native.data_av_native_aces_policy!=='function'){
      setAcesPolicy(null);return;
    }
    let active=true;
    Promise.resolve(native.data_av_native_aces_policy()).then(info=>{
      if(!active)return;
      if(info?.format!=='nvp.native_ocio.pinned_aces2_policy.v1'||
         info.uses_ffmpeg!==false||
         !/^[0-9a-f]{64}$/.test(info.configuration_sha256||''))
        throw Error('Installed ACES source color profile is not verified');
      setAcesPolicy(info);
    }).catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[native]);

  useEffect(()=>{
    if(!native)return;
    let valid=true;
    native.data_av_catalog(project.id).then(result=>{
      if(!valid)return;
      if(result?.format!=='nvp.data_av.native_session.v1'||
         result.ffmpeg_runtime_required!==false||
         !Array.isArray(result.takes))throw Error('Native source catalog rejected');
      setTakes(result.takes);
      setTakeId(result.takes[0]?.take_id||'');
      setOutputCamera(result.takes[0]?.source_cameras?.[0]||'');
    }).catch(e=>{if(valid)setError(e.message);});
    return ()=>{valid=false;};
  },[native,project.id]);

  useEffect(()=>{
    setRevision(0);setParams(DEFAULTS);
    setSavedDirty(false);setPreview(null);setReviewTick('0');
    setPackageReceipt(null);
    setMessage('');
  },[takeId,gradeId]);

  useEffect(()=>{
    setOutputCamera(take?.source_cameras?.[0]||'');
    setPackageReceipt(null);
  },[takeId,takes]);

  async function reopen(){
    if(!gradeId)return;
    setError('');
    try{
      const grade=await api('/projects/'+encodeURIComponent(project.id)+
        '/film/native-color/'+encodeURIComponent(gradeId));
      if(grade.format!=='nvp.data_first.color_decision.v1'||
         grade.take_sha256!==take?.take_document_sha256||
         grade.source_modified!==false||
         grade.ffmpeg_used!==false)throw Error(
           'This color decision does not belong to the selected frozen Take');
      setParams(grade.parameters);
      setRevision(grade.revision);
      setSavedDirty(false);setPreview(null);
      setMessage('Opened original color decision revision '+grade.revision);
    }catch(e){setError(e.message);}
  }

  async function save(){
    if(!take||busy)return;
    setError('');setMessage('');
    try{
      await action(async()=>{
        const receipt=await api('/projects/'+encodeURIComponent(project.id)+
          '/film/native-color/'+encodeURIComponent(gradeId),'POST',{
            take_id:take.take_id,
            take_sha256:take.take_document_sha256,
            expected_revision:revision,
            parameters:params,
          });
        if(receipt?.format!=='nvp.data_first.color_decision.v1'||
           receipt.take_sha256!==take.take_document_sha256||
           receipt.source_modified!==false||
           receipt.rendered_frames!==false||
           receipt.flat_master_approved!==false)
          throw Error('Native color decision did not preserve original source');
        setRevision(receipt.revision);
        setSavedDirty(false);setPreview(null);
        setMessage('Saved version '+receipt.revision+
          ' of the non-destructive original Take presentation grade.');
      });
    }catch(e){setError(e.message);}
  }

  async function previewACES2(){
    if(!take||!acesPolicy||!native||reviewBusy||busy||!revision||
       savedDirty||typeof native.data_av_native_aces_review!=='function')return;
    setError('');setMessage('');setPreview(null);
    if(!/^(0|[1-9][0-9]*)$/.test(reviewTick)||
       !Number.isSafeInteger(Number(reviewTick))){
      setError('Enter an exact non-negative Film Time tick.');return;
    }
    setReviewBusy(true);
    try{
      const original=await api('/projects/'+encodeURIComponent(project.id)+
        '/film/native-color/'+encodeURIComponent(gradeId));
      if(original?.format!=='nvp.data_first.color_decision.v1'||
         original.revision!==revision||
         original.take_sha256!==take.take_document_sha256||
         original.source_modified!==false||
         original.ffmpeg_used!==false)
        throw Error('Saved original color revision must match the selected Take');
      const result=await native.data_av_native_aces_review({
        project_id:project.id,take_id:takeId,
        take_sha256:take.take_document_sha256,
        grade_id:gradeId,grade_revision:revision,
        grade_sha256:original.document_sha256,
        film_time_tick:Number(reviewTick),
        expected_config_sha256:acesPolicy.configuration_sha256,
      });
      if(result?.format!=='nvp.native_ocio.source_pinned_aces2_review.v1'||
         result.status!=='VERIFIED_SOURCE_UNMASTERED_ACES2_SDR_DERIVATIVE'||
         result.take_sha256!==take.take_document_sha256||
         result.grade_sha256!==original.document_sha256||
         result.film_time_tick!==reviewTick||
         result.original_modified!==false||
         result.ffmpeg_used!==false||
         result.cinema_master_approved!==false||
         result.scene_linear_source?.source_modified!==false||
         result.processor?.configuration_sha256!==
           acesPolicy.configuration_sha256||
         result.output_mime!=='image/png'||
         typeof result.png16_base64!=='string'||
         !/^[A-Za-z0-9+/]+={0,2}$/.test(result.png16_base64)||
         result.png16_base64.length>22*1024*1024)
        throw Error('Native ACES output is not verifiable source color');
      setPreview(result);
      setMessage('Native ACES2 SDR review at original Film Time '+
        reviewTick+'. No original media or grade was changed.');
    }catch(e){setError(e.message);}
    finally{setReviewBusy(false);}
  }

  async function publishACESPackage(){
    if(!take||!acesPolicy||!native||exportBusy||reviewBusy||
       busy||!revision||savedDirty||!outputCamera)return;
    if(!/^[A-Za-z][A-Za-z0-9_.:-]{0,60}$/.test(presentationId)){
      setError('Choose a unique, safe non-destructive presentation ID.');
      return;
    }
    setExportBusy(true);setError('');setMessage('');setPackageReceipt(null);
    try{
      const saved=await api('/projects/'+encodeURIComponent(project.id)+
        '/film/native-color/'+encodeURIComponent(gradeId));
      if(saved?.format!=='nvp.data_first.color_decision.v1'||
         saved.take_sha256!==take.take_document_sha256||
         saved.revision!==revision||
         saved.source_modified!==false||
         saved.ffmpeg_used!==false)
        throw Error('Only the exact saved source-bound grade can be exported');
      const packaged=await native.data_av_export_native_aces_package({
        project_id:project.id,take_id:take.take_id,
        take_document_sha256:take.take_document_sha256,
        presentation_id:presentationId,listener_path:outputCamera,
        fps_num:Number(outputFps),fps_den:1,
        aces_color_grade:{
          grade_id:gradeId,revision,
          document_sha256:saved.document_sha256,
          config_sha256:acesPolicy.configuration_sha256,
        },
      });
      if(packaged?.status==='CANCELLED'){
        setMessage('Native ACES package destination selection cancelled.');
        return;
      }
      if(packaged?.format!=='nvp.native_ocio.approved_source_png16_package.v1'||
         packaged.status!=='UNMASTERED_ACES2_PNG16_AUDIO_PACKAGE'||
         packaged.take_sha256!==take.take_document_sha256||
         packaged.color_grade_sha256!==saved.document_sha256||
         packaged.pixel_bit_depth!==16||
         packaged.color_pipeline!=='ocio_aces2_scene_linear_png16_unmastered'||
         packaged.ffmpeg_used!==false||
         packaged.original_modified!==false||
         packaged.master_approved!==false)
        throw Error('Native 16-bit source color package receipt was not verified');
      setPackageReceipt(packaged);
      setMessage('Approved new 16-bit ACES2 + PCM source package. '+
        'Original Digital Take is unchanged; output is not a cinema master.');
    }catch(e){setError(e.message);}
    finally{setExportBusy(false);}
  }

  return <section className="card" aria-label="Native data-first color decisions">
    <h2>Color and lighting presentation decisions</h2>
    <p className="fineprint">Set presentation intent for an original 3D
      Digital Take, not its rendered 2D pixels. This keeps all source
      performance, scene lighting, camera data and sound untouched.
      Saved revisions can now drive an exact-time native ACES 2 SDR
      source review. The source colors/lights and display remain
      uncalibrated, so this is not a professional master.</p>
    {!native&&<p role="status">Open the installed NVP desktop application
      to choose a frozen Digital Take.</p>}
    <label>Frozen source Take
      <select aria-label="Frozen color source" value={takeId}
        onChange={e=>setTakeId(e.target.value)}>
        {!takes.length&&<option value="">No native 3D Takes yet</option>}
        {takes.map(t=><option key={t.take_id} value={t.take_id}>
          {t.take_id}</option>)}
      </select>
    </label>
    <label>Color decision ID
      <input value={gradeId} maxLength={80}
        onChange={e=>setGradeId(e.target.value)}/></label>
    <div className="actions">
      <button disabled={!take||busy||!gradeId} onClick={reopen}>
        Reopen prior color decision</button>
    </div>
    {CONTROLS.map(([key,label,min,max,step])=>
      <label key={key}>{label}: {params[key]}
        <input type="range" min={min} max={max} step={step}
          value={params[key]} onChange={e=>{
            setSavedDirty(true);setPreview(null);
            setParams(v=>({...v,[key]:Number(e.target.value)}));
          }}/>
      </label>
    )}
    <button disabled={!take||busy||!gradeId} onClick={save}>
      Save non-destructive color revision</button>
    <fieldset disabled={!take||busy||reviewBusy||!native||!acesPolicy}>
      <legend>Source-verified native ACES 2 SDR review</legend>
      <p className="fineprint">This generates a temporary 16-bit PNG
        from the original OpenUSD camera, actor geometry and light at an
        exact Film Time moment. A creator authorization is required.
        No filmed Take, audio or scene file is changed.</p>
      <label>Exact original Film Time tick
        <input aria-label="ACES original Film Time tick"
          type="number" min="0" step="1" value={reviewTick}
          onChange={e=>{setReviewTick(e.target.value);setPreview(null);}}/>
      </label>
      <button disabled={!revision||savedDirty||reviewBusy||
          typeof native?.data_av_native_aces_review!=='function'}
        onClick={previewACES2}>
        {reviewBusy?'Evaluating source USD…':'Review verified ACES2 source color'}
      </button>
      {savedDirty&&<p role="status">Save this color revision before
        reviewing its original-source appearance.</p>}
      {acesPolicy&&<p className="fineprint">Pinned processor:
        {acesPolicy.configuration} · {acesPolicy.output_view}.
        Original camera calibration and display accuracy are not certified.</p>}
      {preview&&<figure>
        <img alt="Derived source-verified OpenUSD scene in ACES2 SDR review"
          width={preview.width} height={preview.height}
          style={{maxWidth:'100%',height:'auto'}}
          src={'data:image/png;base64,'+preview.png16_base64}/>
        <figcaption>Camera: {preview.original_camera_path} ·
          {preview.scene_linear_source?.actual_usd_skinned_actors||0}
          source skinned actor(s) ·
          {preview.clipped_channels} clipped color channels ·
          16-bit PNG SHA {preview.png16_sha256?.slice(0,16)}…
          This is not an approved professional color master.
        </figcaption>
      </figure>}
    </fieldset>
    <fieldset disabled={!take||busy||exportBusy||reviewBusy||!native||
        !acesPolicy||!revision||savedDirty}>
      <legend>Creator-approved derived ACES2 16-bit picture + PCM</legend>
      <p className="fineprint">Export a new SHA-verified RGB16 PNG sequence
        and a native synchronized WAV from the original frozen 3D Take.
        The OS asks where to save it and separately confirms publication.
        This is never an AVI/FFmpeg export or a cinema-calibrated master.</p>
      <label>New presentation identity
        <input aria-label="Native ACES presentation identity"
          value={presentationId} maxLength={61}
          onChange={e=>setPresentationId(e.target.value)}/>
      </label>
      <label>Original authored USD camera
        <select aria-label="Native ACES output source camera"
          value={outputCamera} onChange={e=>setOutputCamera(e.target.value)}>
          {(take?.source_cameras||[]).map(camera=>
            <option key={camera} value={camera}>{camera}</option>)}
        </select>
      </label>
      <label>Derived picture cadence
        <select aria-label="Native ACES output frames per second"
          value={outputFps} onChange={e=>setOutputFps(e.target.value)}>
          {['24','25','30','60'].map(value=>
            <option key={value} value={value}>{value} frames/sec</option>)}
        </select>
      </label>
      <button disabled={!outputCamera||exportBusy||
          typeof native?.data_av_export_native_aces_package!=='function'}
        onClick={publishACESPackage}>
        {exportBusy?'Rendering approved RGB16/PCM package…':
          'Approve ACES2 16-bit picture and PCM package'}
      </button>
      {packageReceipt&&<p role="status">
        Saved a new immutable derived package:
        {packageReceipt.directory}. Manifest SHA
        {packageReceipt.manifest_sha256?.slice(0,16)}….
        The original scene, Takes, grades and recordings are unchanged.
      </p>}
    </fieldset>
    {message&&<p role="status">{message}</p>}
    {error&&<p role="alert">{error}</p>
    <p className="fineprint">No FFmpeg, EXR decoder, flattened
      frames, proxy or color grade is written to the original.
      Applying and measuring the chosen grade in final output is
      a separate acceptance requirement.</p>
  </section>;
}
