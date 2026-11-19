import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import DirectorOriginalSections from './DirectorOriginalSections.jsx';
const pid='a'.repeat(32),sha='b'.repeat(64);
const item={object_id:'act_one',revision:1,document_sha256:sha,label:'Act One',view:'section',item_count:1};
const base=(family)=>({format:'nvp.slate.filmmaker_navigation.v1',project_id:pid,family,source_modified:false});
function open(container){const d=container.querySelector('details');d.open=true;fireEvent(d,new Event('toggle'));}
afterEach(cleanup);
describe('Large-film section browser',()=>{
  it('loads on demand, follows page cursor and exact selection, never writes',async()=>{
    const api=vi.fn(async path=>{
      const url=new URL(path,'http://localhost');const f=url.searchParams.get('family');
      if(f==='scenes')return {...base(f),items:[],next_after:null};
      if(url.pathname.endsWith('/act_one'))return {...base(f),selection:item,first:0,total:1,next_first:null,items:[{label:'A chosen scene',view:'take'}]};
      if(url.searchParams.get('after')==='cursor')return {...base(f),items:[item],next_after:null};
      return {...base(f),items:[],next_after:'cursor'};
    });
    const {container}=render(<DirectorOriginalSections projectId={pid} api={api}/>);
    expect(api).not.toHaveBeenCalled();open(container);
    await screen.findByText('Nothing to show on this page.');
    fireEvent.click(screen.getByRole('button',{name:'Takes',exact:true}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Next page'}).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Next page'}));
    fireEvent.click(await screen.findByRole('button',{name:'Act One'}));
    await screen.findByText('A chosen scene');
    expect(api.mock.calls.every(call=>call[1]==='GET')).toBe(true);
    expect(api.mock.calls.at(-1)[0]).toContain('digest='+sha);
    fireEvent.click(screen.getByRole('button',{name:'Back to list'}));
    await screen.findByRole('button',{name:'Act One'});
  });
  it('rejects stale exact source identity and suppresses bad results',async()=>{
    const api=vi.fn(async path=>path.includes('/act_one?')?{...base('takes'),selection:{...item,document_sha256:'f'.repeat(64)},first:0,items:[{label:'Wrong footage'}]}:path.includes('family=takes')?{...base('takes'),items:[item],next_after:null}:{...base('scenes'),items:[],next_after:null});
    const {container}=render(<DirectorOriginalSections projectId={pid} api={api}/>);open(container);
    await screen.findByText('Nothing to show on this page.');fireEvent.click(screen.getByRole('button',{name:'Takes',exact:true}));
    fireEvent.click(await screen.findByRole('button',{name:'Act One'}));
    await screen.findByRole('alert');expect(screen.queryByText('Wrong footage')).toBeNull();
  });
});
