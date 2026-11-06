import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmTimeIndexPanel,{filmTimeClock} from './FilmTimeIndexPanel.jsx';

const pid='a'.repeat(32);
const sha='b'.repeat(64);
const exact='9007199254741137'; // Above Number.MAX_SAFE_INTEGER.
const model={
  format:'nvp.index_time05.editor_source_read.v1',
  project_id:pid,
  edits:[{
    edit_id:'imported_cut',revision:1,edit_document_sha256:sha,
    clip_count:2,duration_tick:'9007199254749999',
  }],
  worker_started:false,original_media_read:false,truncated:false,
};
const page={
  format:model.format,status:'INDEXED_EDIT_CLIPS',project_id:pid,
  edit_id:'imported_cut',edit_revision:1,edit_document_sha256:sha,
  clip_count:2,duration_tick:model.edits[0].duration_tick,
  clips:[{
    ordinal:0,source_id:'original_camera',source_revision:1,
    source_document_sha256:'c'.repeat(64),
    film_start_tick:exact,film_end_tick:'9007199254743000',
    source_in_frame_zero:'49000000000000010',
    source_out_frame_zero:'49000000000000050',
    source_in_pts:'120000000000010',source_out_pts:'120000000001000',
  }],
  next_after_ordinal:0,original_media_read:false,
};
const frame={
  format:model.format,status:'INDEXED_SOURCE_FRAME_SELECTED',
  project_id:pid,edit_id:'imported_cut',edit_revision:1,
  edit_document_sha256:sha,requested_film_tick:exact,
  clip_ordinal:0,source_id:'original_camera',source_frame_zero:'49000000000000010',
  source_pts:'120000000000010',
  frame_film_start_tick:exact,frame_film_end_tick:'9007199254741200',
  frame_index_pts_reads:18,
  original_source_path_disclosed:false,
  native_worker_started:false,film_master_approved:false,
};
const endpoint=vi.fn(async url=>{
  if(url.endsWith('/film-time/edits'))return model;
  if(url.includes('/clips?'))return page;
  if(url.includes('/seek?'))return frame;
  throw new Error('unexpected endpoint '+url);
});

describe('INDEX-TIME-05 native source editor',()=>{
  it('shows a human clock derived from exact integer Film Time',()=>{
    expect(filmTimeClock('0')).toBe('00:00:00.000');
    expect(filmTimeClock('7056000000')).toBe('00:00:01.000');
    expect(filmTimeClock('35280000000')).toBe('00:00:05.000');
    expect(filmTimeClock(exact)).toContain(':');
  });

  it('browses genuine versioned clips without requesting a decoder',async()=>{
    endpoint.mockClear();
    render(<FilmTimeIndexPanel projectId={pid} api={endpoint}/>);
    expect(await screen.findByText(/Clip 1 · original_camera/)).toBeTruthy();
    expect(screen.getByText(/Original frame ordinals/)).toBeTruthy();
    expect(screen.getByText(/not final-media approval/)).toBeTruthy();
    expect(endpoint.mock.calls.some(([url])=>url.includes('/seek?'))).toBe(false);
    expect(screen.queryByText('Render approved film')).toBeNull();
  });

  it('preserves exact >53-bit Film Time ticks and original source PTS',async()=>{
    endpoint.mockClear();
    render(<FilmTimeIndexPanel projectId={pid} api={endpoint}/>);
    const button=await screen.findByText('Inspect clip beginning');
    fireEvent.click(button);
    await waitFor(()=>expect(endpoint.mock.calls.some(([url])=>
      url.includes('tick='+exact))).toBe(true));
    expect(await screen.findByText(/original_camera · frame 49000000000000010/))
      .toBeTruthy();
    expect(screen.getByLabelText('Selected original indexed frame').textContent)
      .toContain('120000000000010');
  });

  it('surfaces an intentional imported-video gap as empty, not a fake frame',async()=>{
    const api=vi.fn(async url=>{
      if(url.endsWith('/film-time/edits'))return model;
      if(url.includes('/clips?'))return page;
      if(url.includes('/seek?'))return {
        ...frame,status:'EMPTY_IMPORTED_VIDEO_GAP',
        requested_film_tick:'0',source_frame_zero:null,clip_ordinal:null,
      };
      throw new Error('unknown');
    });
    render(<FilmTimeIndexPanel projectId={pid} api={api}/>);
    await screen.findByText(/Clip 1 · original_camera/);
    fireEvent.change(screen.getByLabelText('Indexed Film Time tick'),
      {target:{value:'0'}});
    fireEvent.click(screen.getByText('Seek indexed source'));
    expect(await screen.findByText(/This is an intentional gap/)).toBeTruthy();
    expect(screen.queryByLabelText('Selected original indexed frame')).toBeNull();
  });

  it('denies invalid or beyond-bound tick input before asking native source index',async()=>{
    const api=vi.fn(async url=>{
      if(url.endsWith('/film-time/edits'))return model;
      if(url.includes('/clips?'))return page;
      throw new Error('unexpected seek');
    });
    render(<FilmTimeIndexPanel projectId={pid} api={api}/>);
    await screen.findByText(/Clip 1 · original_camera/);
    fireEvent.change(screen.getByLabelText('Indexed Film Time tick'),
      {target:{value:'9007199254750000'}});
    fireEvent.click(screen.getByText('Seek indexed source'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('beyond the indexed edit duration'));
    expect(api.mock.calls.some(([url])=>url.includes('/seek?'))).toBe(false);
  });

  it('rejects mismatched source SHA before showing a result',async()=>{
    const api=vi.fn(async url=>{
      if(url.endsWith('/film-time/edits'))return model;
      if(url.includes('/clips?'))return page;
      if(url.includes('/seek?'))return {...frame,
        edit_document_sha256:'f'.repeat(64)};
      throw new Error('unexpected');
    });
    render(<FilmTimeIndexPanel projectId={pid} api={api}/>);
    fireEvent.click(await screen.findByText('Inspect clip beginning'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('stale or unauthorized'));
    expect(screen.queryByLabelText('Selected original indexed frame')).toBeNull();
  });
});
