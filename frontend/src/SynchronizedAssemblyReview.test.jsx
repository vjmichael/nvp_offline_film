import React from 'react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {createHash} from 'node:crypto';
import SynchronizedAssemblyReview from './SynchronizedAssemblyReview.jsx';

const FORMAT='nvp.index_time09.native_av_host.v1';
const pid='a'.repeat(32),sha='b'.repeat(64);
const edit={edit_id:'safe_original_cut',revision:3,
  edit_document_sha256:sha,clip_count:2,
  duration_tick:'21168000000'};
const clips=[
  {ordinal:0,source_id:'camera1',
   film_start_tick:'0',film_end_tick:'7056000000'},
  {ordinal:1,source_id:'camera2',
   film_start_tick:'14112000000',film_end_tick:'21168000000'},
];
const bytes=Uint8Array.from({length:512},(_,i)=>i%256);
const digest=(data)=>createHash('sha256').update(Buffer.from(data)).digest('hex');
const bytesSha=digest(bytes);
const base64=Buffer.from(bytes).toString('base64');
function native(){
  return {
    start_synchronized_av_review:vi.fn(async(req)=>({
      format:FORMAT,status:'QUEUED',ticket_id:'opaque_native_av_ticket',
      project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      requested_start_tick:req.start_tick,
      actual_start_tick:req.start_tick,
      review_duration_tick:'7056000000',
      original_modified:false,master_approved:false,
    })),
    poll_synchronized_av_review:vi.fn(async()=>({
      format:FORMAT,status:'READY',
      project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      actual_start_tick:'0',review_duration_tick:'7056000000',
      media_sha256:bytesSha,size_bytes:512,
      sample_rate:48000,channels:2,video_frames:24,
      av_drift_ms:'0',original_modified:false,master_approved:false,
    })),
    get_synchronized_av_chunk:vi.fn(async(ticket,offset)=>({
      format:FORMAT,status:'VERIFIED_CHUNK',ticket_id:ticket,
      offset,next_offset:512,total_size:512,
      sha256:bytesSha,data_base64:base64,
      original_modified:false,master_approved:false,
    })),
    stop_synchronized_av_review:vi.fn(async()=>({
      format:FORMAT,status:'CANCELLATION_REQUESTED',
      original_modified:false,master_approved:false,
    })),
  };
}
function mount(api=native(),extra={}){
  render(<SynchronizedAssemblyReview
    projectId={pid} edit={edit} clips={clips}
    native={api} onInspect={vi.fn()} {...extra}/>);
  return api;
}

beforeEach(()=>{
  vi.stubGlobal('crypto',{
    subtle:{digest:vi.fn(async(_algo,raw)=>Uint8Array.from(
      createHash('sha256').update(Buffer.from(raw)).digest()).buffer)},
  });
  const RealURL=URL;
  class TestURL extends RealURL {}
  TestURL.createObjectURL=vi.fn(()=>'blob:nvp-verified-review');
  TestURL.revokeObjectURL=vi.fn();
  vi.stubGlobal('URL',TestURL);
  Object.defineProperty(HTMLMediaElement.prototype,'pause',
    {configurable:true,value:vi.fn()});
});
afterEach(()=>vi.unstubAllGlobals());

describe('INDEX-TIME-09 synchronized unapproved A/V player',()=>{
  it('uses one verified H264/AAC media element clock, never independent picture/audio timers',async()=>{
    const api=mount();
    fireEvent.click(screen.getByText('Prepare synchronized review…'));
    const player=await screen.findByLabelText(
      'Temporary picture and synchronized sound preview');
    expect(player.tagName).toBe('VIDEO');
    expect(player.getAttribute('src')).toBe('blob:nvp-verified-review');
    expect(api.start_synchronized_av_review).toHaveBeenCalledWith({
      project_id:pid,edit_id:edit.edit_id,edit_revision:3,
      edit_document_sha256:sha,start_tick:'0',
    });
    expect(api.get_synchronized_av_chunk).toHaveBeenCalledWith(
      'opaque_native_av_ticket',0);
    expect(api.get_synchronized_av_chunk).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/source samples never modified/)).toBeTruthy();
  });

  it('sends native source cut navigation without fetching any original media',()=>{
    const api=mount();
    fireEvent.click(screen.getByText('Next cut'));
    expect(screen.getByText(/Film Time playhead/).textContent)
      .toContain('00:00:02.000');
    expect(api.start_synchronized_av_review).not.toHaveBeenCalled();
    expect(api.get_synchronized_av_chunk).not.toHaveBeenCalled();
  });

  it('rejects bad media SHA before rendering a video',async()=>{
    const api=native();
    api.poll_synchronized_av_review.mockImplementation(async()=>({
      ...await native().poll_synchronized_av_review(),
      media_sha256:'f'.repeat(64),
    }));
    mount(api);
    fireEvent.click(screen.getByText('Prepare synchronized review…'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('does not match receipt SHA'));
    expect(screen.queryByLabelText(
      'Temporary picture and synchronized sound preview')).toBeNull();
    expect(api.stop_synchronized_av_review).toHaveBeenCalledWith(
      'opaque_native_av_ticket');
  });

  it('denied native OS consent reveals no original or proxy bytes',async()=>{
    const api=native();
    api.start_synchronized_av_review.mockResolvedValue({
      format:FORMAT,status:'DENIED',
      original_modified:false,master_approved:false,
    });
    mount(api);
    fireEvent.click(screen.getByText('Prepare synchronized review…'));
    expect(await screen.findByText(/You cancelled review/)).toBeTruthy();
    expect(api.poll_synchronized_av_review).not.toHaveBeenCalled();
    expect(api.get_synchronized_av_chunk).not.toHaveBeenCalled();
  });

  it('revokes obsolete native approval when user seeks while dialog is open',async()=>{
    const api=native();
    let release;
    api.start_synchronized_av_review.mockReturnValue(new Promise(resolve=>release=resolve));
    mount(api);
    fireEvent.click(screen.getByText('Prepare synchronized review…'));
    fireEvent.click(screen.getByText('Next cut'));
    release({
      format:FORMAT,status:'QUEUED',ticket_id:'late_review',
      project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      actual_start_tick:'0',requested_start_tick:'0',
      original_modified:false,master_approved:false,
    });
    await waitFor(()=>expect(api.stop_synchronized_av_review)
      .toHaveBeenCalledWith('late_review'));
    expect(api.poll_synchronized_av_review).not.toHaveBeenCalled();
  });

  it('can continue next bounded section without changing the saved assembly',async()=>{
    const api=mount();
    fireEvent.click(screen.getByText('Prepare synchronized review…'));
    await screen.findByLabelText('Temporary picture and synchronized sound preview');
    fireEvent.click(screen.getByText('Continue from end of review'));
    expect(api.stop_synchronized_av_review).toHaveBeenCalledWith(
      'opaque_native_av_ticket');
    expect(screen.getByText(/Film Time playhead/).textContent)
      .toContain('00:00:01.000');
    expect(screen.queryByLabelText(
      'Temporary picture and synchronized sound preview')).toBeNull();
  });
});
