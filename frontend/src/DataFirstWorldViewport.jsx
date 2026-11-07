import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

// DA-04: evaluate OpenUSD source geometry IN THREE DIMENSIONS at the actual
// audio presentation Film Time. There is no MP4, frame sequencer, texture
// proxy, video transcoding or persistent picture. SHA-bound NVP procedural
// meshes and UsdSkel actors are source-verified; unbound actors stay gizmos.
function validMatrix(m){
  return Array.isArray(m)&&m.length===4&&
    m.every(r=>Array.isArray(r)&&r.length===4&&
      r.every(x=>typeof x==='number'&&Number.isFinite(x)));
}

export function validateMeshData(item){
  if(!Number.isFinite(item.size_m)||item.size_m<=0||item.size_m>10000)
    throw Error('Untrusted USD mesh size');
  const pts=item.mesh_points,faces=item.mesh_triangles;
  if(!Array.isArray(pts)||pts.length<3||pts.length>2048||
     !Array.isArray(faces)||faces.length<1||faces.length>4096||
     !pts.every(p=>Array.isArray(p)&&p.length===3&&
       p.every(v=>typeof v==='number'&&Number.isFinite(v)&&
         Math.abs(v)<=item.size_m))||
     !faces.every(f=>Array.isArray(f)&&f.length===3&&
       new Set(f).size===3&&f.every(i=>
         Number.isInteger(i)&&i>=0&&i<pts.length)))
    throw Error('Untrusted frozen USD triangle topology or dynamic pose');
  const texture=item.source_material?.source_texture;
  if(texture){
    const uv=item.mesh_uvs;
    if(item.shape!=='mesh'||item.source_material?.original_source_modified!==false||
       texture.format!=='nvp.original_png_rgb8_uv_texture.v1'||
       texture.source_encoding!=='sRGB'||
       texture.uv_interpolation!=='vertex'||
       texture.original_source_modified!==false||
       !/^[a-f0-9]{64}$/.test(texture.blob_sha256||'')||
       !Number.isInteger(texture.width)||texture.width<1||texture.width>256||
       !Number.isInteger(texture.height)||texture.height<1||texture.height>256||
       typeof texture.png_base64!=='string'||texture.png_base64.length>400000||
       !/^[a-zA-Z0-9+/]*={0,2}$/.test(texture.png_base64)||
       !Array.isArray(uv)||uv.length!==pts.length||
       !uv.every(pair=>Array.isArray(pair)&&pair.length===2&&
         pair.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)))
      throw Error('Original USD vertex UV/texture SHA binding untrusted');
  }else if(item.mesh_uvs){
    throw Error('No verified source texture for authored UVs');
  }
  if(item.shape==='skinned_mesh'){
    const mat=item.source_material;
    if(item.source_skinning!==true||
       !/^(0|[1-9][0-9]*)$/.test(item.source_skinning_tick||'')||
       !Array.isArray(item.source_color_rgb)||
       item.source_color_rgb.length!==3||
       !item.source_color_rgb.every(v=>
         typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)||
       !mat||!['nvp.original_usd_preview_surface.v1',
                 'nvp.original_usd_displaycolor_preview.v1'].includes(
                   mat.format)||
       mat.original_source_modified!==false||
       !Array.isArray(mat.base_color_rgb)||mat.base_color_rgb.length!==3||
       mat.base_color_rgb.some((v,i)=>
         typeof v!=='number'||!Number.isFinite(v)||
         Math.abs(v-item.source_color_rgb[i])>1e-5)||
       ![mat.roughness,mat.metallic].every(v=>
         typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1))
      throw Error('Skinned actor pose/material not bound to original USD source');
  }
  return {pts,faces};
}

function shapeFor(item){
  if(!Number.isFinite(item.size_m)||item.size_m<=0||item.size_m>10000)
    throw Error('Untrusted USD 3D geometry scale');
  if(item.shape==='cube')return new THREE.BoxGeometry(
    item.size_m,item.size_m,item.size_m);
  if(item.shape==='sphere')return new THREE.SphereGeometry(
    item.size_m/2,24,16);
  if(item.shape==='mesh'||item.shape==='skinned_mesh'){
    const {pts,faces}=validateMeshData(item);
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(
      pts.flat(),3));
    geometry.setIndex(faces.flat());
    if(item.mesh_uvs)
      geometry.setAttribute('uv',
        new THREE.Float32BufferAttribute(item.mesh_uvs.flat(),2));
    geometry.computeVertexNormals();
    return geometry;
  }
  if(item.shape==='gizmo'){
    if(item.semantic_role==='camera')return new THREE.ConeGeometry(.25,.6,8);
    if(item.semantic_role==='light')return new THREE.OctahedronGeometry(.25);
    return new THREE.SphereGeometry(.22,12,8);
  }
  throw Error('Untrusted native geometry shape');
}

// Updates only disposable Three.js vertex buffers. Original USD binding,
// weights and animation remain on the trusted native scene side.
export function updateSkinnedGeometry(geometry,item){
  const {pts,faces}=validateMeshData(item);
  const attr=geometry.getAttribute('position');
  const index=geometry.getIndex();
  if(!attr||attr.count!==pts.length||!index||
     index.count!==faces.length*3)
    throw Error('Frozen actor topology changed during native live pose');
  let n=0;
  for(const face of faces){
    for(const vertex of face){
      if(index.getX(n++)!==vertex)
        throw Error('Live actor face indices changed without source revision');
    }
  }
  for(let i=0;i<pts.length;i++){
    attr.setXYZ(i,pts[i][0],pts[i][1],pts[i][2]);
  }
  attr.needsUpdate=true;
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
}

function usdMatrix(m){
  // USD Gf.Matrix4d uses ROW-vector transformation convention (translation
  // in row 3). THREE.Matrix4 is column-vector; transpose the authored
  // matrix exactly instead of replacing orientation with guessed positions.
  return new THREE.Matrix4().set(
    m[0][0],m[1][0],m[2][0],m[3][0],
    m[0][1],m[1][1],m[2][1],m[3][1],
    m[0][2],m[1][2],m[2][2],m[3][2],
    m[0][3],m[1][3],m[2][3],m[3][3]
  );
}

export default function DataFirstWorldViewport({
  objects=[],listenerPath='',tick='0',sceneSha='',nativeSchemas=[]
}){
  const holder=useRef(null);
  const env=useRef(null);
  const [disabled,setDisabled]=useState(false);
  const [viewMode,setViewMode]=useState('orbit');
  const [selectedCamera,setSelectedCamera]=useState('');
  const cameraObjects=objects.filter(o=>o?.semantic_role==='camera');
  const cameraPath=cameraObjects.some(o=>o.path===selectedCamera)?
    selectedCamera:cameraObjects[0]?.path||'';
  const bounded=Array.isArray(objects)?objects.slice(0,64):[];
  const missingRigGeometry=bounded.filter(o=>o?.source_rigged_actor===true&&
    o.native_geometry_status!=='VERIFIED_SKINNED');
  const staleRigPoses=bounded.filter(o=>o?.shape==='skinned_mesh'&&
    o.source_skinning_tick!==String(tick));


  useEffect(()=>{
    if(!holder.current)return;
    const root=holder.current;
    let renderer=null,resize=null,raf=0,controls=null;
    let scene=null;
    let disposed=false;
    const meshes=new Map();
    try{
      renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,
        powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
      renderer.domElement.setAttribute('aria-label',
        'Live three-dimensional source Film Time world');
      renderer.domElement.setAttribute('role','img');
      root.appendChild(renderer.domElement);
      scene=new THREE.Scene();
      scene.background=new THREE.Color('#121a2a');
      const world=new THREE.Group();
      scene.add(world);
      const grid=new THREE.GridHelper(40,20,'#526077','#374151');
      grid.rotation.x=Math.PI/2;
      scene.add(grid);
      scene.add(new THREE.AmbientLight(0xffffff,1.7));
      const sun=new THREE.DirectionalLight(0xffffff,2.5);
      sun.position.set(10,-6,16);scene.add(sun);
      const camera=new THREE.PerspectiveCamera(50,2,.01,5000);
      const authoredCamera=new THREE.PerspectiveCamera(50,2,.01,5000);
      camera.up.set(0,0,1);
      camera.position.set(12,-15,12);
      camera.lookAt(0,0,0);
      const render=()=>{
        if(disposed)return;
        raf=0;
        renderer.render(scene,env.current?.activeCamera||camera);
      };
      const requestRender=()=>{
        if(!disposed&&!raf)raf=requestAnimationFrame(render);
      };
      controls=new OrbitControls(camera,renderer.domElement);
      controls.enableDamping=false;
      controls.minDistance=.2;controls.maxDistance=1000;
      controls.addEventListener('change',requestRender);
      const resizeNow=()=>{
        const width=Math.max(280,Math.min(root.clientWidth||640,1900));
        const height=360;
        renderer.setSize(width,height);
        camera.aspect=width/height;
        camera.updateProjectionMatrix();
        authoredCamera.aspect=width/height;
        authoredCamera.updateProjectionMatrix();
        requestRender();
      };
      resizeNow();
      if(typeof ResizeObserver!=='undefined'){
        resize=new ResizeObserver(resizeNow);
        resize.observe(root);
      }
      env.current={world,meshes,requestRender,
        orbitCamera:camera,authoredCamera,activeCamera:camera};
      const lost=event=>{event.preventDefault();setDisabled(true);};
      const restored=()=>{setDisabled(false);requestRender();};
      renderer.domElement.addEventListener('webglcontextlost',lost);
      renderer.domElement.addEventListener('webglcontextrestored',restored);
      env.current.detachDeviceHandlers=()=>{
        renderer.domElement.removeEventListener('webglcontextlost',lost);
        renderer.domElement.removeEventListener('webglcontextrestored',restored);
      };
      setDisabled(false);
    }catch(_error){
      // A headless browser or disabled GPU must still expose textual,
      // immutable scene data rather than claiming to display a 3D picture.
      setDisabled(true);
    }
    return ()=>{
      disposed=true;
      if(raf)cancelAnimationFrame(raf);
      if(resize)resize.disconnect();
      if(controls)controls.dispose();
      for(const mesh of meshes.values()){
        if(mesh.geometry)mesh.geometry.dispose();
        if(mesh.material)mesh.material.dispose();
      }
      if(renderer){
        if(env.current?.detachDeviceHandlers)env.current.detachDeviceHandlers();
        renderer.dispose();
        if(root.contains(renderer.domElement))
          root.removeChild(renderer.domElement);
      }
      env.current=null;
    };
  },[]);

  useEffect(()=>{
    const state=env.current;
    if(!state)return;
    const incoming=new Set();
    for(const obj of bounded){
      if(typeof obj.path!=='string'||!validMatrix(obj.world_matrix))continue;
      // Explicitly report unmeshed authored rigs in source inspection, but
      // do not create a fake sphere/cone body for any captured rigged actor.
      if(obj.shape==='missing_rig_geometry')continue;
      if(obj.source_rigged_actor===true&&obj.shape!=='skinned_mesh')
        continue;
      if(obj.shape==='skinned_mesh'){
        // Never display a pose from a previous Film Time sample as current.
        // A source update is allowed only for the requested exact tick.
        try{
          if(obj.source_skinning_tick!==String(tick))
            throw Error('Stale source skinning result');
          validateMeshData(obj);
        }catch{continue;}
      }
      incoming.add(obj.path);
      const fingerprint=[obj.shape,
        obj.shape==='skinned_mesh'?'skinned-source':obj.size_m,
        obj.semantic_role,obj.geometry_asset_sha256||''].join(':');
      let mesh=state.meshes.get(obj.path);
      if(mesh&&mesh.userData.sourceGeometry!==fingerprint){
        state.world.remove(mesh);
        mesh.geometry.dispose();
        if(mesh.material.map)mesh.material.map.dispose();
        mesh.material.dispose();
        state.meshes.delete(obj.path);mesh=null;
      }
      if(!mesh){
        try{
          const geometry=shapeFor(obj);
          const color=obj.gizmo_only?
            (obj.semantic_role==='camera'?0x38bdf8:
             obj.semantic_role==='actor'?0xc084fc:0xf59e0b):
            0x94a3b8;
          const surface=obj.source_material;
          if(surface&&(
            surface.original_source_modified!==false||
            !Array.isArray(surface.base_color_rgb)||
            surface.base_color_rgb.length!==3||
            surface.base_color_rgb.some(v=>typeof v!=='number'||
              !Number.isFinite(v)||v<0||v>1)||
            !Number.isFinite(surface.roughness)||
            !Number.isFinite(surface.metallic)||
            surface.roughness<0||surface.roughness>1||
            surface.metallic<0||surface.metallic>1))
            throw Error('Original USD material has invalid source provenance');
          const surfaceColor=surface?
            new THREE.Color().setRGB(...surface.base_color_rgb):color;
          let map=null;
          if(surface?.source_texture){
            // Original image bytes are obtained only through FilmIndex SHA
            // authorization. This is an ephemeral GPU texture, never an
            // external URI, flattened movie frame or revised source Take.
            validateMeshData(obj);
            map=new THREE.TextureLoader().load(
              'data:image/png;base64,'+surface.source_texture.png_base64);
            map.colorSpace=THREE.SRGBColorSpace;
            map.wrapS=THREE.ClampToEdgeWrapping;
            map.wrapT=THREE.ClampToEdgeWrapping;
          }
          const material=new THREE.MeshStandardMaterial({
            color:surfaceColor,
            map,
            roughness:surface?surface.roughness:.8,
            metalness:surface?surface.metallic:.05,
            side:obj.shape==='mesh'||obj.shape==='skinned_mesh'?
              THREE.DoubleSide:THREE.FrontSide});
          mesh=new THREE.Mesh(geometry,material);
          mesh.matrixAutoUpdate=false;
          mesh.userData.sourceGeometry=fingerprint;
          state.world.add(mesh);
          state.meshes.set(obj.path,mesh);
        }catch{incoming.delete(obj.path);continue;}
      }
      if(obj.source_material){
        const surface=obj.source_material;
        if(surface.original_source_modified!==false||
           !Array.isArray(surface.base_color_rgb)||
           surface.base_color_rgb.length!==3||
           surface.base_color_rgb.some(v=>!Number.isFinite(v)||v<0||v>1)||
           !Number.isFinite(surface.roughness)||
           !Number.isFinite(surface.metallic)||
           surface.roughness<0||surface.roughness>1||
           surface.metallic<0||surface.metallic>1){
          incoming.delete(obj.path);
          continue;
        }
        mesh.material.color.setRGB(...surface.base_color_rgb);
        mesh.material.roughness=surface.roughness;
        mesh.material.metalness=surface.metallic;
      }
      if(obj.shape==='skinned_mesh'){
        try{
          updateSkinnedGeometry(mesh.geometry,obj);
        }catch{
          // Malformed/late pose must never leave stale actor geometry visible.
          incoming.delete(obj.path);
          continue;
        }
      }
      mesh.matrix.copy(usdMatrix(obj.world_matrix));
      mesh.matrixWorldNeedsUpdate=true;
      mesh.material.emissive.setHex(obj.path===listenerPath?0x065f46:0);
      mesh.material.needsUpdate=true;
    }
    for(const [path,mesh] of state.meshes){
      if(!incoming.has(path)){
        state.world.remove(mesh);
        mesh.geometry.dispose();
        if(mesh.material.map)mesh.material.map.dispose();
        mesh.material.dispose();
        state.meshes.delete(path);
      }
    }
    state.requestRender();
  },[objects,listenerPath,tick]);


  useEffect(()=>{
    const state=env.current;
    if(!state)return;
    if(viewMode!=='authored'||!cameraPath){
      state.activeCamera=state.orbitCamera;
      state.requestRender();
      return;
    }
    const obj=cameraObjects.find(x=>x.path===cameraPath);
    const optic=nativeSchemas.find(x=>x?.prim_path===cameraPath&&
      x.schema==='UsdGeom.Camera');
    if(!obj||!validMatrix(obj.world_matrix)||
       !optic||!Number.isFinite(optic.focal_length_mm)||
       optic.focal_length_mm<1||optic.focal_length_mm>400||
       optic.projection!=='perspective'){
      state.activeCamera=state.orbitCamera;
      state.requestRender();
      return;
    }
    const camera=state.authoredCamera;
    // NVP native UsdGeom.Camera schema authors a 20.25 mm vertical
    // aperture. A variable sensor/aperture is not yet accepted here.
    camera.fov=2*Math.atan(20.25/(2*optic.focal_length_mm))*180/Math.PI;
    camera.updateProjectionMatrix();
    camera.matrixAutoUpdate=false;
    camera.matrix.copy(usdMatrix(obj.world_matrix));
    camera.matrixWorldNeedsUpdate=true;
    state.activeCamera=camera;
    state.requestRender();
  },[objects,nativeSchemas,cameraPath,viewMode]);

  return <section aria-label="Live native OpenUSD three-dimensional scene">
    <p className="fineprint">3D source world at Film Time tick {tick}.
      {sceneSha&&<> Immutable scene SHA: <code>{sceneSha.slice(0,16)}…</code></>}
      {viewMode==='orbit'?' Drag to orbit, scroll to inspect.':
        ' Looking through an authored OpenUSD scene camera.'} Live data, not a movie.</p>
    <div className="actions">
      <label>Live 3D camera view
        <select aria-label="Live source camera mode" value={viewMode}
          onChange={e=>setViewMode(e.target.value)}>
          <option value="orbit">Free 3D orbit</option>
          <option value="authored">Authored USD camera</option>
        </select>
      </label>
      {viewMode==='authored'&&<label>Native authored camera
        <select aria-label="Live authored USD camera" value={cameraPath}
          onChange={e=>setSelectedCamera(e.target.value)}>
          {cameraObjects.map(x=><option key={x.path} value={x.path}>{x.path}</option>)}
        </select>
      </label>}
    </div>
    <div ref={holder} style={{width:'100%',minHeight:'360px',borderRadius:8,
      overflow:'hidden',background:'#121a2a'}}/>
    {disabled&&<p role="status">3D hardware context lost or unavailable.
      The original scene data remains inspectable below.</p>}
    {missingRigGeometry.length>0&&
      <p role="alert">Original USD rigged actors without bound skinned meshes:
        {missingRigGeometry.map(o=>' '+o.path).join(', ')}.
        Their motion remains source data; no substitute character geometry
        was fabricated. Bind original UsdSkel character geometry to display.</p>}
    {staleRigPoses.length>0&&
      <p role="alert">Stale skinned-actor samples were not displayed for
        this Film Time: {staleRigPoses.map(o=>o.path).join(', ')}.</p>}
    <ul>
      {bounded.map(item=><li key={item.path}>
        <strong>{item.path}</strong> ·
        {item.shape==='missing_rig_geometry'
          ?'Rigged actor: original USD mesh not bound (not displayed)'
          : item.gizmo_only?'unbound scene marker':
            'verified authored USD '+item.shape+' ('+item.size_m+' m)'} ·
        {item.shape==='skinned_mesh'&&
          (item.facial_animation_evaluated?
            ' facial USD blendshapes active ·':' source skeletal pose ·')}
        {(item.world_translation||[]).map(n=>Number(n).toFixed(2)).join(', ')} m
      </li>)}
    </ul>
    <p className="fineprint">This WebGL scene uses validated native
      OpenUSD transforms and source-verified procedural/triangle geometry.
      Original USD-skinned actor motion, bounded facial blend shapes and
      USD PreviewSurface parameters are live GPU derivatives. Older immutable
      Takes still display their actual original USD mesh/displayColor rather
      than a fake avatar. Texture networks, advanced materials, Hydra parity,
      calibrated lighting and installed GPU acceptance remain unverified.</p>
  </section>;
}
