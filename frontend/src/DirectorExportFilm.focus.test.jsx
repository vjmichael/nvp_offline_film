import React from 'react';
import {act,cleanup,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import DirectorExportFilm from './DirectorExportFilm.jsx';

vi.mock('./DirectorFinishingRoom.jsx',()=>({default:()=>null}));
vi.mock('./DirectorLongFilmExport.jsx',()=>({default:()=>null}));
vi.mock('./DirectorFilmLibrary.jsx',()=>({default:()=>null}));
vi.mock('./DirectorFinishedReview.jsx',()=>({default:()=>null}));

const PID='a'.repeat(32);
const movie={id:PID,title:'Original Source',revision:1,encrypted:false};
const base='/api/projects/'+PID;
const reply=data=>({ok:true,json:async()=>data});
const edit=revision=>({
  revision, clips:revision?[{id:'original-take'}]:[],
  duration_seconds:revision?4:0,missing_sources:[]
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('STAB-01B export handoff from the separate Post-Production window',()=>{
  it('re-reads the saved edit when the director returns to Export Film',async()=>{
    let saved=edit(0);
    const requests=[];
    vi.stubGlobal('fetch',vi.fn(async url=>{
      requests.push(url);
      if(url===base+'/edit')return reply(saved);
      if(url===base+'/export')return reply({exports:[]});
      throw new Error('Unexpected export request: '+url);
    }));
    render(<DirectorExportFilm movie={movie} onEditFilm={()=>{}} onFilmScenes={()=>{}}/>);
    expect(await screen.findByText('Choose what goes into your film')).toBeTruthy();
    saved=edit(1);
    await act(async()=>{window.dispatchEvent(new Event('focus'));});
    expect(await screen.findByRole('button',{name:'Finish and Save Movie'})).toBeTruthy();
    expect(requests.filter(x=>x===base+'/edit').length).toBeGreaterThanOrEqual(2);
    // Read-only resynchronization cannot authorize a render or approval.
    expect(requests.every(x=>x===base+'/edit'||x===base+'/export')).toBe(true);
  });

  it('does not allow an older asynchronous read to replace a newer edit',async()=>{
    let initialResponse;
    let reads=0;
    vi.stubGlobal('fetch',vi.fn(async url=>{
      if(url===base+'/edit'){
        reads++;
        if(reads===1)return {ok:true,json:()=>new Promise(resolve=>{
          initialResponse=resolve;
        })};
        return reply(edit(1));
      }
      if(url===base+'/export')return reply({exports:[]});
      throw new Error('Unexpected export request: '+url);
    }));
    render(<DirectorExportFilm movie={movie} onEditFilm={()=>{}} onFilmScenes={()=>{}}/>);
    await waitFor(()=>expect(typeof initialResponse).toBe('function');
    await act(async()=>{window.dispatchEvent(new Event('focus'));});
    expect(await screen.findByRole('button',{name:'Finish and Save Movie'})).toBeTruthy();
    await act(async()=>{initialResponse(edit(0));});
    expect(screen.getByRole('button',{name:'Finish and Save Movie'})).toBeTruthy();
    expect(screen.queryByText('Choose what goes into your film')).toBeNull();
  });
});
