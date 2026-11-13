import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,waitFor,fireEvent,cleanup} from '@testing-library/react';
import ActorSceneCastingPanel from './ActorSceneCastingPanel.jsx';

afterEach(cleanup);
const pid='a'.repeat(32),sha='b'.repeat(64);
const actors=[{actor_id:'ActorLead',display_name:'Lead'},
              {actor_id:'ActorSecond',display_name:'Second'}];
const glb={character_asset_id:'CHR_'+'c'.repeat(24),
  original_glb_sha256:sha,license:'creator_owned',
  source:'local',attribution:'Author',joint_count:3,
  vertex_count:3,joints:['Bone000','Bone001','Bone002'],
  facial_targets:['jaw_open']};
function bridge(){
  return {
    data_av_actor_asset_catalog:vi.fn(async()=>({
      format:'nvp.p1bc.native_original_character_assets.v1',
      project_id:pid,assets:[glb],unsupported:[],
      source_bytes_modified:false,
      redistribution_rights_independently_verified:false,
    })),
    data_av_actor_scene_cast:vi.fn(async request=>({
      format:'nvp.p1bc.native_actor_scene_cast_receipt.v1',
      status:'AUTHORITATIVE_ACTOR_SCENE_PUBLISHED',
      scene_id:request.scene_id,scene_revision:1,
      scene_document_sha256:'d'.repeat(64),
      imported_glb_skins:request.cast.length,
      original_sources_modified:false,picture_rendered:false,
      director_authorized:true,
    })),
  };
}
describe('P1-B original GLB actor casting desktop GUI',()=>{
  it('sends only typed ActorIDs and genuine GLB asset IDs to native approval',async()=>{
    const native=bridge(),onScenePublished=vi.fn();
    render(<ActorSceneCastingPanel projectId={pid} native={native}
      actorCatalog={actors} onScenePublished={onScenePublished}/>);
    await screen.findByText(/1 supported original GLB sources/);
    fireEvent.change(screen.getByLabelText('Cast ActorID 1'),
      {target:{value:'ActorLead'}});
    fireEvent.change(screen.getByLabelText('Imported GLB source 1'),
      {target:{value:glb.character_asset_id}});
    fireEvent.change(screen.getByLabelText('Authentic joint to animate 1'),
      {target:{value:'Bone001'}});
    fireEvent.change(screen.getByLabelText(
      'Director-authored joint X travel (metres) 1'),
      {target:{value:'0.25'}});
    fireEvent.change(screen.getByLabelText('Original GLB facial morph 1'),
      {target:{value:'jaw_open'}});
    fireEvent.change(screen.getByLabelText('Author facial strength 0..1 1'),
      {target:{value:'0.6'}});
    fireEvent.click(screen.getByText('Ask native director to publish exact 3D cast'));
    await waitFor(()=>expect(native.data_av_actor_scene_cast).toHaveBeenCalledOnce());
    const request=native.data_av_actor_scene_cast.mock.calls[0][0];
    expect(request).toEqual({
      project_id:pid,scene_id:'ActorSourceScene001',
      camera_height:8,
      cast:[{actor_id:'ActorLead',character_asset_id:glb.character_asset_id,
        position:[0,0,0],motion_joint:'Bone001',travel:.25,
        face_target:'jaw_open',face_strength:.6}],
    });
    expect(request.creator_approved).toBeUndefined();
    expect(request.glb_file).toBeUndefined();
    await waitFor(()=>expect(onScenePublished).toHaveBeenCalledOnce());
    expect(screen.getByText(/New native OpenUSD source scene/)).toBeTruthy();
  });
  it('supports multiple actors but forbids duplicate canonical ActorID',async()=>{
    const native=bridge();
    render(<ActorSceneCastingPanel projectId={pid} native={native}
      actorCatalog={actors}/>);
    await screen.findByText(/1 supported original GLB sources/);
    fireEvent.change(screen.getByLabelText('Cast ActorID 1'),
      {target:{value:'ActorLead'}});
    fireEvent.change(screen.getByLabelText('Imported GLB source 1'),
      {target:{value:glb.character_asset_id}});
    fireEvent.click(screen.getByText('Add another original actor'));
    fireEvent.change(screen.getByLabelText('Cast ActorID 2'),
      {target:{value:'ActorLead'}});
    fireEvent.change(screen.getByLabelText('Imported GLB source 2'),
      {target:{value:glb.character_asset_id}});
    fireEvent.click(screen.getByText('Ask native director to publish exact 3D cast'));
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/ActorID may occur only once/);
    expect(native.data_av_actor_scene_cast).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Cast ActorID 2'),
      {target:{value:'ActorSecond'}});
    fireEvent.click(screen.getByText('Ask native director to publish exact 3D cast'));
    await waitFor(()=>expect(native.data_av_actor_scene_cast).toHaveBeenCalledOnce());
    expect(native.data_av_actor_scene_cast.mock.calls[0][0].cast)
      .toHaveLength(2);
  });
  it('rejects a cross-project source catalog without native scene submission',async()=>{
    const native=bridge();
    native.data_av_actor_asset_catalog.mockResolvedValueOnce({
      format:'nvp.p1bc.native_original_character_assets.v1',
      project_id:'f'.repeat(32),assets:[glb],unsupported:[],
      source_bytes_modified:false,
      redistribution_rights_independently_verified:false,
    });
    render(<ActorSceneCastingPanel projectId={pid} native={native}
      actorCatalog={actors}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/not source-verified/);
    expect(screen.getByText('Ask native director to publish exact 3D cast').disabled)
      .toBe(true);
  });
  it('refuses arbitrary source positions and missing native IPC',async()=>{
    const native=bridge();
    render(<ActorSceneCastingPanel projectId={pid} native={native}
      actorCatalog={actors}/>);
    await screen.findByText(/1 supported original GLB sources/);
    fireEvent.change(screen.getByLabelText('Cast ActorID 1'),
      {target:{value:'ActorLead'}});
    fireEvent.change(screen.getByLabelText('Imported GLB source 1'),
      {target:{value:glb.character_asset_id}});
    fireEvent.change(screen.getByLabelText('Original 3D position X,Y,Z (metres) 1'),
      {target:{value:'1,2,Infinity'}});
    fireEvent.click(screen.getByText('Ask native director to publish exact 3D cast'));
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/bounded metre coordinates/);
    expect(native.data_av_actor_scene_cast).not.toHaveBeenCalled();
  });
});
