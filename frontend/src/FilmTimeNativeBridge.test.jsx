import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmTimeIndexPanel from './FilmTimeIndexPanel.jsx';

const project='a'.repeat(32);
const editSha='b'.repeat(64);
const sourceSha='c'.repeat(64);
const FORMAT='nvp.index_time05.editor_source_read.v1';
const EDIT={
  edit_id:'sourcecut_test',revision:1,edit_document_sha256:editSha,
  clip_count:1,duration_tick:'7056000000',
};
const list=(edits=[])=>({
  format:FORMAT,project_id:project,edits,
  truncated:false,worker_started:false,
});
const clips={
  format:FORMAT,status:'INDEXED_EDIT_CLIPS',
  project_id:project,edit_id:EDIT.edit_id,edit_revision:1,
  edit_document_sha256:editSha,clip_count:1,
  duration_tick:EDIT.duration_tick,original_media_read:false,
  next_after_ordinal:null,
  clips:[{
    ordinal:0,source_id:'footage_test',source_revision:1,
    source_document_sha256:sourceSha,
    film_start_tick:'0',film_end_tick:EDIT.duration_tick,
    source_in_frame_zero:'0',source_out_frame_zero:'24',
    source_in_pts:'24576',source_out_pts:'49152',
    rounding_policy:'nearest',
  }],
};
const selection={
  format:FORMAT,status:'INDEXED_SOURCE_FRAME_SELECTED',
  project_id:project,edit_id:EDIT.edit_id,edit_revision:1,
  edit_document_sha256:editSha,requested_film_tick:'0',
  source_id:'footage_test',source_frame_zero:'0',
  source_pts:'24576',frame_film_start_tick:'0',
  frame_film_end_tick:'294000000',frame_index_pts_reads:14,
  original_source_path_disclosed:false,
  native_worker_started:false,film_master_approved:false,
};
function apiFactory(edits=[EDIT]){
  return vi.fn(async url=>{
    if(url.endsWith('/film-time/edits'))return list(edits);
    if(url.includes('/clips?'))return clips;
    if(url.includes('/seek?'))return selection;
    throw new Error('Unexpected source route: '+url);
  });
}
function nativeFixture(){
  return {
    video_import_capabilities:vi.fn(async()=>({
      format:'nvp.index_time06.native_capability.v1',
      native_window:true,native_dialog:true,video_tools_available:true,
    })),
    pick_and_import_footage:vi.fn(async()=>({
      format:'nvp.index_time06.native_import.v1',status:'IMPORTED',
      project_id:project,source_id:'footage_test',source_revision:1,
      source_document_sha256:sourceSha,
      edit_id:EDIT.edit_id,edit_revision:1,
      edit_document_sha256:editSha,
      indexed_source_frames:'25',placed_frames:'24',
      original_modified:false,original_copied:false,
      source_hash_verified_at_import:true,
    })),
    request_source_frame_preview:vi.fn(async()=>({
      format:'nvp.index_time06.preview_ticket.v1',
      status:'QUEUED',ticket_id:'native_opaque_ticket',
      project_id:project,edit_document_sha256:editSha,
      source_tick:'0',source_frame_zero:'0',
    })),
    poll_source_frame_preview:vi.fn(async()=>({
      format:'nvp.index_time06.verified_png.v1',
      status:'READY',project_id:project,
      edit_id:EDIT.edit_id,edit_revision:1,
      edit_document_sha256:editSha,
      source_tick:'0',source_frame_zero:'0',
      source_pts:'24576',film_master_approved:false,
      original_modified:false,source_integrity:'SOURCE_STAMP_UNVERIFIED_PREVIEW',
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
    })),
    cancel_source_frame_preview:vi.fn(async()=>({
      status:'CANCELLATION_REQUESTED',
    })),
  };
}

describe('INDEX-TIME-06 installed footage import and preview',()=>{
  it('keeps all native filesystem actions unavailable in a normal browser',async()=>{
    render(<FilmTimeIndexPanel api={apiFactory([])} projectId={project}/>);
    expect(await screen.findByText(/No indexed imported-video edit/)).toBeTruthy();
    expect(screen.queryByText('Import original footage…')).toBeNull();
    expect(screen.getByText(/Browser-only mode is read-only/)).toBeTruthy();
  });

  it('imports through native OS dialog, refreshes indexed edit and never asks browser for path',async()=>{
    let present=false;
    const api=vi.fn(async url=>{
      if(url.endsWith('/film-time/edits'))return list(present?[EDIT]:[]);
      if(url.includes('/clips?'))return clips;
      throw new Error('unexpected '+url);
    });
    const native=nativeFixture();
    native.pick_and_import_footage.mockImplementation(async()=>{
      present=true;
      return {
        format:'nvp.index_time06.native_import.v1',status:'IMPORTED',
        project_id:project,source_id:'footage_test',
        source_document_sha256:sourceSha,
        edit_id:EDIT.edit_id,edit_revision:1,edit_document_sha256:editSha,
        original_modified:false,original_copied:false,
        source_hash_verified_at_import:true,
        indexed_source_frames:'25',placed_frames:'24',
      };
    });
    render(<FilmTimeIndexPanel api={api} projectId={project}
      nativeBridge={native}/>);
    const importButton=await screen.findByText('Import original footage…');
    fireEvent.click(importButton);
    expect(await screen.findByText(/Original indexed: 25 measured frames/)).toBeTruthy();
    expect(await screen.findByText(/Clip 1 · footage_test/)).toBeTruthy();
    expect(native.pick_and_import_footage).toHaveBeenCalledWith(project);
    expect(native.pick_and_import_footage.mock.calls[0].length).toBe(1);
    expect(api.mock.calls.some(([url])=>url.includes('import'))).toBe(false);
  });

  it('renders only the verified native exact PTS still and labels it unapproved',async()=>{
    const native=nativeFixture();
    render(<FilmTimeIndexPanel api={apiFactory()} projectId={project}
      nativeBridge={native}/>);
    fireEvent.click(await screen.findByText('Inspect clip beginning'));
    await screen.findByLabelText('Selected original indexed frame');
    fireEvent.click(await screen.findByText('Preview actual source frame'));
    const picture=await screen.findByAltText(
      /Independently verified unapproved frame/);
    expect(picture.getAttribute('src')).toMatch(/^data:image\/png;base64,/);
    expect(native.request_source_frame_preview).toHaveBeenCalledWith({
      project_id:project,edit_id:EDIT.edit_id,edit_revision:1,
      edit_document_sha256:editSha,source_tick:'0',
      source_frame_zero:'0',source_pts:'24576',
    });
    expect(screen.getByText(/not a final approved film frame/)).toBeTruthy();
  });

  it('refuses a native ready PNG with an unrelated source SHA',async()=>{
    const native=nativeFixture();
    native.poll_source_frame_preview.mockResolvedValue({
      ...await native.poll_source_frame_preview(),
      edit_document_sha256:'f'.repeat(64),
    });
    render(<FilmTimeIndexPanel api={apiFactory()} projectId={project}
      nativeBridge={native}/>);
    fireEvent.click(await screen.findByText('Inspect clip beginning'));
    await screen.findByLabelText('Selected original indexed frame');
    fireEvent.click(await screen.findByText('Preview actual source frame'));
    expect(await screen.findByText(/mismatched original source selection/))
      .toBeTruthy();
    expect(screen.queryByLabelText('Verified original source frame preview'))
      .toBeNull();
  });

  it('never paints a stale preview after source Film Time changes',async()=>{
    let resolve;
    const pending=new Promise(r=>{resolve=r;});
    const native=nativeFixture();
    native.request_source_frame_preview.mockReturnValue(pending);
    render(<FilmTimeIndexPanel api={apiFactory()} projectId={project}
      nativeBridge={native}/>);
    fireEvent.click(await screen.findByText('Inspect clip beginning'));
    await screen.findByLabelText('Selected original indexed frame');
    fireEvent.click(await screen.findByText('Preview actual source frame'));
    await waitFor(()=>expect(native.request_source_frame_preview).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Indexed Film Time tick'),
      {target:{value:'1'}});
    fireEvent.click(screen.getByText('Seek indexed source'));
    resolve({
      format:'nvp.index_time06.preview_ticket.v1',status:'QUEUED',
      ticket_id:'stale',project_id:project,
      edit_document_sha256:editSha,source_tick:'0',source_frame_zero:'0',
    });
    await waitFor(()=>expect(screen.queryByAltText(
      /Independently verified unapproved frame/)).toBeNull());
    expect(native.poll_source_frame_preview).not.toHaveBeenCalled();
  });
});
