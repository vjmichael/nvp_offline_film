// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import ModularWorldDirector from './ModularWorldDirector.jsx';

vi.mock('./ModularWorldSourcePreview.jsx',()=>({
  default:({preview})=><div role="img" aria-label="Source-verified original USD 3D volumes">
    Original USD native geometry: {preview.instances.length} parts
  </div>,
}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});

const project='a'.repeat(32),sourceSHA='a'.repeat(64);
const worldSHA='b'.repeat(64),rootSHA='c'.repeat(64);
const build='BuildingOriginalSource';
const p1=(version=1,hidden=[])=>({
  format:'nvp.usd_film02m_f.durable_director_proposal.v1',
  project_id:project,draft_id:'ab'.repeat(12),district_id:'OriginalFilmDistrict',
  version,state:'DRAFT',base_revision:0,base_source_sha256:null,
  original_plan_sha256:hidden.length?'d'.repeat(64):sourceSHA,
  original_usd_root_sha256:hidden.length?'e'.repeat(64):rootSHA,
  undo_steps:version-1,proposed_by:'ai',
  director_approved:false,published_revision:null,published_sha256:null,
  original_actor_takes_modified:false,native_blender_workers_started:0,
});
function preview(draft){
  const hidden=draft.original_plan_sha256!==(sourceSHA);
  return {
    format:'nvp.usd_film02m_f.original_source_lowfi_preview.v1',
    proposal:draft,source_plan_sha256:draft.original_plan_sha256,
    usd_layer_root_sha256:draft.original_usd_root_sha256,
    generated_source_layer_sha256:worldSHA,
    director_override_layer_sha256:'f'.repeat(64),
    instances:[{
      instance_id:1,name:'Generated_1',building_id:build,
      position_local_m:[0,0,0],yaw_deg:0,
      source_bounds_m:[[-5,-5,-.2],[5,5,6]],
      source_building_sha256:worldSHA,
      source_mesh_count:10,
      hidden, director_placed:false}],
    diff:{
      format:'nvp.usd_film02m_f.original_layer_diff.v1',
      generated_slots:1,base_revision:0,
      generated_source_changed:true,
      added_director_opinions:hidden?[{op:'hide_generated',instance_id:1}]:[],
      removed_director_opinions:[],
      actual_source_triangles_estimated:120,
      original_film_takes_modified:false},
    native_usd_source_reopened:true,
    preview_is_source_bounds_not_cycles_pixels:true,
    source_triangles_estimated:120,
    source_prototype_count:1,verified_openusd_point_instancer:1,
    native_blender_workers_started:0,original_world_takes_modified:false,
  };
}
function nativeHost(){
  let current=p1();
  const native={
    film02mf_catalog:vi.fn(async()=>({
      format:'nvp.usd_film02m_f.native_source_catalog.v1',
      project_id:project,native_blender_workers_started:0,
      source_buildings:[{
        building_id:build,revision:1,modules:10,
        document_sha256:worldSHA,source_triangles:120}],
      approved_districts:[],drafts:[],
    })),
    film02mf_propose:vi.fn(async()=>{
      current=p1();return current;
    }),
    film02mf_reopen:vi.fn(async()=>current),
    film02mf_preview:vi.fn(async()=>preview(current)),
    film02mf_edit:vi.fn(async request=>{
      if(request.version!==current.version)throw Error('Stale original source');
      current=p1(current.version+1,[1]);return current;
    }),
    film02mf_undo:vi.fn(async()=>{
      current=p1(current.version+1,[]);return current;
    }),
    film02mf_discard:vi.fn(async()=>{
      current={...current,state:'DISCARDED',version:current.version+1};
      return current;
    }),
    film02mf_commit:vi.fn(async()=>{
      current={...current,
        format:'nvp.usd_film02m_f.original_director_approved_commit.v1',
        state:'COMMITTED',version:current.version+1,
        published_revision:1,published_sha256:worldSHA,
        original_source_plan_sha256:sourceSHA,
        original_usd_root_sha256:rootSHA,
        original_film_take_modified:false,
        native_cycles_render_started:false};
      return current;
    }),
  };
  return native;
}

describe('02M-F installed original source/world director',()=>{
  it('denies browser-only source authoring and never uses HTTP mutation',()=>{
    render(<ModularWorldDirector projectId={project} nativeBridge={null}/>);
    expect(screen.getByText(/Original world authoring is read-only here/)).toBeTruthy();
    expect(screen.queryByRole('button',{
      name:'OS director approval · publish exact world revision'})).toBeNull();
  });

  it('typed AI suggestion -> verified source preview -> reversible hide -> draft undo -> host OS commit',async()=>{
    const native=nativeHost();
    render(<ModularWorldDirector projectId={project} nativeBridge={native}/>);
    await screen.findByRole('checkbox',{name:'Use building '+build});
    await waitFor(()=>expect(screen.getByRole('checkbox',{
      name:'Use building '+build}).checked).toBe(true));
    fireEvent.change(screen.getByLabelText('Original proposal origin'),{
      target:{value:'ai'}});
    fireEvent.click(screen.getByRole('button',{
      name:'Save source-verified draft proposal (no OS approval)'}));
    await waitFor(()=>expect(native.film02mf_propose).toHaveBeenCalledTimes(1));
    expect(native.film02mf_propose.mock.calls[0][0]).toMatchObject({
      project_id:project,expected_revision:0,proposed_by:'ai',
      params:{source_buildings:[{building_id:build,revision:1}],
              seed:7,grid_cols:3,grid_rows:2}});
    await screen.findByRole('img',{name:'Source-verified original USD 3D volumes'});
    expect(screen.getByRole('button',{
      name:'OS director approval · publish exact world revision'}).disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('Generated original building instance'),{
      target:{value:'1'}});
    fireEvent.click(screen.getByRole('button',{
      name:'Hide generated original instance'}));
    await waitFor(()=>expect(native.film02mf_edit).toHaveBeenCalledTimes(1));
    expect(native.film02mf_edit.mock.calls[0][0]).toMatchObject({
      action:{op:'hide_generated',instance_id:1},version:1});
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Undo last draft change'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'Undo last draft change'}));
    await waitFor(()=>expect(native.film02mf_undo).toHaveBeenCalledTimes(1));
    expect(native.film02mf_undo.mock.calls[0][0].version).toBe(2);
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'OS director approval · publish exact world revision'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:'OS director approval · publish exact world revision'}));
    await waitFor(()=>expect(native.film02mf_commit).toHaveBeenCalledTimes(1));
    expect(native.film02mf_commit.mock.calls[0][0]).toMatchObject({
      project_id:project,version:3,
      source_plan_sha256:sourceSHA,usd_layer_root_sha256:rootSHA});
    await screen.findByText(/Native-approved original FilmIndex scene revision saved/);
    expect(native.film02mf_catalog.mock.calls.length).toBeGreaterThan(1);
  });

  it('discard never grants an OS approval and prevents stale edit/commit',async()=>{
    const native=nativeHost();
    render(<ModularWorldDirector projectId={project} nativeBridge={native}/>);
    await screen.findByRole('checkbox',{name:'Use building '+build});
    fireEvent.click(screen.getByRole('button',{
      name:'Save source-verified draft proposal (no OS approval)'}));
    await screen.findByRole('img',{name:'Source-verified original USD 3D volumes'});
    fireEvent.click(screen.getByRole('button',{name:'Discard unapproved draft'}));
    await waitFor(()=>expect(native.film02mf_discard).toHaveBeenCalledTimes(1));
    await screen.findByText(/Unapproved source proposal discarded/);
    expect(native.film02mf_commit).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{
      name:'OS director approval · publish exact world revision'})).toBeNull();
  });
});
