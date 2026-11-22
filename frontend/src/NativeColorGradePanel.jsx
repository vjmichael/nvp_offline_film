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
    if(!native)return;
    let valid=true;
    native.data_av_catalog(project.id).then(result=>{
      if(!valid)return;
      if(result?.format!=='nvp.data_av.native_session.v1'||
         result.ffmpeg_runtime_required!==false||
         !Array.isArray(result.takes))throw Error('Native source catalog rejected');
      setTakes(result.takes);
      setTakeId(result.takes[0]?.take_id||'');
    }).catch(e=>{if(valid)setError(e.message);});
    return ()=>{valid=false;};
  },[native,project.id]);

  useEffect(()=>{
    setRevision(0);setParams(DEFAULTS);
    setMessage('');
  },[takeId,gradeId]);

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
        setMessage('Saved version '+receipt.revision+
          ' of the non-destructive original Take presentation grade.');
      });
    }catch(e){setError(e.message);}
  }

  return <section className="card" aria-label="Native data-first color decisions">
    <h2>Color and lighting presentation decisions</h2>
    <p className="fineprint">Set presentation intent for an original 3D
      Digital Take, not its rendered 2D pixels. This keeps all source
      performance, scene lighting, camera data and sound untouched.
      These controls are versioned for future native scene evaluation,
      not yet a calibrated color-managed output.</p>
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
          value={params[key]} onChange={e=>setParams(v=>({
            ...v,[key]:Number(e.target.value)
          }))}/>
      </label>
    )}
    <button disabled={!take||busy||!gradeId} onClick={save}>
      Save non-destructive color revision</button>
    {message&&<p role="status">{message}</p>}
    {error&&<p role="alert">{error}</p>}
    <p className="fineprint">No FFmpeg, EXR decoder, flattened
      frames, proxy or color grade is written to the original.
      Applying and measuring the chosen grade in final output is
      a separate acceptance requirement.</p>
  </section>;
}
