// @vitest-environment jsdom
import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import SlateBranchTimelinePane from './SlateBranchTimelinePane.jsx';

const node=(n,active=false)=>({
  branch_id:'take_'+n,group_id:'reaction',
  kind:n===1?'performance':'coverage',
  parent_id:n===1?null:'take_1',selected:active,
  slate:{shot:'01A',take_number:n,camera:'A',wild:false},
});

describe('SLATE-02 timeline window component',()=>{
  it('inspects without activating; Make Active remains explicit host callback',()=>{
    const preview=vi.fn(),approve=vi.fn();
    const graph={project_id:'a'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:[node(1,true),node(2)]}};
    const {container,rerender}=render(<SlateBranchTimelinePane
      graphView={graph} onPreviewTake={preview} onMakeActive={approve}/>);
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(1);
    const rows=container.querySelectorAll('.nvp-slate-entry');
    fireEvent.click(rows[1].querySelector('.nvp-slate-name'));
    expect(preview).toHaveBeenCalledOnce();
    expect(approve).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(1);
    fireEvent.click(rows[1].querySelector('.nvp-slate-actions button:nth-child(2)'));
    expect(approve).toHaveBeenCalledOnce();
    // Even invoking the callback does not optimistically change the green
    // path until the authoritative backend sends its committed edit view.
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(1);
    const updated={...graph,parallel_groups:{reaction:[node(1,false),node(2,true)]}};
    rerender(<SlateBranchTimelinePane graphView={updated}
      onPreviewTake={preview} onMakeActive={approve}/>);
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(1);
  });

  it('accommodates 60 take choices in a bounded scroll viewport',()=>{
    const graph={project_id:'b'.repeat(32),scene_label:'01',
      parallel_groups:{reaction:Array.from({length:60},(_,i)=>node(i+1,i===0))}};
    const {container}=render(<SlateBranchTimelinePane graphView={graph}/>);
    expect(screen.getByText('60 takes and camera views')).toBeTruthy();
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
      sequence:[{segment_id:'segment_a',branch_id:'take_1'},
                {segment_id:'segment_b',branch_id:'take_2'}]};
    const {container}=render(<SlateBranchTimelinePane
      graphView={graph} activeView={cut}/>);
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(2);
    fireEvent.click(container.querySelectorAll('.nvp-slate-name')[2]);
    expect(container.querySelectorAll('.nvp-slate-line.green')).toHaveLength(2);
    expect(container.querySelectorAll('.nvp-slate-entry.inspected')).toHaveLength(1);
  });
});
