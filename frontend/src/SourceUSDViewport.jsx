import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';

const FORMAT='nvp.usd_film01r.source_3d_lofi_viewpoint.v1';

function meshGeometry(object){
  if(object.geometry_kind==='mesh' &&
     Array.isArray(object.points)&&Array.isArray(object.triangle_indices)){
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position',new THREE.Float32BufferAttribute(
      object.points.flat(),3));
    geo.setIndex(object.triangle_indices);
    geo.computeVertexNormals();
    return geo;
  }
  const min=object.world_bbox_min_m;
  const max=object.world_bbox_max_m;
  if(!Array.isArray(min)||!Array.isArray(max)||min.length!==3||max.length!==3)
    return null;
  const dims=max.map((v,i)=>Math.max(.01,v-min[i]));
  let geo;
  if(object.geometry_kind==='sphere_proxy'){
    geo=new THREE.SphereGeometry(1,12,8);
  }else if(object.geometry_kind==='cylinder_proxy'){
    geo=new THREE.CylinderGeometry(1,1,2,12,1);
  }else if(object.geometry_kind==='cone_proxy'){
    geo=new THREE.ConeGeometry(1,2,12,1);
  }else{
    geo=new THREE.BoxGeometry(1,1,1);
  }
  geo.scale(...dims.map(v=>v/(
    object.geometry_kind==='sphere_proxy'||
    object.geometry_kind==='cylinder_proxy'||
    object.geometry_kind==='cone_proxy'?2:1)));
  geo.translate(...min.map((v,i)=>(v+max[i])/2));
  return geo;
}

function softwareProjectedMarkers(snapshot){
  // True camera/world USD transforms; simple 2D diagnostic if WebGL fails.
  // NOT a raster of shaded original geometry.
  const matrix=new THREE.Matrix4().fromArray(
    snapshot.camera_world_matrix_rows.flat());
  const inverse=matrix.clone().invert();
  const vertical=Math.tan(THREE.MathUtils.degToRad(
    snapshot.camera_vertical_fov_degrees/2));
  const horizontal=vertical*(16/9);
  return snapshot.objects.filter(o=>
    Array.isArray(o.world_bbox_min_m)&&
    Array.isArray(o.world_bbox_max_m)).map(o=>{
    const center=o.world_bbox_min_m.map((v,i)=>
      (v+o.world_bbox_max_m[i])/2);
    const view=new THREE.Vector3(...center).applyMatrix4(inverse);
    if(view.z>=-.01)return null;
    const px=(.5+view.x/(-view.z*horizontal)*.5)*640;
    const py=(.5-view.y/(-view.z*vertical)*.5)*360;
    if(!Number.isFinite(px)||!Number.isFinite(py)||
       px<0||px>640||py<0||py>360)return null;
    return {id:o.prim_path,x:px,y:py,actor:Boolean(o.actor_id),
      label:o.prim_path.split('/').at(-1)};
  }).filter(Boolean);
}

export default function SourceUSDViewport({snapshot,orbit=false}){
  const mount=useRef(null);
  const [renderError,setRenderError]=useState('');
  const valid=snapshot?.format===FORMAT &&
    snapshot?.preview_is_source_derived_not_final_cycles_image===true &&
    snapshot?.native_blender_workers_started===0 &&
    Array.isArray(snapshot?.objects) &&
    Array.isArray(snapshot?.camera_world_matrix_rows);
  useEffect(()=>{
    if(!valid||!mount.current)return;
    const target=mount.current;
    let renderer,controls,raf=0,active=true;
    const objects=[];
    try{
      const scene=new THREE.Scene();
      scene.background=new THREE.Color(0x17202a);
      const camera=new THREE.PerspectiveCamera(
        snapshot.camera_vertical_fov_degrees,16/9,.01,1000000);
      const rows=snapshot.camera_world_matrix_rows;
      if(rows.length!==4||rows.some(x=>!Array.isArray(x)||x.length!==4))
        throw Error('Original USD camera transform unavailable');
      // USD Gf.Matrix4 is row-vector/row-major; fromArray(column-major)
      // reads its numeric rows as the correct transposed Three.js matrix.
      camera.matrix.fromArray(rows.flat());
      camera.matrix.decompose(camera.position,camera.quaternion,camera.scale);
      camera.updateMatrixWorld(true);
      for(const item of snapshot.objects){
        const geo=meshGeometry(item);
        if(!geo)continue;
        const material=new THREE.MeshBasicMaterial({
          color:item.actor_id?0x74bddf:0xcab18b,
          wireframe:true,side:THREE.DoubleSide,
          depthTest:true,transparent:false});
        const mesh=new THREE.Mesh(geo,material);
        mesh.name=item.prim_path;
        scene.add(mesh);objects.push(mesh);
      }
      const guide=new THREE.GridHelper(20,20,0x405365,0x273644);
      scene.add(guide);
      const axes=new THREE.AxesHelper(1.0);
      scene.add(axes);
      renderer=new THREE.WebGLRenderer({
        antialias:false,powerPreference:'low-power',alpha:false});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.25));
      renderer.domElement.setAttribute('aria-label',
        'OpenUSD low-fi source geometry from selected virtual camera');
      target.replaceChildren(renderer.domElement);
      controls=new OrbitControls(camera,renderer.domElement);
      controls.enableDamping=true;
      controls.enabled=orbit;
      const actor=snapshot.objects.find(x=>x.actor_id&&x.world_bbox_min_m);
      if(actor){
        const center=actor.world_bbox_min_m.map((v,i)=>
          (v+actor.world_bbox_max_m[i])/2);
        controls.target.set(...center);
      }
      if(orbit)controls.update();
      const resize=()=>{
        if(!active)return;
        const width=Math.max(320,target.clientWidth||640);
        const height=Math.round(width*9/16);
        renderer.setSize(width,height,false);
        camera.aspect=width/height;
        camera.updateProjectionMatrix();
      };
      resize();
      window.addEventListener('resize',resize);
      let last=0;
      const draw=(stamp)=>{
        if(!active)return;
        if(stamp-last>=50){
          controls.enabled=orbit;
          if(orbit)controls.update();
          renderer.render(scene,camera);
          last=stamp;
        }
        raf=window.requestAnimationFrame(draw);
      };
      raf=window.requestAnimationFrame(draw);
      setRenderError('');
      return ()=>{
        active=false;
        window.cancelAnimationFrame(raf);
        window.removeEventListener('resize',resize);
        controls.dispose();
        for(const obj of objects){
          obj.geometry.dispose();obj.material.dispose();
        }
        guide.geometry.dispose();
        if(Array.isArray(guide.material))guide.material.forEach(m=>m.dispose());
        else guide.material.dispose();
        axes.geometry.dispose();axes.material.dispose();
        renderer.dispose();
        if(renderer.domElement.parentNode===target)
          target.removeChild(renderer.domElement);
      };
    }catch(error){
      setRenderError(
        'WebGL low-fi view unavailable: '+(error.message||'renderer unsupported'));
      if(renderer)renderer.dispose();
      target.replaceChildren();
    }
  },[snapshot,valid,orbit]);

  if(!valid)return <div role="status">Choose a verified original camera and Film Time frame to inspect its 3D data.</div>;
  return <div>
    <div ref={mount} style={{width:'100%',minHeight:280,
      background:'#17202a',borderRadius:8,overflow:'hidden'}}/>
    <p className="fineprint">
      Source OpenUSD geometry at frame {snapshot.frame} ({(snapshot.frame/24).toFixed(2)}s),
      {snapshot.objects.length} drawable objects,
      {snapshot.total_native_mesh_triangles_sent} real source triangles,
      {snapshot.proxy_objects} simplified proxies.
      {snapshot.truncated_prims>0&&' Scene geometry truncated for this low-power view.'}
    </p>
    <p className="fineprint">This is an interactive geometric preview, not Cycles
      lighting, materials, shadows or finished movie pixels.
      {orbit?' Orbit navigation is temporary; the saved source camera remains unchanged.'
        :' The view follows the original authored camera.'}
    </p>
    {renderError&&<div role="region" aria-label="Software projected source fallback">
      <p role="status">{renderError}. Falling back to source-derived camera-space markers.</p>
      <svg viewBox="0 0 640 360" aria-label="Software projected original USD positions"
        style={{width:'100%',background:'#192633',borderRadius:8}}>
        {softwareProjectedMarkers(snapshot).map(m=><g key={m.id}>
          <circle cx={m.x} cy={m.y} r={m.actor?7:5}
            fill={m.actor?'#8ac7ec':'#ddc3a3'}/>
          <text x={m.x+8} y={m.y-5} fill="#e4e9ed" fontSize="12">
            {m.label}</text>
        </g>)}
      </svg>
      <p className="fineprint">CPU-only geometry projection; no occlusion,
        shading, surface materials or reflective camera effects.</p>
    </div>}
  </div>;
}
