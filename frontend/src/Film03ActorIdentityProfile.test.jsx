// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Film03ActorIdentityProfile from './Film03ActorIdentityProfile.jsx';

const actorId='a'.repeat(32);
const project={id:'b'.repeat(32),revision:1};
const actorProfile={
  appearance:{
    silhouette:'Copper torus',palette:'Copper/blue',
    surface:'Brushed metal',signature_marks:'Small notch',
    visual_expression:'Tiny head-like tilt',
  },
  behavior:{
    personality_traits:'Loyal, cautious',
    habits:'Double checks',
    emotional_rules:'Short replies when worried',
    speech_style:'Slow, dry remarks',
  },
  movement:{
    gait:'Lopsided roll every third rotation',
    posture:'Slight off axis tilt',
    signature_gestures:'Wobbles gently',
    movement_peculiarities:'Off gait and weak left recovery',
  },
  voice_type:{
    voice_type_id:'VoiceType_DonutWarmLow',
    register:'Low',pitch:'Low-mid',timbre:'Warm grain',
    accent:'Neutral',cadence:'Slow',articulation:'Crisp',
    signature_quirks:'Breath before relay jargon',
  },
  voice_generation:{
    engine_id:'NvpLocalReviewedTTS',model_id:'TestModel',
    model_revision:'Revision001',engine_voice_id:'DonutVoiceEngineUnique',
    seed:123,rate:1,pitch_shift:0,stability:0.95,language:'en',
  },
  director_notes:'Original character identity from actual scene',
};
const existing={
  profile_revision:1,document_sha256:'c'.repeat(64),
  voice_id:'Voice_DonutOriginal',voice_cast_revision:1,
  profile:actorProfile,
};
const detail={
  bible_revision:7,current_identity_profile:existing,
  immutable_identity_profile_history:[existing],
  current_voice_identity:{voice_id:'Voice_DonutOriginal',
    cast_revision:1,reference_audio_sha256:'d'.repeat(64)},
};

describe('FILM03-05 ActorID character identity and pinned AI VoiceType',()=>{
  const originalPywebview=window.pywebview;
  afterEach(()=>{
    cleanup();vi.restoreAllMocks();window.pywebview=originalPywebview;
  });
  it('shows gait, behavior, appearance, VoiceType, AI model selector from one immutable ActorID',()=>{
    window.pywebview=undefined;
    render(<Film03ActorIdentityProfile project={project} actorId={actorId}
      detail={detail} action={async fn=>fn()} busy={false}
      onUpdated={vi.fn()}/>);
    expect(screen.getByText(/Voice_DonutOriginal/)).toBeTruthy();
    expect(screen.getByLabelText('Actor movement.gait').value)
      .toBe('Lopsided roll every third rotation');
    expect(screen.getByLabelText('Actor voice_type.voice_type_id').value)
      .toBe('VoiceType_DonutWarmLow');
    expect(screen.getByLabelText('Actor voice_generation.engine_voice_id').value)
      .toBe('DonutVoiceEngineUnique');
    expect(screen.getByLabelText('Actor behavior.personality_traits').value)
      .toBe('Loyal, cautious');
    expect(screen.getByRole('button',{
      name:/Publish immutable ActorID identity/}).disabled).toBe(true);
  });
  it('publishes one explicit version only using installed trusted NVP director host',async()=>{
    const author=vi.fn(async request=>({
      format:'nvp.film03.actor_identity_profile.v1',
      actor_id:actorId,
      current:{profile_revision:2},
      host_native_director_confirmation:true,
      original_actor_assets_modified:false,
      original_voice_recordings_modified:false,
      tts_or_animation_worker_invoked:false,
    }));
    window.pywebview={api:{film03_publish_actor_identity_profile:author}};
    const onUpdated=vi.fn(async()=>{});
    render(<Film03ActorIdentityProfile project={project} actorId={actorId}
      detail={detail} action={async fn=>fn()} busy={false}
      onUpdated={onUpdated}/>);
    fireEvent.change(screen.getByLabelText('Actor movement.gait'),{
      target:{value:'New deliberately uneven gait on left side'}});
    fireEvent.change(screen.getByLabelText('Actor identity approval reason'),{
      target:{value:'Director explicitly approves a revised performance gait'}});
    const publish=screen.getByRole('button',{
      name:/Publish immutable ActorID identity/});
    expect(publish.disabled).toBe(false);
    fireEvent.click(publish);
    await waitFor(()=>expect(author).toHaveBeenCalledTimes(1));
    expect(author.mock.calls[0][0]).toMatchObject({
      project_id:project.id,actor_id,
      expected_profile_revision:1,expected_bible_revision:7,
      profile:{
        movement:{gait:'New deliberately uneven gait on left side'},
        voice_type:{voice_type_id:'VoiceType_DonutWarmLow'},
        voice_generation:{engine_voice_id:'DonutVoiceEngineUnique'},
      },
    });
    await waitFor(()=>expect(onUpdated).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/previous appearance, behavior, gait and VoiceType remain in history/))
      .toBeTruthy();
  });
});
