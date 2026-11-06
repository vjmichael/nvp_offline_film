import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import FilmTimeAssemblyPanel from './FilmTimeAssemblyPanel.jsx';

const pid='a'.repeat(32),sha='b'.repeat(64),newsha='c'.repeat(64);
const edit={
  edit_id:'director_assembly',revision:2,
  edit_document_sha256:sha,clip_count:2,duration_tick:'14112000000',
};
const clips=[
  {ordinal:0,source_id:'camera_A',source_revision:1,
   source_in_frame_zero:'10',source_out_frame_zero:'40',
   film_start_tick:'0',film_end_tick:'7056000000',
   rounding_policy:'nearest'},
  {ordinal:1,source_id:'camera_B',source_revision:1,
   source_in_frame_zero:'30',source_out_frame_zero:'60',
   film_start_tick:'7056000000',film_end_tick:'14112000000',
   rounding_policy:'nearest'},
];
const available=[edit,{
  edit_id:'source_camera_C',revision:1,
  edit_document_sha256:'d'.repeat(64),clip_count:1,
  duration_tick:'7056000000',
}];
const plan={
  format:'nvp.index_time07.assembly_plan.v1',
  project_id:pid,edit_id:edit.edit_id,
  source_revision:2,source_document_sha256:sha,
  next_revision:3,clip_count:2,duration_tick:'14112000000',
  original_sources_modified:false,approved_final_master:false,
  plan_sha256:'f'.repeat(64),
  placements:[
    {ordinal:0,source_id:'camera_B',source_in_frame_zero:'30',
     source_out_frame_zero:'60',film_start_tick:'0',rounding_policy:'nearest'},
    {ordinal:1,source_id:'camera_A',source_in_frame_zero:'10',
     source_out_frame_zero:'40',film_start_tick:'7056000000',
     rounding_policy:'nearest'},
  ],
};
const save={
  format:plan.format,status:'SAVED_NEW_EDIT_REVISION',
  project_id:pid,edit_id:edit.edit_id,
  revision:3,edit_document_sha256:newsha,
  original_sources_modified:false,
  previous_revision_preserved:true,
  approved_final_master:false,
};
function fixture(){
  return {
    preview_footage_assembly:vi.fn(async()=>plan),
    save_footage_assembly:vi.fn(async()=>save),
  };
}
function setup(native=fixture(),saved=vi.fn()){
  render(<FilmTimeAssemblyPanel
    projectId={pid} edit={edit} clips={clips} edits={available}
    native={native} onSaved={saved}/>);
  return {native,saved};
}

describe('INDEX-TIME-07 human-first immutable source assembly',()=>{
  it('previews a move and asks native OS confirmation only on save',async()=>{
    const {native,saved}=setup();
    fireEvent.change(screen.getByLabelText('Assembly clip'),
      {target:{value:'1'}});
    fireEvent.click(screen.getByText('Move earlier'));
    expect(await screen.findByText(/Proposed new assembly/)).toBeTruthy();
    expect(native.preview_footage_assembly).toHaveBeenCalledWith({
      project_id:pid,edit_id:edit.edit_id,edit_revision:2,
      edit_document_sha256:sha,change:{
        operation:'move',index:1,target:0,
      },
    });
    expect(native.save_footage_assembly).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Save new edit revision…'));
    await waitFor(()=>expect(saved).toHaveBeenCalledWith(edit.edit_id,3));
    expect(native.save_footage_assembly).toHaveBeenCalledWith({
      project_id:pid,edit_id:edit.edit_id,edit_revision:2,
      edit_document_sha256:sha,change:{
        operation:'move',index:1,target:0,
      },
      plan_sha256:'f'.repeat(64),
    });
  });

  it('discards metadata preview without publishing any edit',async()=>{
    const {native}=setup();
    fireEvent.click(screen.getByText('Duplicate placement'));
    expect(await screen.findByText(/Proposed new assembly/)).toBeTruthy();
    fireEvent.click(screen.getByText('Discard proposed change'));
    expect(screen.queryByText(/Proposed new assembly/)).toBeNull();
    expect(native.save_footage_assembly).not.toHaveBeenCalled();
  });

  it('sends decimal original frame trim and gap, not rounded JS numbers',async()=>{
    const {native}=setup();
    fireEvent.change(screen.getByLabelText('Trim source in'),
      {target:{value:'9007199254740993'}});
    fireEvent.change(screen.getByLabelText('Trim source out'),
      {target:{value:'9007199254741010'}});
    fireEvent.click(screen.getByText('Preview trim'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'trim',index:0,
      source_in_frame_zero:'9007199254740993',
      source_out_frame_zero:'9007199254741010',
    });
  });

  it('inserts a source clip reference from another saved edit',async()=>{
    const {native}=setup();
    fireEvent.change(screen.getByLabelText('Insert from indexed edit'),
      {target:{value:'source_camera_C'}});
    fireEvent.change(screen.getByLabelText('Insert source ordinal'),
      {target:{value:'0'}});
    fireEvent.change(screen.getByLabelText('Assembly insert slot'),
      {target:{value:'2'}});
    fireEvent.click(screen.getByText('Preview insert from source edit'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'insert',target:2,
      source_edit_id:'source_camera_C',source_edit_revision:1,
      source_edit_sha256:'d'.repeat(64),source_ordinal:0,
    });
  });

  it('refuses mismatched plan provenance before enabling native save',async()=>{
    const native=fixture();
    native.preview_footage_assembly.mockResolvedValue({
      ...plan,source_document_sha256:'0'.repeat(64),
    });
    setup(native);
    fireEvent.click(screen.getByText('Duplicate placement'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('source assembly changed'));
    expect(screen.queryByText('Save new edit revision…')).toBeNull();
  });

  it('marks a native approval denial as an unchanged current version',async()=>{
    const native=fixture();
    native.save_footage_assembly.mockResolvedValue({
      format:plan.format,status:'DENIED',
      original_sources_modified:false,
    });
    setup(native);
    fireEvent.click(screen.getByText('Duplicate placement'));
    await screen.findByText(/Proposed new assembly/);
    fireEvent.click(screen.getByText('Save new edit revision…'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('not approved'));
  });

  it('restores previous immutable revision through a NEW revision',async()=>{
    const {native}=setup();
    fireEvent.click(screen.getByText(
      'Restore previous arrangement as a new revision'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'restore',from_revision:1,
    });
  });
});
