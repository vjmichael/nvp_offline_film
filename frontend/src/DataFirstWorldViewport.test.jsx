import {describe,it,expect} from 'vitest';
import {sourceGeometryFor} from './DataFirstWorldViewport.jsx';

const sha='a'.repeat(64);
const realActor=()=>({
  path:'/World/Actor',semantic_role:'actor',
  shape:'skinned_mesh',size_m:2,
  geometry_asset_sha256:sha,
  source_mesh_reopened:true,source_texture_pixels_exposed:false,
  source_skinning_authorized:true,source_skinning_tick:'48000',
  source_rig_binding:{
    actor_path:'/World/Actor',source_skeleton_layer_sha256:sha},
  mesh_points:[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
  mesh_triangles:[[0,1,2],[0,2,3]],
  mesh_uvs:[[0,0],[1,0],[1,1],[0,1]],
  mesh_face_uvs:null,source_color_rgb:[0.2,0.4,0.6]
});

describe('Original source-authentic USD mesh viewer',()=>{
  it('creates actual source GPU geometry from native UsdSkel and retains original UVs',()=>{
    const data=realActor();
    const geometry=sourceGeometryFor(data);
    try{
      expect(geometry.getAttribute('position').count).toBe(4);
      expect(geometry.getIndex().count).toBe(6);
      expect(geometry.getAttribute('uv').getY(2)).toBe(1);
      const next=sourceGeometryFor({...data,
        source_skinning_tick:'96000',
        mesh_points:data.mesh_points.map(p=>[p[0]+1,p[1],p[2]])});
      try{
        expect(next.getAttribute('position').getX(0)).toBe(1);
        expect(next.getAttribute('position').getX(0)).not.toBe(
          geometry.getAttribute('position').getX(0));
      }finally{next.dispose();}
    }finally{geometry.dispose();}
  });

  it('displays true face-varying USD triangles without inventing UVs',()=>{
    const data={...realActor(),shape:'mesh',
      source_skinning_authorized:false,
      source_rig_binding:null,source_skinning_tick:null,
      mesh_uvs:null,
      mesh_face_uvs:[
        [[0,0],[1,0],[1,1]],
        [[0,0],[1,1],[0,1]]
      ]};
    const geometry=sourceGeometryFor(data);
    try{
      expect(geometry.getIndex()).toBeNull();
      expect(geometry.getAttribute('position').count).toBe(6);
      expect(geometry.getAttribute('uv').count).toBe(6);
      expect(geometry.getAttribute('uv').getY(5)).toBe(1);
    }finally{geometry.dispose();}
  });

  it('rejects forged source, fake actor grant, changed skeleton SHA and triangle escape',()=>{
    const data=realActor();
    const hostile=[
      {...data,source_mesh_reopened:false},
      {...data,source_texture_pixels_exposed:true},
      {...data,source_skinning_authorized:false},
      {...data,source_rig_binding:{...data.source_rig_binding,
        source_skeleton_layer_sha256:'b'.repeat(64)}},
      {...data,geometry_asset_sha256:'file:///etc/passwd'},
      {...data,mesh_triangles:[[0,1,999]]},
      {...data,mesh_triangles:[[0,0,1]]},
      {...data,mesh_points:[[NaN,0,0],...data.mesh_points.slice(1)]},
      {...data,mesh_uvs:[[0,0]]},
      {...data,mesh_face_uvs:[[[0,0],[1,0],[1,1]]]},
    ];
    hostile.forEach(source=>expect(()=>sourceGeometryFor(source)).toThrow());
    expect(()=>sourceGeometryFor({shape:'gizmo'})).toThrow();
  });
});
