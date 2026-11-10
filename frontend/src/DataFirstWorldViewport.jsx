import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

// DA-04: evaluate OpenUSD source geometry IN THREE DIMENSIONS at the actual
// audio presentation Film Time. There is no MP4, frame sequencer, texture
// proxy, video transcoding or persistent picture. SHA-bound NVP procedural
// cubes/spheres are exact assets; other objects remain clearly-marked gizmos.
function validMatrix(m){
  return Array.isArray(m)&&m.length===4&&
    m.every(r=>Array.isArray(r)&&r.length===4&&
      r.every(x=>typeof x==='number'&&Number.isFinite(x)));
}

function shapeFor(item){
  if(!Number.isFinite(item.size_m)||item.size_m<=0||item.size_m>10000)
    throw Error('Untrusted USD 3D geometry scale');
  if(item.shape==='cube')return new THREE.BoxGeometry(
    item.size_m,item.size_m,item.size_m);
  if(item.shape==='sphere')return new THREE.SphereGeometry(
    item.size_m/2,24,16);
  if(item.shape==='gizmo'){
    if(item.semantic_role==='camera')return new THREE.ConeGeometry(.25,.6,8);
    if(item.semantic_role==='light')return new THREE.OctahedronGeometry(.25);
    return new THREE.SphereGeometry(.22,12,8);
  }
  throw Error('Untrusted native geometry shape');
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
  objects=[],listenerPath='',tick='0',sceneSha='',railSamples=[]
}){
  const holder=useRef(null);
  const env=useRef(null);
  const [disabled,setDisabled]=useState(false);
  const bounded=Array.isArray(objects)?objects.slice(0,64):[];

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
      const railGroup=new THREE.Group();
      scene.add(railGroup);
      const grid=new THREE.GridHelper(40,20,'#526077','#374151');
      grid.rotation.x=Math.PI/2;
      scene.add(grid);
      scene.add(new THREE.AmbientLight(0xffffff,1.7));
      const sun=new THREE.DirectionalLight(0xffffff,2.5);
      sun.position.set(10,-6,16);scene.add(sun);
      const camera=new THREE.PerspectiveCamera(50,2,.01,5000);
      camera.up.set(0,0,1);
      camera.position.set(12,-15,12);
      camera.lookAt(0,0,0);
      const render=()=>{
        if(disposed)return;
        raf=0;
        renderer.render(scene,camera);
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
        requestRender();
      };
      resizeNow();
      if(typeof ResizeObserver!=='undefined'){
        resize=new ResizeObserver(resizeNow);
        resize.observe(root);
      }
      env.current={world,meshes,requestRender,railGroup};
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
      if(env.current?.railGroup){
        for(const drawn of env.current.railGroup.children){
          drawn.geometry?.dispose();
          drawn.material?.dispose();
        }
      }
      if(renderer){
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
      incoming.add(obj.path);
      const fingerprint=[obj.shape,obj.size_m,obj.semantic_role].join(':');
      let mesh=state.meshes.get(obj.path);
      if(mesh&&mesh.userData.sourceGeometry!==fingerprint){
        state.world.remove(mesh);
        mesh.geometry.dispose();mesh.material.dispose();
        state.meshes.delete(obj.path);mesh=null;
      }
      if(!mesh){
        try{
          const geometry=shapeFor(obj);
          const color=obj.gizmo_only?
            (obj.semantic_role==='camera'?0x38bdf8:
             obj.semantic_role==='actor'?0xc084fc:0xf59e0b):
            0x94a3b8;
          const material=new THREE.MeshStandardMaterial({
            color,roughness:.8,metalness:.05});
          mesh=new THREE.Mesh(geometry,material);
          mesh.matrixAutoUpdate=false;
          mesh.userData.sourceGeometry=fingerprint;
          state.world.add(mesh);
          state.meshes.set(obj.path,mesh);
        }catch{incoming.delete(obj.path);continue;}
      }
      mesh.matrix.copy(usdMatrix(obj.world_matrix));
      mesh.matrixWorldNeedsUpdate=true;
      mesh.material.emissive.setHex(obj.path===listenerPath?0x065f46:0);
      mesh.material.needsUpdate=true;
    }
    for(const [path,mesh] of state.meshes){
      if(!incoming.has(path)){
        state.world.remove(mesh);
        mesh.geometry.dispose();mesh.material.dispose();
        state.meshes.delete(path);
      }
    }
    state.requestRender();
  },[objects,listenerPath]);

  // A verified prospective rail is a disposable camera GUIDE over the
  // native 3D source world, not authored actor geometry or a film frame.
  useEffect(()=>{
    const state=env.current;
    if(!state?.railGroup)return;
    const group=state.railGroup;
    while(group.children.length){
      const child=group.children[0];
      group.remove(child);
      child.geometry?.dispose();
      child.material?.dispose();
    }
    if(!Array.isArray(railSamples)||railSamples.length>64)return;
    const valid=railSamples.every(sample=>
      sample&&Number.isSafeInteger(sample.film_tick)&&
      Array.isArray(sample.position_m)&&sample.position_m.length===3&&
      sample.position_m.every(x=>typeof x==='number'&&Number.isFinite(x)&&
        Math.abs(x)<=100000));
    if(!valid||railSamples.length<2)return;
    const pts=railSamples.map(x=>new THREE.Vector3(...x.position_m));
    const line=new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({color:0x22d3ee}));
    group.add(line);
    for(const point of pts){
      const marker=new THREE.Mesh(
        new THREE.SphereGeometry(.14,8,8),
        new THREE.MeshBasicMaterial({color:0xe879f9}));
      marker.position.copy(point);group.add(marker);
    }
    state.requestRender();
  },[railSamples]);

  return <section aria-label="Live native OpenUSD three-dimensional scene">
    <p className="fineprint">3D source world at Film Time tick {tick}.
      {sceneSha&&<> Immutable scene SHA: <code>{sceneSha.slice(0,16)}…</code></>}
      Drag to orbit, scroll to inspect. Live data, not a movie.
      {Array.isArray(railSamples)&&railSamples.length>1&&
        <> Cyan line and violet control markers are a temporary unapproved camera guide; no original USD or PCM was changed.</>}</p>
    <div ref={holder} style={{width:'100%',minHeight:'360px',borderRadius:8,
      overflow:'hidden',background:'#121a2a'}}/>
    {disabled&&<p role="status">3D hardware context unavailable.
      The original scene data remains inspectable below.</p>}
    <ul>
      {bounded.map(item=><li key={item.path}>
        <strong>{item.path}</strong> ·
        {item.gizmo_only?'scene-location gizmo':
          'authored USD '+item.shape+' ('+item.size_m+' m)'} ·
        {(item.world_translation||[]).map(n=>Number(n).toFixed(2)).join(', ')} m
      </li>)}
    </ul>
    <p className="fineprint">This WebGL scene uses validated native
      OpenUSD transforms and procedural geometry. Full character meshes,
      textures, physical materials, Hydra parity and cinema-quality
      lighting still require separate acceptance.</p>
  </section>;
}
