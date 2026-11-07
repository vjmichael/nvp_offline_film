import {describe,it,expect} from 'vitest';
import * as THREE from 'three';
import {validateMeshData,updateSkinnedGeometry,validateSourceTexture}
  from './DataFirstWorldViewport.jsx';

const actor={
  path:'/World/Actor',shape:'skinned_mesh',source_skinning:true,
  source_skinning_tick:'7056000000',
  size_m:2,source_color_rgb:[0.35,0.55,0.82],
  source_material:{
    format:'nvp.original_usd_preview_surface.v1',
    material_path:'/World/Actor/Rig/Material',
    base_color_rgb:[0.35,0.55,0.82],
    roughness:.37,metallic:.12,original_source_modified:false,
  },
  mesh_points:[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
  mesh_triangles:[[0,1,2],[0,2,3]],
};

describe('DA-04B bounded source-verified live skinned actor',()=>{
  it('updates disposable GPU pose points in place without changing topology',()=>{
    expect(validateMeshData(actor).faces).toHaveLength(2);
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',
      new THREE.Float32BufferAttribute(actor.mesh_points.flat(),3));
    geometry.setIndex(actor.mesh_triangles.flat());
    const before=geometry.getIndex().array.slice();
    updateSkinnedGeometry(geometry,{
      ...actor,source_skinning_tick:'14112000000',
      mesh_points:actor.mesh_points.map((p,i)=>
        i===1?[2,0,0]:p),
    });
    expect(geometry.getAttribute('position').getX(1)).toBe(2);
    expect([...geometry.getIndex().array]).toEqual([...before]);
    geometry.dispose();
  });

  it('rejects impossible skinning authority, pose and changed mesh faces',()=>{
    expect(()=>validateMeshData({...actor,source_skinning:false})).toThrow();
    expect(()=>validateMeshData({...actor,source_material:{
      ...actor.source_material,roughness:2,
    }})).toThrow();
    expect(()=>validateMeshData({...actor,source_material:{
      ...actor.source_material,base_color_rgb:[1,0,0],
    }})).toThrow();
    expect(()=>validateMeshData({...actor,
      source_skinning_tick:'1.5'})).toThrow();
    expect(()=>validateMeshData({...actor,
      mesh_points:[[Infinity,0,0],...actor.mesh_points.slice(1)]})).toThrow();
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',
      new THREE.Float32BufferAttribute(actor.mesh_points.flat(),3));
    geometry.setIndex(actor.mesh_triangles.flat());
    expect(()=>updateSkinnedGeometry(geometry,{
      ...actor,mesh_triangles:[[0,2,1],[0,2,3]]
    })).toThrow(/indices changed/);
    geometry.dispose();
  });
});

describe('WO2 original USD UV source contract',()=>{
  const authored={
    ...actor,shape:'mesh',source_skinning:false,
    mesh_uvs:[[0,0],[1,0],[0,1],[1,1]],
  };
  it('accepts finite per-vertex source st coordinates',()=>{
    expect(validateMeshData(authored).uv).toEqual(authored.mesh_uvs);
    expect(validateMeshData({...authored,mesh_uvs:null}).uv).toBeNull();
  });
  it('rejects fake skinned UVs, wrong vertex counts and unsafe numbers',()=>{
    expect(validateMeshData({...actor,mesh_uvs:authored.mesh_uvs}).uv)
      .toEqual(authored.mesh_uvs);
    expect(()=>validateMeshData({...authored,mesh_uvs:[[0,0]]}))
      .toThrow(/UV/);
    expect(()=>validateMeshData({...authored,
      mesh_uvs:[[0,0],[1,0],[NaN,1],[1,1]]})).toThrow(/UV/);
    expect(()=>validateMeshData({...authored,
      mesh_uvs:[[0,0],[1025,0],[0,1],[1,1]]})).toThrow(/UV/);
  });
});

describe('WO2 SHA-bound native PNG source transport',()=>{
  const sha='a'.repeat(64);
  const surface={
    texture:{format:'nvp.original.usd_texture_png.v1',sha256:sha,
      width:2,height:2,color_space:'sRGB',wrap:'repeat',
      source_modified:false},
    texture_transport:{format:'nvp.original.usd_texture_png.v1',
      sha256:sha,width:2,height:2,color_space:'sRGB',wrap:'repeat',
      png_base64:'iVBORw0KGgoAAA==',source_modified:false},
  };
  const mesh={
    shape:'mesh',mesh_uvs:[[0,0],[1,0],[0,1]],
  };
  it('accepts native-verified source scoped texture transport',()=>{
    expect(validateSourceTexture(surface,mesh).sha256).toBe(sha);
  });
  it('refuses arbitrary image paths, replaced digests and actors without UVs',()=>{
    expect(()=>validateSourceTexture({
      ...surface,texture_transport:{...surface.texture_transport,
        sha256:'b'.repeat(64)}
    },mesh)).toThrow(/texture/);
    expect(()=>validateSourceTexture(surface,{
      ...mesh,mesh_uvs:null})).toThrow(/texture/);
    expect(()=>validateSourceTexture({...surface,
      texture_transport:{...surface.texture_transport,
        png_base64:'https://host/asset.png'}},mesh)).toThrow(/texture/);
  });
});
