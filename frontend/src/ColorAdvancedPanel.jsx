import React, { useEffect, useMemo, useState } from 'react';
import './ColorAdvancedPanel.css';
import ColorCurvePanel from './ColorCurvePanel.jsx';

const WHEEL_FORMAT = 'nvp.color.wheels.linear_lift_gamma_gain.v1';
const FORMAT = 'nvp.color.grade.shot_wheels.v1';
const WHEELS = [
  { key: 'lift', label: 'Lift · dark tones', min: -.05, max: .05, step: .002,
    note: 'A small additive shift in scene-linear RGB, before the ACES view.' },
  { key: 'gamma', label: 'Gamma · midtones', min: .7, max: 1.4, step: .01,
    note: 'A middle-gray-pivoted power adjustment. 1 is neutral.' },
  { key: 'gain', label: 'Gain · highlights', min: .75, max: 1.3, step: .01,
    note: 'Multiplicative RGB balance after the gamma adjustment. 1 is neutral.' },
];
const CHANNELS = ['red','green','blue'];
const COLOR = { red: '#ed8b87', green: '#8ddaa5', blue: '#9bb4ed', luma: '#dedbce' };
const neutral = () => ({ format: WHEEL_FORMAT, lift: [0,0,0], gamma: [1,1,1], gain: [1,1,1] });
const initial = (global) => ({ format: FORMAT, global, shots: {} });
const api = async (url, options={}) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    const e = await response.json().catch(() => ({detail:response.statusText}));
    throw Error(typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail));
  }
  return response.json();
};
const max = (values) => Math.max(1, ...values);
const svgPath = (data) => {
  const peak = max(data);
  return data.map((count, index) => `${index ? 'L':'M'}${(index/63*100).toFixed(2)},${(100-count/peak*97).toFixed(2)}`).join(' ');
};
function Histogram({ scope }) {
  const series = scope?.histogram;
  if (!series) return null;
  return <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="grade-advanced-graph"
    role="img" aria-label="Actual 64-bin RGB and luma pixel histogram">
    {[25,50,75].map((y) => <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="#777" strokeWidth=".25" opacity=".4"/>)}
    {['red','green','blue','luma'].map((key) => <path key={key} d={svgPath(series[key])}
      fill="none" stroke={COLOR[key]} strokeWidth="1.25" vectorEffect="non-scaling-stroke" opacity=".85"/>)}
  </svg>;
}
function HeatScope({ scope, kind }) {
  const pixels = scope?.[kind];
  if (!pixels) return null;
  const maximum = max(pixels.flat());
  const marks=[];
  for (let y=0; y<64; ++y) for (let x=0; x<64; ++x) {
    const count=pixels[y][x];
    if (count>0) marks.push(<rect key={`${x}-${y}`} x={x} y={63-y} width="1" height="1"
      fill={kind === 'waveform' ? '#f6e9a8' : '#94e1dc'}
      opacity={Math.min(.98,.16 + .84*Math.sqrt(count/maximum))}/>);
  }
  return <svg viewBox="0 0 64 64" className="grade-advanced-graph" preserveAspectRatio="none"
    role="img" aria-label={kind === 'waveform' ? 'Real 64-column display luma waveform' : 'Real 64 by 64 BT.709 chroma vectorscope'}>
    {marks}
  </svg>;
}
function Wheel({ definition, wheels, onUpdate }) {
  return <section className="grade-wheel" aria-label={definition.label}>
    <h4>{definition.label}</h4>
    <p>{definition.note}</p>
    {CHANNELS.map((channel,i) => <label key={channel}>
      <span style={{ color:COLOR[channel] }}>{channel[0].toUpperCase() + channel.slice(1)}</span>
      <input type="range" min={definition.min} max={definition.max} step={definition.step}
        value={wheels[definition.key][i]}
        onChange={(e) => onUpdate(definition.key,i,Number(e.target.value))}
        aria-label={definition.label + ' ' + channel}/>
      <input type="number" min={definition.min} max={definition.max} step={definition.step}
        value={wheels[definition.key][i]}
        onChange={(e) => {
          const n=Number(e.target.value);
          if (e.target.value !== '' && Number.isFinite(n))
            onUpdate(definition.key,i,Math.min(definition.max,Math.max(definition.min,n)));
        }}
        aria-label={definition.label + ' ' + channel + ' numeric'}/>
    </label>)}
  </section>;
}

export default function ColorAdvancedPanel({ project, sourceId, frame, onFrameChange, globalGrade }) {
  const [timeline,setTimeline] = useState(null);
  const [shotSettings,setShotSettings] = useState({});
  const [past,setPast]=useState([]);
  const [future,setFuture]=useState([]);
  const [output,setOutput] = useState(null);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  const [note,setNote] = useState('');
  const [lookId,setLookId] = useState('shot_look_main');
  const [revision,setRevision] = useState(0);
  const [declared,setDeclared] = useState(false);
  const [saving,setSaving] = useState(false);
  const base = '/api/projects/' + encodeURIComponent(project.id) + '/color-grading/advanced';
  const shot = timeline?.shots?.find((s) => frame>=s.start_frame && frame<=s.end_frame);
  const selected = shot ? shotSettings[shot.shot_id] || neutral() : neutral();
  const plan = useMemo(() => ({
    format: FORMAT,global:globalGrade,shots:shotSettings
  }),[globalGrade,shotSettings]);

  useEffect(() => {
    let alive=true;
    setTimeline(null);setShotSettings({});setPast([]);setFuture([]);
    setOutput(null);setNote('');setError('');setRevision(0);setDeclared(false);
    if (!sourceId) return;
    api(base + '/shots?source_id=' + encodeURIComponent(sourceId))
      .then((v)=>{if(alive)setTimeline(v);})
      .catch((e)=>{if(alive)setError('Shot timeline: '+e.message);});
    return ()=>{alive=false;};
  },[base,sourceId]);

  useEffect(()=>{
    if(!timeline||!shot){setOutput(null);return;}
    const controller = new AbortController();
    const timer=setTimeout(async()=>{
      setLoading(true);
      try {
        const result=await api(base+'/preview',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({source_id:sourceId,frame,plan}),
          signal:controller.signal
        });
        if(!controller.signal.aborted)setOutput(result);
      }catch(e){
        if(!controller.signal.aborted)setError('Advanced preview: '+e.message);
      }finally{if(!controller.signal.aborted)setLoading(false);}
    },320);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[base,sourceId,frame,plan,timeline?.timeline_sha256,shot?.shot_id]);

  function updateWheel(field,i,value) {
    if(!shot)return;
    setPast((p)=>[...p.slice(-49),shotSettings]);
    setFuture([]);
    setShotSettings((prev)=>{
      const target=prev[shot.shot_id]||neutral();
      const wheels={...target,[field]:target[field].map((v,j)=>j===i?value:v)};
      return {...prev,[shot.shot_id]:wheels};
    });
    setNote('');
  }
  const revert=()=>{
    if(!past.length)return;
    setFuture((f)=>[...f,shotSettings]);
    setShotSettings(past[past.length-1]);setPast((p)=>p.slice(0,-1));
  };
  const reapply=()=>{
    if(!future.length)return;
    setPast((p)=>[...p,shotSettings]);
    setShotSettings(future[future.length-1]);setFuture((p)=>p.slice(0,-1));
  };
  const resetShot=()=>{
    if(!shot)return;
    setPast((p)=>[...p,shotSettings]);setFuture([]);
    setShotSettings((old)=>({...old,[shot.shot_id]:neutral()}));
  };
  async function save() {
    if(!timeline||!declared||saving)return;
    setSaving(true);setError('');setNote('');
    try{
      const saved=await api(base+'/grades',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          source_id:sourceId,grade_id:lookId,expected_revision:revision,
          source_primaries_declared:true,plan
        })
      });
      setRevision(saved.revision);
      setNote('Saved independent advanced draft revision '+saved.revision+'; neither take nor EXRs were changed.');
    }catch(e){setError(e.message);}
    finally{setSaving(false);}
  }
  async function load(){
    if(!lookId||saving)return;
    setSaving(true);setError('');
    try{
      const row=await api(base+'/grades/'+encodeURIComponent(lookId));
      if(row.source_id!==sourceId)throw Error('Saved look belongs to another immutable source');
      setShotSettings(row.plan.shots);
      setPast([]);setFuture([]);setRevision(row.revision);
      setNote('Advanced draft restored from version '+row.revision+'; creative approval is still required.');
    }catch(e){setError(e.message);}
    finally{setSaving(false);}
  }
  return <section className="grade-advanced card" aria-labelledby="grade-advanced-title">
    <div className="grade-advanced-heading">
      <div><span className="kicker">GRADE-UI-02A</span>
        <h3 id="grade-advanced-title">Shot grading & professional scopes</h3>
        <p className="muted">Each shot has its own lift, gamma and gain balance. No look alters the Digital Take.</p>
      </div>
      <span className="grade-unapproved">Draft only · not calibrated</span>
    </div>
    {error&&<p className="grade-advanced-error" role="alert">{error}</p>}
    {note&&<p role="status">{note}</p>}
    {!timeline? <p>Choose a verified full-frame EXR source to load its authored shot timeline.</p> : <>
      <div className="grade-shotstrip" role="group" aria-label="Frozen shot timeline">
        {timeline.shots.map((s,i)=><button key={s.shot_id} type="button" className={shot?.shot_id===s.shot_id?'selected':''}
          onClick={()=>onFrameChange(s.start_frame)}
          aria-pressed={shot?.shot_id===s.shot_id}>
          <strong>Shot {i+1}</strong>
          <small>Frames {s.start_frame}–{s.end_frame}</small>
          <span>{shotSettings[s.shot_id]?'Adjusted':'Neutral'}</span>
        </button>)}
      </div>
      <p className="fineprint">Selected: {shot?.shot_id||'—'} · frame {frame} of {timeline.frames} · 24 fps. Source shot boundaries are frozen.</p>
      <div className="grade-advanced-viewport">
        <section>
          <h4>Actual post-ACES preview</h4>
          {output?.png_base64?<img src={'data:image/png;base64,'+output.png_base64}
            alt={'Real color-managed display preview of source frame '+frame+' with its current shot grade'}/>
            :<p>Rendering source image…</p>}
          <p className="fineprint">{loading?'Recalculating… ':''}Measured from full-precision EXR; this browser display is not an approved color reference.</p>
          <div className="grade-wheel-grid">
            {WHEELS.map((w)=><Wheel key={w.key} definition={w} wheels={selected} onUpdate={updateWheel}/>)}
          </div>
          <div className="grade-advanced-actions">
            <button className="secondary" type="button" disabled={!past.length} onClick={revert}>Undo shot edit</button>
            <button className="secondary" type="button" disabled={!future.length} onClick={reapply}>Redo shot edit</button>
            <button className="secondary" type="button" onClick={resetShot}>Reset selected shot</button>
          </div>
        </section>
        <section className="grade-advanced-scopes" aria-label="Measured pixel scopes">
          <h4>Histogram</h4><Histogram scope={output?.scope}/>
          <h4>Waveform · display luma</h4><HeatScope scope={output?.scope} kind="waveform"/>
          <h4>Vectorscope · BT.709 chroma</h4><HeatScope scope={output?.scope} kind="vectorscope"/>
          {output?.scope&&<>
            <p className="fineprint">Measured {output.scope.pixels.toLocaleString()} decoded pixels · mean display luma {output.scope.luma_mean.toFixed(4)}</p>
            <p className="fineprint">Scope source checksum: {output.scope.rgb48_sha256.slice(0,16)}…</p>
          </>}
          <p className="fineprint">Scopes represent post-ACES RGB48 software samples, not measured display output, live SDI signals or an approved monitor.</p>
        </section>
      </div>
      <div className="grade-advanced-save">
        <label>Advanced look ID
          <input value={lookId} maxLength={80} onChange={(e)=>{setLookId(e.target.value);setRevision(0);}}/>
        </label>
        <label className="grade-advanced-check">
          <input type="checkbox" checked={declared} onChange={(e)=>setDeclared(e.target.checked)}/>
          <span>I confirm the source EXR has the declared linear Rec.709 primaries; this is not a colorimetric measurement or grade approval.</span>
        </label>
        <button className="primary" type="button" disabled={!declared||saving||!lookId}
          onClick={save}>{revision?'Save new advanced draft revision':'Save advanced draft look'}</button>
        <button className="secondary" type="button" disabled={saving||!lookId} onClick={load}>Load saved advanced look</button>
      </div>
      <ColorCurvePanel project={project} sourceId={sourceId} frame={frame}
        timeline={timeline} basePlan={plan}/>
    </>}
  </section>;
}
