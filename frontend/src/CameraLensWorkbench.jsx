import React,{useMemo,useState} from 'react';
import './CameraLensWorkbench.css';

// CAM-01: this live optical overlay operates on a single source scene
// snapshot. It is NOT a rendered feature-film frame or a filter applied to
// frozen Takes. The native host must revalidate every save/render command.
const LENSES=[
  ['ultrawide_18',18,'18 mm · Ultra wide'],
  ['wide_24',24,'24 mm · Wide'],
  ['story_35',35,'35 mm · Story'],
  ['standard_50',50,'50 mm · Standard'],
  ['portrait_85',85,'85 mm · Portrait'],
  ['tele_135',135,'135 mm · Telephoto'],
];
const SENSORS=[
  ['full_frame',36,20.25,'Full frame 36 mm'],
  ['super_35',24.89,14,'Super 35'],
  ['micro_four_thirds',17.3,9.73,'Micro Four Thirds'],
];
const fStopChoices=[1.4,2,2.8,4,5.6,8,11,16];

function projectMarker(marker,focal,sensorWidth,sensorHeight,focus,fStop){
  const [x,y,z]=marker.camera_space_xyz;
  if(![x,y,z].every(Number.isFinite) || z>=-0.06)return null;
  const depth=-z;
  const px=500+(x/depth)*focal/sensorWidth*1000;
  const py=281.25-(y/depth)*focal/sensorHeight*562.5;
  const radius=Math.min(70,Math.max(2,
    (marker.hint_radius_m||0.4)/depth*focal/sensorWidth*1000));
  if(px<-100||px>1100||py<-100||py>663)return null;
  // Only an educational fast DOF CUE: not a physical blur-kernel render.
  const focusError=Math.abs(depth-focus)/Math.max(depth,focus,0.001);
  const blur=Math.min(11,focusError*(focal/35)*(5.6/fStop)*3);
  return {...marker,px,py,radius,blur,depth};
}

export default function CameraLensWorkbench({
  sceneSnapshot=null,onRequestRenderedPreview=null,
  onSavePreset=null,onApplyToShot=null,onSelectCamera=null,
  cameraChoices=[],renderResult=null,
  renderBusy=false,onCancelRenderedPreview=null,
}){
  const [lens,setLens]=useState('standard_50');
  const [sensor,setSensor]=useState('full_frame');
  const [fStop,setFStop]=useState(2.8);
  const [focus,setFocus]=useState(5);
  const [customFocal,setCustomFocal]=useState(null);
  const focal=customFocal??LENSES.find(x=>x[0]===lens)[1];
  const sensorValues=SENSORS.find(x=>x[0]===sensor);
  const sensorWidth=sensorValues[1],sensorHeight=sensorValues[2];
  const fov=180/Math.PI*2*Math.atan(sensorWidth/(2*focal));
  const markers=useMemo(()=>(
    (sceneSnapshot?.markers||[])
      .map(m=>projectMarker(m,focal,sensorWidth,sensorHeight,focus,fStop))
      .filter(Boolean)
  ),[sceneSnapshot,focal,sensorWidth,sensorHeight,focus,fStop]);
  const valid=sceneSnapshot?.format==='nvp.camera.lens_workbench.v1' &&
    typeof sceneSnapshot.scene_document_sha256==='string';
  const imageMatches=valid &&
    (renderResult?.status==='READY'||renderResult?.status==='CACHE_HIT') &&
    renderResult.scene_document_sha256===sceneSnapshot.scene_document_sha256 &&
    renderResult.camera_path===sceneSnapshot.camera_path &&
    renderResult.source_tick===sceneSnapshot.source_tick &&
    renderResult.lens_settings?.focal_length_mm===focal &&
    renderResult.lens_settings?.sensor_width_mm===sensorWidth &&
    renderResult.lens_settings?.sensor_height_mm===sensorHeight &&
    renderResult.lens_settings?.f_stop===fStop &&
    renderResult.lens_settings?.focus_distance_m===focus &&
    typeof renderResult.image_data_url==='string' &&
    renderResult.image_data_url.startsWith('data:image/png;base64,') &&
    renderResult.image_data_url.length<12*1024*1024;
  const settings={
    format:'nvp.camera.lens_workbench.v1',
    preset:lens,sensor,focal_length_mm:focal,
    sensor_width_mm:sensorWidth,sensor_height_mm:sensorHeight,
    f_stop:fStop,focus_distance_m:focus,
    horizontal_fov_degrees:fov,
    vertical_fov_degrees:180/Math.PI*2*Math.atan(sensorHeight/(2*focal)),
    squeeze_factor:1,projection:'perspective',lens_type:'spherical',
    distortion_filter_applied:false,lens_effect_stack:[],
    optics_mathematically_previewed:true,
  };
  function actionPayload(){
    return {
      source_scene_id:sceneSnapshot.scene_id,
      source_scene_revision:sceneSnapshot.scene_revision,
      source_scene_document_sha256:sceneSnapshot.scene_document_sha256,
      source_tick:sceneSnapshot.source_tick,
      camera_path:sceneSnapshot.camera_path,
      lens_settings:settings,
      source_modified:false,
      frozen_take_created:false,
    };
  }
  return <section className="nvp-camera-workbench" aria-label="Virtual Camera Workbench">
    <header><div>
      <h3>Virtual Camera Workbench</h3>
      <small>Pre-Take optical study · non-destructive</small>
    </div><span>CAM-01</span></header>
    <div className="nvp-camera-controls">
      <label>Lens preset
        <select aria-label="Lens preset" value={lens} onChange={event=>{
          setLens(event.target.value);setCustomFocal(null);}}>
          {LENSES.map(([id,,label])=>
            <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <label>Sensor / filmback
        <select aria-label="Sensor / filmback" value={sensor}
          onChange={event=>setSensor(event.target.value)}>
          {SENSORS.map(([id,,,label])=>
            <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <label>Focal length · {focal.toFixed(0)} mm
        <input aria-label="Focal length" type="range" min="12" max="200" step="1"
          value={focal} onChange={event=>setCustomFocal(Number(event.target.value))}/>
      </label>
      <label>Aperture · f/{fStop}
        <select aria-label="Aperture" value={String(fStop)}
          onChange={event=>setFStop(Number(event.target.value))}>
          {fStopChoices.map(value=>
            <option key={value} value={value}>f/{value}</option>)}
        </select>
      </label>
      <label>Focus · {focus.toFixed(1)} m
        <input aria-label="Focus distance" type="range" min="0.2" max="50"
          step="0.1" value={focus}
          onChange={event=>setFocus(Number(event.target.value))}/>
      </label>
      {cameraChoices.length>1 && <label>Camera
        <select aria-label="Source camera" value={sceneSnapshot?.camera_path||''}
          onChange={event=>onSelectCamera?.(event.target.value)}>
          {cameraChoices.map(c=>
            <option key={c.path} value={c.path}>{c.label||c.path}</option>)}
        </select>
      </label>}
    </div>
    <div className="nvp-camera-live" data-preview-mode="live-projection">
      <svg viewBox="0 0 1000 562.5" role="img"
        aria-label="Live camera optical framing diagram; not rendered film pixels">
        <rect x="0" y="0" width="1000" height="562.5" fill="#19212a"/>
        <path d="M 0 281.25 H 1000 M 500 0 V 562.5"
          stroke="#55636e" strokeWidth="1" strokeDasharray="8 8"/>
        {markers.map((point,i)=>(
          <g key={point.path} aria-label={point.path}>
            <circle cx={point.px} cy={point.py} r={point.radius}
              fill={point.role==='actor'?'#82bce4':point.role==='prop'?'#caa66c':'#83ad8f'}
              fillOpacity=".8" stroke="#e2f4ff"
              style={{filter:point.blur? `blur(${point.blur.toFixed(1)}px)`:'none'}}/>
            <text x={point.px} y={point.py+point.radius+19} textAnchor="middle"
              fontSize="15" fill="#f4f7fa">{point.path.split('/').at(-1)}</text>
          </g>
        ))}
        <text x="20" y="38" fontSize="20" fill="#e2edf8">
          {focal.toFixed(0)} mm · {fov.toFixed(1)}° horizontal FOV
        </text>
      </svg>
      {!valid&&<p>Choose an authored camera and evaluate a scene to begin.</p>}
      <div className="nvp-camera-live-legend">
        Live reframing · approximate focus cue · no GPU or full geometry loaded
      </div>
    </div>
    <div className="nvp-camera-actions">
      <button disabled={!valid||!onRequestRenderedPreview||renderBusy}
        onClick={()=>onRequestRenderedPreview(actionPayload())}>
        Render accurate optics still
      </button>
      {renderBusy&&onCancelRenderedPreview&&
        <button onClick={onCancelRenderedPreview}>
          Cancel native still
        </button>}
      <button disabled={!valid||!onSavePreset}
        onClick={()=>onSavePreset(actionPayload())}>
        Save lens preset
      </button>
      <button disabled={!valid||!onApplyToShot}
        onClick={()=>onApplyToShot(actionPayload())}>
        Apply to shot
      </button>
    </div>
    {renderResult?.status==='QUEUED'&&
      <p>Higher-quality optics preview queued; source scene unchanged.</p>}
    {imageMatches
      ? <figure className="nvp-camera-native-image">
          <img src={renderResult.image_data_url}
            alt="Native rendered camera/lens study of original 3D scene; not a frozen Take"
            loading="lazy"/>
          <figcaption>Verified native camera still · source scene unchanged · not a final shot</figcaption>
        </figure>
      : renderResult?.status==='READY'
        ? <p>Previous optics preview differs from these live lens settings; render again to compare.</p>
        : null}
    <p className="nvp-camera-disclaimer">
      Spherical lenses use real focal length, filmback, aperture and focus
      models. Anamorphic effects, flares, vignetting and lens distortion
      are separate optical effects—not interchangeable color filters.
      The instant diagram is an approximation; high-quality depth of field
      requires a native render. Nothing here freezes or changes a Take.
    </p>
  </section>;
}
