import React,{useEffect,useRef,useState} from 'react';
import './director-environment-look.css';

const materialDefault={color:'#8799aa',roughness:.72,metallic:0,
  emission:0,kind:'stone'};
const names={original:'Original setting',interior:'Interior',
  city:'City',mountains:'Mountains',coast:'Coast',forest:'Forest',
  desert:'Desert',farmland:'Farmland',space:'Space',open:'Open landscape'};
const firstPosition=[0,0,0];
async function request(url,method='GET',body){
  const response=await fetch(url,{method,credentials:'same-origin',
    headers:{'x-nvp-director':'1','Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw new Error(typeof error.detail==='string'?error.detail:
      'This scene change was not saved. Your earlier look remains available.');
  }
  return response.json();
}
function Coords({name,values,onChange}){
  return <fieldset className="director-look-coords"><legend>{name}</legend>
    {['X','Y','Z'].map((label,index)=><label key={label}>{label}
      <input type="number" step=".25" min="-150" max="150"
        value={values[index]} onChange={e=>onChange(values.map((n,i)=>
          index===i?Number(e.target.value):n))}/></label>)}
  </fieldset>;
}
function Material({value,onChange}){
  const v=value||materialDefault;
  const set=(key,val)=>onChange({...v,[key]:val});
  return <div className="director-look-material">
    <label>Surface type<select value={v.kind}
      onChange={e=>set('kind',e.target.value)}>
      {['stone','plaster','glass','wood','metal','earth','foliage','fabric']
        .map(x=><option key={x} value={x}>{x[0].toUpperCase()+x.slice(1)}</option>)}
    </select></label>
    <label>Surface color<input type="color" value={v.color}
      onChange={e=>set('color',e.target.value)}/></label>
    <label>Surface softness
      <input type="range" min=".03" max="1" step=".01" value={v.roughness}
        onChange={e=>set('roughness',Number(e.target.value))}/>
      <small>{Math.round(v.roughness*100)}%</small></label>
    <label>Metallic finish
      <input type="range" min="0" max="1" step=".01" value={v.metallic}
        onChange={e=>set('metallic',Number(e.target.value))}/>
    </label>
    <label>Glow
      <input type="range" min="0" max="20" step=".25" value={v.emission}
        onChange={e=>set('emission',Number(e.target.value))}/>
    </label>
  </div>;
}
export default function DirectorEnvironmentLook({movie,takeId}){
  const prefix='/api/projects/'+encodeURIComponent(movie.id)+
    (movie.encrypted?'/live':'')+'/production/looks/'+encodeURIComponent(takeId||'');
  const [data,setData]=useState(null);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [preview,setPreview]=useState('');
  const [chosenPreset,setChosenPreset]=useState('original');
  const [lights,setLights]=useState(null);
  const [selectedObject,setSelectedObject]=useState('');
  const [objectMaterial,setObjectMaterial]=useState(materialDefault);
  const [pieceName,setPieceName]=useState('Set object');
  const [pieceShape,setPieceShape]=useState('box');
  const [piecePosition,setPiecePosition]=useState([0,0,0]);
  const [pieceScale,setPieceScale]=useState([1,1,1]);
  const [pieceMaterial,setPieceMaterial]=useState(materialDefault);
  const [selectedPiece,setSelectedPiece]=useState('');
  const [pieceDraft,setPieceDraft]=useState(null);
  const [kitName,setKitName]=useState('');
  const [selectedKit,setSelectedKit]=useState('');
  const alive=useRef(true);
  useEffect(()=>{
    alive.current=true;setData(null);setError('');setNotice('');setPreview('');
    if(!takeId)return()=>{alive.current=false};
    request(prefix).then(doc=>{
      if(alive.current)setData(doc);
    }).catch(e=>{if(alive.current)setError(e.message)});
    return()=>{alive.current=false};
  },[prefix,takeId]);

  useEffect(()=>{
    if(!data)return;
    const d=data.draft;
    setChosenPreset(d.preset);
    setLights({sun:{...d.sun},atmosphere:{...d.atmosphere},
      sky:d.sky,ground:d.ground});
    const first=data.filmed_objects?.[0]?.id||'';
    setSelectedObject(x=>data.filmed_objects.some(y=>y.id===x)?x:first);
  },[data?.revision,takeId]);
  useEffect(()=>{
    if(!data||!selectedObject)return;
    setObjectMaterial({...materialDefault,...(
      data.draft.materials?.[selectedObject]||{})});
  },[data?.revision,selectedObject]);
  useEffect(()=>{
    const selected=data?.draft?.set_pieces?.find(x=>x.id===selectedPiece);
    setPieceDraft(selected?{...selected,
      position:[...selected.position],
      rotation:[...selected.rotation],
      scale:[...selected.scale],
      material:{...selected.material}}:null);
  },[selectedPiece,data?.revision]);

  useEffect(()=>{
    if(!data||!takeId)return;
    let cancelled=false,url=null;
    fetch(prefix+'/preview',{
      credentials:'same-origin',headers:{'x-nvp-director':'1'}
    }).then(async response=>{
      if(!response.ok)throw Error('The scene preview is unavailable on this device');
      return await response.blob();
    }).then(blob=>{
      if(cancelled)return;
      url=URL.createObjectURL(blob);
      setPreview(url);
    }).catch(()=>{if(!cancelled)setPreview('')});
    return()=>{
      cancelled=true;
      if(url)URL.revokeObjectURL(url);
    };
  },[prefix,data?.revision]);

  async function update(operation,details,success){
    if(busy||!data)return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await request(prefix+'/change','POST',{
        expected_revision:data.revision,operation,details});
      if(alive.current){setData(doc);if(success)setNotice(success)}
    }catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  async function approve(){
    if(!data||busy)return;
    if(!window.confirm('Approve this scene look for your finished movie? Your filmed performance and sound will stay the same.'))return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await request(prefix+'/approve','POST',{
        expected_revision:data.revision});
      if(alive.current){setData(doc);
        setNotice('This scene look is approved for your movie.')}}
    catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  async function saveKit(){
    if(!data||busy||!kitName.trim())return;
    setBusy(true);setError('');setNotice('');
    try{
      const doc=await request(prefix+'/save-set','POST',{
        expected_revision:data.revision,name:kitName.trim()});
      if(alive.current){setData(doc);setKitName('');
        setNotice('Your set is saved. It can be reused in another scene.')}}
    catch(e){if(alive.current)setError(e.message)}
    finally{if(alive.current)setBusy(false)}
  }
  if(!takeId)return null;
  const d=data?.draft;
  const approved=data?.revision===data?.approved_revision&&
    (data?.approved_revision||0)>0;
  const sourcePiece=d?.set_pieces.find(x=>x.id===selectedPiece);
  return <section className="director-look-room" aria-label="Finish this scene's look">
    <div className="director-look-heading">
      <div><h3>Finish the scene's look</h3>
        <p className="film-muted">Choose a setting, dress the set and shape
          the light. Your original performance and sound never change.</p>
      </div>
      <span className="director-look-status">{approved?
        'Approved for your movie':data?'Creative changes awaiting approval':
        'Opening the scene…'}</span>
    </div>
    {error&&<p className="director-look-error" role="alert">{error}</p>}
    {notice&&<p className="director-look-notice" role="status">{notice}</p>}
    {data&&<>
      <div className="director-look-preview">
        {preview?<img src={preview}
          alt="A rendered frame of your actual scene with the current visual look"/>:
          <p className="film-muted">Scene preview unavailable. Your original
            Takes remain usable; you can still make the decisions below.</p>}
        <p className="film-hint">A quick view of the real scene. Final picture
          quality depends on the chosen film rendering profile.</p>
      </div>
      <div className="director-look-grid">
        <div className="director-look-section">
          <h4>Where does the scene take place?</h4>
          <label>Environment
            <select value={chosenPreset}
              onChange={e=>setChosenPreset(e.target.value)}>
              {data.presets.map(p=><option key={p} value={p}>{names[p]||p}</option>)}
            </select></label>
          <button className="film-secondary" disabled={busy}
            onClick={()=>update('preset',{preset:chosenPreset},
              'Setting updated. Review it, then approve when ready.')}>
            Use This Setting</button>
        </div>
        <div className="director-look-section">
          <h4>Light and atmosphere</h4>
          {lights&&<>
            <div className="director-look-colors">
              <label>Sky<input type="color" value={lights.sky}
                onChange={e=>setLights(x=>({...x,sky:e.target.value}))}/></label>
              <label>Ground<input type="color" value={lights.ground}
                onChange={e=>setLights(x=>({...x,ground:e.target.value}))}/></label>
              <label>Haze color<input type="color"
                value={lights.atmosphere.color}
                onChange={e=>setLights(x=>({...x,
                  atmosphere:{...x.atmosphere,color:e.target.value}}))}/></label>
            </div>
            {[
              ['azimuth','Sun direction',-180,180,1],
              ['elevation','Sun height',-5,90,1],
              ['intensity','Light strength',0,8,.1],
              ['fill','Ambient light',0,3,.05],
              ['temperature','Warm / cool light',2000,12000,100]
            ].map(([key,label,min,max,step])=><label key={key}>
              {label}<input type="range" min={min} max={max} step={step}
                value={lights.sun[key]}
                onChange={e=>setLights(x=>({...x,
                  sun:{...x.sun,[key]:Number(e.target.value)}}))}/>
              <small>{lights.sun[key]}</small>
            </label>)}
            <label>Fog
              <input type="range" min="0" max=".3" step=".002"
                value={lights.atmosphere.density}
                onChange={e=>setLights(x=>({...x,
                  atmosphere:{...x.atmosphere,
                    density:Number(e.target.value)}}))}/>
              <small>{Math.round(lights.atmosphere.density*1000)/10}%</small>
            </label>
            <button className="film-secondary" disabled={busy}
              onClick={()=>update('light',lights,'Lighting choices saved for review.')}>
              Save Lighting</button>
          </>}
        </div>
        <div className="director-look-section">
          <h4>Give objects their materials</h4>
          <label>Choose an object in this scene
            <select value={selectedObject}
              onChange={e=>setSelectedObject(e.target.value)}>
              {data.filmed_objects.map(o=><option key={o.id} value={o.id}>
                {o.name}</option>)}
            </select></label>
          {selectedObject&&<>
            <Material value={objectMaterial} onChange={setObjectMaterial}/>
            <button className="film-secondary" disabled={busy}
              onClick={()=>update('material',{
                object_id:selectedObject,material:objectMaterial},
                'The object surface was saved for review.')}>
              Save Object Material</button>
          </>}
        </div>
        <div className="director-look-section">
          <h4>Dress the set</h4>
          <label>New object name<input maxLength={80} value={pieceName}
            onChange={e=>setPieceName(e.target.value)}/></label>
          <label>Shape<select value={pieceShape}
            onChange={e=>setPieceShape(e.target.value)}>
            {['box','sphere','cone','cylinder'].map(x=>
              <option key={x}>{x}</option>)}
          </select></label>
          <Coords name="Where to put it" values={piecePosition}
            onChange={setPiecePosition}/>
          <Coords name="Size" values={pieceScale}
            onChange={setPieceScale}/>
          <Material value={pieceMaterial} onChange={setPieceMaterial}/>
          <button className="film-secondary" disabled={busy}
            onClick={()=>update('add_piece',{
              name:pieceName,shape:pieceShape,position:piecePosition,
              rotation:[0,0,0],scale:pieceScale,material:pieceMaterial,lod:0
            },'Set piece added. Its original scene remains unchanged.')}>
            Add to Set</button>
          {d.set_pieces.length>0&&<>
            <h4>Objects on this set ({d.set_pieces.length})</h4>
            <label>Choose an object to adjust
              <select value={selectedPiece}
                onChange={e=>setSelectedPiece(e.target.value)}>
                <option value="">Choose set piece</option>
                {d.set_pieces.map(item=><option key={item.id} value={item.id}>
                  {item.name}</option>)}
              </select></label>
            {sourcePiece&&<>
              <Coords name="Set-piece position"
                values={pieceDraft?.position||sourcePiece.position}
                onChange={v=>setPieceDraft(old=>({...old,position:v}))}/>
              <button className="film-secondary" disabled={busy||!pieceDraft}
                onClick={()=>update('update_piece',{item:pieceDraft},
                  'Set position saved. The original performance is unchanged.')}>
                Save Position</button>
              <button className="film-secondary" disabled={busy}
                onClick={()=>update('remove_piece',{item_id:selectedPiece},
                  'Set piece removed without changing the original Take.')}>
                Remove Set Piece</button>
            </>}
          </>}
        </div>
      </div>
      <div className="director-look-approval">
        <div><strong>{approved?'Your scene look is approved':
            'Review the scene before filming the final presentation'}</strong>
          <p className="film-muted">Only an approved look will be used in
            your finished movie. Any later changes need a fresh approval.</p>
        </div>
        <button className="film-primary" onClick={approve}
          disabled={busy||approved||data.revision===0}>
          {approved?'Approved':'Approve This Scene Look'}</button>
      </div>
      <div className="director-look-reuse">
        <h4>Reuse a set in other scenes</h4>
        <div className="director-look-reuse-controls">
          <label>Save this setting as
            <input maxLength={80} value={kitName}
              placeholder="Courtyard at dusk"
              onChange={e=>setKitName(e.target.value)}/>
          </label>
          <button className="film-secondary"
            disabled={busy||!approved||!kitName.trim()}
            onClick={saveKit}>Save Reusable Set</button>
        </div>
        {data.kits.length>0&&<div className="director-look-reuse-controls">
          <label>Saved settings
            <select value={selectedKit} onChange={e=>setSelectedKit(e.target.value)}>
              <option value="">Choose an existing set</option>
              {data.kits.map(x=><option key={x.id} value={x.id}>
                {x.description}</option>)}
            </select>
          </label>
          <button className="film-secondary" disabled={busy||!selectedKit}
            onClick={()=>update('apply_kit',{kit_id:selectedKit},
              'Reusable set applied. Please review and approve it.')}>
            Use Saved Set</button>
        </div>}
      </div>
    </>}
  </section>;
}
