import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import DirectorCameraActorContinuity from './DirectorCameraActorContinuity.jsx';

const pid='a'.repeat(32);
const movie={id:pid,encrypted:false};
const nativeSources=()=>({
  camfx03_camera_sources:vi.fn(async()=>({
    format:'nvp.conv06.original_camera_bank_sources.v1',
    project_id:pid,actor_take_pcm_modified:false,
    unapproved_source_only:true,sources:[]})),
  camfx03_draft_catalog:vi.fn(async()=>({
    format:'nvp.cam_fx03.original_camera_draft_catalog.v1',
    project_id:pid,drafts:[]})),
  film03_actor_catalog:vi.fn(async()=>({
    format:'nvp.conv06.story_bible_actorid_catalog.v1',
    project_id:pid,actors:[]})),
  film02md_architecture_catalog:vi.fn(async()=>({
    format:'nvp.conv06.original_architecture_source_catalog.v1',
    project_id:pid,native_source_reopened:true,
    actual_cycles_accepted:false,original_take_or_pcm_modified:false,
    buildings:[{building_id:'OriginalBuilding',revision:1,
      document_sha256:'b'.repeat(64),original_mesh_count:11}],
    cell_worlds:[{cell_world_id:'SavedCellWorld',revision:1,
      document_sha256:'c'.repeat(64),cell_ids:['CellEast','CellWest']}] })),
  film01c_texture_catalog:vi.fn(async()=>({
    format:'nvp.conv06.original_texture_metadata_catalog.v1',
    project_id:pid,original_png_bytes_exposed:false,
    external_texture_paths_allowed:false,
    sources:[{source_kind:'asset',source_id:'OriginalTextureAsset',
      revision:1,document_sha256:'d'.repeat(64),
      png_sha256:['e'.repeat(64)]}],
    original_uv_meshes:[{
      asset_id:'SourceMappedMesh',revision:1,
      document_sha256:'f'.repeat(64)}]})),
  data_av_import_original_mesh_texture:vi.fn(async()=>({
    format:'nvp.wo2.native_original_texture_import.v1',
    status:'ORIGINAL_SOURCE_TEXTURE_BOUND',
    asset_id:'SourceMappedMesh',source_revision:1,
    source_asset_sha256:'f'.repeat(64),
    original_png_sha256:'9'.repeat(64),
    native_source_reopened:true,original_modified:false,
    film_master_approved:false})),
  film02md_publish_cells:vi.fn(async()=>{throw Error('Only native creator confirmation');})
});

afterEach(()=>{
  cleanup();
  delete window.pywebview;
});

describe('CONV-06 original source environment inventory on one trusted desktop',()=>{
  it('displays source IDs and evidence without exposing PNG bytes or publishing cells',async()=>{
    const native=nativeSources();
    window.pywebview={api:native};
    render(<DirectorCameraActorContinuity movie={movie}/>);
    fireEvent.click(screen.getByText(/Advanced direction: camera drafts/));
    fireEvent.click(screen.getByText('Advanced: original architecture and image sources'));
    await waitFor(()=>expect(native.film02md_architecture_catalog).toHaveBeenCalledWith(pid));
    await screen.findByText(/OriginalBuilding · revision 1 · 11 reopened source meshes/);
    expect(screen.getByText(/SavedCellWorld · 2 original cells/)).toBeTruthy();
    expect(screen.getByText(/OriginalTextureAsset · 1 source-verified images/)).toBeTruthy();
    expect(native.film02md_publish_cells).not.toHaveBeenCalled();
    expect(screen.queryByText('e'.repeat(64))).toBeNull();
  });

  it('uses only selected original asset identity for the native PNG picker',async()=>{
    const native=nativeSources();
    window.pywebview={api:native};
    render(<DirectorCameraActorContinuity movie={movie}/>);
    fireEvent.click(screen.getByText(/Advanced direction: camera drafts/));
    fireEvent.click(screen.getByText('Advanced: original architecture and image sources'));
    await screen.findByText(/SourceMappedMesh — revision 1/);
    fireEvent.click(screen.getByText('Choose PNG and confirm in native window'));
    await waitFor(()=>expect(native.data_av_import_original_mesh_texture)
      .toHaveBeenCalledWith({
        project_id:pid,asset_id:'SourceMappedMesh',source_revision:1,
        source_document_sha256:'f'.repeat(64)}));
    const request=native.data_av_import_original_mesh_texture.mock.calls[0][0];
    expect(Object.keys(request).sort()).toEqual([
      'asset_id','project_id','source_document_sha256','source_revision']);
    expect(request).not.toHaveProperty('file');
    expect(request).not.toHaveProperty('approved');
    await screen.findByText(/Native-approved original image saved/);
    expect(native.film01c_texture_catalog.mock.calls.length).toBeGreaterThan(1);
  });

  it('rejects cross-project or fake Cycles approval metadata',async()=>{
    const native=nativeSources();
    native.film02md_architecture_catalog.mockResolvedValueOnce({
      format:'nvp.conv06.original_architecture_source_catalog.v1',
      project_id:'other-movie',actual_cycles_accepted:true,
      original_take_or_pcm_modified:false,buildings:[],cell_worlds:[]});
    window.pywebview={api:native};
    render(<DirectorCameraActorContinuity movie={movie}/>);
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toMatch(/native custody mismatch/i);
    expect(native.film02md_publish_cells).not.toHaveBeenCalled();
  });

  it('denies native source requests while the movie is protected',()=>{
    const native=nativeSources();
    window.pywebview={api:native};
    const {container}=render(
      <DirectorCameraActorContinuity movie={{...movie,encrypted:true}}/>);
    expect(container.textContent).toBe('');
    expect(native.film02md_architecture_catalog).not.toHaveBeenCalled();
    expect(native.film01c_texture_catalog).not.toHaveBeenCalled();
  });
});
