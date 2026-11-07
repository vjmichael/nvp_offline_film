import {describe,it,expect} from 'vitest';
import * as THREE from 'three';
import {validateMeshData,updateSkinnedGeometry}
  from './DataFirstWorldViewport.jsx';

const actor={
  path:'/World/Actor',shape:'skinned_mesh',source_skinning:true,
  source_skinning_tick:'7056000000',
  size_m:2,source_color_rgb:[0.35,0.55,0.82],
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
