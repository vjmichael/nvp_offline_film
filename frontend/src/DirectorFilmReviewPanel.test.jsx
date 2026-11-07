// @vitest-environment jsdom
import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react';
import DirectorFilmReviewPanel,{buildSourceBoundShots} from './DirectorFilmReviewPanel.jsx';

vi.mock('./DataFirstAVPanel.jsx',()=>({
  default:({initialTakeId,initialSourceSample})=>
    <div role="region" aria-label="Real original Take playback">
      Real source A/V selected: {initialTakeId} / {initialSourceSample}
    </div>
}));

afterEach(()=>{cleanup();delete window.pywebview;vi.restoreAllMocks();});

const project='a'.repeat(32);
const sourceSha='b'.repeat(64);
const cut={assembly_id:'DirectorCut01',assembly_revision:1,
           assembly_sha256:sourceSha,end_tick:48*294000000,
           reel_count:2};
const feature={feature_id:'durable-feature-01',assembly_id:'DirectorCut01',
  assembly_revision:1,assembly_sha256:sourceSha,state:'INDEXED',production_accepted:false};

function catalog(){return{
  status:'NATIVE_PROJECT_SCOPED_READ_ONLY',project_id:project,
  assemblies:[cut],features:[feature],director_intents:[],director_reviews:[],
  full_finished_dcp_playback_verified:false
};}
function bridge(extra={}){return{
  wo5_review_catalog:vi.fn(async()=>catalog()),
  wo5_review_read_intent:vi.fn(),
  wo5_review_save_intent:vi.fn(async()=>({
    status:'DIRECTOR_INTENT_FROZEN_NOT_FILM_ACCEPTED',
    intent_id:'DirectorIntent001',production_acceptance:false
  })),
  wo5_review_inspect_feature:vi.fn(async()=>({
    status:'SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED',
    project_id:project,feature_id:feature.feature_id,
    frame_count:48,reel_count:2,seconds:2,
    ordered_picture_custody_sha256:sourceSha,
    source_reels_for_native_take_audition:[{
      reel_number:1,take_id:'FrozenRealTake01',
      take_start_tick:294000000,approved_frame_count:24,
      source_playback_only:true,finished_dcp_playback_verified:false
    }],
    production_acceptance:false,
  })),
  wo5_review_save_observations:vi.fn(),...extra
};}

describe('WO5 actual NVP director review desktop workflow',()=>{
  it('cannot authorize from an ordinary web browser',()=>{
    render(<DirectorFilmReviewPanel projectId={project}/>);
    expect(screen.getByText(/Requires the installed NVP desktop window/)).toBeTruthy();
    expect(screen.queryByText('Request native approval to freeze intent')).toBeNull();
  });

  it('builds bounded exact Film Time shots without trusting frame hashes as creative quality',()=>{
    expect(buildSourceBoundShots([{
      shot_id:'Arrival',duration_frames:43200,
      expected_action:'Person enters',expected_camera:'Wide angle',
      expected_sound:'Speech',
    }],43200)).toEqual([{
      shot_id:'Arrival',start_tick:0,end_tick:43200*294000000,
      expected_action:'Person enters',expected_camera:'Wide angle',
      expected_sound:'Speech',
    }]);
    expect(()=>buildSourceBoundShots([{
      shot_id:'Arrival',duration_frames:720,
      expected_action:'Person enters',expected_camera:'Wide angle',
      expected_sound:'Speech',
    }],43200)).toThrow(/cover the entire/);
    expect(()=>buildSourceBoundShots([{
      shot_id:'Arrival',duration_frames:43201,
      expected_action:'Person enters',expected_camera:'Wide angle',
      expected_sound:'Speech',
    }],43200)).toThrow(/past the selected/);
  });

  it('records creator-defined film intent using native method, not HTTP approvals',async()=>{
    const native=bridge();
    render(<DirectorFilmReviewPanel projectId={project} nativeBridge={native}/>);
    await screen.findByText(/Frozen assembly SHA/);
    fireEvent.click(screen.getByRole('button',{name:'Plan original film shots'}));
    fireEvent.change(screen.getByLabelText('Shot 1 Intended action'),
      {target:{value:'Actor enters scene'}});
    fireEvent.change(screen.getByLabelText('Shot 1 Intended camera'),
      {target:{value:'Wide tracking move'}});
    fireEvent.change(screen.getByLabelText('Shot 1 Intended sound'),
      {target:{value:'Footsteps and dialogue'}});
    fireEvent.click(screen.getByRole('button',{
      name:'Request native approval to freeze intent'}));
    await waitFor(()=>expect(native.wo5_review_save_intent).toHaveBeenCalledWith({
      project_id:project,assembly_id:'DirectorCut01',assembly_revision:1,
      intent_id:'DirectorIntent001',
      shots:[{shot_id:'Shot01',start_tick:0,end_tick:48*294000000,
        expected_action:'Actor enters scene',expected_camera:'Wide tracking move',
        expected_sound:'Footsteps and dialogue'}]
    }));
    expect(screen.getByText(/Original shot intention frozen in FilmIndex/)).toBeTruthy();
    expect(native.wo5_review_save_observations).not.toHaveBeenCalled();
  });

  it('links trusted indexed feature to existing real source playback and refuses DCP claim',async()=>{
    const native=bridge();
    render(<DirectorFilmReviewPanel projectId={project} nativeBridge={native}/>);
    await screen.findByText(/Frozen assembly SHA/);
    fireEvent.click(screen.getByRole('button',{
      name:'Verify original source and delivery receipts'}));
    await waitFor(()=>expect(native.wo5_review_inspect_feature)
      .toHaveBeenCalledWith(project,'durable-feature-01'));
    expect(screen.getByText(/This is not playback of the final flattened DCP/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Audition original source'}));
    expect(screen.getByRole('region',{name:'Real original Take playback'}).textContent)
      .toContain('FrozenRealTake01 / 2000');
    expect(native.wo5_review_save_observations).not.toHaveBeenCalled();
  });

  it('disables technical inspection of interrupted/unindexed productions',async()=>{
    const native=bridge({wo5_review_catalog:vi.fn(async()=>({
      ...catalog(),features:[{...feature,state:'REVIEW_REQUIRED'}]
    }))});
    render(<DirectorFilmReviewPanel projectId={project} nativeBridge={native}/>);
    await screen.findByText(/Frozen assembly SHA/);
    expect(screen.getByRole('button',{
      name:'Verify original source and delivery receipts'}).disabled).toBe(true);
    expect(screen.getByText(/Feature not indexed/i)).toBeTruthy();
    expect(native.wo5_review_inspect_feature).not.toHaveBeenCalled();
  });
});
