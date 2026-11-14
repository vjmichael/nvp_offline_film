import React, { useEffect, useMemo, useState } from 'react';
import './ColorGradingPanel.css';
import ColorAdvancedPanel from './ColorAdvancedPanel.jsx';

const DEFAULT = {
  exposure_stops: 0,
  contrast: 1,
  saturation: 1,
  red_gain: 1,
  green_gain: 1,
  blue_gain: 1
};
const FORMAT = 'nvp.color.grade.global.v1';
const FIELDS = [
  { key: 'exposure_stops', label: 'Exposure', min: -4, max: 4, step: 0.05, unit: ' stops',
    help: 'Brightness before tone mapping. +1 stop doubles scene-linear light.' },
  { key: 'contrast', label: 'Contrast', min: 0.5, max: 2, step: 0.01,
    help: 'Increase the separation between dark and light details.' },
  { key: 'saturation', label: 'Saturation', min: 0, max: 2, step: 0.01,
    help: '0 removes all color, 1 is neutral; higher values increase color.' },
  { key: 'red_gain', label: 'Red balance', min: 0.7, max: 1.3, step: 0.005,
    help: 'Increase for a warmer look or decrease for a cooler look.' },
  { key: 'green_gain', label: 'Green balance', min: 0.7, max: 1.3, step: 0.005,
    help: 'Adjust the balance between green and magenta.' },
  { key: 'blue_gain', label: 'Blue balance', min: 0.7, max: 1.3, step: 0.005,
    help: 'Increase for a cooler look or decrease for a warmer look.' }
];
const PRESETS = {
  Neutral: DEFAULT,
  Warm: { ...DEFAULT, red_gain: 1.05, blue_gain: 0.96, saturation: 1.03 },
  Cool: { ...DEFAULT, red_gain: 0.96, blue_gain: 1.06, saturation: 0.96 },
  'Soft daylight': { ...DEFAULT, exposure_stops: 0.2, contrast: 0.93, saturation: 0.98 },
  'Low-key drama': { ...DEFAULT, exposure_stops: -0.25, contrast: 1.12, saturation: 0.78 }
};
function asRecipe(values) {
  return { format: FORMAT, scope: 'global_all_frames', ...values };
}
async function jsonFetch(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  }
  return response.json();
}
async function previewImage(url, signal) {
  const response = await fetch(url, { signal, cache: 'no-store' });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  }
  const blob = await response.blob();
  if (blob.type !== 'image/png' || blob.size < 64) throw Error('The actual graded PNG preview could not be verified.');
  return URL.createObjectURL(blob);
}
function formatNumber(x) { return Number(x).toFixed(x === 0 ? 1 : 3).replace(/0+$/, '').replace(/\.$/, ''); }
function GradeSlider({ field, value, onChange }) {
  const controlId = 'grade_' + field.key;
  return <div className="grade-field">
    <div className="grade-field-label"><label htmlFor={controlId}>{field.label}</label>
      <span title={field.help}>{field.help}</span></div>
    <div className="grade-field-inputs">
      <input id={controlId} type="range" min={field.min} max={field.max} step={field.step}
        value={value} onChange={(e) => onChange(field.key, Number(e.target.value))}
        aria-label={field.label}/>
      <input type="number" min={field.min} max={field.max} step={field.step} value={value}
        aria-label={field.label + ' numeric value'}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (e.target.value !== '' && Number.isFinite(next))
            onChange(field.key, Math.min(field.max, Math.max(field.min, next)));
        }}/>
    </div>
  </div>;
}

export default function ColorGradingPanel({ project, onHelp }) {
  const [sources, setSources] = useState([]);
  const [sourceId, setSourceId] = useState('');
  const [frame, setFrame] = useState(1);
  const [controls, setControls] = useState({ ...DEFAULT });
  const [past, setPast] = useState([]);
  const [future, setFuture] = useState([]);
  const [gradeId, setGradeId] = useState('look_main');
  const [currentRevision, setCurrentRevision] = useState(0);
  const [savedGradeId, setSavedGradeId] = useState('');
  const [saved, setSaved] = useState([]);
  const [history, setHistory] = useState([]);
  const [declared, setDeclared] = useState(false);
  const [wipe, setWipe] = useState(50);
  const [before, setBefore] = useState(null);
  const [after, setAfter] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const active = sources.find((s) => s.id === sourceId);
  const base = '/api/projects/' + encodeURIComponent(project.id) + '/color-grading';
  const recipe = useMemo(() => asRecipe(controls), [controls]);

  useEffect(() => {
    let alive = true;
    setError(''); setNotice(''); setSourceId(''); setSources([]);
    jsonFetch(base + '/sources')
      .then((list) => { if (alive) {
        setSources(list);
        setSourceId(list[0]?.id || '');
      } })
      .catch((err) => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, [base]);

  useEffect(() => {
    setFrame(1); setControls({ ...DEFAULT }); setPast([]); setFuture([]);
    setCurrentRevision(0); setSavedGradeId(''); setGradeId('look_main');
    setDeclared(false); setHistory([]); setSaved([]);
    if (!sourceId) return;
    let alive = true;
    jsonFetch(base + '/grades?source_id=' + encodeURIComponent(sourceId))
      .then((items) => { if (alive) setSaved(items); })
      .catch((err) => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, [base, sourceId]);

  const update = (field, value) => {
    if (Object.is(value, controls[field])) return;
    setPast((list) => [...list.slice(-49), controls]);
    setControls((old) => ({ ...old, [field]: value }));
    setFuture([]);
    setNotice('');
  };
  const preset = (values) => {
    setPast((list) => [...list.slice(-49), controls]);
    setControls({ ...values });
    setFuture([]); setNotice('');
  };
  const undo = () => {
    if (!past.length) return;
    setFuture((list) => [...list, controls]);
    setControls(past[past.length - 1]);
    setPast((list) => list.slice(0, -1));
  };
  const redo = () => {
    if (!future.length) return;
    setPast((list) => [...list, controls]);
    setControls(future[future.length - 1]);
    setFuture((list) => list.slice(0, -1));
  };

  useEffect(() => {
    if (!active) { setBefore(null); return; }
    const ac = new AbortController();
    let url = null;
    const params = new URLSearchParams({ frame: String(frame), mode: 'before' });
    previewImage(base + '/sources/' + encodeURIComponent(sourceId) + '/preview?' + params, ac.signal)
      .then((link) => { if (!ac.signal.aborted) { url = link; setBefore(link); } else URL.revokeObjectURL(link); })
      .catch((err) => { if (!ac.signal.aborted) setError('Original preview: ' + err.message); });
    return () => { ac.abort(); if (url) URL.revokeObjectURL(url); };
  }, [base, sourceId, frame, active?.source_sha256]);

  useEffect(() => {
    if (!active) { setAfter(null); return; }
    const ac = new AbortController();
    let url = null;
    const handle = setTimeout(async () => {
      const params = new URLSearchParams({ frame: String(frame), mode: 'after' });
      FIELDS.forEach(({ key }) => params.set(key, String(controls[key])));
      setLoading(true);
      try {
        const link = await previewImage(base + '/sources/' + encodeURIComponent(sourceId) + '/preview?' + params, ac.signal);
        if (!ac.signal.aborted) { url = link; setAfter(link); }
        else URL.revokeObjectURL(link);
      } catch (err) {
        if (!ac.signal.aborted) setError('Graded preview: ' + err.message);
      } finally { if (!ac.signal.aborted) setLoading(false); }
    }, 280);
    return () => { clearTimeout(handle); ac.abort(); if (url) URL.revokeObjectURL(url); };
  }, [base, sourceId, frame, active?.source_sha256, controls]);

  async function saveGrade() {
    if (!sourceId || busy) return;
    if (!declared) { setError('Confirm the source-space declaration before saving.'); return; }
    if (!/^[a-zA-Z][a-zA-Z0-9_.:-]{0,79}$/.test(gradeId)) {
      setError('The look ID must start with a letter and contain only letters, numbers, _, ., : or -.'); return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await jsonFetch(base + '/grades', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade_id: gradeId, source_exr_id: sourceId,
          expected_revision: savedGradeId === gradeId ? currentRevision : 0,
          source_primaries_declared: true, recipe
        })
      });
      setSavedGradeId(result.id); setCurrentRevision(result.revision);
      const [items, versions] = await Promise.all([
        jsonFetch(base + '/grades?source_id=' + encodeURIComponent(sourceId)),
        jsonFetch(base + '/grades/' + encodeURIComponent(result.id) + '/history')
      ]);
      setSaved(items); setHistory(versions);
      setNotice('Draft look saved as immutable FilmIndex revision ' + result.revision + '. No source or master was changed.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function loadSaved(id, rev = null) {
    setBusy(true); setError(''); setNotice('');
    try {
      const qs = rev === null ? '' : '?revision=' + rev;
      const doc = await jsonFetch(base + '/grades/' + encodeURIComponent(id) + qs);
      if (doc.source_exr_id !== sourceId) throw Error('This look belongs to a different frozen EXR source.');
      const values = Object.fromEntries(FIELDS.map(({ key }) => [key, doc.recipe[key]]));
      setPast((list) => [...list.slice(-49), controls]); setFuture([]);
      setControls(values); setGradeId(id);
      // An earlier historical revision is a baseline to compare, not an
      // implicit rewrite of newer saved history.
      setCurrentRevision(rev === null ? doc.revision : 0);
      setSavedGradeId(rev === null ? id : '');
      setHistory(await jsonFetch(base + '/grades/' + encodeURIComponent(id) + '/history'));
      setNotice(rev === null ? 'Loaded draft. You may revise it and save a new version.' :
        'Loaded historic look for comparison. Save under a different ID to keep later revisions untouched.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <section className="grade-workspace" aria-labelledby="grade-workspace-title">
    <header className="grade-title">
      <div><div className="kicker">NVP · GRADE-UI-01</div>
        <h2 id="grade-workspace-title">Color grading workspace</h2>
        <p className="muted">Adjust the look of your film without changing its original performance or scene-linear frames.</p>
      </div>
      <button className="secondary" type="button" onClick={onHelp}>Learn color grading</button>
    </header>
    {error && <p role="alert" className="alert grade-alert">{error}</p>}
    {notice && <p role="status" className="notice grade-alert">{notice}</p>}
    {!sources.length ? <div className="card">
      <h3>No mastering-ready EXR sequence in this film yet</h3>
      <p>This workspace requires a frozen Digital Take with a complete 24fps Cycles HALF OpenEXR sequence. Render it first using NVP’s native production pipeline. PNG proxies and isolated keyframes are not interchangeable with a full film master.</p>
    </div> : <>
      <div className="grade-topbar card">
        <label>Frozen source
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            {sources.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.frames} frames · {item.width}×{item.height}</option>)}
          </select></label>
        <label>Frame <span>{frame} of {active?.frames ?? 0}</span>
          <input type="range" min="1" max={active?.frames || 1} step="1" value={frame}
            onChange={(e) => setFrame(Number(e.target.value))} aria-label="Preview source frame"/>
        </label>
        <p className="fineprint">24 fps · source/take SHA verified · uncalibrated monitor preview</p>
      </div>
      <div className="grade-layout">
        <div className="card grade-monitor-section">
          <h3>Before / after · real OCIO-generated pixels</h3>
          <div className="grade-monitor" style={{ aspectRatio: active ? `${active.width} / ${active.height}` : '16 / 9' }}>
            {before && after ? <>
              <img src={before} alt="Original neutral-grade source viewed through the matching ACES transform" />
              <div className="grade-after" style={{ clipPath: `inset(0 ${100 - wipe}% 0 0)` }}>
                <img src={after} alt="Current non-destructive grade through the same ACES transform"/>
              </div>
              <div className="grade-wipe-line" style={{ left: `${wipe}%` }} aria-hidden="true"/>
            </> : <p role="status">Loading actual FilmIndex frames…</p>}
          </div>
          <div className="grade-wipe-row">
            <span>Original</span>
            <input type="range" min="0" max="100" step="1" value={wipe} onChange={(e) => setWipe(Number(e.target.value))}
              aria-label="Before and after comparison wipe" />
            <span>Graded</span>
          </div>
          <p className="fineprint">{loading ? 'Re-rendering selected grade… ' : ''}
            This is a browser review preview, not a color-calibrated grading display. The source EXR remains immutable.
          </p>
        </div>
        <div className="card grade-controls">
          <h3>Essentials · global look</h3>
          <div className="grade-presets" aria-label="Starting looks">
            {Object.entries(PRESETS).map(([name, values]) => (
              <button key={name} className="secondary" type="button" onClick={() => preset(values)}>{name}</button>
            ))}
          </div>
          {FIELDS.map((field) => <GradeSlider key={field.key} field={field}
            value={controls[field.key]} onChange={update}/>)}
          <div className="grade-actions">
            <button className="secondary" type="button" disabled={!past.length} onClick={undo}>Undo</button>
            <button className="secondary" type="button" disabled={!future.length} onClick={redo}>Redo</button>
            <button className="secondary" type="button" onClick={() => preset(DEFAULT)}>Reset neutral</button>
          </div>
        </div>
      </div>
      <ColorAdvancedPanel project={project} sourceId={sourceId} frame={frame}
        onFrameChange={setFrame} globalGrade={recipe}/>
      <div className="card grade-save-panel">
        <h3>Save a look · never overwrite the frozen take</h3>
        <label>Look ID
          <input value={gradeId} onChange={(e) => setGradeId(e.target.value)} maxLength={80}
            placeholder="look_main" aria-label="Draft grade ID" />
        </label>
        <label className="grade-check"><input type="checkbox" checked={declared}
          onChange={(e) => setDeclared(e.target.checked)} />
          <span>I confirm this scene-linear EXR source uses declared Linear Rec.709 (sRGB) primaries. This is not a calibrated color measurement.</span>
        </label>
        <button className="primary" disabled={busy || !declared || !sourceId}
          onClick={saveGrade}>{busy ? 'Working…' : savedGradeId === gradeId ? 'Save a new draft revision' : 'Save draft look'}</button>
        <p className="fineprint">Saving a look creates a versioned FilmIndex edit document. It does not approve the grade, render a master, modify a source file, or grant an AI permission to choose colors.</p>
      </div>
      <div className="card">
        <h3>Saved looks and revisions</h3>
        {!saved.length && <p className="muted">No draft looks saved for this EXR source.</p>}
        {saved.map((item) => <button key={item.id} type="button" className="scene-item"
          onClick={() => loadSaved(item.id)} disabled={busy}>
          <strong>{item.id}</strong><span>Draft revision {item.revision} · {item.status}</span>
        </button>)}
        {history.length > 0 && <>
          <h3>Revision history</h3>
          {history.map((v) => <button key={v.revision} type="button" className="secondary grade-history"
            onClick={() => loadSaved(gradeId, v.revision)} disabled={busy}>
            Review version {v.revision} · {v.sha256.slice(0, 12)}…
          </button>)}
        </>}
      </div>
    </>}
  </section>;
}
