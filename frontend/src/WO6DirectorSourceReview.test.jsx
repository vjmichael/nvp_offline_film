// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import WO6DirectorSourceReview from './WO6DirectorSourceReview.jsx';

const pid='a'.repeat(32), editSha='b'.repeat(64), originalSha='c'.repeat(64);
const review={
  format:'nvp.wo6_07e.exact_edited_source_pcm_review.v1',
  project_id:pid,edit_document_sha256:editSha,
  output_frame_zero:24,
  output_film_time_tick:'7056000000',
  source_film_time_tick:'7056000000',
  source_take_id:'OriginalTake',
  source_take_sha256:originalSha,
  source_review_sha256:'d'.repeat(64),
  source_projection:{segment_id:'Middle'},
  scene_poses:[
    {prim_path:'/World/Actor',role:'actor',world_translation:[1,2,3]},
    {prim_path:'/World/Camera',role:'camera',world_translation:[2,3,-8],
     native_schema:{schema:'UsdGeom.Camera'}},
    {prim_path:'/World/Light',role:'light',world_translation:[2,4,5],
     native_schema:{schema:'UsdLux.SphereLight'}},
  ],
  source_pcm_sample_rate:48000,
  source_pcm_samples:2000,
  source_pcm_tracks:[{source_id:'ActorFoley'}],
  source_pcm_omissions:[],
  audio_data_url:'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEA',
  frame_spans_edit_boundary:false,
  zero_audio_when_no_source:false,
  audio_muted_until_user_action:true,
  frame_pixels_rendered:false,screen_image_provided:false,
  frame_and_audio_continuous_24fps_verified:false,
  finished_film_mastered_audio:false,
  native_worker_authorized:false,original_source_modified:false,
};
const catalog={
  format:'nvp.wo6_07e.original_source_review_catalog.v1',
  project_id:pid,native_worker_authorized:false,
  edits:[
    {edit_id:'OriginalEdit',edit_revision:1,edit_sha256:editSha,
     duration_tick:'14112000000',segment_count:2},
    {edit_id:'OtherEdit',edit_revision:1,edit_sha256:'e'.repeat(64),
     duration_tick:'7056000000',segment_count:1},
  ],
  timelines:[
    {timeline_id:'DerivedSound',revision:1,sha256:'f'.repeat(64),event_count:2},
  ],
};
afterEach(()=>{cleanup();delete window.pywebview;vi.restoreAllMocks()});

describe('WO6-07E trusted original source frame and PCM reviewer',()=>{
  it('requests one exact original cut frame and real user-triggered PCM without invented picture playback',async()=>{
    const api={
      wo6_07e_source_review_catalog:vi.fn(async()=>catalog),
      wo6_07e_review_source_frame:vi.fn(async()=>review),
    };
    window.pywebview={api};
    const {container}=render(<WO6DirectorSourceReview projectId={pid}/>);
    await screen.findByText(/OriginalEdit · rev 1/);
    fireEvent.change(screen.getByLabelText('Recorded sound timeline'),
      {target:{value:'DerivedSound'}});
    fireEvent.change(screen.getByLabelText('Output frame at 24 fps (zero-based)'),
      {target:{value:'24'}});
    fireEvent.click(screen.getByText('Inspect exact original frame and PCM'));
    await waitFor(()=>expect(api.wo6_07e_review_source_frame).toHaveBeenCalledWith({
      project_id:pid,
      edit_id:'OriginalEdit',edit_revision:1,edit_sha256:editSha,
      frame_zero:24,
      sound_timeline_id:'DerivedSound',sound_timeline_revision:1,
      sound_timeline_sha256:'f'.repeat(64),
    }));
    expect(await screen.findByText(/Original Take SHA:/)).toBeTruthy();
    expect(screen.getByText(/OriginalTake/)).toBeTruthy();
    expect(screen.getByText(/actor \/World\/Actor/)).toBeTruthy();
    expect(screen.getByText(/camera \/World\/Camera/)).toBeTruthy();
    expect(screen.getByText(/light \/World\/Light/)).toBeTruthy();
    const audio=container.querySelector('audio');
    expect(audio).toBeTruthy();
    expect(audio.getAttribute('src')).toBe(review.audio_data_url);
    expect(audio.hasAttribute('autoplay')).toBe(false);
    expect(screen.getByText(/no picture/)).toBeTruthy();
    expect(api.wo6_07e_source_review_catalog).toHaveBeenCalledWith(pid);
    expect(Object.keys(api).some(x=>/create|execute|approve/i.test(x))).toBe(false);
  });

  it('clears stale WAV on source change and refuses to request beyond exact cut',async()=>{
    const api={
      wo6_07e_source_review_catalog:vi.fn(async()=>catalog),
      wo6_07e_review_source_frame:vi.fn(async()=>review),
    };
    window.pywebview={api};
    const {container}=render(<WO6DirectorSourceReview projectId={pid}/>);
    await screen.findByText(/OriginalEdit · rev 1/);
    fireEvent.change(screen.getByLabelText('Output frame at 24 fps (zero-based)'),
      {target:{value:'24'}});
    fireEvent.click(screen.getByText('Inspect exact original frame and PCM'));
    await screen.findByText(/Original Take SHA:/);
    expect(container.querySelector('audio')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Approved immutable editorial cut'),
      {target:{value:'OtherEdit'}});
    expect(container.querySelector('audio')).toBeNull();
    fireEvent.change(screen.getByLabelText('Output frame at 24 fps (zero-based)'),
      {target:{value:'24'}});
    fireEvent.click(screen.getByText('Inspect exact original frame and PCM'));
    await waitFor(()=>expect(screen.getByText(/Source frame exceeds/)).toBeTruthy());
    expect(api.wo6_07e_review_source_frame).toHaveBeenCalledTimes(1);
  });

  it('shows no model or browser execution fallback when installed native bridge is missing',async()=>{
    render(<WO6DirectorSourceReview projectId={pid}/>);
    expect(await screen.findByText(/requires the installed NVP native host/)).toBeTruthy();
    expect(screen.getByText('Inspect exact original frame and PCM').disabled).toBe(true);
  });
});
