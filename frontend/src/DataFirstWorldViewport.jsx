import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {BokehPass} from 'three/addons/postprocessing/BokehPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {defaultWO2Look,validateWO2Look,textureChannelLook,physicalMaterialLook,
  suggestWO2Look,WO2_MOODS} from './WO2PresentationLook.js';
import {runGPUTextureReference,runGPUSourceTextureReference}
  from './NativeTextureGPUReference.js';

// DA-04: evaluate OpenUSD source geometry IN THREE DIMENSIONS at the actual
// audio presentation Film Time. There is no MP4, frame sequencer, texture
// proxy, video transcoding or persistent picture. SHA-bound NVP procedural
// meshes and UsdSkel actors are source-verified; unbound actors stay gizmos.
// The native host, not JavaScript, verifies the source PNG against FilmIndex.
export function validateSourceTexture(surface,item){
  const descriptor=surface?.texture;
  if(!descriptor)return null;
  const packet=surface?.texture_transport;
  if(!['mesh','skinned_mesh'].includes(item.shape)||
     (!item.mesh_uvs&&!item.mesh_face_uvs)||
     descriptor.format!=='nvp.original.usd_texture_png.v1'||
     packet?.format!==descriptor.format||
     descriptor.source_modified!==false||packet.source_modified!==false||
     !/^[0-9a-f]{64}$/.test(descriptor.sha256||'')||
     packet.sha256!==descriptor.sha256||
     descriptor.width!==packet.original_width||
     descriptor.height!==packet.original_height||
     !Number.isInteger(packet.width)||!Number.isInteger(packet.height)||
     packet.width<1||packet.height<1||
     packet.width>512||packet.height>512||
     !Number.isInteger(descriptor.width)||descriptor.width>2048||
     !Number.isInteger(descriptor.height)||descriptor.height>2048||
     (packet.derived_preview!==true&&packet.derived_preview!==false)||
     !/^[0-9a-f]{64}$/.test(packet.preview_sha256||'')||
     (packet.derived_preview===false&&
       (packet.width!==descriptor.width||packet.height!==descriptor.height||
        packet.preview_sha256!==descriptor.sha256))||
     descriptor.color_space!=='sRGB'||packet.color_space!=='sRGB'||
     descriptor.wrap!=='repeat'||packet.wrap!=='repeat'||
     typeof packet.png_base64!=='string'||packet.png_base64.length>2800000||
     !packet.png_base64.startsWith('iVBORw0KGgo'))
    throw Error('Unverified original USD texture transport');
  return packet;
}

export function validatePBRChannelPackets(surface,item){
  const maps=surface?.pbr_maps;
  if(maps==null)return null;
  if(typeof maps!=='object'||Array.isArray(maps)||
     !Object.keys(maps).length||Object.keys(maps).length>5||
     Object.keys(maps).some(ch=>
       !['roughness','metallic','emission','normal','opacity'].includes(ch)))
    throw Error('Unsupported original PBR channel manifest');
  if(!surface.pbr_map_transports||
     Object.keys(surface.pbr_map_transports).length!==Object.keys(maps).length)
    throw Error('Original PBR channel image transport incomplete');
  const result={};
  for(const [channel,descriptor] of Object.entries(maps)){
    const packet=surface.pbr_map_transports[channel];
    result[channel]=validateSourceTexture({
      texture:descriptor,texture_transport:packet,
    },item);
  }
  return result;
}

export function approximateKelvinRGB(kelvin){
  if(!Number.isFinite(kelvin)||kelvin<1000||kelvin>20000)
    throw Error('Untrusted authored USD light temperature');
  const k=kelvin/100;
  const r=k<=66?255:329.698727446*Math.pow(k-60,-.1332047592);
  const g=k<=66?99.4708025861*Math.log(k)-161.1195681661:
    288.1221695283*Math.pow(k-60,-.0755148492);
  const b=k>=66?255:k<=19?0:
    138.5177312231*Math.log(k-10)-305.0447927307;
  return [r,g,b].map(n=>Math.max(0,Math.min(255,n))/255);
}

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
  const uv=item.mesh_uvs;
  if(uv!=null&&(
    !['mesh','skinned_mesh'].includes(item.shape)||
    !Array.isArray(uv)||uv.length!==pts.length||
    !uv.every(pair=>Array.isArray(pair)&&pair.length===2&&
      pair.every(v=>typeof v==='number'&&Number.isFinite(v)&&
        Math.abs(v)<=1024))))
    throw Error('Source mesh UV primvar is invalid or mismatched');
  const faceUV=item.mesh_face_uvs;
  if(faceUV!=null&&(
    !['mesh','skinned_mesh'].includes(item.shape)||uv!=null||
    !Array.isArray(faceUV)||faceUV.length!==faces.length||
    !faceUV.every(face=>Array.isArray(face)&&face.length===3&&
      face.every(pair=>Array.isArray(pair)&&pair.length===2&&
        pair.every(v=>typeof v==='number'&&Number.isFinite(v)&&
          Math.abs(v)<=1024)))))
    throw Error('Original face-varying USD UV topology is invalid');
  return {pts,faces,uv:uv||null,faceUV:faceUV||null};
}

export function validateMaterialSlots(item){
  const slots=item.source_material_slots;
  if(slots==null)return null;
  if(item.shape!=='mesh'||!Array.isArray(item.mesh_triangles)||
     !Array.isArray(slots)||slots.length<1||slots.length>8)
    throw Error('Invalid frozen USD face material subset scope');
  const faces=item.mesh_triangles.length;
  const occupied=new Set();
  for(let i=0;i<slots.length;i++){
    const spec=slots[i];
    if(spec?.format!=='nvp.original.usd_material_subsets.v1'||
       spec.source_modified!==false||
       spec.material_path!=='/Asset/Materials/Slot'+i||
       spec.subset_path!=='/Asset/Geometry/MaterialSlot'+i||
       !Array.isArray(spec.faces)||spec.faces.length===0||
       !spec.faces.every(n=>Number.isInteger(n)&&n>=0&&n<faces)||
       !Array.isArray(spec.base_color_rgb)||
       spec.base_color_rgb.length!==3||
       !spec.base_color_rgb.every(v=>typeof v==='number'&&
         Number.isFinite(v)&&v>=0&&v<=1)||
       ![spec.roughness,spec.metallic].every(v=>typeof v==='number'&&
         Number.isFinite(v)&&v>=0&&v<=1))
      throw Error('Malformed original USD subset source');
    for(const face of spec.faces){
      if(occupied.has(face))throw Error('Overlapping original USD face materials');
      occupied.add(face);
    }
  }
  return slots;
}

function disposeMeshMaterial(material,cache=null){
  for(const entry of Array.isArray(material)?material:[material]){
    const map=entry?.map;
    if(map){
      const digest=entry.userData?.originalTextureSha;
      const stored=digest&&cache?.get(digest);
      if(stored&&stored.texture===map){
        stored.refs-=1;
        if(stored.refs<=0){map.dispose();cache.delete(digest);}
      }else map.dispose();
    }
    entry?.dispose();
  }
}

function shapeFor(item){
  if(!Number.isFinite(item.size_m)||item.size_m<=0||item.size_m>10000)
    throw Error('Untrusted USD 3D geometry scale');
  if(item.shape==='cube')return new THREE.BoxGeometry(
    item.size_m,item.size_m,item.size_m);
  if(item.shape==='sphere')return new THREE.SphereGeometry(
    item.size_m/2,24,16);
  if(item.shape==='mesh'||item.shape==='skinned_mesh'){
    const {pts,faces,uv,faceUV}=validateMeshData(item);
    const geometry=new THREE.BufferGeometry();
    if(faceUV){
      // Preserve seams: a shared position can have different st on each
      // authored face corner. GPU vertices are disposable duplicates only.
      geometry.setAttribute('position',new THREE.Float32BufferAttribute(
        faces.flatMap(face=>face.flatMap(i=>pts[i])),3));
      geometry.setAttribute('uv',new THREE.Float32BufferAttribute(
        faceUV.flat(2),2));
      geometry.computeVertexNormals();
      return geometry;
    }
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(
      pts.flat(),3));
    geometry.setIndex(faces.flat());
    if(uv)geometry.setAttribute('uv',new THREE.Float32BufferAttribute(
      uv.flat(),2));
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
  const {pts,faces,faceUV}=validateMeshData(item);
  const attr=geometry.getAttribute('position');
  const index=geometry.getIndex();
  if(faceUV){
    const texcoords=geometry.getAttribute('uv');
    if(!attr||index||attr.count!==faces.length*3||
       !texcoords||texcoords.count!==attr.count)
      throw Error('Original skinned face-varying topology changed');
    let offset=0;
    for(let i=0;i<faces.length;i++){
      for(let corner=0;corner<3;corner++){
        const p=pts[faces[i][corner]];
        const uv=faceUV[i][corner];
        if(Math.abs(texcoords.getX(offset)-uv[0])>1e-6||
           Math.abs(texcoords.getY(offset)-uv[1])>1e-6)
          throw Error('Original rig UV seams changed without source revision');
        attr.setXYZ(offset++,p[0],p[1],p[2]);
      }
    }
    attr.needsUpdate=true;
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    return;
  }
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
  objects=[],listenerPath='',tick='0',sceneSha='',nativeSchemas=[],
  upgradedTexture=null,presentationLook=null,onLookChange=null,
}){
  const holder=useRef(null);
  const env=useRef(null);
  const [disabled,setDisabled]=useState(false);
  const [gpuFixture,setGpuFixture]=useState(null);
  const [localLook,setLocalLook]=useState(defaultWO2Look);
  const [lookWarning,setLookWarning]=useState('');
  const [selectedMaterial,setSelectedMaterial]=useState('');
  const [selectedUvChannel,setSelectedUvChannel]=useState('base_color');
  const activeLook=presentationLook||localLook;
  const sceneRoles=Object.fromEntries(objects.filter(o=>
    typeof o?.path==='string'&&typeof o?.semantic_role==='string')
    .map(o=>[o.path,o.semantic_role]));
  const setPresentation=updated=>{
    try{
      const verified=validateWO2Look(updated,sceneRoles);
      for(const [path,channels] of Object.entries(
          verified.textures.transforms)){
        const material=objects.find(o=>o.path===path)?.source_material;
        const available=new Set([
          ...(material?.texture?['base_color']:[]),
          ...Object.keys(material?.pbr_maps||{}),
        ]);
        if(!Object.keys(channels).every(ch=>available.has(ch)))
          throw Error('Original actor does not own that texture channel');
      }
      for(const [path,physical] of Object.entries(verified.materials)){
        const material=objects.find(o=>o.path===path)?.source_material;
        if(physical.opacity<1&&material?.pbr_maps?.opacity)
          throw Error('Cannot blend an original binary cutout without a compositing graph');
      }
      if(onLookChange)onLookChange(verified);
      else setLocalLook(verified);
      setLookWarning('');
    }catch(error){setLookWarning(error.message);}
  };
  const changeLook=callback=>{
    const changed=structuredClone(activeLook);
    callback(changed);
    setPresentation(changed);
  };
  const [viewMode,setViewMode]=useState('orbit');
  const [selectedCamera,setSelectedCamera]=useState('');
  const cameraObjects=objects.filter(o=>o?.semantic_role==='camera');
  const cameraPath=cameraObjects.some(o=>o.path===selectedCamera)?
    selectedCamera:cameraObjects[0]?.path||'';
  const bounded=Array.isArray(objects)?objects.slice(0,64):[];
  const originalTexturePacket=bounded.find(obj=>
    obj?.source_material?.texture_transport?.gpu_reference_rgb
  )?.source_material?.texture_transport||null;
  const missingRigGeometry=bounded.filter(o=>o?.source_rigged_actor===true&&
    o.native_geometry_status!=='VERIFIED_SKINNED');
  const staleRigPoses=bounded.filter(o=>o?.shape==='skinned_mesh'&&
    o.source_skinning_tick!==String(tick));


  useEffect(()=>{
    if(!holder.current)return;
    const root=holder.current;
    let renderer=null,resize=null,raf=0,controls=null;
    let composer=null,renderPass=null,bokehPass=null,environmentMap=null,pmrem=null;
    let scene=null;
    let disposed=false;
    const meshes=new Map();
    const textureCache=new Map();
    const sourceLights=new Map();
    const MAX_GPU_TEXTURES=16;
    const MAX_GPU_TEXELS=8*1024*1024; // 32 MiB decoded GPU texture budget
    let gpuTexels=0;
    const acquireTexture=(transport,override=null,rawColor=false,options=null)=>{
      const approvedFull=(override&&
        override.source_sha256===transport.sha256&&
        override.derived_preview_only===true&&
        override.source_modified===false&&
        Number.isInteger(override.width)&&Number.isInteger(override.height)&&
        override.width>=1&&override.height>=1&&
        override.width<=2048&&override.height<=2048&&
        override.canvas?.width===override.width&&
        override.canvas?.height===override.height);
      const sha=(approvedFull?transport.sha256+':full':
        transport.sha256)+(rawColor?':raw':'')+
        (options?':'+JSON.stringify(options):'');
      const current=textureCache.get(sha);
      if(current){
        current.refs++;
        return current.texture;
      }
      const pixels=(approvedFull?
        override.width*override.height:transport.width*transport.height);
      if(textureCache.size>=MAX_GPU_TEXTURES||
         gpuTexels+pixels>MAX_GPU_TEXELS)
        throw Error('Native texture resource budget exceeded');
      const tex=approvedFull?
        new THREE.CanvasTexture(override.canvas):
        new THREE.TextureLoader().load(
          'data:image/png;base64,'+transport.png_base64,
          ()=>{if(!disposed)requestRender();});
      tex.colorSpace=rawColor?THREE.NoColorSpace:THREE.SRGBColorSpace;
      tex.wrapS=THREE.RepeatWrapping;
      tex.wrapT=THREE.RepeatWrapping;
      const filter=options?.filter||'nearest';
      tex.magFilter=filter==='nearest'?THREE.NearestFilter:THREE.LinearFilter;
      tex.minFilter=filter==='nearest'?THREE.NearestFilter:
        filter==='bilinear'?THREE.LinearFilter:THREE.LinearMipmapLinearFilter;
      tex.generateMipmaps=filter==='trilinear';
      tex.anisotropy=Math.max(1,Math.min(
        options?.anisotropy||1,renderer.capabilities.getMaxAnisotropy()));
      if(options?.uv){
        tex.repeat.set(...options.uv.repeat);
        tex.offset.set(...options.uv.offset);
        tex.rotation=options.uv.rotation_deg*Math.PI/180;
        // USD UsdTransform2d uses scale/rotation about the UV origin.
        // Never use Three's default centered-rotation convenience here.
        tex.center.set(0,0);
      }
      tex.flipY=true;
      textureCache.set(sha,{texture:tex,refs:1,pixels});
      gpuTexels+=pixels;
      return tex;
    };
    const releaseMaterial=material=>{
      for(const entry of Array.isArray(material)?material:[material]){
        if(!entry)continue;
        const keys=entry.userData?.textureCacheKeys||{
          map:entry.userData?.originalTextureSha,
        };
        for(const [channel,key] of Object.entries(keys)){
          if(!key)continue;
          const current=textureCache.get(key);
          if(current&&current.texture===entry[channel]){
            current.refs--;
            if(current.refs<=0){
              current.texture.dispose();
              textureCache.delete(key);
              gpuTexels-=current.pixels;
            }
          }else entry[channel]?.dispose();
        }
        entry.dispose();
      }
    };
    try{
      renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,
        powerPreference:'high-performance'});
      renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
      renderer.outputColorSpace=THREE.SRGBColorSpace;
      renderer.shadowMap.enabled=true;
      renderer.shadowMap.type=THREE.PCFSoftShadowMap;
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
      const ambient=new THREE.HemisphereLight(0xffffff,0x394552,.7);
      scene.add(ambient);
      const sun=new THREE.DirectionalLight(0xffffff,2.5);
      sun.position.set(10,-6,16);
      sun.castShadow=true;
      sun.shadow.camera.left=-40;sun.shadow.camera.right=40;
      sun.shadow.camera.top=40;sun.shadow.camera.bottom=-40;
      sun.shadow.camera.near=.1;sun.shadow.camera.far=140;
      sun.shadow.bias=-.00015;
      scene.add(sun);
      try{
        pmrem=new THREE.PMREMGenerator(renderer);
        const studio=new RoomEnvironment();
        try{environmentMap=pmrem.fromScene(studio,.08).texture;}
        finally{studio.dispose();}
        scene.environment=environmentMap;
      }catch{
        // A low-budget or recovering GPU may lack PMREM support. Preserve
        // accurate source geometry and direct lighting instead of hiding
        // the entire original scene or claiming reflection acceptance.
        environmentMap?.dispose();
        pmrem?.dispose();
        pmrem=null;environmentMap=null;
        scene.environment=null;
      }
      scene.environmentIntensity=1;
      const camera=new THREE.PerspectiveCamera(50,2,.01,5000);
      const authoredCamera=new THREE.PerspectiveCamera(50,2,.01,5000);
      camera.up.set(0,0,1);
      camera.position.set(12,-15,12);
      camera.lookAt(0,0,0);
      const render=()=>{
        if(disposed)return;
        raf=0;
        const current=env.current?.activeCamera||camera;
        if(composer&&bokehPass){
          renderPass.camera=current;
          bokehPass.camera=current;
          composer.render();
        }else renderer.render(scene,current);
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
        if(composer)composer.setSize(width,height);
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
      env.current={world,meshes,requestRender,acquireTexture,releaseMaterial,
        orbitCamera:camera,authoredCamera,activeCamera:camera,
        renderer,scene,sun,ambient,sourceLights,
        configureDof:(cameraLook)=>{
          if(composer){composer.dispose();composer=null;renderPass=null;
            bokehPass=null;}
          if(cameraLook.depth_of_field){
            try{
              const width=Math.max(280,Math.min(root.clientWidth||640,1900));
              composer=new EffectComposer(renderer);
              renderPass=new RenderPass(scene,camera);
              composer.addPass(renderPass);
              bokehPass=new BokehPass(scene,camera,{
                focus:cameraLook.focus_distance_m,
                aperture:Math.min(.05,.015/(cameraLook.f_stop*cameraLook.f_stop)),
                maxblur:.018,width,height:360});
              composer.addPass(bokehPass);
              composer.addPass(new OutputPass());
              composer.setSize(width,360);
            }catch{
              composer?.dispose();
              composer=null;renderPass=null;bokehPass=null;
              setLookWarning('Optical DOF unavailable on this device; normal 3D preview remains usable.');
            }
          }
          requestRender();
        }};
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
        releaseMaterial(mesh.material);
      }
      for(const light of sourceLights.values()){
        scene?.remove(light);
        light.shadow?.map?.dispose();
        light.dispose?.();
      }
      sourceLights.clear();
      if(renderer){
        if(env.current?.detachDeviceHandlers)env.current.detachDeviceHandlers();
        composer?.dispose();
        environmentMap?.dispose();
        pmrem?.dispose();
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
      const isFullResolution=upgradedTexture?.source_sha256===
        obj.source_material?.texture?.sha256;
      const fingerprint=[obj.shape,
        obj.shape==='skinned_mesh'?'skinned-source':obj.size_m,
        obj.semantic_role,obj.geometry_asset_sha256||'',
        obj.source_material?.texture?.sha256||'',
        JSON.stringify(activeLook.materials[obj.path]||null),
        JSON.stringify(activeLook.textures),
        isFullResolution?'full-resolution':'bounded-preview'].join(':');
      let mesh=state.meshes.get(obj.path);
      if(mesh&&mesh.userData.sourceGeometry!==fingerprint){
        state.world.remove(mesh);
        mesh.geometry.dispose();
        state.releaseMaterial(mesh.material);
        state.meshes.delete(obj.path);mesh=null;
      }
      if(!mesh){
        let pendingGeometry=null,pendingMaterial=null;
        try{
          const geometry=shapeFor(obj);
          pendingGeometry=geometry;
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
          const transport=validateSourceTexture(surface,obj);
          const physical=physicalMaterialLook(activeLook,obj.path);
          const material=new THREE.MeshPhysicalMaterial({
            color:surfaceColor,
            roughness:surface?surface.roughness:.8,
            metalness:surface?surface.metallic:.05,
            opacity:physical.opacity,
            transparent:physical.opacity<1,
            depthWrite:physical.opacity>=1,
            transmission:physical.transmission,
            thickness:physical.thickness_m,
            ior:physical.ior,
            side:obj.shape==='mesh'||obj.shape==='skinned_mesh'?
              THREE.DoubleSide:THREE.FrontSide});
          pendingMaterial=material;
          material.userData.textureCacheKeys={};
          const sourceOptions=channel=>({
            filter:activeLook.textures.filter,
            anisotropy:activeLook.textures.anisotropy,
            uv:textureChannelLook(activeLook,obj.path,channel),
          });
          const originalKey=(packet,raw,channel,full=false)=>
            packet.sha256+(full?':full':'')+(raw?':raw':'')+
            ':'+JSON.stringify(sourceOptions(channel));
          if(transport){
            const full=isFullResolution&&!!upgradedTexture;
            material.map=state.acquireTexture(
              transport,full?upgradedTexture:null,false,
              sourceOptions('base_color'));
            material.userData.textureCacheKeys.map=
              originalKey(transport,false,'base_color',full);
            material.needsUpdate=true;
          }
          const verifiedPBR=validatePBRChannelPackets(surface,obj)||{};
          for(const [channel,desc] of Object.entries(surface?.pbr_maps||{})){
            if(!['roughness','metallic','emission','normal','opacity'].includes(channel))
              throw Error('Unsupported original PBR map channel');
            const channelTransport=verifiedPBR[channel];
            const raw=channel!=='emission';
            const key=originalKey(channelTransport,raw,channel);
            const tex=state.acquireTexture(
              channelTransport,null,raw,sourceOptions(channel));
            const field={
              roughness:'roughnessMap',
              metallic:'metalnessMap',
              emission:'emissiveMap',
              normal:'normalMap',
              opacity:'alphaMap',
            }[channel];
            material[field]=tex;
            material.userData.textureCacheKeys[field]=key;
            if(channel==='roughness')material.roughness=1;
            if(channel==='metallic')material.metalness=1;
            if(channel==='emission')material.emissive.setRGB(1,1,1);
            if(channel==='opacity'){
              material.alphaTest=.5;
              material.transparent=physical.opacity<1;
              material.depthWrite=physical.opacity>=1;
            }
            material.needsUpdate=true;
          }
          const slots=validateMaterialSlots(obj);
          let materialSet=material;
          if(slots){
            const others=slots.map(slot=>new THREE.MeshPhysicalMaterial({
              color:new THREE.Color().setRGB(...slot.base_color_rgb),
              roughness:slot.roughness,metalness:slot.metallic,
              opacity:physical.opacity,transparent:physical.opacity<1,
              depthWrite:physical.opacity>=1,
              transmission:physical.transmission,
              thickness:physical.thickness_m,ior:physical.ior,
              side:THREE.DoubleSide,
            }));
            const faceMaterial=new Array(obj.mesh_triangles.length).fill(0);
            slots.forEach((slot,slotIndex)=>slot.faces.forEach(face=>{
              faceMaterial[face]=slotIndex+1;
            }));
            // Reorder only disposable GPU triangles by source material.
            // This keeps <= 9 draw groups, even for 4,096 alternating faces.
            // FilmIndex/USD face indices and original UVs never change.
            const groups=new Map();
            faceMaterial.forEach((mat,faceIndex)=>{
              if(!groups.has(mat))groups.set(mat,[]);
              groups.get(mat).push(faceIndex);
            });
            const order=[...groups.keys()].sort((a,b)=>a-b);
            const faces=obj.mesh_triangles;
            const faceUV=obj.mesh_face_uvs;
            if(faceUV){
              const positions=[];
              const coordinates=[];
              for(const materialId of order)
                for(const face of groups.get(materialId))
                  for(let corner=0;corner<3;corner++){
                    positions.push(...obj.mesh_points[faces[face][corner]]);
                    coordinates.push(...faceUV[face][corner]);
                  }
              geometry.setAttribute('position',
                new THREE.Float32BufferAttribute(positions,3));
              geometry.setAttribute('uv',
                new THREE.Float32BufferAttribute(coordinates,2));
              geometry.computeVertexNormals();
            }else{
              geometry.setIndex(order.flatMap(mat=>
                groups.get(mat).flatMap(face=>faces[face])));
              geometry.computeVertexNormals();
            }
            geometry.clearGroups();
            let offset=0;
            for(const materialId of order){
              const count=groups.get(materialId).length*3;
              geometry.addGroup(offset,count,materialId);
              offset+=count;
            }
            materialSet=[material,...others];
            pendingMaterial=materialSet;
          }
          mesh=new THREE.Mesh(geometry,materialSet);
          mesh.castShadow=!obj.gizmo_only;
          mesh.receiveShadow=!obj.gizmo_only;
          mesh.matrixAutoUpdate=false;
          mesh.userData.sourceGeometry=fingerprint;
          state.world.add(mesh);
          state.meshes.set(obj.path,mesh);
          pendingGeometry=null;pendingMaterial=null;
        }catch{
          pendingGeometry?.dispose();
          if(pendingMaterial)state.releaseMaterial(pendingMaterial);
          incoming.delete(obj.path);continue;
        }
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
        const base=Array.isArray(mesh.material)?
          mesh.material[0]:mesh.material;
        base.color.setRGB(...surface.base_color_rgb);
        base.roughness=base.roughnessMap?1:surface.roughness;
        base.metalness=base.metalnessMap?1:surface.metallic;
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
      const allMaterials=Array.isArray(mesh.material)?
        mesh.material:[mesh.material];
      for(const current of allMaterials){
        if(current.emissiveMap)
          current.emissive.setRGB(1,1,1);
        else current.emissive.setHex(obj.path===listenerPath?0x065f46:0);
        current.needsUpdate=true;
      }
    }
    for(const [path,mesh] of state.meshes){
      if(!incoming.has(path)){
        state.world.remove(mesh);
        mesh.geometry.dispose();
        state.releaseMaterial(mesh.material);
        state.meshes.delete(path);
      }
    }
    state.requestRender();
  },[objects,listenerPath,tick,upgradedTexture,activeLook]);


  useEffect(()=>{
    const state=env.current;
    if(!state)return;
    const desired=new Set();
    for(const obj of bounded){
      if(obj?.semantic_role!=='light'||typeof obj.path!=='string'||
         !Array.isArray(obj.world_translation)||
         obj.world_translation.length!==3||
         !obj.world_translation.every(n=>Number.isFinite(n)&&
           Math.abs(n)<=100000))
        continue;
      const source=nativeSchemas.find(s=>
        s?.prim_path===obj.path&&s.schema==='UsdLux.SphereLight');
      if(!source||!Number.isFinite(source.intensity)||
         source.intensity<0||source.intensity>1000000)
        continue;
      desired.add(obj.path);
      let light=state.sourceLights.get(obj.path);
      if(!light){
        light=new THREE.PointLight(0xffffff,1,0,2);
        light.castShadow=true;
        light.shadow.mapSize.set(512,512);
        light.shadow.bias=-.0002;
        state.scene.add(light);
        state.sourceLights.set(obj.path,light);
      }
      light.position.set(...obj.world_translation);
      light.intensity=Math.min(100,source.intensity/100);
      light.castShadow=activeLook.lighting.shadows;
      try{
        const rgb=source.temperature_enabled?
          approximateKelvinRGB(source.temperature_kelvin):[1,1,1];
        light.color.setRGB(...rgb);
      }catch{light.color.setRGB(1,1,1);}
    }
    for(const [path,light] of state.sourceLights){
      if(!desired.has(path)){
        state.scene.remove(light);
        light.shadow.map?.dispose();
        light.dispose?.();
        state.sourceLights.delete(path);
      }
    }
    state.requestRender();
  },[objects,nativeSchemas,activeLook]);

  useEffect(()=>{
    const state=env.current;
    if(!state)return;
    try{
      validateWO2Look(activeLook,sceneRoles);
      const {lighting,environment,camera}=activeLook;
      const colors={
        neutral_studio:{sun:0xffffff,sky:0xffffff,ground:0x394552,
                        background:0x121a2a},
        soft_daylight:{sun:0xfff6e5,sky:0xeaf4ff,ground:0x536476,
                       background:0x26364c},
        golden_hour:{sun:0xffbb75,sky:0xffdbad,ground:0x6f4b41,
                     background:0x47352e},
        moonlight:{sun:0x92b9ff,sky:0x657ca5,ground:0x1d293b,
                   background:0x0b1020},
      };
      const preset=colors[environment.preset];
      state.sun.color.setHex(preset.sun);
      state.sun.intensity=lighting.direct_intensity;
      state.sun.castShadow=lighting.shadows;
      state.sun.shadow.mapSize.set(
        lighting.shadow_resolution,lighting.shadow_resolution);
      state.sun.shadow.radius=lighting.shadow_softness;
      state.sun.shadow.map?.dispose();
      state.sun.shadow.map=null;
      state.ambient.color.setHex(preset.sky);
      state.ambient.groundColor.setHex(preset.ground);
      state.ambient.intensity=lighting.ambient_intensity*
        environment.intensity;
      state.scene.background.setHex(preset.background);
      state.scene.environmentIntensity=environment.reflections*
        environment.intensity;
      state.renderer.toneMapping=camera.tone_curve==='filmic_preview'?
        THREE.ACESFilmicToneMapping:THREE.NoToneMapping;
      state.renderer.toneMappingExposure=Math.pow(2,camera.exposure_ev);
      state.configureDof(camera);
      setLookWarning('');
      state.requestRender();
    }catch(error){setLookWarning(error.message);}
  },[activeLook]);

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
    <section aria-label="Creator cinematic presentation look">
      <h3>Film look and material direction</h3>
      <p className="fineprint">Change how the approved USD scene is presented,
        not its original camera, actor, mesh or source images.
        Filmic preview is an interactive look, not a certified ACES master.
        Suggestions are editable and never automatically committed.</p>
      <div className="actions">
        {WO2_MOODS.map(mood=><button type="button" key={mood}
          onClick={()=>setPresentation(suggestWO2Look(
            mood,sceneRoles).look)}>
          {mood.charAt(0).toUpperCase()+mood.slice(1)} lighting
        </button>)}
      </div>
      <div className="actions">
        <label>Lighting environment
          <select aria-label="WO2 environment" value={activeLook.environment.preset}
            onChange={e=>changeLook(x=>{x.environment.preset=e.target.value;})}>
            <option value="neutral_studio">Neutral studio</option>
            <option value="soft_daylight">Soft daylight</option>
            <option value="golden_hour">Golden hour</option>
            <option value="moonlight">Moonlight</option>
          </select>
        </label>
        <label><input type="checkbox" checked={activeLook.lighting.shadows}
          onChange={e=>changeLook(x=>{x.lighting.shadows=e.target.checked;})}/>
          Cast and receive soft shadows</label>
        <label>Shadow quality
          <select aria-label="WO2 shadow resolution"
            value={activeLook.lighting.shadow_resolution}
            onChange={e=>changeLook(x=>{
              x.lighting.shadow_resolution=Number(e.target.value);})}>
            <option value={512}>Balanced</option>
            <option value={1024}>High</option>
            <option value={2048}>Very high</option>
          </select>
        </label>
        <label>Shadow softness
          <input type="range" min="0" max="12" step=".5"
            aria-label="WO2 shadow softness"
            value={activeLook.lighting.shadow_softness}
            onChange={e=>changeLook(x=>{
              x.lighting.shadow_softness=Number(e.target.value);})}/>
        </label>
        <label>Environment reflection strength
          <input type="range" min="0" max="3" step=".1"
            aria-label="WO2 reflection strength"
            value={activeLook.environment.reflections}
            onChange={e=>changeLook(x=>{
              x.environment.reflections=Number(e.target.value);})}/>
        </label>
        <label>Exposure (stops)
          <input type="range" min="-8" max="8" step=".1"
            aria-label="WO2 camera exposure"
            value={activeLook.camera.exposure_ev}
            onChange={e=>changeLook(x=>{
              x.camera.exposure_ev=Number(e.target.value);})}/>
          {activeLook.camera.exposure_ev.toFixed(1)} EV
        </label>
        <label>Image view
          <select aria-label="WO2 tone curve"
            value={activeLook.camera.tone_curve}
            onChange={e=>changeLook(x=>{
              x.camera.tone_curve=e.target.value;})}>
            <option value="filmic_preview">Filmic working preview</option>
            <option value="linear">Neutral linear working preview</option>
          </select>
        </label>
        <label><input type="checkbox"
          checked={activeLook.camera.depth_of_field}
          onChange={e=>changeLook(x=>{
            x.camera.depth_of_field=e.target.checked;})}/>
          Show optical depth of field</label>
        {activeLook.camera.depth_of_field&&<>
          <label>F-stop
            <input type="range" min="1" max="22" step=".5"
              aria-label="WO2 f-stop" value={activeLook.camera.f_stop}
              onChange={e=>changeLook(x=>{
                x.camera.f_stop=Number(e.target.value);})}/>
            f/{activeLook.camera.f_stop.toFixed(1)}
          </label>
          <label>Focus distance (meters)
            <input type="number" min=".1" max="10000" step=".1"
              aria-label="WO2 focus distance"
              value={activeLook.camera.focus_distance_m}
              onChange={e=>changeLook(x=>{
                x.camera.focus_distance_m=Number(e.target.value);})}/>
          </label>
        </>}
        <label>Texture clarity
          <select aria-label="WO2 texture filtering"
            value={activeLook.textures.filter}
            onChange={e=>changeLook(x=>{x.textures.filter=e.target.value;})}>
            <option value="nearest">Pixel accurate</option>
            <option value="bilinear">Smooth</option>
            <option value="trilinear">Mipmapped (recommended)</option>
          </select>
        </label>
        <label>Detail at camera angles
          <select aria-label="WO2 anisotropic filtering"
            value={activeLook.textures.anisotropy}
            onChange={e=>changeLook(x=>{
              x.textures.anisotropy=Number(e.target.value);})}>
            {[1,2,4,8,16].map(n=><option key={n} value={n}>
              {n}× anisotropic</option>)}
          </select>
        </label>
      </div>
      <div className="actions">
        <label>Character or prop material
          <select aria-label="WO2 physical material actor"
            value={selectedMaterial}
            onChange={e=>setSelectedMaterial(e.target.value)}>
            <option value="">Select source actor or prop</option>
            {bounded.filter(o=>['actor','prop','environment'].includes(
              o.semantic_role)&&!o.gizmo_only).map(o=>
              <option value={o.path} key={o.path}>{o.path}</option>)}
          </select>
        </label>
        {selectedMaterial&&['actor','prop','environment'].includes(
          sceneRoles[selectedMaterial])&&(()=>{
          const physical=physicalMaterialLook(activeLook,selectedMaterial);
          return <>
            <label>Opacity
              <input aria-label="WO2 material opacity" type="range"
                min="0" max="1" step=".05" value={physical.opacity}
                onChange={e=>changeLook(x=>{
                  x.materials[selectedMaterial]={...physical,
                    opacity:Number(e.target.value)};})}/>
            </label>
            <label>Glass / transmission
              <input aria-label="WO2 material transmission" type="range"
                min="0" max="1" step=".05" value={physical.transmission}
                onChange={e=>changeLook(x=>{
                  x.materials[selectedMaterial]={...physical,
                    transmission:Number(e.target.value)};})}/>
            </label>
            <label>Refraction index
              <input aria-label="WO2 material IOR" type="number"
                min="1" max="2.5" step=".05" value={physical.ior}
                onChange={e=>changeLook(x=>{
                  x.materials[selectedMaterial]={...physical,
                    ior:Number(e.target.value)};})}/>
            </label>
            <label>Thickness (m)
              <input aria-label="WO2 material thickness" type="number"
                min="0" max="10" step=".01" value={physical.thickness_m}
                onChange={e=>changeLook(x=>{
                  x.materials[selectedMaterial]={...physical,
                    thickness_m:Number(e.target.value)};})}/>
            </label>
            <button type="button" onClick={()=>changeLook(x=>{
              delete x.materials[selectedMaterial];})}>
              Reset material presentation
            </button>
            {(()=>{
              const source=bounded.find(o=>o.path===selectedMaterial);
              const channels=[
                ...(source?.source_material?.texture?['base_color']:[]),
                ...Object.keys(source?.source_material?.pbr_maps||{}),
              ];
              const current=channels.includes(selectedUvChannel)?
                selectedUvChannel:channels[0];
              if(!current)return <p>No verified original PNG
                channels are attached to this actor yet.</p>;
              const uv=textureChannelLook(activeLook,selectedMaterial,current);
              const changeUv=(key,value)=>{
                changeLook(x=>{
                  const transforms=x.textures.transforms;
                  const assigned=transforms[selectedMaterial]||{};
                  assigned[current]={...uv,[key]:value};
                  transforms[selectedMaterial]=assigned;
                });
              };
              return <>
                <label>Original texture channel
                  <select aria-label="WO2 source UV channel"
                    value={current}
                    onChange={e=>setSelectedUvChannel(e.target.value)}>
                    {channels.map(name=><option value={name}
                      key={name}>{name.replace('_',' ')}</option>)}
                  </select>
                </label>
                <label>Tile horizontally
                  <input type="number" min=".01" max="64" step=".1"
                    aria-label="WO2 UV repeat U" value={uv.repeat[0]}
                    onChange={e=>changeUv('repeat',[
                      Number(e.target.value),uv.repeat[1]])}/>
                </label>
                <label>Tile vertically
                  <input type="number" min=".01" max="64" step=".1"
                    aria-label="WO2 UV repeat V" value={uv.repeat[1]}
                    onChange={e=>changeUv('repeat',[
                      uv.repeat[0],Number(e.target.value)])}/>
                </label>
                <label>Texture offset horizontal
                  <input type="number" min="-64" max="64" step=".05"
                    aria-label="WO2 UV offset U" value={uv.offset[0]}
                    onChange={e=>changeUv('offset',[
                      Number(e.target.value),uv.offset[1]])}/>
                </label>
                <label>Texture offset vertical
                  <input type="number" min="-64" max="64" step=".05"
                    aria-label="WO2 UV offset V" value={uv.offset[1]}
                    onChange={e=>changeUv('offset',[
                      uv.offset[0],Number(e.target.value)])}/>
                </label>
                <label>Texture rotation (degrees)
                  <input type="range" min="-360" max="360" step="1"
                    aria-label="WO2 UV rotation" value={uv.rotation_deg}
                    onChange={e=>changeUv('rotation_deg',
                      Number(e.target.value))}/>
                  {uv.rotation_deg}°
                </label>
                <button type="button" onClick={()=>changeLook(x=>{
                  const assigned=x.textures.transforms[selectedMaterial];
                  if(assigned){
                    delete assigned[current];
                    if(!Object.keys(assigned).length)
                      delete x.textures.transforms[selectedMaterial];
                  }
                })}>Reset this channel's UV presentation</button>
              </>;
            })()}
          </>;
        })()}
      </div>
      {lookWarning&&<p role="alert">Presentation look: {lookWarning}</p>}
    </section>
    <div className="actions">
      <button type="button" disabled={disabled}
        onClick={()=>{
          try{setGpuFixture(runGPUTextureReference());}
          catch(e){setGpuFixture({passed:false,reason:String(e.message),
            actual_gpu_readback:false});}
        }}>Check GPU texture reference</button>
      <button type="button" disabled={disabled||!originalTexturePacket}
        onClick={async()=>{
          try{setGpuFixture(await runGPUSourceTextureReference(
            originalTexturePacket));}
          catch(e){setGpuFixture({passed:false,reason:String(e.message),
            actual_gpu_readback:false});}
        }}>Compare actual source PNG CPU–GPU texels</button>
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
    {gpuFixture&&<p role={gpuFixture.passed?'status':'alert'}>
      {gpuFixture.passed?
        'Real WebGL reference readback passed':
        'GPU texture reference not accepted'} ·
      {gpuFixture.actual_gpu_readback?
        'Actual 4 × 4 GPU pixels compared':'No accepted GPU readback'}
      {typeof gpuFixture.max_channel_error==='number'&&
        ' · max channel error '+gpuFixture.max_channel_error}
      {gpuFixture.reason&&' · '+gpuFixture.reason}.
      This checks a native GPU texture reference, not full scene, color
      calibration or Hydra material fidelity.
    </p>}
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
