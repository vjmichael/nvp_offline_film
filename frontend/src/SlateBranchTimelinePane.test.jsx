// @vitest-environment jsdom
import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import SlateBranchTimelinePane from './SlateBranchTimelinePane.jsx';

const node=(n,active=false)=>({
  branch_id:'take_'+n,group_id:'reaction',
  kind:n===1?'performance':'coverage',
  parent_id:n===1?null:'take_1',selected:active,
  source_start_tick:0,source_end_tick:1000,
  slate:{shot:'01A',take_number:n,camera:'A',wild:false},
});

describe('SLATE-03 paged timeline and assembly source cards',()=>{
  it('inspects without activating; Make Active remains explicit host callback',()=>{
    const preview=vi.fn(),approve=vi.fn();
    const graph={project_id:'a'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true),node(2)]}};
    const {container,rerender}=render(<SlateBranchTimelinePane
      graphView={graph} onPreviewTake={preview} onMakeActive={approve}/>);
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
    const rows=container.querySelectorAll('.nvp-slate-entry');
    fireEvent.click(rows[1].querySelector('.nvp-slate-name'));
    expect(preview).toHaveBeenCalledOnce();
    expect(approve).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
    fireEvent.click(rows[1].querySelector('.nvp-slate-actions button:nth-child(2)'));
    expect(approve).toHaveBeenCalledOnce();
    // Even invoking the callback does not optimistically change the green
    // path until the authoritative backend sends its committed edit view.
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
    const updated={...graph,parallel_groups:{reaction:[node(1,false),node(2,true)]}};
    rerender(<SlateBranchTimelinePane graphView={updated}
      onPreviewTake={preview} onMakeActive={approve}/>);
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
  });

  it('accommodates 60 take choices in a bounded scroll viewport',()=>{
    const graph={project_id:'b'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:Array.from({length:60},(_,i)=>node(i+1,i===0))}};
    const {container}=render(<SlateBranchTimelinePane graphView={graph}/>);
    expect(screen.getByText(/60 shown takes and camera views/)).toBeTruthy();
    expect(container.querySelectorAll('.nvp-slate-entry').length).toBeLessThan(60);
    const scroller=container.querySelector('.nvp-slate-scroll');
    expect(scroller.style.height).toBe('744px');
    expect(container.querySelector('.nvp-slate-vertical-dashes')).toBeTruthy();
    expect(container.querySelector('.nvp-slate-entry.inspected')).toBeNull();
  });

  it('shows multiple committed sources in one group without coloring inspected alternatives green',()=>{
    const graph={project_id:'c'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1),node(2),node(3)]}};
    const cut={edit_document_sha256:'f'.repeat(64),
      sequence:[{segment_id:'segment_a',branch_id:'take_1',
                 source_in_tick:0,source_out_tick:500},
                {segment_id:'segment_b',branch_id:'take_2',
                 source_in_tick:500,source_out_tick:1000}]};
    const {container}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={cut}/>);
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(2);
    fireEvent.click(container.querySelectorAll('.nvp-slate-name')[2]);
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(2);
    expect(container.querySelectorAll('.nvp-slate-entry.inspected')).toHaveLength(1);
  });
  it('renders real source Take metadata inside assembled cut boxes, with AI unreviewed',()=>{
    const base=node(1,true);
    const n={...base,slate:{...base.slate,scene:'01',camera:'B',wild:true},
      semantic:{
        shot_type:'reaction',beat_ids:['reunion'],emotion_tags:['surprised'],
        director_rating:5,technical_status:'acceptable',
        director_notes:'Best expression during the reaction',
        moment_cues:[{
          source_in_tick:120,source_out_tick:450,origin:'editor_tag',
          beat_ids:['eyeline_change'],dialogue_ids:['line_17'],
          emotion_tags:['relieved'],character_ids:['Actor'],
          action_tags:['reaction'],
        }],
        ai_observations:[{
          model_id:'assistant_v1',summary:'Check eyeline on next cut',
          status:'UNREVIEWED_AI_PROPOSAL',
          source_in_tick:100,source_out_tick:600,
          confidence:0.68,
        }],
      }};
    const graph={project_id:'d'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[n,node(2)]}};
    const cut={edit_document_sha256:'f'.repeat(64),sequence:[{
      segment_id:'clip_A',branch_id:'take_1',
      source_in_tick:100,source_out_tick:600,
      timeline_start_tick:0,timeline_end_tick:500,
      incoming_transition:{requires_continuity_review:true},
    }]};
    const {container}=render(<SlateBranchTimelinePane graphView={graph} activeView={cut}/>);
    expect(screen.getByText('Scene 01 · Shot 01A')).toBeTruthy();
    expect(screen.getByText('Wild · Take 1 · Camera B')).toBeTruthy();
    expect(screen.getByText('Edit 0–500 ticks')).toBeTruthy();
    expect(screen.getByText('Source 100–600 ticks')).toBeTruthy();
    expect(screen.getByText(/reunion · eyeline_change · surprised · relieved/)).toBeTruthy();
    expect(screen.getByText(/Dialogue cues: line_17/)).toBeTruthy();
    expect(screen.getByText('Director rating 5/5')).toBeTruthy();
    expect(screen.getByText(/Director: Best expression/)).toBeTruthy();
    expect(screen.getByText(/AI suggestion · unreviewed: Check eyeline/)).toBeTruthy();
    expect(screen.getByText('Continuity review at incoming cut')).toBeTruthy();
    expect(container.querySelectorAll('.nvp-slate-assembly-card')).toHaveLength(1);
  });

  it('requests more catalog pages without accepting or committing any source branch',()=>{
    const load=vi.fn(),activate=vi.fn();
    const page={branch_count:4096,next_after_index:63,
      items:Array.from({length:64},(_,i)=>node(i+1,i===0))};
    const {container}=render(<SlateBranchTimelinePane
      catalogPage={page} onLoadMore={load} onMakeActive={activate}/>);
    expect(screen.getByText(/64 shown of 4096 takes and camera views/)).toBeTruthy();
    fireEvent.click(screen.getByText('Load more takes'));
    expect(load).toHaveBeenCalledWith(63);
    expect(activate).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.nvp-slate-entry').length).toBeLessThan(64);
  });

  it('copies/cuts/pastes only draft references without changing active green source',()=>{
    const draftCut=vi.fn(),draftPaste=vi.fn(),commit=vi.fn(),preview=vi.fn();
    const graph={project_id:'e'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true),node(2)]}};
    const source={segment_id:'original',branch_id:'take_1',
      source_in_tick:100,source_out_tick:600,
      timeline_start_tick:0,timeline_end_tick:500};
    const activeView={edit_document_sha256:'a'.repeat(64),
      sequence:[source]};
    const draftView={draft_uncommitted:true,segments:[
      {...source,segment_id:'draft_one'},
      {...source,segment_id:'draft_two',
        branch_id:'take_2',timeline_start_tick:500,
        timeline_end_tick:1000},
    ]};
    const {container}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={activeView}
      draftView={draftView} onDraftCut={draftCut}
      onDraftPaste={draftPaste} onCommitDraft={commit}
      onRequestDataPreview={preview}/>);
    expect(screen.getByText('Uncommitted draft assembly')).toBeTruthy();
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
    fireEvent.click(container.querySelectorAll('.nvp-slate-assembly-card')[1]);
    fireEvent.click(screen.getByText('Copy reference'));
    expect(draftCut).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Paste before'));
    expect(draftPaste).toHaveBeenCalledWith({
      branch_id:'take_2',source_in_tick:100,source_out_tick:600
    },'draft_two','before');
    expect(commit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Cut draft reference'));
    expect(draftCut).toHaveBeenCalledWith('draft_two');
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
    expect(screen.getByText('Preview source data').disabled).toBe(true);
    fireEvent.click(screen.getByText('Make draft active'));
    expect(commit).toHaveBeenCalledWith(draftView);
    expect(container.querySelectorAll('.nvp-slate-range.green')).toHaveLength(1);
  });

  it('requests data preview only for a selected committed time interval',()=>{
    const renderTicket=vi.fn();
    const graph={project_id:'f'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const cut={edit_document_sha256:'b'.repeat(64),sequence:[{
      segment_id:'selected',branch_id:'take_1',
      source_in_tick:100,source_out_tick:600,
      timeline_start_tick:900,timeline_end_tick:1400,
    }]};
    const {container}=render(<SlateBranchTimelinePane graphView={graph}
      activeView={cut} onRequestDataPreview={renderTicket}/>);
    expect(renderTicket).not.toHaveBeenCalled();
    fireEvent.click(container.querySelector('.nvp-slate-assembly-card'));
    fireEvent.click(screen.getByText('Preview source data'));
    expect(renderTicket).toHaveBeenCalledOnce();
    expect(renderTicket).toHaveBeenCalledWith(900);
  });

  it('shows one trusted host PNG proxy only for the currently selected committed edit',()=>{
    const graph={project_id:'a'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const activeView={edit_document_sha256:'a'.repeat(64),
      sequence:[{segment_id:'clip_1',branch_id:'take_1',
        source_in_tick:0,source_out_tick:100,
        timeline_start_tick:0,timeline_end_tick:100}]};
    const previewPane={
      status:'READY',segment_id:'clip_1',
      edit_document_sha256:'a'.repeat(64),
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB',
    };
    const {container,rerender}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={activeView} previewPane={previewPane}/>);
    expect(container.querySelector('.nvp-slate-proxy-preview img')).toBeNull();
    fireEvent.click(container.querySelector('.nvp-slate-assembly-card'));
    expect(screen.getByAltText(/low-resolution geometry-proxy/)).toBeTruthy();
    rerender(<SlateBranchTimelinePane graphView={graph} activeView={activeView}
      previewPane={{...previewPane,edit_document_sha256:'b'.repeat(64)}}/>);
    expect(container.querySelector('.nvp-slate-proxy-preview img')).toBeNull();
    expect(screen.getByText(/Preview not ready for this selected committed segment/)).toBeTruthy();
  });

  it('never treats a queued low-fi proxy as a rendered picture',()=>{
    const graph={project_id:'b'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const {container}=render(<SlateBranchTimelinePane graphView={graph}
      previewPane={{status:'QUEUED',segment_id:'clip_1'}}/>);
    expect(screen.getByText(/Preview queued/)).toBeTruthy();
    expect(container.querySelector('.nvp-slate-proxy-preview img')).toBeNull();
  });

  it('requires committed selection and distinct native-camera choice for authored geometry render',()=>{
    const request=vi.fn();
    const graph={project_id:'a'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const source={segment_id:'clip_A',branch_id:'take_1',
      source_in_tick:100,source_out_tick:600,
      timeline_start_tick:240,timeline_end_tick:740};
    const cut={edit_document_sha256:'b'.repeat(64),sequence:[source]};
    const cameras=[{path:'/World/CamA',label:'Camera A'},
                   {path:'/World/CamB',label:'Camera B'}];
    const {container,rerender}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={cut}
      onRequestGeometryPreview={request} cameraChoices={cameras}/>);
    expect(screen.getByText('Render authored 3D preview').disabled).toBe(true);
    fireEvent.click(container.querySelector('.nvp-slate-assembly-card'));
    expect(screen.getByText('Render authored 3D preview').disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Authored camera'),
                     {target:{value:'/World/CamB'}});
    fireEvent.click(screen.getByText('Render authored 3D preview'));
    expect(request).toHaveBeenCalledWith({
      presentation:'geometry',film_tick:240,segment_id:'clip_A',
      edit_document_sha256:'b'.repeat(64),
      camera_path:'/World/CamB'});
    expect(request).toHaveBeenCalledOnce();
    const draft={draft_uncommitted:true,segments:[{...source}]};
    rerender(<SlateBranchTimelinePane graphView={graph}
      activeView={cut} draftView={draft}
      onRequestGeometryPreview={request} cameraChoices={cameras}/>);
    expect(screen.getByText('Render authored 3D preview').disabled).toBe(true);
  });

  it('distinguishes authored OpenUSD geometry from proxy and flags missing actor meshes',()=>{
    const graph={project_id:'c'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const cut={edit_document_sha256:'f'.repeat(64),
      sequence:[{segment_id:'clip_1',branch_id:'take_1',
        source_in_tick:0,source_out_tick:500,
        timeline_start_tick:0,timeline_end_tick:500}]};
    const presentation={presentation:'geometry',status:'READY',
      segment_id:'clip_1',edit_document_sha256:'f'.repeat(64),
      unmeshed_actors:['/World/Actor'],skeletal_rig_count:1,
      image_data_url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB'};
    const {container}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={cut} previewPane={presentation}/>);
    expect(screen.getByText('Authored OpenUSD geometry preview')).toBeTruthy();
    fireEvent.click(container.querySelector('.nvp-slate-assembly-card'));
    expect(screen.getByAltText(/Authored OpenUSD camera and geometry preview/)).toBeTruthy();
    expect(screen.getByText(/at least one actor lacks supported/)).toBeTruthy();
    expect(screen.getByText(/supported weighted skinning · no final master approval/)).toBeTruthy();
  });

  it('scrubs real performance Film Time without changing a source Take or activating a draft',()=>{
    const req=vi.fn();
    const source={segment_id:'pose_clip',branch_id:'take_1',
      source_in_tick:100,source_out_tick:600,
      timeline_start_tick:1000,timeline_end_tick:1500};
    const cut={edit_document_sha256:'a'.repeat(64),sequence:[source]};
    const graph={project_id:'e'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true)]}};
    const {container}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={cut}
      onRequestGeometryPreview={req}
      cameraChoices={[{path:'/World/Camera'}]}/>);
    fireEvent.click(container.querySelector('.nvp-slate-assembly-card'));
    expect(screen.getByLabelText('Performance time')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Performance time'),
      {target:{value:'1350'}});
    expect(screen.getByText(/Performance time · 1350 ticks/)).toBeTruthy();
    expect(req).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Render authored 3D preview'));
    expect(req).toHaveBeenCalledWith({
      presentation:'geometry',film_tick:1350,segment_id:'pose_clip',
      edit_document_sha256:'a'.repeat(64),camera_path:null});
  });

});
