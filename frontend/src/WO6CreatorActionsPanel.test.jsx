// @vitest-environment jsdom
import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import WO6CreatorActionsPanel from './WO6CreatorActionsPanel.jsx';

const pid='a'.repeat(32);
const sceneSha='b'.repeat(64);
const timelineSha='c'.repeat(64);
const takeSha='d'.repeat(64);
const previewSha='e'.repeat(64);
const soundSha='f'.repeat(64);
const slateSha='9'.repeat(64);
const typedSha='8'.repeat(64);
const catalog={
  format:'nvp.wo6.director_desktop_native_consent.v1',
  project_id:pid,model_execute_enabled:false,
  finished_film_accepted:false,approvals_preissued:false,
  scenes:[{id:'SceneA',kind:'scene',revision:1,sha256:sceneSha,
    data:{format:'nvp.scene.openusd.composition.v1',
      prim_roles:{'/World/Actor':'actor','/World/Camera':'camera',
        '/World/Light':'light'}}}],
  timelines:[{id:'TimelineA',kind:'temporal',revision:1,
    sha256:timelineSha,data:{duration_tick:7056000000*3}}],
  takes:[{id:'TakeA',kind:'take',revision:1,sha256:takeSha,
    data:{scene_id:'SceneA',scene_revision:1,
      scene_document_sha256:sceneSha,
      timeline_id:'TimelineA',timeline_revision:1,
      timeline_document_sha256:timelineSha}}],
  grades:[],
  audio_sources:[{id:'OriginalPCM',kind:'audio',revision:1,
    sha256:soundSha,data:{format:'nvp.data_av.recorded_pcm.v1',
      sample_count:48000}}],
  slate_graphs:[{id:'SlateA',kind:'presentation',revision:1,
    sha256:slateSha,data:{format:'nvp.slate.branch_graph.v1',
      nodes:[{branch_id:'root_take',take_id:'TakeA',
        take_document_sha256:takeSha,
        source_start_tick:0,source_end_tick:2*7056000000}]}}],
};
const impact={
  status:'READ_ONLY_IMPACT_PREVIEW_NO_CREATOR_GRANT',
  indexed_downstream_truncated:false,preview_sha256:previewSha,
  approval_not_granted:true,
};

function native(overrides={}){
  const api={
    wo6_source_catalog:vi.fn(async()=>catalog),
    wo6_source_impact:vi.fn(async()=>impact),
    wo6_preview_typed_decision:vi.fn(async()=>({
      status:'READ_ONLY_TYPED_DECISION_NO_GRANT',
      typed_preview_sha256:typedSha,
      creative_approval_granted:false,
      native_worker_authorized:false,
      rendered_sound:false,
    })),
    wo6_create_take:vi.fn(async()=>({
      format:'nvp.wo6.director_desktop_native_consent.v1',
      queued_task_id:'wo6take_'+'1'.repeat(24),
      executed_task_id:'wo6take_'+'1'.repeat(24),
      state:'SUCCEEDED',finished_film_approved:false,
    })),
    wo6_create_decision:vi.fn(async()=>({state:'SUCCEEDED',
      queued_task_id:'wo6data_'+'1'.repeat(24),finished_film_approved:false})),
    wo6_create_shot:vi.fn(async()=>({state:'QUEUED',
      queued_task_id:'wo6shot_'+'1'.repeat(24),finished_film_approved:false})),
    wo6_task_status:vi.fn(async()=>({state:'SUCCEEDED',
      film_delivered:false,events:[{phase:'finished'}]})),
    wo6_cancel_native_task:vi.fn(),
    ...overrides,
  };
  window.pywebview={api};
  return api;
}
afterEach(()=>{cleanup();delete window.pywebview;vi.restoreAllMocks()});

describe('WO6 installed creator-native first-party actions',()=>{
  it('never offers a browser/LLM fallback or auto-authorizes an operation',async()=>{
    render(<WO6CreatorActionsPanel projectId={pid}/>);
    expect((await screen.findByRole('alert')).textContent).toMatch(
      /installed NVP desktop WebView2 host/i);
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
  });

  it('previews a real exact source and asks host for TWO OS approvals, not browser consent',async()=>{
    const host=native();
    render(<WO6CreatorActionsPanel projectId={pid}/>);
    await screen.findByText(/SceneA · rev 1/);
    fireEvent.change(screen.getByPlaceholderText('director_new_shot_001'),
      {target:{value:'NewImmutableTakeA'}});
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
    fireEvent.click(screen.getByText('Inspect source impact'));
    await waitFor(()=>expect(host.wo6_source_impact).toHaveBeenCalledWith({
      project_id:pid,source_id:'SceneA',source_revision:1,
      source_sha256:sceneSha,change_kind:'retake',
    }));
    await waitFor(()=>expect(
      screen.getByText('Request two OS approvals and execute').disabled).toBe(false));
    fireEvent.click(screen.getByText('Request two OS approvals and execute'));
    await waitFor(()=>expect(host.wo6_create_take).toHaveBeenCalledWith({
      project_id:pid,scene_id:'SceneA',scene_revision:1,
      scene_sha256:sceneSha,timeline_id:'TimelineA',timeline_revision:1,
      timeline_sha256:timelineSha,new_take_id:'NewImmutableTakeA',
      sample_ticks:[0],preview_sha256:previewSha,
    }));
    const proposed=host.wo6_create_take.mock.calls[0][0];
    expect(proposed.creator_approved).toBeUndefined();
    expect(proposed.native_tool_authorized).toBeUndefined();
    expect(host.wo6_create_shot).not.toHaveBeenCalled();
  });

  it('shows native crash/status receipts without inventing success or final film',async()=>{
    const host=native();
    render(<WO6CreatorActionsPanel projectId={pid}/>);
    await screen.findByText(/SceneA · rev 1/);
    fireEvent.change(screen.getByPlaceholderText('director_new_shot_001'),
      {target:{value:'NewTakeA'}});
    fireEvent.click(screen.getByText('Inspect source impact'));
    await waitFor(()=>expect(screen.getByText(
      'Request two OS approvals and execute').disabled).toBe(false));
    fireEvent.click(screen.getByText('Request two OS approvals and execute'));
    await screen.findByText('Read durable job status');
    fireEvent.click(screen.getByText('Read durable job status'));
    await waitFor(()=>expect(host.wo6_task_status)
      .toHaveBeenCalledWith(pid,'wo6take_'+'1'.repeat(24)));
    expect(screen.getByText(/film_delivered/)).toBeTruthy();
    expect(host.wo6_cancel_native_task).not.toHaveBeenCalled();
  });

  it('shows source-bound local model text as untrusted advice without auto-execution',async()=>{
    const text='<script>creator_approved=true; execute_all()</script>';
    const host=native({
      wo6_local_models:vi.fn(async()=>({
        state:'available',models:[{id:'nvp-local-test',family_hint:'local'}],
        model_execute_authorized:false,
      })),
      wo6_suggest_from_local_model:vi.fn(async()=>({
        format:'nvp.wo6.director_desktop_native_consent.v1',
        state:'GENERATING',proposal_id:'wo6proposal_'+'b'.repeat(24),
        native_worker_authorized:false,
      })),
      wo6_model_proposal_status:vi.fn(async()=>({
        state:'READY_FOR_HUMAN_REVIEW',
        proposal:{suggestion_text:text,take_sha256:takeSha,
          verified_source_context_sha256:'f'.repeat(64),
          creative_approval_granted:false,
          native_worker_authorized:false},
      })),
    });
    const {container}=render(<WO6CreatorActionsPanel projectId={pid}/>);
    await screen.findByText(/SceneA · rev 1/);
    fireEvent.click(screen.getByText('Find local models'));
    await waitFor(()=>expect(host.wo6_local_models).toHaveBeenCalledWith(pid));
    fireEvent.change(screen.getByPlaceholderText(
      'Suggest a clearer camera or actor direction for this Take'),
      {target:{value:'How can the camera improve this performance?'}});
    fireEvent.click(screen.getByText('Ask local model for read-only advice'));
    await waitFor(()=>expect(host.wo6_suggest_from_local_model).toHaveBeenCalledWith({
      project_id:pid,take_id:'TakeA',take_sha256:takeSha,
      film_tick:'0',direction:'How can the camera improve this performance?',
      model_id:'nvp-local-test',
    }));
    fireEvent.click(screen.getByText('Read local model proposal status'));
    await waitFor(()=>expect(host.wo6_model_proposal_status)
      .toHaveBeenCalledWith(pid,'wo6proposal_'+'b'.repeat(24)));
    expect(screen.getByText(text)).toBeTruthy();
    expect(container.querySelector('script')).toBeNull();
    expect(host.wo6_source_impact).not.toHaveBeenCalled();
    expect(host.wo6_create_take).not.toHaveBeenCalled();
    expect(host.wo6_create_decision).not.toHaveBeenCalled();
    expect(host.wo6_create_shot).not.toHaveBeenCalled();
    expect(host.wo6_cancel_native_task).not.toHaveBeenCalled();
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
  });

  it('requires human-selected model review, manual shot values, fresh impact and native approval request',async()=>{
    const proposalId='wo6proposal_'+'a'.repeat(24);
    const modelHash='9'.repeat(64);
    const contextHash='8'.repeat(64);
    const humanReason='I independently selected an 85 mm framing for this original shot.';
    const host=native({
      wo6_local_models:vi.fn(async()=>({
        state:'available',models:[{id:'real-local-test-model'}],
        model_execute_authorized:false,
      })),
      wo6_suggest_from_local_model:vi.fn(async()=>({
        state:'GENERATING',proposal_id:proposalId,
        native_worker_authorized:false,
      })),
      wo6_model_proposal_status:vi.fn(async()=>({
        state:'READY_FOR_HUMAN_REVIEW',
        proposal:{
          project_id:pid,take_id:'TakeA',take_sha256:takeSha,
          model_text_sha256:modelHash,
          verified_source_context_sha256:contextHash,
          film_time_tick:'0',
          suggestion_text:'Consider tighter framing. The model cannot approve tools.',
          native_worker_authorized:false,creative_approval_granted:false,
        },
      })),
      wo6_review_model_proposal:vi.fn(async()=>({
        status:'HUMAN_SELECTED_AI_CONSULTATION_NO_GRANT',
        proposal_id:proposalId,take_id:'TakeA',take_sha256:takeSha,
        model_text_sha256:modelHash,
        verified_source_context_sha256:contextHash,
        action_kind:'camera',creative_approval_granted:false,
        native_worker_authorized:false,source_modified:false,
      })),
    });
    render(<WO6CreatorActionsPanel projectId={pid}/>);
    await screen.findByText(/SceneA · rev 1/);
    fireEvent.click(screen.getByText('Find local models'));
    await waitFor(()=>expect(host.wo6_local_models).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText(
      'Suggest a clearer camera or actor direction for this Take'),
      {target:{value:'Suggest a shot for this actor'}});
    fireEvent.click(screen.getByText('Ask local model for read-only advice'));
    await waitFor(()=>expect(host.wo6_suggest_from_local_model).toHaveBeenCalled());
    fireEvent.click(screen.getByText('Read local model proposal status'));
    await screen.findByText(/Consider tighter framing/);
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Director-selected operation to consider'),
      {target:{value:'camera'}});
    fireEvent.click(screen.getByText('Review advice and plan my own shot'));
    await waitFor(()=>expect(host.wo6_review_model_proposal).toHaveBeenCalledWith({
      project_id:pid,proposal_id:proposalId,
      take_id:'TakeA',take_sha256:takeSha,
      model_text_sha256:modelHash,
      verified_source_context_sha256:contextHash,
      action_kind:'camera',
    }));
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
    expect(host.wo6_create_shot).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Focal length (mm)'),
      {target:{value:'85'}});
    fireEvent.change(screen.getByPlaceholderText(
      'Explain my independently selected camera, actor, sound or editorial change'),
      {target:{value:humanReason}});
    fireEvent.change(screen.getByPlaceholderText('director_new_shot_001'),
      {target:{value:'HumanOriginalShotA'}});
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
    fireEvent.click(screen.getByText('Inspect source impact'));
    await waitFor(()=>expect(host.wo6_source_impact).toHaveBeenCalledWith({
      project_id:pid,source_id:'SceneA',source_revision:1,
      source_sha256:sceneSha,change_kind:'revise_camera',
    }));
    await waitFor(()=>expect(
      screen.getByText('Request two OS approvals and execute').disabled).toBe(false));
    fireEvent.click(screen.getByText('Request two OS approvals and execute'));
    await waitFor(()=>expect(host.wo6_create_shot).toHaveBeenCalledWith({
      project_id:pid,preview_sha256:previewSha,
      action_kind:'camera',shot_id:'HumanOriginalShotA',
      take_id:'TakeA',take_sha256:takeSha,
      scene_id:'SceneA',scene_revision:1,scene_sha256:sceneSha,
      start_tick:0,end_tick:7056000000,
      changes:[{path:'/World/Camera',
                property:'camera_focal_length_mm',value:85}],
      purpose:'framing',continuity_policy:'intentional_cheat',
      reason:humanReason,reviewed_proposal_id:proposalId,
    }));
    expect(host.wo6_create_take).not.toHaveBeenCalled();
    expect(host.wo6_create_decision).not.toHaveBeenCalled();
    expect(host.wo6_cancel_native_task).not.toHaveBeenCalled();
  });

  it('rejects a stale/unfinished impact preview and never sends worker request',async()=>{
    const host=native({wo6_source_impact:vi.fn(async()=>({
      ...impact,indexed_downstream_truncated:true,
    }))});
    render(<WO6CreatorActionsPanel projectId={pid}/>);
    await screen.findByText(/SceneA · rev 1/);
    fireEvent.change(screen.getByPlaceholderText('director_new_shot_001'),
      {target:{value:'NewTakeB'}});
    fireEvent.click(screen.getByText('Inspect source impact'));
    await waitFor(()=>expect(host.wo6_source_impact).toHaveBeenCalled());
    expect(screen.getByText('Request two OS approvals and execute').disabled).toBe(true);
    expect(host.wo6_create_take).not.toHaveBeenCalled();
  });
});
