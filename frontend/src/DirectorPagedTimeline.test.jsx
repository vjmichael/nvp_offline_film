import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import DirectorPagedTimeline from './DirectorPagedTimeline.jsx';
const pid='a'.repeat(32),digest='b'.repeat(64),format='nvp.g07.paged_active_edit.v1';
const edit={format,project_id:pid,revision:3,active_digest:digest,clip_count:280,duration_tick:'3951360000000',title:'Feature arrangement'};
const reply=body=>({format,project_id:pid,revision:body.revision,active_digest:body.digest,first:body.first,total:280,render_approved:false,items:Array.from({length:Math.min(32,280-body.first)},(_,i)=>({index:body.first+i,scene_id:'SC_abcdef012345',start_tick:String(BigInt(body.first+i)*14112000000n),end_tick:String(BigInt(body.first+i+1)*14112000000n),transition:'cut'})),next_first:body.first+32<280?body.first+32:null});
afterEach(cleanup);
describe('Chapter-based active edit',()=>{
 it('keeps only one page mounted and jumps to the final cuts in protected storage',async()=>{
  const api=vi.fn(async(_,__,body)=>reply(body));render(<DirectorPagedTimeline projectId={pid} encrypted edit={edit} api={api} sceneTitles={{SC_abcdef012345:'Valley'}}/>);
  await screen.findByRole('list',{name:'Current edit cuts'});expect(screen.getAllByRole('listitem')).toHaveLength(32);expect(screen.getByText('Cuts 1–32 of 280')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Next'}));await screen.findByText('Cuts 33–64 of 280');await waitFor(()=>expect(screen.getAllByRole('listitem')).toHaveLength(32));
  fireEvent.change(screen.getByLabelText('Go to cut'),{target:{value:'280'}});fireEvent.click(screen.getByRole('button',{name:'Go'}));await waitFor(()=>expect(screen.getAllByRole('listitem')).toHaveLength(24));expect(screen.getByText('Cuts 257–280 of 280')).toBeTruthy();expect(screen.getByText('280',{selector:'.film-active-cut-number'}).closest('li').getAttribute('aria-current')).toBe('true');
  expect(api.mock.calls.at(-1)[0]).toContain('/live/edit/sections/active-page');expect(api.mock.calls.at(-1)[2]).toEqual({revision:3,digest,first:256,limit:32});expect(screen.getByRole('button',{name:'Next'}).disabled).toBe(true);
  expect(screen.getByText(/export are not yet available/)).toBeTruthy();
 });
 it('rejects a wrong revision and never displays the returned material',async()=>{
  const api=vi.fn(async(_,__,body)=>({...reply(body),revision:2}));render(<DirectorPagedTimeline projectId={pid} edit={edit} api={api}/>);
  await screen.findByRole('alert');expect(screen.queryByRole('listitem')).toBeNull();
 });
 it('discards late previous-project responses after a scope change',async()=>{
  let resolve;const api=vi.fn(async(_,__,body)=>new Promise(r=>{resolve=r;}));const {rerender}=render(<DirectorPagedTimeline projectId={pid} edit={edit} api={api}/>);
  const oldResolve=resolve;
  rerender(<DirectorPagedTimeline projectId={'c'.repeat(32)} edit={{...edit,revision:4,active_digest:'d'.repeat(64)}} api={api}/>);
  await act(async()=>oldResolve(reply({revision:3,digest,first:0})));
  expect(screen.queryByRole('listitem')).toBeNull();
  await act(async()=>resolve({...reply({revision:4,digest:'d'.repeat(64),first:0}),project_id:'c'.repeat(32)}));await screen.findByRole('list',{name:'Current edit cuts'});
 });
});

it('mounts the actual separate filmmaker editor and clears the paged edit when locked',async()=>{
 const {default:PostProduction}=await import('./PostProduction.jsx');
 const original=window.location.pathname+window.location.search;
 window.history.replaceState({},'',`/postproduction.html?project=${pid}&encrypted=1`);
 const response=x=>({ok:true,json:async()=>x});
 const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async(url,options)=>{
  if(url===`/api/projects/${pid}/live`)return response({id:pid,encrypted:true,revision:1,title:'Protected movie',scenes:[]});
  if(url.endsWith('/live/edit'))return response({...edit,notes:'',master_gain:1,clips:[],timeline:[],missing_sources:[],history:[{revision:1}]});
  if(url.endsWith('/active-page'))return response(reply(JSON.parse(options.body)));
  if(url.endsWith('/preproduction'))return response({scenes:[]});
  if(url==='/api/creative/models')return response({state:'unavailable'});
  throw Error('Unexpected request '+url);
 });
 try{
  render(<PostProduction/>);await screen.findByRole('list',{name:'Current edit cuts'});
  expect(screen.getByRole('heading',{name:'Protected movie'})).toBeTruthy();expect(screen.queryByLabelText('Select a frozen Take')).toBeNull();
  fireEvent(window,new StorageEvent('storage',{key:`nvp-film-lock-${pid}`,newValue:'1'}));await screen.findByText(/This movie is locked/);
  expect(screen.queryByRole('list',{name:'Current edit cuts'})).toBeNull();expect(screen.queryByText('Feature arrangement')).toBeNull();
 }finally{fetcher.mockRestore();window.history.replaceState({},'',original);}
});
