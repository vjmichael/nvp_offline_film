import React from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,within,cleanup} from '@testing-library/react';
import FilmmakerHome from './FilmmakerHome.jsx';
import PostProduction from './PostProduction.jsx';

const ID='a'.repeat(32);
const MOVIE={
 id:ID,title:'Forest Documentary',idea:'Fog in the forest',
 screenplay:'EXT. FOREST - MORNING\n\nMist moves between trees.',
 revision:1,scenes:[{id:'SC_123456789abc',number:1,heading:'EXT. FOREST - MORNING',
 text:'EXT. FOREST - MORNING\n\nMist moves between trees.',
 characters:[],dialogue:[],shots:[]}],
};
const snapshot={id:ID,title:MOVIE.title,idea:MOVIE.idea,revision:1,
 updated_at:'2026-11-10T00:00:00Z',locked:false,unlocked:true};

function server(projectList=[snapshot]) {
 const log=[];
 const handler=vi.fn(async (url, options={})=>{
  log.push({url,method:options.method||'GET'});
  let body={};
  if(url==='/api/status') body={status:'ready'};
  else if(url==='/api/projects' && (options.method||'GET')==='GET')body=projectList;
  else if(url==='/api/projects'&&options.method==='POST')body={...MOVIE,revision:0,scenes:[],screenplay:''};
  else if(url==='/api/projects/'+ID)body=MOVIE;
  else if(url==='/api/projects/'+ID+'/protect')body={locked:true};
  else if(url==='/api/projects/'+ID+'/screenplay')body=MOVIE;
  else body={};
  return {ok:true,json:async()=>body};
 });
 vi.stubGlobal('fetch',handler);
 return {log,handler};
}
describe('G03 filmmaker shell (not an AI/render acceptance test)',()=>{
 beforeEach(()=>{window.localStorage.clear()});
 afterEach(()=>{cleanup();vi.unstubAllGlobals()});

 it('opens with the filmmaker dialogue and never shows engineering tabs',async()=>{
  server();
  render(<FilmmakerHome/>);
  const dialog=await screen.findByRole('dialog');
  expect(within(dialog).getByText(/new movie or resume working/)).toBeTruthy();
  expect(screen.getByLabelText('Your movie projects')).toBeTruthy();
  expect(screen.queryByText(/Protobuf|FFmpeg|workers|GPU allocation|cgroup/i)).toBeNull();
  fireEvent.click(within(dialog).getByRole('button',{name:'New Movie'}));
  expect(screen.getByText(/Start with a script or just an idea/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'Next →'}).disabled).toBe(true);
 });

 it('new movie can start with an idea and expose the five creative steps',async()=>{
  const {log}=server([]);
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'New Movie'}));
  fireEvent.change(screen.getByLabelText('Movie title'),{target:{value:MOVIE.title}});
  fireEvent.change(screen.getByLabelText('Tell us what your movie is about'),{target:{value:'Fog over the valley'}});
  fireEvent.click(screen.getByRole('button',{name:'Next →'}));
  await waitFor(()=>expect(log.some(x=>x.method==='POST'&&x.url==='/api/projects')).toBe(true));
  await waitFor(()=>expect(screen.getByRole('navigation',{name:'Filmmaking steps'})).toBeTruthy());
  expect(screen.getByRole('button',{name:/Set Up Scenes/})).toBeTruthy();
  expect(screen.getByRole('button',{name:/Edit Film/})).toBeTruthy();
  expect(screen.queryByText('Stage 3D scene')).toBeNull();
 });

 it('resumes an existing film with actor-free scenes and truthful stage status',async()=>{
  server();
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('navigation',{name:'Filmmaking steps'})).toBeTruthy());
  expect(screen.getByText('Actor-free scenes welcome')).toBeTruthy();
  expect(screen.getByText('Scene preview not generated')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/Edit Film/}));
  expect(screen.getByRole('link',{name:/Open Post-Production Window/}).getAttribute('href'))
    .toContain('postproduction.html');
 });

 it('switches between two saved movies without reusing the previous scene',async()=>{
  const B='b'.repeat(32);
  const second={...MOVIE,id:B,title:'Coastal Documentary',idea:'Waves by the coast',
    screenplay:'EXT. COAST - DAY\n\nWaves move.',scenes:[{
      id:'SC_222222222222',number:1,heading:'EXT. COAST - DAY',
      text:'EXT. COAST - DAY\n\nWaves move.',characters:[],dialogue:[],shots:[]
    }]};
  const other={...snapshot,id:B,title:second.title,idea:second.idea};
  const {handler}=server([snapshot,other]);
  handler.mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,json:async()=>({status:'ready'})};
    if(url==='/api/projects')return {ok:true,json:async()=>[snapshot,other]};
    if(url==='/api/projects/'+ID)return {ok:true,json:async()=>MOVIE};
    if(url==='/api/projects/'+B)return {ok:true,json:async()=>second};
    throw new Error('Unexpected URL: '+url);
  });
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByText('EXT. FOREST - MORNING')).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'Resume movie: Coastal Documentary'}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Coastal Documentary'})).toBeTruthy());
  expect(screen.getByText('EXT. COAST - DAY')).toBeTruthy();
  expect(screen.queryByText('Mist moves between trees.')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Resume movie: Forest Documentary'}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy());
  expect(screen.getByText('EXT. FOREST - MORNING')).toBeTruthy();
 });

 it('keeps the real source-line screenplay editor editable on resume',async()=>{
  server();
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('navigation',{name:'Filmmaking steps'})).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:/Script/}));
  const editor=screen.getByRole('textbox',{name:'Edit screenplay'});
  const revision='EXT. GARDEN - DAWN\n\nA bird lands.';
  fireEvent.change(editor,{target:{value:revision}});
  expect(editor.value).toBe(revision);
  expect(screen.getByRole('button',{name:'Save Screenplay'}).disabled).toBe(false);
 });

 it('requests unlock before reading a locked film',async()=>{
  const {log}=server([{...snapshot,locked:true,unlocked:false,idea:undefined}]);
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Locked/i}));
  expect(screen.getByRole('dialog',{name:'Unlock Movie'})).toBeTruthy();
  expect(log.some(x=>x.url==='/api/projects/'+ID)).toBe(false);
 });

 it('clears a separate Post-Production window when the film is locked elsewhere',async()=>{
  server();
  window.history.replaceState({},'', '/postproduction.html?project='+ID);
  render(<PostProduction/>);
  await waitFor(()=>expect(screen.getByText('EXT. FOREST - MORNING')).toBeTruthy());
  fireEvent(window,new StorageEvent('storage',{key:'nvp-film-lock-'+ID,newValue:'1'}));
  await waitFor(()=>expect(screen.queryByText('EXT. FOREST - MORNING')).toBeNull());
  expect(screen.getByText(/This movie is locked/)).toBeTruthy();
  window.history.replaceState({},'','/');
 });

 it('keeps AI unavailability explicit rather than pretending to generate film',async()=>{
  server();
  render(<FilmmakerHome/>);
  expect(await screen.findByText('AI assistance not connected')).toBeTruthy();
 });
});
