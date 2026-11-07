/** WO2 independent GPU texture fixture. A real WebGL readback is required.
 * This tests original sRGB texel orientation/wrapping and disposable GPU
 * texture semantics, NOT entire Hydra/ACES/light transport equivalence.
 */
import * as THREE from 'three';

export function compareGPUTexturePixels(rgba,{tolerance=4}={}){
  if(!(rgba instanceof Uint8Array)||rgba.length!==4*4*4)
    throw Error('Actual 4x4 RGBA GPU readback required');
  if(!Number.isInteger(tolerance)||tolerance<0||tolerance>16)
    throw Error('Unbounded GPU fixture pixel tolerance');
  // renderTarget pixel origin is lower left; image texture bottom row:
  // red, blue; top row: green, white.
  const targets=[
    {x:0,y:0,rgb:[255,0,0]},
    {x:3,y:0,rgb:[0,0,255]},
    {x:0,y:3,rgb:[0,255,0]},
    {x:3,y:3,rgb:[255,255,255]},
  ];
  const observations=targets.map(({x,y,rgb})=>{
    const base=(y*4+x)*4;
    const actual=Array.from(rgba.slice(base,base+3));
    return {pixel:[x,y],expected:rgb,actual,
      error:Math.max(...actual.map((v,i)=>Math.abs(v-rgb[i])))};
  });
  return {
    format:'nvp.wo2.native_gpu_texture_fixture.v1',
    actual_gpu_readback:true,
    color_pipeline:'sRGB nearest unlit original PNG reference',
    passed:observations.every(o=>o.error<=tolerance),
    max_channel_error:Math.max(...observations.map(o=>o.error)),
    observations,
    source_modified:false,
    full_usd_material_parity_proven:false,
    physical_display_calibrated:false,
  };
}

export function runGPUTextureReference(){
  const renderer=new THREE.WebGLRenderer({
    antialias:false,alpha:false,preserveDrawingBuffer:false});
  const target=new THREE.WebGLRenderTarget(4,4,{
    depthBuffer:false,stencilBuffer:false,
    magFilter:THREE.NearestFilter,minFilter:THREE.NearestFilter,
    format:THREE.RGBAFormat,type:THREE.UnsignedByteType,
  });
  let geometry=null,material=null,texture=null;
  try{
    renderer.setSize(4,4,false);
    renderer.setPixelRatio(1);
    renderer.toneMapping=THREE.NoToneMapping;
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    // DataTexture convention: first bytes are bottom row in UV-space.
    texture=new THREE.DataTexture(
      new Uint8Array([
        255,0,0,255, 0,0,255,255,
        0,255,0,255, 255,255,255,255,
      ]),2,2,THREE.RGBAFormat);
    texture.colorSpace=THREE.SRGBColorSpace;
    texture.wrapS=THREE.RepeatWrapping;
    texture.wrapT=THREE.RepeatWrapping;
    texture.magFilter=THREE.NearestFilter;
    texture.minFilter=THREE.NearestFilter;
    texture.flipY=false;
    texture.needsUpdate=true;
    geometry=new THREE.PlaneGeometry(2,2);
    material=new THREE.MeshBasicMaterial({map:texture,
      color:0xffffff,side:THREE.DoubleSide,depthTest:false});
    const scene=new THREE.Scene();
    scene.add(new THREE.Mesh(geometry,material));
    const camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);
    camera.position.z=1;
    const bytes=new Uint8Array(4*4*4);
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene,camera);
    renderer.readRenderTargetPixels(target,0,0,4,4,bytes);
    const evidence=compareGPUTexturePixels(bytes);
    const gl=renderer.getContext();
    return {...evidence,real_webgl_context:Boolean(gl),
      drawing_buffer_width:4,drawing_buffer_height:4};
  }finally{
    renderer.setRenderTarget(null);
    geometry?.dispose();
    material?.dispose();
    texture?.dispose();
    target.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
  }
}


export function compareGPUSourcePixels(actual,packet,{tolerance=6}={}){
  if(!(actual instanceof Uint8Array)||actual.length!==64||
     !Number.isInteger(tolerance)||tolerance<0||tolerance>16||
     !packet||!/^[0-9a-f]{64}$/.test(packet.sha256||'')||
     !/^[0-9a-f]{64}$/.test(packet.preview_sha256||'')||
     !Array.isArray(packet.gpu_reference_rgb)||
     packet.gpu_reference_rgb.length!==4||
     !packet.gpu_reference_rgb.every(rgb=>
       Array.isArray(rgb)&&rgb.length===3&&
       rgb.every(v=>Number.isInteger(v)&&v>=0&&v<=255)))
    throw Error('Actual source-bound GPU texture readback is required');
  const locations=[[0,0],[3,0],[0,3],[3,3]];
  const samples=locations.map(([x,y],i)=>{
    const expected=packet.gpu_reference_rgb[i];
    const observed=Array.from(actual.slice(4*(4*y+x),4*(4*y+x)+3));
    return {uv:packet.gpu_reference_uv?.[i],
      expected,observed,error:Math.max(
        ...expected.map((v,j)=>Math.abs(v-observed[j])))};
  });
  return {
    format:'nvp.wo2.native_source_cpu_gpu_texture_comparison.v1',
    source_texture_sha256:packet.sha256,
    source_preview_sha256:packet.preview_sha256,
    actual_gpu_readback:true,
    measured_texture_sampling_only:true,
    passed:samples.every(sample=>sample.error<=tolerance),
    max_channel_error:Math.max(...samples.map(s=>s.error)),
    samples,
    original_modified:false,
    full_usd_material_parity_proven:false,
    physical_display_calibrated:false,
  };
}

export async function runGPUSourceTextureReference(packet){
  if(!packet||packet.format!=='nvp.original.usd_texture_png.v1'||
     typeof packet.png_base64!=='string'||
     packet.png_base64.length>11200000||
     !packet.png_base64.startsWith('iVBORw0KGgo'))
    throw Error('Native approved source texture transport required');
  const renderer=new THREE.WebGLRenderer({
    antialias:false,alpha:false,preserveDrawingBuffer:false});
  const target=new THREE.WebGLRenderTarget(4,4,{
    depthBuffer:false,stencilBuffer:false,
    minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,
    format:THREE.RGBAFormat,type:THREE.UnsignedByteType,
  });
  let texture=null,material=null,geometry=null;
  try{
    renderer.setSize(4,4,false);
    renderer.setPixelRatio(1);
    renderer.toneMapping=THREE.NoToneMapping;
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    texture=await new Promise((resolve,reject)=>{
      new THREE.TextureLoader().load(
        'data:image/png;base64,'+packet.png_base64,resolve,
        undefined,()=>reject(Error('Native source PNG GPU decode failed')));
    });
    texture.colorSpace=THREE.SRGBColorSpace;
    texture.wrapS=THREE.RepeatWrapping;
    texture.wrapT=THREE.RepeatWrapping;
    texture.minFilter=THREE.NearestFilter;
    texture.magFilter=THREE.NearestFilter;
    texture.flipY=true;
    texture.needsUpdate=true;
    geometry=new THREE.PlaneGeometry(2,2);
    material=new THREE.MeshBasicMaterial({
      color:0xffffff,map:texture,depthTest:false,
      side:THREE.DoubleSide,
    });
    const scene=new THREE.Scene();
    scene.add(new THREE.Mesh(geometry,material));
    const camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,10);
    camera.position.z=1;
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene,camera);
    const actual=new Uint8Array(64);
    renderer.readRenderTargetPixels(target,0,0,4,4,actual);
    const gl=renderer.getContext();
    const debug=gl.getExtension('WEBGL_debug_renderer_info');
    const gpuVendor=debug?String(gl.getParameter(debug.UNMASKED_VENDOR_WEBGL)):'';
    const gpuRenderer=debug?String(gl.getParameter(
      debug.UNMASKED_RENDERER_WEBGL)):'';
    const advertised=(gpuVendor+' '+gpuRenderer).trim();
    const software=/swiftshader|llvmpipe|softpipe|warp|software|basic render/i
      .test(advertised);
    return {...compareGPUSourcePixels(actual,packet),
      webgl_context_created:true,
      webgl_vendor_claim:gpuVendor||null,
      webgl_renderer_claim:gpuRenderer||null,
      webgl_software_renderer_detected:software,
      hardware_classification:software?'SOFTWARE_RENDERER':
        advertised?'ADVERTISED_GPU_UNVERIFIED':'UNKNOWN_GPU',
      physical_gpu_accepted:false,
      independent_hydra_parity_accepted:false};
  }finally{
    renderer.setRenderTarget(null);
    geometry?.dispose();material?.dispose();texture?.dispose();
    target.dispose();renderer.dispose();renderer.forceContextLoss();
  }
}
