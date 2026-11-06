import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import FilmTimePlaybackPanel from './FilmTimePlaybackPanel.jsx';

const pid='a'.repeat(32);
const sha='b'.repeat(64);
const edit={
  edit_id:'frozen_camera_cut',
  revision:3,edit_document_sha256:sha,
  clip_count:2,duration_tick:'21168000000',
};
const clips=[
  {ordinal:0,source_id:'cameraA',
   film_start_tick:'0',film_end_tick:'7056000000'},
  {ordinal:1,source_id:'cameraB',
   film_start_tick:'14112000000',film_end_tick:'21168000000'},
];
const frames=[
  {index:0,clip_ordinal:0,source_id:'cameraA',source_revision:1,
   source_frame_zero:'2',source_pts:'25000',
   film_time_tick:'0',film_end_tick:'7056000000'},
  {index:1,clip_ordinal:1,source_id:'cameraB',source_revision:1,
   source_frame_zero:'30',source_pts:'55000',
   film_time_tick:'14112000000',film_end_tick:'14406000000'},
];
function fake(){
  return {
    start_assembly_review:vi.fn(async args=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'QUEUED',ticket_id:'opaque_native_source_ticket',
      project_id:pid,edit_id:edit.edit_id,edit_revision:3,
      edit_document_sha256:sha,requested_film_tick:args.start_tick,
      planned_frames:2,ready_frames:0,
      original_modified:false,master_approved:false,
    })),
    poll_assembly_review:vi.fn(async()=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'COMPLETE',project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      original_modified:false,master_approved:false,
      planned_frames:2,ready_frames:2,frames,finished:true,
    })),
    get_assembly_review_frame:vi.fn(async(_ticket,index)=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'VERIFIED_FRAME',project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      original_modified:false,master_approved:false,
      ...frames[index],image_data_url:
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
      png_sha256:'f'.repeat(64),
    })),
    cancel_assembly_review:vi.fn(async()=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'CANCELLATION_REQUESTED',
    })),
  };
}
function view(native=fake(),props={}){
  const inspect=vi.fn();
  render(<FilmTimePlaybackPanel
    projectId={pid} edit={edit} clips={clips}
    native={native} onInspect={inspect} selection={null}
    {...props}/>);
  return {native,inspect};
}
describe('INDEX-TIME-08 safe visual source assembly transport',()=>{
  it('requests exactly bounded source-native review, never a mutation',async()=>{
    const {native}=view();
    fireEvent.click(screen.getByText('Review & play original footage…'));
    await waitFor(()=>expect(native.poll_assembly_review).toHaveBeenCalled());
    expect(native.start_assembly_review).toHaveBeenCalledWith({
      project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,start_tick:'0',
    });
    expect(await screen.findByAltText(
      'Audited temporary original-camera review frame')).toBeTruthy();
    expect(screen.getByText(/Temporary preview, not an approved film master/))
      .toBeTruthy();
    expect(native.get_assembly_review_frame).toHaveBeenCalledWith(
      'opaque_native_source_ticket',0);
    fireEvent.click(screen.getByText('Pause'));
    fireEvent.click(screen.getByText('Next frame'));
    await waitFor(()=>expect(native.get_assembly_review_frame)
      .toHaveBeenCalledWith('opaque_native_source_ticket',1));
    expect(screen.getByText(/Original cameraB/)).toBeTruthy();
  });

  it('scrubs to a cut without downloading source media or starting a worker',()=>{
    const {native,inspect}=view();
    fireEvent.click(screen.getByText('Next cut'));
    expect(screen.getByText(/Film playhead/).textContent).toContain('00:00:02.000');
    fireEvent.click(screen.getByText('Inspect playhead'));
    expect(inspect).toHaveBeenCalledWith('14112000000');
    expect(native.start_assembly_review).not.toHaveBeenCalled();
    expect(native.get_assembly_review_frame).not.toHaveBeenCalled();
  });

  it('moves the visual playhead and advances across an intentional black gap',async()=>{
    const native=fake();
    const shortFrames=[
      {...frames[0],film_end_tick:'7056000'},
      {...frames[1],film_time_tick:'705600000',
        film_end_tick:'1411200000'},
    ];
    native.poll_assembly_review.mockResolvedValue({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'COMPLETE',project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      original_modified:false,master_approved:false,
      planned_frames:2,ready_frames:2,frames:shortFrames,finished:true,
    });
    native.get_assembly_review_frame.mockImplementation(async(_token,index)=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'VERIFIED_FRAME',project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:sha,
      original_modified:false,master_approved:false,
      ...shortFrames[index],
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
    }));
    view(native);
    fireEvent.click(screen.getByText('Review & play original footage…'));
    await waitFor(()=>expect(native.get_assembly_review_frame)
      .toHaveBeenCalledWith('opaque_native_source_ticket',1),{
      timeout:2000,
    });
    expect(screen.getByText(/Film playhead/).textContent)
      .toContain('00:00:00.100');
    expect(screen.getByText(/Original cameraB/)).toBeTruthy();
  });

  it('clears a previously verified picture when the user scrubs elsewhere',async()=>{
    const {native}=view();
    fireEvent.click(screen.getByText('Review & play original footage…'));
    await screen.findByAltText('Audited temporary original-camera review frame');
    fireEvent.change(screen.getByLabelText('Scrub film assembly'),
      {target:{value:'700'}});
    expect(screen.queryByAltText(
      'Audited temporary original-camera review frame')).toBeNull();
    expect(native.cancel_assembly_review).toHaveBeenCalledWith(
      'opaque_native_source_ticket');
    expect(screen.getByText(/Film playhead/).textContent)
      .toContain('00:00:02.100');
    expect(native.start_assembly_review).toHaveBeenCalledTimes(1);
  });

  it('supports exact high precision BigInt scrub positions without Number rounding',()=>{
    const bigDuration='90071992547409931';
    const {native}=view(fake(),{edit:{...edit,duration_tick:bigDuration}});
    fireEvent.change(screen.getByLabelText('Scrub film assembly'),
      {target:{value:'500'}});
    fireEvent.click(screen.getByText('Review & play original footage…'));
    expect(native.start_assembly_review).toHaveBeenCalledWith(
      expect.objectContaining({
        start_tick:(BigInt(bigDuration)/2n).toString(),
      }));
  });

  it('never paints a stale native source or wrongly approved master',async()=>{
    const native=fake();
    native.get_assembly_review_frame.mockImplementation(async(_ticket,index)=>({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'VERIFIED_FRAME',project_id:pid,edit_id:edit.edit_id,
      edit_revision:3,edit_document_sha256:'c'.repeat(64),
      original_modified:false,master_approved:false,
      ...frames[index],image_data_url:'data:image/png;base64,TEST',
    }));
    view(native);
    fireEvent.click(screen.getByText('Review & play original footage…'));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      expect.stringContaining('receipt disagreed'));
    expect(screen.queryByAltText(
      'Audited temporary original-camera review frame')).toBeNull();
  });

  it('stops a bounded worker and discards all unapproved preview images',async()=>{
    const {native}=view();
    fireEvent.click(screen.getByText('Review & play original footage…'));
    await screen.findByAltText('Audited temporary original-camera review frame');
    fireEvent.click(screen.getByText('Stop review'));
    expect(await screen.findByText(
      /Playback stopped; your original recordings remain unchanged/)).toBeTruthy();
    expect(native.cancel_assembly_review).toHaveBeenCalledWith(
      'opaque_native_source_ticket');
    expect(screen.queryByAltText(
      'Audited temporary original-camera review frame')).toBeNull();
  });

  it('revokes a late OS approval after the playhead has moved',async()=>{
    const native=fake();
    let resume;
    const gated=new Promise(resolve=>{resume=resolve;});
    native.start_assembly_review.mockReturnValue(gated);
    view(native);
    fireEvent.click(screen.getByText('Review & play original footage…'));
    fireEvent.change(screen.getByLabelText('Scrub film assembly'),
      {target:{value:'600'}});
    resume({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'QUEUED',ticket_id:'late_approved_ticket',
      project_id:pid,edit_id:edit.edit_id,edit_revision:3,
      edit_document_sha256:sha,requested_film_tick:'0',
      planned_frames:2,ready_frames:0,
      original_modified:false,master_approved:false,
    });
    await waitFor(()=>expect(native.cancel_assembly_review)
      .toHaveBeenCalledWith('late_approved_ticket'));
    expect(native.poll_assembly_review).not.toHaveBeenCalled();
    expect(native.get_assembly_review_frame).not.toHaveBeenCalled();
  });

  it('respects a native OS rejection without revealing a frame',async()=>{
    const native=fake();
    native.start_assembly_review.mockResolvedValue({
      format:'nvp.index_time08.original_assembly_review.v1',
      status:'DENIED',original_modified:false,master_approved:false,
    });
    view(native);
    fireEvent.click(screen.getByText('Review & play original footage…'));
    expect(await screen.findByText(
      /Picture review was not approved/)).toBeTruthy();
    expect(native.poll_assembly_review).not.toHaveBeenCalled();
    expect(native.get_assembly_review_frame).not.toHaveBeenCalled();
  });
});
