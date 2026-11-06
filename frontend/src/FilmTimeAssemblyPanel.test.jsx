import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import FilmTimeAssemblyPanel from './FilmTimeAssemblyPanel.jsx';
import {filmTimeClock,clockToFilmTick} from './filmTimeClock.js';

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
  it('converts readable gap times exactly without lossy JavaScript Number',()=>{
    expect(clockToFilmTick('00:00:01.000')).toBe('7056000000');
    expect(clockToFilmTick('00:00:00.001')).toBe('7056000');
    expect(clockToFilmTick('123:45:06.789')).toBe(
      ((123n*3600n+45n*60n+6n)*7056000000n+
       789n*7056000n).toString());
    const huge='9007199254740993';
    expect(filmTimeClock(huge)).toContain(':');
    expect(()=>clockToFilmTick('00:00:60.000')).toThrow();
    expect(()=>clockToFilmTick('10:00:00.1000')).toThrow();
    expect(()=>clockToFilmTick('999999:00:00.000')).toThrow();
  });

  it('previews one-second time gap as exact native source ticks',async()=>{
    const {native}=setup();
    fireEvent.change(screen.getByLabelText('Gap time clock'),
      {target:{value:'00:00:01.000'}});
    fireEvent.click(screen.getByText('Preview gap by clock'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'set_gap',index:0,gap_before_tick:'7056000000',
    });
  });


  it('selects a source strip placement and inspects that exact Film Time start',async()=>{
    const native=fixture();
    const inspect=vi.fn();
    render(<FilmTimeAssemblyPanel
      projectId={pid} edit={edit} clips={clips} edits={available}
      native={native} onSaved={vi.fn()} onInspect={inspect}/>);
    fireEvent.click(screen.getByLabelText('Select source clip 2'));
    expect(screen.getByLabelText('Select source clip 2').getAttribute('aria-pressed'))
      .toBe('true');
    fireEvent.click(screen.getByText('Inspect clip start'));
    expect(inspect).toHaveBeenCalledWith('7056000000');
    expect(native.preview_footage_assembly).not.toHaveBeenCalled();
    expect(native.save_footage_assembly).not.toHaveBeenCalled();
  });

  it('splits at the exact real source frame selected on the film playhead',async()=>{
    const native=fixture();
    const selected={
      status:'INDEXED_SOURCE_FRAME_SELECTED',
      clip_ordinal:0,source_id:'camera_A',source_revision:1,
      source_frame_zero:'25',source_pts:'54321',
      edit_document_sha256:sha,
    };
    render(<FilmTimeAssemblyPanel
      projectId={pid} edit={edit} clips={clips} edits={available}
      native={native} onSaved={vi.fn()}
      selectedFrame={selected}/>);
    fireEvent.click(screen.getByText('Split at selected playhead frame'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'split',index:0,source_frame_zero:'25',
    });
    expect(native.save_footage_assembly).not.toHaveBeenCalled();
  });

  it('splits one original into two adjacent references, not physical copies',async()=>{
    const {native}=setup();
    fireEvent.change(screen.getByLabelText('Split source at frame'),
      {target:{value:'25'}});
    fireEvent.click(screen.getByText('Split clip at source frame'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'split',index:0,source_frame_zero:'25',
    });
    expect(native.save_footage_assembly).not.toHaveBeenCalled();
  });

  it('refuses incomplete 65-clip assembly until all pages are source-bound',async()=>{
    const longEdit={...edit,clip_count:65};
    const all=Array.from({length:65},(_,i)=>({
      ordinal:i,source_id:'source_camera',source_revision:1,
      source_in_frame_zero:'10',source_out_frame_zero:'40',
      film_start_tick:(BigInt(i)*7056000000n).toString(),
      film_end_tick:(BigInt(i+1)*7056000000n).toString(),
      rounding_policy:'nearest',
    }));
    let release;
    const gate=new Promise(resolve=>{release=resolve;});
    const api=vi.fn(async url=>{
      const after=new URL('http://localhost'+url).searchParams.get('after_ordinal');
      if(after==='-1')return {
        format:'nvp.index_time05.editor_source_read.v1',
        status:'INDEXED_EDIT_CLIPS',
        project_id:pid,edit_id:edit.edit_id,edit_revision:2,
        edit_document_sha256:sha,clip_count:65,original_media_read:false,
        clips:all.slice(0,40),next_after_ordinal:39,
      };
      await gate;
      return {
        format:'nvp.index_time05.editor_source_read.v1',
        status:'INDEXED_EDIT_CLIPS',
        project_id:pid,edit_id:edit.edit_id,edit_revision:2,
        edit_document_sha256:sha,clip_count:65,original_media_read:false,
        clips:all.slice(40),next_after_ordinal:null,
      };
    });
    const native=fixture();
    render(<FilmTimeAssemblyPanel
      projectId={pid} edit={longEdit} clips={all.slice(0,40)}
      edits={available} native={native} api={api} onSaved={vi.fn()}/>);
    await waitFor(()=>expect(api).toHaveBeenCalled());
    // The staged async page may not have mounted its disabled controls
    // yet. No edit may be launched while the remainder is unverified.
    const pendingMove=screen.queryByText('Move later');
    expect(pendingMove===null||pendingMove.disabled).toBe(true);
    release();
    await waitFor(()=>expect(screen.getByText('Move later').disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Assembly clip'),
      {target:{value:'64'}});
    fireEvent.click(screen.getByText('Split clip at source frame'));
    await screen.findByText(/Proposed new assembly/);
    expect(native.preview_footage_assembly.mock.calls[0][0].change).toEqual({
      operation:'split',index:64,source_frame_zero:'25',
    });
    expect(api).toHaveBeenCalledTimes(2);
  });

  it('fails closed on mismatched second page rather than editing hidden clips',async()=>{
    const large={...edit,clip_count:45};
    const initial=Array.from({length:40},(_,i)=>({
      ...clips[0],ordinal:i,
      film_start_tick:(BigInt(i)*7056000000n).toString(),
      film_end_tick:(BigInt(i+1)*7056000000n).toString(),
    }));
    const api=vi.fn(async url=>({
      format:'nvp.index_time05.editor_source_read.v1',
      status:'INDEXED_EDIT_CLIPS',project_id:pid,
      edit_id:edit.edit_id,edit_revision:2,
      edit_document_sha256:'0'.repeat(64),
      clip_count:45,original_media_read:false,
      clips:initial,next_after_ordinal:39,
    }));
    const native=fixture();
    render(<FilmTimeAssemblyPanel
      projectId={pid} edit={large} clips={initial}
      edits={available} native={native} api={api} onSaved={vi.fn()}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('stale'));
    // Failed source-page custody may hide controls altogether rather
    // than mounting disabled controls; both must fail closed.
    const placement=screen.queryByText('Duplicate placement');
    expect(placement===null||placement.disabled).toBe(true);
    expect(native.preview_footage_assembly).not.toHaveBeenCalled();
  });

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
