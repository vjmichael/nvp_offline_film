import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import DirectorScreenplayAssistant from './DirectorScreenplayAssistant.jsx';

const PID='a'.repeat(32);
const movie={
  id:PID,revision:0,idea:'A mountain sunrise',screenplay:'',
  encrypted:false,
};
const base='/api/projects/'+PID+'/preproduction';

function server({state='disconnected',message='Lu Workspace is not connected.'}={}) {
  const calls=[];
  const fetcher=vi.fn(async(url,options={})=>{
    calls.push({url,method:options.method||'GET',payload:options.body});
    let data={};
    if(url===base)data={screenplay_drafts:[]};
    else if(url==='/api/projects/'+PID+'/lu/status')
      data={state,message};
    else if(url===base+'/screenplay/suggestions'&&options.method==='POST')
      data={screenplay_drafts:[{
        id:'b'.repeat(32),content:'INT. CABIN - MORNING\n\nLight rises.',
        status:'proposed',stale:false}]};
    else if(url===base+'/screenplay/'+'b'.repeat(32)+'/decision')
      data={applied:false};
    else if(url==='/api/projects/'+PID)
      data=movie;
    else if(url==='/api/projects/'+PID+'/lu/cancel')
      data={state:'cancellation_requested',terminal_verified:false};
    return {ok:true,json:async()=>data};
  });
  vi.stubGlobal('fetch',fetcher);
  return calls;
}

describe('INT-01D filmmaker Lu proposal-only UI',()=>{
  afterEach(()=>{cleanup();vi.unstubAllGlobals()});

  it('does not enable Lu writing from a generic model catalog or disconnected status',async()=>{
    const calls=server();
    render(<DirectorScreenplayAssistant movie={movie} unsaved={false}
      onApproved={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText(/Lu Workspace is not connected/)).toBeTruthy());
    expect(screen.getByRole('button',{name:/Ask Lu/}).disabled).toBe(true);
    expect(calls.every(x=>x.url!=='/api/creative/models')).toBe(true);
    expect(calls.some(x=>x.url==='/api/projects/'+PID+'/lu/status')).toBe(true);
  });

  it('requires ready Lu state then exposes reviewable draft, not auto-approval',async()=>{
    const calls=server({state:'ready',message:'Lu is ready to help.'});
    const approve=vi.fn();
    render(<DirectorScreenplayAssistant movie={movie} unsaved={false}
      onApproved={approve}/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:/Ask Lu/}).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText(/What would you like help writing/),
      {target:{value:'An early morning scene'}});
    fireEvent.click(screen.getByRole('button',{name:/Ask Lu/}));
    await waitFor(()=>expect(screen.getByText(/needs your review/)).toBeTruthy());
    expect(approve).not.toHaveBeenCalled();
    expect(calls.some(x=>x.url===base+'/screenplay/suggestions'
      && x.method==='POST')).toBe(true);
    expect(calls.every(x=>x.url!=='/api/creative/models')).toBe(true);
  });

  it('does not send encrypted original source to Lu',async()=>{
    const calls=server({state:'ready',message:'Lu is ready to help.'});
    render(<DirectorScreenplayAssistant movie={{...movie,encrypted:true}}
      unsaved={false} onApproved={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText(/Private-film Lu integration is not yet authorized/)).toBeTruthy());
    expect(screen.getByRole('button',{name:/Ask Lu/}).disabled).toBe(true);
    expect(calls.every(x=>!x.url.endsWith('/lu/status'))).toBe(true);
  });

  it('does not request Lu when the filmmaker has unsaved screenplay changes',async()=>{
    server({state:'ready',message:'Lu is ready to help.'});
    render(<DirectorScreenplayAssistant movie={movie} unsaved={true}
      onApproved={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText(/Save your current screenplay changes/)).toBeTruthy());
    expect(screen.getByRole('button',{name:/Ask Lu/}).disabled).toBe(true);
  });
});
