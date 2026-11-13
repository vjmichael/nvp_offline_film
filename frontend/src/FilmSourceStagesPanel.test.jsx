import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import FilmSourceStagesPanel from './FilmSourceStagesPanel.jsx';

afterEach(cleanup);
const pid='a'.repeat(32),editSha='b'.repeat(64),planSha='c'.repeat(64);
const catalog={
  format:'nvp.p1def.p2.native_source_stage_catalog.v1',
  project_id:pid,source_modified:false,export_authorized:false,
  film_master_approved:false,
  edits:[{edit_id:'OriginalCut',edit_revision:1,edit_sha256:editSha,
    duration_tick:'7056000000',
    listeners:['/World/Camera'],cameras:['/World/Camera'],
    segments:[{segment_id:'SourceClip1',source_take_id:'TakeOriginal',
      source_take_sha256:'d'.repeat(64),source_shot_id:null}]}],
  original_dialogue:[{dialogue_id:'LeadLine',revision:1,
    actor_id:'ActorLead',take_id:'TakeOriginal'}],
  continuity:[{continuity_id:'ReviewedCut',revision:1,
    edit_id:'OriginalCut',edit_sha256:editSha,
    review_status:'READY_FOR_SEPARATE_EXPORT_AUTHORIZATION'}],
  actor_spatial_mixes:[{mix_id:'LeadVoiceBus',revision:1,
    mix_sha256:'e'.repeat(64),take_id:'TakeOriginal',
    take_sha256:'d'.repeat(64),listener_path:'/World/Camera',
    actor_ids:['ActorLead']}],
  longform_plans:[{plan_id:'OriginalPlan',revision:1,plan_sha256:planSha,
    source_edit_sha256:editSha,total_chunks:1,total_frames:24,longform:false}],
};
const chunk={index:0,chunk_id:'P2FilmChunk000000',first_frame:0,
  frame_count:24,source_take_id:'TakeOriginal',
  source_take_sha256:'d'.repeat(64),source_start_tick:'0',
  source_shot_sha256:null};

function bridge(){
  return {
    data_av_film_stage_catalog:vi.fn(async()=>catalog),
    data_av_film_stage_director_commit:vi.fn(async request=>({
      format:'nvp.p1d.native_director_commit_receipt.v1',
      status:'ORIGINAL_EDIT_REVIEW_COMMITTED',
      continuity_id:request.continuity_id,revision:1,
      document_sha256:'e'.repeat(64),
      original_source_modified:false,export_approved:false,
    })),
    data_av_film_stage_actor_bus_commit:vi.fn(async request=>({
      format:'nvp.p1e.native_actor_bus_receipt.v1',
      status:'SOURCE_DIALOGUE_BUS_COMMITTED',
      mix_id:request.mix_id,revision:1,
      document_sha256:'f'.repeat(64),
      original_pcm_modified:false,sound_master_approved:false,
    })),
    data_av_film_stage_longform_publish:vi.fn(async request=>({
      format:'nvp.p2.native_longform_source_plan_receipt.v1',
      status:'SOURCE_ONLY_LONGFORM_PLAN_INDEXED',
      plan_id:request.plan_id,revision:1,
      total_frames:24,total_chunks:1,
      document_sha256:planSha,
      rendered_frames:0,film_master_approved:false,
    })),
    data_av_film_stage_longform_page:vi.fn(async()=>({
      format:'nvp.p2.original_film_longform_source_schedule.v1',
      plan_sha256:planSha,start_index:0,chunks:[chunk],
      next_index:null,full_film_picture_sound_delivered:false,
    })),
    data_av_film_stage_longform_audit_page:vi.fn(async()=>({
      format:'nvp.p2.original_film_longform_source_schedule.v1',
      verified_chunks:[],missing_chunks:[chunk.chunk_id],
      full_film_master_approved:false,
    })),
    data_av_film_stage_chunk_preflight:vi.fn(async()=>({
      format:'nvp.p1f.immutable_picture_sound_chunk.v1',
      source_take_sha256:chunk.source_take_sha256,
      source_start_tick:chunk.source_start_tick,
      output_frames_generated:false,full_film_master_approved:false,
    })),
    data_av_film_stage_chunk_begin:vi.fn(async()=>({
      format:'nvp.p1f.native_source_chunk_ticket.v1',
      status:'QUEUED_NATIVE_APPROVAL',
      ticket:'ticket-original',film_master_approved:false,
    })),
    data_av_film_stage_chunk_poll:vi.fn(async()=>({
      format:'nvp.p1f.native_source_chunk_ticket.v1',
      status:'INDEPENDENT_SOURCE_CHUNK_VERIFIED_NOT_MASTER',
      film_master_approved:false,
      receipt:{status:'INDEPENDENT_SOURCE_CHUNK_VERIFIED'},
    })),
    data_av_film_stage_chunk_cancel:vi.fn(async()=>({
      format:'nvp.p1f.native_source_chunk_ticket.v1',
      status:'CANCELLATION_REQUESTED_NOT_VERIFIED',
      film_master_approved:false,
    })),
  };
}

describe('P1-D/E/F/P2 original film stages creator GUI',()=>{
  it('publishes only a source cut with every explicit continuity checkbox',async()=>{
    const native=bridge();
    render(<FilmSourceStagesPanel projectId={pid} native={native}/>);
    await screen.findByText(/Reviewed original SourceClip1/);
    fireEvent.click(screen.getByText('Ask director to save source continuity review'));
    expect((await screen.findByRole('alert')).textContent).toMatch(
      /Acknowledge the original continuity/);
    expect(native.data_av_film_stage_director_commit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText(/Reviewed original SourceClip1/));
    fireEvent.click(screen.getByText('Ask director to save source continuity review'));
    await waitFor(()=>expect(native.data_av_film_stage_director_commit)
      .toHaveBeenCalledOnce());
    const exact=native.data_av_film_stage_director_commit.mock.calls[0][0];
    expect(exact.project_id).toBe(pid);
    expect(exact.edit_id).toBe('OriginalCut');
    expect(exact.cues).toHaveLength(1);
    expect(exact.cues[0].segment_id).toBe('SourceClip1');
    expect(exact.cues[0].continuity).toBe('accepted');
    expect(exact.creator_approved).toBeUndefined();
    expect(exact.output_directory).toBeUndefined();
  });

  it('creates actor-owned original PCM route, never a browser voice generator',async()=>{
    const native=bridge();
    render(<FilmSourceStagesPanel projectId={pid} native={native}/>);
    await screen.findByText(/Reviewed original SourceClip1/);
    fireEvent.click(screen.getByText('Ask director to save original actor mix'));
    await waitFor(()=>expect(native.data_av_film_stage_actor_bus_commit)
      .toHaveBeenCalledOnce());
    const req=native.data_av_film_stage_actor_bus_commit.mock.calls[0][0];
    expect(req).toEqual({
      project_id:pid,mix_id:'OriginalActorMix001',
      take_id:'TakeOriginal',listener_path:'/World/Camera',
      routes:[{dialogue_id:'LeadLine',revision:1,gain:1}],
      expected_revision:0,
    });
    expect(req.voice_model).toBeUndefined();
    expect(req.audio_file_path).toBeUndefined();
  });

  it('opens a SHA-pinned 24-frame source page and only native-chunk approval',async()=>{
    const native=bridge();
    render(<FilmSourceStagesPanel projectId={pid} native={native}/>);
    await screen.findByText(/Reviewed original SourceClip1/);
    fireEvent.click(screen.getByText('View first source reel chunks'));
    const renderButton=await screen.findByText('Authorize and film this chunk');
    fireEvent.click(renderButton);
    await waitFor(()=>expect(native.data_av_film_stage_chunk_preflight)
      .toHaveBeenCalledOnce());
    await waitFor(()=>expect(native.data_av_film_stage_chunk_begin)
      .toHaveBeenCalledOnce());
    const req=native.data_av_film_stage_chunk_begin.mock.calls[0][0];
    expect(req.chunk_id).toBe('P2FilmChunk000000');
    expect(req.frame_count).toBe(24);
    expect(req.first_frame).toBe(0);
    expect(req.camera_path).toBe('/World/Camera');
    expect(req.actor_mix_id).toBe('LeadVoiceBus');
    expect(req.actor_mix_revision).toBe(1);
    expect(req.output_directory).toBeUndefined();
    await waitFor(()=>expect(native.data_av_film_stage_chunk_poll)
      .toHaveBeenCalled());
    expect((await screen.findByRole('status')).textContent)
      .toMatch(/film|source|picture/i);
  });

  it('rejects mismatched project inventory without any native write',async()=>{
    const native=bridge();
    native.data_av_film_stage_catalog.mockResolvedValueOnce({
      ...catalog,project_id:'f'.repeat(32),
    });
    render(<FilmSourceStagesPanel projectId={pid} native={native}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/source catalog cannot be verified/);
    expect(native.data_av_film_stage_director_commit).not.toHaveBeenCalled();
    expect(native.data_av_film_stage_chunk_begin).not.toHaveBeenCalled();
  });
});
