import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup,within,act} from '@testing-library/react';
import DirectorEditorialSections from './DirectorEditorialSections.jsx';
const pid='a'.repeat(32),digest='b'.repeat(64),approval='c'.repeat(64);
const edit={kind:'edit',revision:1,digest,label:'Edit 1 — Original',clip_count:4,duration_tick:'56448000000'};
const group={kind:'section',section_id:'d'.repeat(32),digest,label:'First act',clip_count:4,duration_tick:'56448000000'};
const base={format:'nvp.g07.sections.v1',project_id:pid,render_approved:false};
const directory=(family,items=[],next_after=null)=>({...base,family,items,next_after,active_revision:1,active_section:null});
function open(container){const d=container.querySelector('details');d.open=true;fireEvent(d,new Event('toggle'));}
const click=name=>fireEvent.click(screen.getByRole('button',{name,exact:true}));
afterEach(cleanup);
describe('Filmmaker editorial sections',()=>{
 it('uses sealed routes and exact ordered source slices; save does not activate',async()=>{
  const api=vi.fn(async (path,method,body)=>{
   if(path.endsWith('/preview'))return {...base,title:body.title,clip_count:2,duration_tick:'28224000000',digest:approval};
   if(path.endsWith('/save'))return {...base,selection:{...group,label:body.title}};
   if(path.endsWith('/page'))return {...base,selection:edit,first:0,items:[{label:'Cut 1'}],next_first:null};
   const u=new URL(path,'http://localhost');const family=u.searchParams.get('family');
   return family==='edits'?directory(family,[edit]):directory(family);
  });
  const {container}=render(<DirectorEditorialSections projectId={pid} encrypted api={api}/>);open(container);
  await screen.findByText('Nothing saved on this page.');click('Saved edits');
  fireEvent.click(await screen.findByRole('button',{name:edit.label}));await screen.findByText('Cut 1');
  fireEvent.change(screen.getByLabelText('First cut'),{target:{value:'2'}});fireEvent.change(screen.getByLabelText('Last cut'),{target:{value:'3'}});click('Add cut range');
  fireEvent.change(screen.getByLabelText('Section name'),{target:{value:'Act A'}});click('Review section');await screen.findByRole('button',{name:'Save section'});
  expect(api.mock.calls.some(([p])=>p.endsWith('/save'))).toBe(false);click('Save section');await screen.findByText('Section saved.');
  const save=api.mock.calls.find(([p])=>p.endsWith('/save'));
  expect(save[2]).toEqual({title:'Act A',children:[{kind:'edit',revision:1,digest,first:1,count:2}],digest:approval});
  expect(api.mock.calls.every(([p])=>p.startsWith(`/api/projects/${pid}/live/edit/sections`))).toBe(true);
  expect(api.mock.calls.some(([p])=>p.endsWith('/activate'))).toBe(false);
 });
 it('requires separate activation review, supports refusal and refreshes the existing edit',async()=>{
  const onActivated=vi.fn(async()=>{});
  const api=vi.fn(async(path,method,body)=>{
   if(path.endsWith('/page'))return {...base,selection:group,first:0,items:[],next_first:null};
   if(path.endsWith('/activation-preview'))return {...base,section_id:group.section_id,section_digest:digest,expected_revision:body.expected_revision,approval_digest:approval,clip_count:4,duration_tick:group.duration_tick};
   if(path.endsWith('/activate'))return {...base,revision:2,original_sources_unchanged:true};
   return directory('sections',[group]);
  });
  const {container}=render(<DirectorEditorialSections projectId={pid} api={api} activeRevision={1} onActivated={onActivated}/>);open(container);
  fireEvent.click(await screen.findByRole('button',{name:group.label}));await screen.findByRole('button',{name:'Review as active edit'});click('Review as active edit');await screen.findByRole('button',{name:'Use this edit'});click('Cancel');
  expect(api.mock.calls.some(([p])=>p.endsWith('/activate'))).toBe(false);
  click('Review as active edit');await screen.findByRole('button',{name:'Use this edit'});click('Use this edit');await waitFor(()=>expect(onActivated).toHaveBeenCalledWith(2));
  expect(api.mock.calls.find(([p])=>p.endsWith('/activate'))[2]).toEqual({section_id:group.section_id,digest,expected_revision:1,approval_digest:approval});
 });
 it('rejects activation review arriving after the edit head changed',async()=>{
  let resolve;const api=vi.fn(async(path)=>path.endsWith('/activation-preview')?new Promise(r=>{resolve=r;}):path.endsWith('/page')?{...base,selection:group,first:0,items:[],next_first:null}:directory('sections',[group]));
  const onActivated=vi.fn();const {container,rerender}=render(<DirectorEditorialSections projectId={pid} api={api} activeRevision={1} onActivated={onActivated}/>);open(container);
  fireEvent.click(await screen.findByRole('button',{name:group.label}));await screen.findByRole('button',{name:'Review as active edit'});click('Review as active edit');
  rerender(<DirectorEditorialSections projectId={pid} api={api} activeRevision={2} onActivated={onActivated}/>);
  await act(async()=>resolve({...base,section_id:group.section_id,section_digest:digest,expected_revision:1,approval_digest:approval}));
  expect(screen.queryByRole('button',{name:'Use this edit'})).toBeNull();expect(onActivated).not.toHaveBeenCalled();
 });
 it('navigates scene takes using an exact scene identity and bounded cursor',async()=>{
  const scene={kind:'scene',scene_id:'SC_abcdef012345',revision:3,digest,label:'Scene 1'};
  const api=vi.fn(async(path,method,body)=>path.endsWith('/page')?{...base,selection:scene,first:0,items:[{kind:'take',label:body.after?'Later take':'First take'}],next_after:body.after?null:'cursor'}:path.includes('family=scenes')?directory('scenes',[scene]):directory('sections'));
  const {container}=render(<DirectorEditorialSections projectId={pid} encrypted api={api}/>);open(container);await screen.findByText('Nothing saved on this page.');click('Scenes');fireEvent.click(await screen.findByRole('button',{name:scene.label}));await screen.findByText('First take');click('Next');await screen.findByText('Later take');
  expect(api.mock.calls.at(-1)[2]).toEqual({selection:{kind:'scene',scene_id:scene.scene_id,revision:3,digest},first:0,limit:32,after:'cursor'});
 });
});

it('keeps the source browser collapsed and scene stage browse-only',async()=>{
 const api=vi.fn(async(path)=>directory('scenes'));
 const {container}=render(<DirectorEditorialSections projectId={pid} api={api} browseOnly/>);
 expect(api).not.toHaveBeenCalled();open(container);await screen.findByText('Nothing saved on this page.');
 expect(screen.queryByRole('button',{name:'Saved edits'})).toBeNull();
 expect(screen.queryByLabelText('Section name')).toBeNull();
 expect(api.mock.calls[0][0]).toContain('family=scenes');
});
it('has both directions for arranging selected cuts, with explicit review',async()=>{
 const other={...edit,revision:2,digest:'e'.repeat(64),label:'Edit 2 — Alternate'};
 const api=vi.fn(async(path,method,body)=>path.endsWith('/preview')?{...base,title:body.title,clip_count:8,duration_tick:'112896000000',digest:approval}:path.includes('family=edits')?directory('edits',[edit,other]):directory('sections'));
 const {container}=render(<DirectorEditorialSections projectId={pid} api={api}/>);open(container);await screen.findByText('Nothing saved on this page.');click('Saved edits');await screen.findByText(other.label);
 screen.getAllByRole('button',{name:'Add to section'}).forEach(b=>fireEvent.click(b));
 click('Move 1 down');fireEvent.change(screen.getByLabelText('Section name'),{target:{value:'Act two'}});click('Review section');await screen.findByRole('button',{name:'Save section'});
 const request=api.mock.calls.find(([p])=>p.endsWith('/preview'));
 expect(request[2].children.map(x=>x.revision)).toEqual([2,1]);
 expect(api.mock.calls.some(([p])=>p.endsWith('/activate'))).toBe(false);
});
it('uses the separately reviewed chapter timeline when the arrangement exceeds the finite edit',async()=>{
 const large={...group,clip_count:280,duration_tick:'3951360000000'};const onActivated=vi.fn(async()=>{});
 const api=vi.fn(async(path,method,body)=>{
  if(path.endsWith('/page'))return {...base,selection:large,first:0,items:[],next_first:null};
  if(path.endsWith('/paged-activation-preview'))return {...base,section_id:large.section_id,section_digest:digest,expected_revision:body.expected_revision,approval_digest:approval,clip_count:280,duration_tick:large.duration_tick,paged:true};
  if(path.endsWith('/paged-activate'))return {...base,revision:2,paged:true,original_sources_unchanged:true};
  return directory('sections',[large]);
 });
 const {container}=render(<DirectorEditorialSections projectId={pid} encrypted api={api} activeRevision={1} onActivated={onActivated}/>);open(container);fireEvent.click(await screen.findByRole('button',{name:large.label}));await screen.findByRole('button',{name:'Review as active edit'});click('Review as active edit');await screen.findByRole('button',{name:'Use this edit'});
 expect(screen.getByText(/Sampled scene previews are available; final export is not yet available/)).toBeTruthy();click('Use this edit');await waitFor(()=>expect(onActivated).toHaveBeenCalledWith(2));expect(api.mock.calls.some(([p])=>p.endsWith('/paged-activate'))).toBe(true);expect(api.mock.calls.some(([p])=>p.endsWith('/activate'))).toBe(false);
});
