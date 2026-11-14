import React, { useEffect, useMemo, useState } from 'react';
import './ColorCurvePanel.css';

const CURVE_FORMAT = 'nvp.color.grade.luma_ev_curve.v1';
const FORMAT = 'nvp.color.grade.shot_curves.v1';
const LABELS = ['Deep black', 'Shadows', 'Middle gray', 'Highlights', 'Bright white'];
const STOPS = [-8,-4,0,4,8];
const neutral = () => ({format: CURVE_FORMAT, ev_offsets:[0,0,0,0,0]});
async function json(url,opts={}) {
  const r=await fetch(url,opts);
  if(!r.ok) {
    const data=await r.json().catch(()=>({detail:r.statusText}));
    throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return r.json();
}
function ToneGraph({curve}) {
  const xs=STOPS.map((n)=> (n+8)/16*100);
  const ys=STOPS.map((n,i)=> 100-(n+curve.ev_offsets[i]+9.5)/19*100);
  const curveLine=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(2)},${ys[i].toFixed(2)}`).join(' ');
  const neutralLine=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(2)},${(100-(STOPS[i]+9.5)/19*100).toFixed(2)}`).join(' ');
  return <svg viewBox="0 0 100 100" role="img" aria-label="Editable scene-linear EV tone curve compared against neutral"
    className="curve-graph">
    {[25,50,75].map((v)=><line key={v} x1="0" x2="100" y1={v} y2={v} stroke="#596170" strokeWidth=".4"/>)}
    <path d={neutralLine} stroke="#818694" strokeDasharray="3 2" strokeWidth="1" fill="none"/>
    <path d={curveLine} stroke="#ffd18a" strokeWidth="1.9" fill="none"/>
    {xs.map((x,i)=><circle key={i} cx={x} cy={ys[i]} r="1.7" fill="#ffe2b4"/>)}
  </svg>;
}
export default function ColorCurvePanel({project,sourceId,frame,timeline,basePlan}) {
  const [curves,setCurves]=useState({});
  const [undo,setUndo]=useState([]);
  const [redo,setRedo]=useState([]);
  const [preview,setPreview]=useState(null);
  const [referenceFrame,setReferenceFrame]=useState(1);
  const [suggestion,setSuggestion]=useState(null);
  const [error,setError]=useState('');
  const [note,setNote]=useState('');
  const [loading,setLoading]=useState(false);
  const [saveId,setSaveId]=useState('curve_look_main');
  const [revision,setRevision]=useState(0);
  const [approvedSource,setApprovedSource]=useState(false);
  const current=timeline?.shots?.find(s=>frame>=s.start_frame&&frame<=s.end_frame);
  const curve=current ? curves[current.shot_id] || neutral() : neutral();
  const plan=useMemo(()=>({format:FORMAT,base:basePlan,curves}),[basePlan,curves]);
  const root='/api/projects/'+encodeURIComponent(project.id)+'/color-grading/curves';

  useEffect(()=>{
    setCurves({});setUndo([]);setRedo([]);setPreview(null);
    setSuggestion(null);setRevision(0);setApprovedSource(false);
    setReferenceFrame(1);setError('');setNote('');
  },[sourceId]);

  useEffect(()=>{
    if(!current||!timeline)return;
    const abort=new AbortController();
    const t=setTimeout(async()=>{
      setLoading(true);
      try {
        const data=await json(root+'/preview',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({source_id:sourceId,frame,plan}),
          signal:abort.signal
        });
        if(!abort.signal.aborted)setPreview(data);
      }catch(e){if(!abort.signal.aborted)setError('Tone-curve preview: '+e.message);}
      finally{if(!abort.signal.aborted)setLoading(false);}
    },350);
    return()=>{clearTimeout(t);abort.abort();};
  },[root,sourceId,frame,timeline?.timeline_sha256,plan,current?.shot_id]);

  function adjust(index,value) {
    if(!current||index===0||index===4)return;
    setUndo(x=>[...x.slice(-49),curves]);setRedo([]);setSuggestion(null);
    setCurves(old=>{
      const p=old[current.shot_id]||neutral();
      return {...old,[current.shot_id]:{...p,ev_offsets:p.ev_offsets.map((v,i)=>i===index?value:v)}};
    });
  }
  function reset(){
    if(!current)return;
    setUndo(x=>[...x.slice(-49),curves]);setRedo([]);
    setCurves(p=>({...p,[current.shot_id]:neutral()}));
  }
  function back(){
    if(!undo.length)return;
    setRedo(x=>[...x,curves]);setCurves(undo.at(-1));setUndo(x=>x.slice(0,-1));
  }
  function forward(){
    if(!redo.length)return;
    setUndo(x=>[...x,curves]);setCurves(redo.at(-1));setRedo(x=>x.slice(0,-1));
  }
  async function match(){
    if(!current)return;
    setError('');setSuggestion(null);
    try {
      const data=await json(root+'/reference-suggestion',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({source_id:sourceId,target_frame:frame,
          reference_frame:referenceFrame,base_plan:basePlan})
      });
      setSuggestion(data);
    }catch(e){setError('Reference comparison: '+e.message);}
  }
  async function save(){
    if(!approvedSource||!sourceId)return;
    setError('');
    try {
      const data=await json(root+'/grades',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({source_id:sourceId,grade_id:saveId,
          expected_revision:revision,source_primaries_declared:true,plan})
      });
      setRevision(data.revision);
      setNote('Saved immutable unapproved curve draft revision '+data.revision+'.');
    }catch(e){setError('Save failed: '+e.message);}
  }
  async function load(){
    setError('');setNote('');
    try{
      const data=await json(root+'/grades/'+encodeURIComponent(saveId));
      if(data.source_id!==sourceId)throw Error('This look belongs to a different frozen source');
      setCurves(data.plan.curves);
      setRevision(data.revision);setUndo([]);setRedo([]);
      setNote('Loaded saved curve revision '+data.revision+'; no source frames changed.');
    }catch(e){setError('Load failed: '+e.message);}
  }
  return <section className="card color-curve-panel" aria-label="HDR scene-linear curves and reference shot matching">
    <div className="curve-title">
      <div><span className="kicker">GRADE-UI-02B1</span>
        <h3>HDR tone curves & reference-shot advice</h3>
        <p className="fineprint">Adjust shadows, middle gray and highlights in exposure stops before ACES. The endpoints remain fixed; the frozen source stays unchanged.</p>
      </div>
      <span className="curve-draft">Preview only · not calibrated</span>
    </div>
    {error&&<p className="grade-advanced-error" role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    {!timeline||!current?<p>Choose a frozen shot to edit its tone curve.</p>:<>
      <div className="curve-main">
        <div>
          <h4>Current shot: {current.shot_id}</h4>
          <ToneGraph curve={curve}/>
          <div className="curve-knots">
            {LABELS.map((label,i)=><label key={label}>
              <span>{label} · {STOPS[i]} EV</span>
              <input type="range" min="-1.5" max="1.5" step=".05"
                value={curve.ev_offsets[i]} disabled={i===0||i===4}
                onChange={e=>adjust(i,Number(e.target.value))}
                aria-label={label+' offset in stops'}/>
              <input type="number" min="-1.5" max="1.5" step=".05"
                value={curve.ev_offsets[i]} disabled={i===0||i===4}
                onChange={e=>{
                  const n=Number(e.target.value);
                  if(e.target.value!==''&&Number.isFinite(n))
                    adjust(i,Math.max(-1.5,Math.min(1.5,n)));
                }} aria-label={label+' numeric EV offset'}/>
            </label>)}
          </div>
          <div className="grade-advanced-actions">
            <button type="button" className="secondary" disabled={!undo.length} onClick={back}>Undo curve</button>
            <button type="button" className="secondary" disabled={!redo.length} onClick={forward}>Redo curve</button>
            <button type="button" className="secondary" onClick={reset}>Reset shot curve</button>
          </div>
        </div>
        <div>
          <h4>Real tone-curved preview</h4>
          {preview?.png_base64 ? <img className="curve-preview" src={'data:image/png;base64,'+preview.png_base64}
             alt={'Real scene-linear tone-curved frame '+frame} />:<p>Decoding OpenEXR and applying OCIO…</p>}
          <p className="fineprint">{loading?'Re-rendering… ':''}Image/scopes derived from the same decoded source and pinned ACES view. Not approved color output.</p>
          <h4>Reference-shot exposure suggestion</h4>
          <label>Reference frame
            <input type="number" min="1" max={timeline.frames} step="1" value={referenceFrame}
              onChange={e=>setReferenceFrame(Math.max(1,Math.min(timeline.frames,Number(e.target.value)||1)))}/>
          </label>
          <button className="secondary" onClick={match} type="button"
            disabled={referenceFrame===frame}>Compare reference without changing any image</button>
          {suggestion&&<div className="curve-suggestion">
            <strong>Estimated difference: {suggestion.suggested_exposure_stops.toFixed(2)} stops</strong>
            <p>Based on mean display luminance from actual source frames. This is a starting-point suggestion, not an automatic match or calibrated measurement.</p>
            <button type="button" className="secondary" onClick={()=>adjust(2,
              Math.max(-1.5,Math.min(1.5,suggestion.suggested_exposure_stops)))}>
              Apply suggestion to this shot’s middle-gray knot
            </button>
          </div>}
        </div>
      </div>
      <div className="curve-save">
        <label>Curve-look ID <input value={saveId} maxLength={80}
          onChange={e=>{setSaveId(e.target.value);setRevision(0);}}/></label>
        <label className="grade-advanced-check"><input type="checkbox"
          checked={approvedSource} onChange={e=>setApprovedSource(e.target.checked)}/>
          <span>I confirm the source has declared linear Rec.709 primaries. This is not calibrated or a director's grade approval.</span>
        </label>
        <button className="primary" type="button" disabled={!approvedSource||!saveId} onClick={save}>
          {revision?'Save new curve draft revision':'Save curve draft'}
        </button>
        <button className="secondary" type="button" disabled={!saveId} onClick={load}>Load curve draft</button>
      </div>
    </>}
  </section>;
}
