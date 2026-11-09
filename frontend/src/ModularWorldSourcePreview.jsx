import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';

const FORMAT='nvp.usd_film02m_f.original_source_lowfi_preview.v1';

/**
 * Genuine FilmIndex/USD-reviewed bounding volumes, not procedurally
 * imagined buildings and not pixel-level Blender/Cycles preview.
 * The low-power HTML/SVG footprint fallback remains available.
 */
export default function ModularWorldSourcePreview({preview}){
  const mount=useRef(null);
  const [error,setError]=useState('');
  const valid=preview?.format===FORMAT&&
    preview.native_usd_source_reopened===true&&
    preview.preview_is_source_bounds_not_cycles_pixels===true&&
    preview.native_blender_workers_started===0&&
    Array.isArray(preview.instances);
  useEffect(()=>{
    if(!valid||!mount.current)return;
    const target=mount.current;
    let renderer,controls,raf=0,active=true;
    const disposed=[];
    const scene=new THREE.Scene();
    try{
      scene.background=new THREE.Color(0x17232c);
      const shown=preview.instances.filter(x=>!x.hidden);
      const camera=new THREE.PerspectiveCamera(55,16/9,.05,10000);
      const centers=shown.map(x=>x.position_local_m);
      const x=centers.reduce((a,p)=>a+p[0],0)/Math.max(1,centers.length);
      const y=centers.reduce((a,p)=>a+p[1],0)/Math.max(1,centers.length);
      const targetPoint=new THREE.Vector3(x,0,-y);
      const spread=Math.max(32,...centers.map(p=>
        Math.hypot(p[0]-x,p[1]-y)))+18;
      camera.position.set(x+spread,spread*.85,-y+spread);
      camera.lookAt(targetPoint);
      for(const [i,item] of shown.entries()){
        const bounds=item.source_bounds_m,position=item.position_local_m;
        if(!Array.isArray(bounds)||bounds.length!==2||
           bounds.some(b=>!Array.isArray(b)||b.length!==3))
          throw Error('Native OpenUSD source module bounds incomplete');
        const dims=bounds[1].map((v,j)=>Math.max(.01,v-bounds[0][j]));
        const middle=bounds[0].map((v,j)=>(v+bounds[1][j])/2);
        const angle=(item.yaw_deg||0)*Math.PI/180;
        const rx=middle[0]*Math.cos(angle)-middle[1]*Math.sin(angle);
        const ry=middle[0]*Math.sin(angle)+middle[1]*Math.cos(angle);
        const geometry=new THREE.BoxGeometry(dims[0],dims[2],dims[1]);
        const material=new THREE.MeshBasicMaterial({
          color:item.director_placed?0x79c7e4:(
            i%2?0xd5bd96:0x9bc3a1),
          wireframe:true,transparent:true,opacity:.86});
        const mesh=new THREE.Mesh(geometry,material);
        mesh.rotation.y=angle;
        mesh.position.set(position[0]+rx,position[2]+middle[2],
                          -(position[1]+ry));
        mesh.name=item.name;
        scene.add(mesh);
        disposed.push([geometry,material]);
      }
      const guide=new THREE.GridHelper(
        Math.max(30,Math.min(1000,spread*3)),20,0x52636c,0x2a3e48);
      scene.add(guide);
      const axes=new THREE.AxesHelper(4);
      scene.add(axes);
      disposed.push([guide.geometry,guide.material]);
      disposed.push([axes.geometry,axes.material]);
      renderer=new THREE.WebGLRenderer({
        antialias:false,alpha:false,powerPreference:'low-power'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.2));
      renderer.domElement.setAttribute('aria-label',
        'Source-verified 3D bounding volumes of original USD district');
      target.replaceChildren(renderer.domElement);
      controls=new OrbitControls(camera,renderer.domElement);
      controls.enableDamping=true;controls.target.copy(targetPoint);
      controls.update();
      const resize=()=>{
        if(!active)return;
        const w=Math.max(320,target.clientWidth||640);
        renderer.setSize(w,Math.round(w*9/16),false);
        camera.aspect=16/9;camera.updateProjectionMatrix();
      };
      resize();
      let last=0;
      const draw=stamp=>{
        if(!active)return;
        if(stamp-last>90){
          controls.update();renderer.render(scene,camera);last=stamp;
        }
        raf=window.requestAnimationFrame(draw);
      };
      window.addEventListener('resize',resize);
      raf=window.requestAnimationFrame(draw);
      setError('');
      return ()=>{
        active=false;
        window.cancelAnimationFrame(raf);
        window.removeEventListener('resize',resize);
        controls.dispose();
        disposed.forEach(([geometry,material])=>{
          geometry.dispose();material.dispose();});
        renderer.dispose();
        if(renderer.domElement.parentNode===target)
          target.removeChild(renderer.domElement);
      };
    }catch(e){
      if(renderer)renderer.dispose();
      for(const [geometry,material] of disposed){
        geometry.dispose();material.dispose();
      }
      target.replaceChildren();
      setError('3D WebGL unavailable: '+(e.message||'no renderer'));
    }
  },[preview,valid]);
  if(!valid)return <p role="status">No verified original district source view.</p>;
  const points=preview.instances.filter(x=>!x.hidden);
  const xs=points.map(p=>p.position_local_m[0]);
  const ys=points.map(p=>p.position_local_m[1]);
  const xmin=Math.min(0,...xs)-25,xmax=Math.max(0,...xs)+25;
  const ymin=Math.min(0,...ys)-25,ymax=Math.max(0,...ys)+25;
  const sizeX=Math.max(1,xmax-xmin),sizeY=Math.max(1,ymax-ymin);
  return <div role="region" aria-label="Native USD source geometry preview">
    {!error&&<div ref={mount} style={{
      minHeight:250,width:'100%',background:'#17232c',
      borderRadius:8,overflow:'hidden'}}/>}
    {error&&<p role="status">{error}. Using verified plan footprint map.</p>}
    <svg viewBox="0 0 800 270"
      style={{width:'100%',height:200,background:'#1e2b36',borderRadius:8}}
      role="img" aria-label="Original USD director source footprints and manual objects">
      {points.map((x,i)=>{
        const b=x.source_bounds_m;
        const w=b[1][0]-b[0][0],h=b[1][1]-b[0][1];
        const cx=30+(x.position_local_m[0]-xmin)/sizeX*740;
        const cy=12+(x.position_local_m[1]-ymin)/sizeY*245;
        const bw=Math.max(3,w/sizeX*740),bh=Math.max(3,h/sizeY*245);
        return <g key={x.name} transform={'translate('+cx+' '+cy+') rotate('+x.yaw_deg+')'}>
          <rect x={-bw/2} y={-bh/2} width={bw} height={bh}
            rx="2" fill={x.director_placed?'#2e6d89':'#426b52'}
            stroke={x.director_placed?'#95d0f6':'#badabe'} strokeWidth="1.3"/>
          <title>{x.name+' · original '+x.building_id}</title>
          <text y="3" x="0" fontSize="9" textAnchor="middle" fill="#fff">
            {x.instance_id??'D'}</text>
        </g>;
      })}
    </svg>
    <p className="fineprint">{points.length} source-visible building placements
      · {preview.source_prototype_count} approved prototype(s)
      · {preview.verified_openusd_point_instancer} original USD instances.
      Technical wireframe uses real source bounding volumes; it is not the
      full original mesh, lighting, shadows, textures, interior view or
      a completed Cycles picture. Hidden source instances remain preserved.</p>
  </div>;
}
