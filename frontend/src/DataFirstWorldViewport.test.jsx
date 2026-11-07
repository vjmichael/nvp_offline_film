import {describe,it,expect} from 'vitest';
import * as THREE from 'three';
import {validateMeshData,updateSkinnedGeometry}
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

describe('Batch 3D SHA-bound original USD UV image vertex data',()=>{
  const original={
    path:'/World/OriginalMesh',shape:'mesh',size_m:2,
    mesh_points:[[0,0,0],[1,0,0],[0,1,0]],
    mesh_triangles:[[0,1,2]],
    mesh_uvs:[[0,0],[1,0],[0,1]],
    source_material:{
      format:'nvp.original_usd_preview_surface.v1',
      base_color_rgb:[1,1,1],roughness:.4,metallic:0,
      original_source_modified:false,
      source_texture:{
        format:'nvp.original_png_rgb8_uv_texture.v1',
        blob_sha256:'a'.repeat(64),
        width:8,height:8,source_encoding:'sRGB',
        uv_interpolation:'vertex',
        original_source_modified:false,
        png_base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
      },
    },
  };
  it('retains exact original source UVs without a frame proxy',()=>{
    expect(validateMeshData(original).pts).toHaveLength(3);
  });
  it('rejects altered vertex UVs, invalid source image or external URI',()=>{
    expect(()=>validateMeshData({...original,
      mesh_uvs:[[0,0],[1,0],[1,2]]})).toThrow(/UV/);
    expect(()=>validateMeshData({...original,
      source_material:{...original.source_material,
        source_texture:{...original.source_material.source_texture,
          blob_sha256:'https://example.com/image.png'}}})).toThrow(/UV/);
    expect(()=>validateMeshData({...original,mesh_uvs:null})).toThrow(/UV/);
  });
});
