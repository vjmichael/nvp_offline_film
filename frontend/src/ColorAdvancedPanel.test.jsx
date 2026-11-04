// @vitest-environment jsdom
import React from 'react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ColorAdvancedPanel from './ColorAdvancedPanel.jsx';

const PID='a'.repeat(32);
const IDS=['SH_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','SH_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'];
const GLOBAL={format:'nvp.color.grade.global.v1',scope:'global_all_frames',
  exposure_stops:0,contrast:1,saturation:1,red_gain:1,green_gain:1,blue_gain:1};
const TL={source_id:'exr_source_16f',source_sha256:'a'.repeat(64),frames:16,fps:24,
  width:256,height:144,timeline_sha256:'b'.repeat(64),
  shots:[
    {shot_id:IDS[0],start_frame:1,end_frame:8,frames:8},
    {shot_id:IDS[1],start_frame:9,end_frame:16,frames:8}
  ]};
const bins=()=>Array.from({length:64},(_,i)=>i===0?256:0);
const matrix=()=>Array.from({length:64},(_,y)=>Array.from({length:64},(_,x)=>(x===0&&y===0?256:0)));
const PREVIEW={png_base64:'aGVsbG8=',frame:1,shot_id:IDS[0],
  scope:{format:'nvp.scope.display_rgb48.v1',pixels:256*144,
    rgb48_sha256:'d'.repeat(64),luma_mean:.31,
    histogram:{red:bins(),green:bins(),blue:bins(),luma:bins()},
    waveform:matrix(),vectorscope:matrix()}};
let calls=[];
beforeEach(()=>{
  calls=[];
  global.fetch=vi.fn(async (url,opts)=>{
    const text=String(url);calls.push([text,opts]);
    if(text.includes('/advanced/shots?'))return{ok:true,json:async()=>TL};
    if(text.endsWith('/advanced/preview'))return{ok:true,json:async()=>PREVIEW};
    if(text.endsWith('/advanced/grades') && opts?.method==='POST'){
      const data=JSON.parse(opts.body);
      return{ok:true,json:async()=>({id:data.grade_id,revision:1,plan:data.plan})};
    }
    if(text.endsWith('/advanced/grades/shot_look_main')){
      return{ok:true,json:async()=>({id:'shot_look_main',revision:1,
        source_id:'exr_source_16f',
        plan:{format:'nvp.color.grade.shot_wheels.v1',global:GLOBAL,shots:{}}})};
    }
    throw Error('Unexpected mock URL '+text);
  });
});
afterEach(()=>{cleanup();vi.restoreAllMocks();});

describe('NVP GRADE-UI-02A',()=>{
  it('shows real two-shot timeline and post-ACES measured scope descriptions',async()=>{
    render(<ColorAdvancedPanel project={{id:PID}} sourceId="exr_source_16f"
      frame={1} onFrameChange={()=>{}} globalGrade={GLOBAL}/>);
    await screen.findByRole('button',{name:/Shot 1/});
    expect(screen.getByRole('button',{name:/Shot 2/})).toBeTruthy();
    expect(screen.getByRole('heading',{name:'Histogram'})).toBeTruthy();
    await waitFor(()=>expect(calls.some(([url])=>url.endsWith('/advanced/preview'))).toBe(true),
      {timeout:3500});
    expect(screen.getByRole('img',{name:/64-bin RGB/})).toBeTruthy();
    expect(screen.getByRole('img',{name:/display luma waveform/})).toBeTruthy();
    expect(screen.getByRole('img',{name:/BT.709 chroma vectorscope/})).toBeTruthy();
    expect(screen.getByText(/not an approved color reference/)).toBeTruthy();
  });
  it('makes selected shot editable without changing the frozen timeline',async()=>{
    const setFrame=vi.fn();
    render(<ColorAdvancedPanel project={{id:PID}} sourceId="exr_source_16f"
      frame={1} onFrameChange={setFrame} globalGrade={GLOBAL}/>);
    await screen.findByRole('button',{name:/Shot 2/});
    fireEvent.click(screen.getByRole('button',{name:/Shot 2/}));
    expect(setFrame).toHaveBeenCalledWith(9);
    const gain=screen.getByRole('slider',{name:'Gain · highlights red'});
    fireEvent.change(gain,{target:{value:'1.10'}});
    expect(screen.getByRole('spinbutton',{name:'Gain · highlights red numeric'}).value).toBe('1.1');
    fireEvent.click(screen.getByRole('button',{name:'Undo shot edit'}));
    expect(screen.getByRole('spinbutton',{name:'Gain · highlights red numeric'}).value).toBe('1');
    fireEvent.click(screen.getByRole('button',{name:'Redo shot edit'}));
    expect(screen.getByRole('spinbutton',{name:'Gain · highlights red numeric'}).value).toBe('1.1');
  });
  it('does not save a shot plan without source-space declaration',async()=>{
    render(<ColorAdvancedPanel project={{id:PID}} sourceId="exr_source_16f"
      frame={1} onFrameChange={()=>{}} globalGrade={GLOBAL}/>);
    await screen.findByRole('button',{name:/Shot 1/});
    const save=screen.getByRole('button',{name:'Save advanced draft look'});
    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(save);
    await waitFor(()=>expect(calls.some(([url,opts])=>url.endsWith('/advanced/grades')&&opts?.method==='POST')).toBe(true));
    const saved=calls.find(([url,opts])=>url.endsWith('/advanced/grades')&&opts?.method==='POST');
    const data=JSON.parse(saved[1].body);
    expect(data.source_primaries_declared).toBe(true);
    expect(data.expected_revision).toBe(0);
    expect(data.plan.format).toBe('nvp.color.grade.shot_wheels.v1');
    await screen.findByText(/independent advanced draft revision 1/);
  });
});
