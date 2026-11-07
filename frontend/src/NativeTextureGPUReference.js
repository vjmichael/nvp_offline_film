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
