// @vitest-environment jsdom
import React from 'react';
import {beforeEach,afterEach,describe,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import ColorCurvePanel from './ColorCurvePanel.jsx';

const project={id:'a'.repeat(32)};
const basePlan={format:'nvp.color.grade.shot_wheels.v1',
  global:{format:'nvp.color.grade.global.v1',scope:'global_all_frames',
    exposure_stops:0,contrast:1,saturation:1,
    red_gain:1,green_gain:1,blue_gain:1},
  shots:{}};
const shot='SH_f1f228babbc546a7ae88574c13d1ee43';
const timeline={frames:16,timeline_sha256:'b'.repeat(64),
  shots:[{shot_id:shot,start_frame:1,end_frame:8,frames:8},
         {shot_id:'SH_3aee4d8822d14366b73ffa07e16172ce',
          start_frame:9,end_frame:16,frames:8}]};
let calls;
beforeEach(()=>{
  calls=[];
  global.fetch=vi.fn(async(url,options)=>{
    const path=String(url);
    calls.push([path,options]);
    if(path.endsWith('/curves/preview'))return {
      ok:true,json:async()=>({
        png_base64:'aGVsbG8=',png_sha256:'c'.repeat(64),
        calibrated:false,scope:{pixels:256*144}
      })
    };
    if(path.endsWith('/curves/reference-suggestion'))return {
      ok:true,json:async()=>({
        status:'inspectable_heuristic_only_not_applied',
        suggested_exposure_stops:.25,target_frame:1,reference_frame:9
      })
    };
    if(path.endsWith('/curves/grades')&&options?.method==='POST')return {
      ok:true,json:async()=>({id:'curve_look_main',revision:1})
    };
    if(path.endsWith('/curves/grades/curve_look_main'))return {
      ok:true,json:async()=>({
        source_id:'exr_source_16f',revision:1,
        plan:{format:'nvp.color.grade.shot_curves.v1',base:basePlan,curves:{}}
      })
    };
    throw Error('Unrecognized mock request '+path);
  });
});
afterEach(()=>{cleanup();vi.restoreAllMocks();});

describe('GRADE-UI-02B1',()=>{
  it('loads an actual source-derived tone curve preview, exposes bounded knot controls',async()=>{
    render(<ColorCurvePanel project={project} sourceId="exr_source_16f"
      timeline={timeline} frame={1} basePlan={basePlan}/>);
    expect(screen.getByRole('img',{name:/Editable scene-linear EV tone curve/})).toBeTruthy();
    expect(screen.getByRole('slider',{name:'Shadows offset in stops'})).toBeTruthy();
    expect(screen.getByRole('slider',{name:'Deep black offset in stops'}).disabled).toBe(true);
    await waitFor(()=>expect(calls.some(([path])=>path.endsWith('/curves/preview'))).toBe(true),
      {timeout:3500});
    expect(screen.getByText(/not approved color output/i)).toBeTruthy();
  });

  it('adjusts a tone point, undoes and redoes without changing source',async()=>{
    render(<ColorCurvePanel project={project} sourceId="exr_source_16f"
      timeline={timeline} frame={1} basePlan={basePlan}/>);
    const slider=screen.getByRole('slider',{name:'Middle gray offset in stops'});
    fireEvent.change(slider,{target:{value:'.5'}});
    expect(screen.getByRole('spinbutton',{name:'Middle gray numeric EV offset'}).value).toBe('0.5');
    fireEvent.click(screen.getByRole('button',{name:'Undo curve'}));
    expect(screen.getByRole('spinbutton',{name:'Middle gray numeric EV offset'}).value).toBe('0');
    fireEvent.click(screen.getByRole('button',{name:'Redo curve'}));
    expect(screen.getByRole('spinbutton',{name:'Middle gray numeric EV offset'}).value).toBe('0.5');
  });

  it('keeps reference advice opt-in and requires source declaration for draft',async()=>{
    render(<ColorCurvePanel project={project} sourceId="exr_source_16f"
      timeline={timeline} frame={1} basePlan={basePlan}/>);
    expect(screen.getByRole('button',{name:'Save curve draft'}).disabled).toBe(true);
    fireEvent.change(screen.getByRole('spinbutton',{name:'Reference frame'}),
      {target:{value:'9'}});
    fireEvent.click(screen.getByRole('button',{name:/Compare reference without changing/}));
    await screen.findByText(/Estimated difference: 0.25 stops/);
    expect(screen.getByRole('spinbutton',{name:'Middle gray numeric EV offset'}).value).toBe('0');
    fireEvent.click(screen.getByRole('button',{name:/Apply suggestion to this shot/}));
    expect(screen.getByRole('spinbutton',{name:'Middle gray numeric EV offset'}).value).toBe('0.25');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button',{name:'Save curve draft'}));
    await waitFor(()=>expect(calls.some(([path,opts])=>path.endsWith('/curves/grades')&&opts?.method==='POST')).toBe(true));
    const payload=JSON.parse(calls.find(([path,opts])=>path.endsWith('/curves/grades')&&opts?.method==='POST')[1].body);
    expect(payload.source_primaries_declared).toBe(true);
    expect(payload.plan.curves[shot].ev_offsets[2]).toBe(0.25);
    expect(payload.expected_revision).toBe(0);
    await screen.findByText(/Saved immutable unapproved curve draft revision 1/);
  });
});
