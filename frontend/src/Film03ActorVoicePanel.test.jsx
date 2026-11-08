// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Film03ActorVoicePanel from './Film03ActorVoicePanel.jsx';

const pid='a'.repeat(32), actorId='b'.repeat(32), sha='c'.repeat(64);
const project={id:pid,revision:1};
const source={family:'filmindex',kind:'audio',
  target_id:'DonutOriginalReference',target_revision:1,
  sha256:sha,sample_count:48000};
const catalog={sources:[source]};
const candidate={
  performance_id:'DonutRecordedLine',
  source_audio_id:'DonutOriginalReference',
  source_audio_revision:1,source_audio_sha256:sha,
  source_sample_count:48000,
  script_line_text:'The relay is silent.',
  latest_approval_revision:0,approved_voice_id:null,
};
const candidates={
  format:'nvp.film03.voice_candidate_audition_catalog.v1',
  project_id:pid,actor_id:actorId,candidates:[candidate],
};
const originalNative=window.pywebview;

function mount({current=null,native={}}={}) {
  window.pywebview={api:native};
  const onUpdated=vi.fn(async()=>{});
  const api=vi.fn(async(url,method)=>{
    if(method)throw new Error('No trusted VoiceID action may use HTTP');
    if(url.endsWith('/voice-candidates'))return candidates;
    throw new Error('Unexpected '+url);
  });
  const result=render(<Film03ActorVoicePanel
    project={project} actorId={actorId}
    detail={{actor_id:actorId,bible_revision:1,
      current_voice_identity:current,
      immutable_voice_cast_history:current?[current]:[]}}
    catalog={catalog} api={api}
    action={async fn=>fn()} busy={false} onUpdated={onUpdated}/>);
  return {...result,api,onUpdated};
}

describe('FILM03-04 ActorID immutable character voice and director review',()=>{
  afterEach(()=>{cleanup();vi.restoreAllMocks();window.pywebview=originalNative;});

  it('never accepts browser HTTP or voice AI as a director voice cast',async()=>{
    const mounted=mount();
    await waitFor(()=>expect(mounted.api).toHaveBeenCalled());
    expect(screen.getByText(/This actor has no approved VoiceID/)).toBeTruthy();
    expect(screen.getByRole('button',{name:/Enroll first ActorID VoiceID/}).disabled)
      .toBe(true);
    expect(screen.getByRole('button',{name:/Approve this VoiceID for the exact recorded Take/}).disabled)
      .toBe(true);
    expect(mounted.api.mock.calls.every(([,method])=>!method)).toBe(true);
  });

  it('auditions SHA-matched source then requires deliberate director native VoiceID enrollment',async()=>{
    const sample=vi.fn(async request=>({
      format:'nvp.film03.original_actor_voice_audition.v1',
      source_audio_id:request.source_audio_id,
      source_audio_revision:request.source_audio_revision,
      source_audio_sha256:sha,original_recording_not_tts:true,
      audition_not_voice_identity_approval:true,
      wav_data_base64:'UklGRgAAAAA=',
    }));
    const cast=vi.fn(async request=>({
      format:'nvp.film03.production_bible_voice_identity.v1',
      actor_id:actorId,
      current:{voice_id:request.voice_id,cast_revision:1},
      host_native_director_confirmation:true,
      source_voice_performance_generated:false,audio_take_overwritten:false,
    }));
    const mounted=mount({native:{
      film03_audition_original_voice:sample,
      film03_cast_actor_voice:cast,
    }});
    await waitFor(()=>expect(screen.getByLabelText('Voice reference recording').value)
      .toContain('DonutOriginalReference'));
    fireEvent.change(screen.getByLabelText('Canonical VoiceID'),{
      target:{value:'Voice_Donut_Original'}});
    fireEvent.change(screen.getByLabelText('Reference voice audition notes'),{
      target:{value:'I have reviewed the original reference recording.'}});
    expect(screen.getByRole('button',{name:/Enroll first ActorID VoiceID/}).disabled)
      .toBe(true);
    fireEvent.click(screen.getByRole('button',{
      name:/Audition this original VoiceID reference/}));
    await waitFor(()=>expect(sample).toHaveBeenCalledTimes(1));
    expect(sample.mock.calls[0][0]).toMatchObject({
      project_id:pid,source_audio_id:'DonutOriginalReference',
      source_audio_revision:1,first_sample:0,sample_count:48000,
    });
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(()=>expect(screen.getByRole('button',{
      name:/Enroll first ActorID VoiceID/}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{
      name:/Enroll first ActorID VoiceID/}));
    await waitFor(()=>expect(cast).toHaveBeenCalledTimes(1));
    expect(cast.mock.calls[0][0]).toMatchObject({
      project_id:pid,actor_id:actorId,voice_id:'Voice_Donut_Original',
      reference_audio_id:'DonutOriginalReference',
      reference_audio_revision:1,expected_cast_revision:0,
    });
    expect(mounted.onUpdated).toHaveBeenCalledTimes(1);
    expect(mounted.api.mock.calls.every(([,method])=>!method)).toBe(true);
  });

  it('requires separate reference and candidate auditions before recording approval',async()=>{
    const baseline={actor_id:actorId,cast_revision:1,
      voice_id:'Voice_Donut_Original',reference_audio_id:'DonutOriginalReference',
      reference_audio_revision:1,reference_audio_sha256:sha,
      reference_sample_count:48000};
    const sample=vi.fn(async request=>({
      format:'nvp.film03.original_actor_voice_audition.v1',
      source_audio_id:request.source_audio_id,
      source_audio_revision:request.source_audio_revision,
      source_audio_sha256:sha,original_recording_not_tts:true,
      audition_not_voice_identity_approval:true,
      wav_data_base64:'UklGRgAAAAA=',
    }));
    const approve=vi.fn(async request=>({
      format:'nvp.film03.voice_performance_review.v1',
      actor_id:actorId,voice_id:'Voice_Donut_Original',
      approval_revision:1,host_native_director_confirmation:true,
      original_recording_overwritten:false,audio_voice_model_invoked:false,
    }));
    const mounted=mount({current:baseline,native:{
      film03_audition_original_voice:sample,
      film03_approve_actor_voice_take:approve,
    }});
    await screen.findByRole('option',{name:/DonutRecordedLine/});
    fireEvent.change(screen.getByLabelText('Actor recorded dialogue Take'),{
      target:{value:'DonutRecordedLine'}});
    fireEvent.change(screen.getByLabelText(
      'Actor voice consistency comparison notes'),{
      target:{value:'I compared both approved original recordings by listening.'}});
    const accept=screen.getByRole('button',{
      name:/Approve this VoiceID for the exact recorded Take/});
    expect(accept.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{
      name:/Audition current ActorID VoiceID reference/}));
    await waitFor(()=>expect(sample).toHaveBeenCalledTimes(1));
    expect(accept.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{
      name:/Audition this exact recorded dialogue Take/}));
    await waitFor(()=>expect(sample).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(()=>expect(accept.disabled).toBe(false));
    fireEvent.click(accept);
    await waitFor(()=>expect(approve).toHaveBeenCalledTimes(1));
    expect(approve.mock.calls[0][0]).toMatchObject({
      project_id:pid,actor_id:actorId,
      performance_id:'DonutRecordedLine',
      voice_id:'Voice_Donut_Original',expected_cast_revision:1,
      expected_approval_revision:0,reference_audio_sha256:sha,
    });
    expect(mounted.onUpdated).toHaveBeenCalledTimes(1);
    expect(mounted.api.mock.calls.every(([,method])=>!method)).toBe(true);
  });
});
