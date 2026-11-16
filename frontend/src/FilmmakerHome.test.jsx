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

// Original G04/G07 API-shaped test responses. Never pretend a successful
// scene or editor read returns an empty object: the real director components
// require authoritative Bible and edit fields, including empty source lists.
function preproduction(movie=MOVIE) {
 return {
  format:'nvp.g04.director_preproduction.v1',project_id:movie.id,
  screenplay_revision:movie.revision,mode:movie.screenplay?.trim()?'script':'idea',
  title_conflict:null,scenes:(movie.scenes||[]).map((scene,index)=>({
   id:scene.id,number:scene.number||index+1,heading:scene.heading,
   script_excerpt:scene.text||'',cast:[],dialogue:[],notes:{},
   notes_revision:0,notes_history:[],questions:[],proposals:[],
   location:'',time_of_day:''
  })),
  bible:{story:movie.idea,cast:[],locations:[],props:[],continuity:[],
   facts:[],scene_settings:[],approved_story:[],speakers_to_review:[]},
  screenplay_drafts:[],ready_for_scene_generation:false,filming_authorized:false
 };
}
function emptyFilmEdit(movie=MOVIE) {
 return {
  format:'nvp.g07.edit.v1',project_id:movie.id,revision:0,
  title:movie.title,notes:'',master_gain:1,clips:[],timeline:[],
  duration_tick:0,duration_seconds:0,available_takes:[],
  history:[],ai_suggestions:[],missing_sources:[],
  original_sources_unchanged:true,final_movie_exported:false
 };
}
function readOriginalSubresource(url,movie=MOVIE) {
 const base='/api/projects/'+movie.id;
 if(url===base+'/preproduction'||url===base+'/live/preproduction')
  return preproduction(movie);
 if(url===base+'/edit'||url===base+'/live/edit')return emptyFilmEdit(movie);
 if(url.startsWith(base+'/stage/')||url.startsWith(base+'/live/stage/'))
  return {created:false,revision:0};
 return null;
}

function server(projectList=[snapshot]) {
 const log=[];
 let created=null;
 const handler=vi.fn(async (url, options={})=>{
  log.push({url,method:options.method||'GET'});
  let body={};
  if(url==='/api/status') body={status:'ready'};
  else if(url==='/api/projects' && (options.method||'GET')==='GET')body=projectList;
  else if(url==='/api/projects'&&options.method==='POST') {
   created={...MOVIE,revision:0,scenes:[],screenplay:''};
   body=created;
  }
  else if(url==='/api/projects/'+ID)body=created||MOVIE;
  else if(url==='/api/projects/'+ID+'/protect')body={locked:true};
  else if(url==='/api/projects/'+ID+'/screenplay')body=created||MOVIE;
  else if(url==='/api/creative/models')body={state:'unavailable'};
  else body=readOriginalSubresource(url,created||MOVIE)||{};
  return {ok:true,json:async()=>body};
 });
 vi.stubGlobal('fetch',handler);
 return {log,handler};
}
describe('G03 filmmaker shell (not an AI/render acceptance test)',()=>{
 beforeEach(()=>{window.localStorage.clear()});
 afterEach(()=>{cleanup();vi.unstubAllGlobals();
  window.history.replaceState({},'','/');});

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
  expect(await screen.findByText('No performers required')).toBeTruthy();
  expect(await screen.findByText('Bring this scene to life')).toBeTruthy();
  expect(screen.getByText(/Nothing is filmed yet/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/Edit Film/}));
  expect(screen.getByRole('link',{name:/Open Post-Production Window/}).getAttribute('href'))
    .toContain('postproduction.html');
 });

 it('reports an original movie read failure instead of inventing navigation',async()=>{
  const {handler}=server();
  handler.mockImplementation(async url=>{
   if(url==='/api/status')return {ok:true,json:async()=>({status:'ready'})};
   if(url==='/api/projects')return {ok:true,json:async()=>[snapshot]};
   if(url==='/api/projects/'+ID)return {ok:false,status:409,
     json:async()=>({detail:'Original saved source read was rejected'})};
   if(url==='/api/creative/models')return {ok:true,
     json:async()=>({state:'unavailable'})};
   return {ok:true,json:async()=>({})};
  });
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(await screen.findByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('alert').textContent)
    .toContain('Original saved source read was rejected'));
  expect(screen.queryByRole('navigation',{name:'Filmmaking steps'})).toBeNull();
  expect(screen.getByRole('heading',{name:'Resume Working'})).toBeTruthy();
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
    const original=url.startsWith('/api/projects/'+B+'/')?second:MOVIE;
    const source=readOriginalSubresource(url,original);
    if(source)return {ok:true,json:async()=>source};
    throw new Error('Unexpected URL: '+url);
  });
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getAllByText('EXT. FOREST - MORNING')[0]).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'Resume movie: Coastal Documentary'}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Coastal Documentary'})).toBeTruthy());
  expect(screen.getAllByText('EXT. COAST - DAY')[0]).toBeTruthy();
  expect(document.querySelector('.film-script-excerpt')?.textContent||'').not.toContain('Mist moves between trees.');
  fireEvent.click(screen.getByRole('button',{name:'Resume movie: Forest Documentary'}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy());
  expect(screen.getAllByText('EXT. FOREST - MORNING')[0]).toBeTruthy();
 });

 it('keeps the real source-line screenplay editor editable on resume',async()=>{
  server();
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('navigation',{name:'Filmmaking steps'})).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:/Script/}));
  const editor=screen.getByRole('textbox',{name:'Edit screenplay'});
  expect(editor.value).toBe(MOVIE.screenplay);
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
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy());
  await waitFor(()=>expect(screen.getByText(/No frozen Takes are available yet/)).toBeTruthy());
  fireEvent(window,new StorageEvent('storage',{key:'nvp-film-lock-'+ID,newValue:'1'}));
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Forest Documentary'})).toBeNull());
  expect(screen.getByText(/This movie is locked/)).toBeTruthy();
  expect(screen.queryByText(/No frozen Takes are available yet/)).toBeNull();
  window.history.replaceState({},'','/');
 });

 it('does not silently discard edited screenplay on movie switch',async()=>{
  const another='b'.repeat(32);
  const original={...snapshot};
  const other={...snapshot,id:another,title:'Other Movie'};
  const {handler}=server([original,other]);
  handler.mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,json:async()=>({status:'ready'})};
    if(url==='/api/projects')return {ok:true,json:async()=>[original,other]};
    if(url==='/api/projects/'+ID)return {ok:true,json:async()=>MOVIE};
    if(url==='/api/projects/'+another)return {ok:true,json:async()=>({...MOVIE,id:another,title:'Other Movie'})};
    const original=url.startsWith('/api/projects/'+another+'/')
      ?{...MOVIE,id:another,title:'Other Movie'}:MOVIE;
    const source=readOriginalSubresource(url,original);
    if(source)return {ok:true,json:async()=>source};
    throw new Error('Unexpected request '+url);
  });
  const confirmation=vi.spyOn(window,'confirm').mockReturnValue(false);
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:/Script/}));
  const field=screen.getByRole('textbox',{name:'Edit screenplay'});
  fireEvent.change(field,{target:{value:'EXT. MOUNTAIN - DAY\n\nAn unsaved scene.'}});
  fireEvent.click(screen.getByRole('button',{name:'Resume movie: Other Movie'}));
  expect(confirmation).toHaveBeenCalled();
  expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy();
  expect(field.value).toContain('An unsaved scene.');
  confirmation.mockRestore();
 });

 it('relock from a second director window clears cached screenplay immediately',async()=>{
  server();
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Resume movie/i}));
  await waitFor(()=>expect(screen.getByRole('heading',{name:'Forest Documentary'})).toBeTruthy());
  fireEvent(window,new StorageEvent('storage',{key:'nvp-film-lock-'+ID,newValue:'2'}));
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Forest Documentary'})).toBeNull());
  expect(screen.getByText(/This movie was locked/)).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Resume Working'})).toBeTruthy();
 });

 it('creates an opt-in encrypted movie using protected host route, never plaintext creation',async()=>{
  const sent=[];
  const secure={...MOVIE,encrypted:true,revision:0,idea:'A private film'};
  vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
    sent.push({url,method:options.method||'GET',data:options.body});
    let data={};
    if(url==='/api/status')data={status:'ready',capabilities:{
      project_file_encryption:'new_windows_movies_only'}};
    else if(url==='/api/projects')data=[];
    else if(url==='/api/projects/encrypted'&&options.method==='POST')data=secure;
    else if(url==='/api/projects/'+ID+'/live')data=secure;
    else if(url.startsWith('/api/projects/'+ID+'/live/film/'))
      return {ok:false,status:409,json:async()=>({
        detail:'Approve the original scene before filming'})};
    else data=readOriginalSubresource(url,secure)||{};
    return {ok:true,json:async()=>data};
  }));
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'New Movie'}));
  const option=await screen.findByLabelText('Encrypt this new movie on this Windows account');
  fireEvent.click(option);
  fireEvent.change(screen.getByLabelText('Movie title'),{target:{value:'Private nature film'}});
  fireEvent.change(screen.getByLabelText('Movie passphrase'),
    {target:{value:'Human-operator-private-passphrase-2026'}});
  fireEvent.change(screen.getByLabelText('Confirm movie passphrase'),
    {target:{value:'Human-operator-private-passphrase-2026'}});
  fireEvent.click(screen.getByRole('button',{name:'Next →'}));
  await waitFor(()=>expect(sent.some(x=>x.url==='/api/projects/encrypted'&&x.method==='POST')).toBe(true));
  expect(sent.some(x=>x.url==='/api/projects'&&x.method==='POST')).toBe(false);
  await waitFor(()=>expect(screen.getByText(/Encrypted movie/)).toBeTruthy());
  fireEvent.click(within(screen.getByRole('navigation',{name:'Filmmaking steps'}))
    .getByRole('button',{name:/Film Scenes/}));
  await waitFor(()=>expect(screen.getByRole('alert').textContent)
    .toContain('Approve the original scene before filming'));
  expect(screen.getByRole('button',{name:'Review and approve the visual scene'}))
    .toBeTruthy();
  expect(screen.queryByText(/Original recording saved/)).toBeNull();
 });

 it('reopens an unlocked encrypted movie only via the host secure route',async()=>{
  const encrypted={...snapshot,locked:true,unlocked:false,encrypted:true};
  const calls=[];
  let granted=false;
  vi.stubGlobal('fetch',vi.fn(async(url,options={})=>{
    calls.push(url);
    if(url==='/api/status')return {ok:true,json:async()=>({status:'ready'})};
    if(url==='/api/projects')return {ok:true,json:async()=>
      [{...encrypted,unlocked:granted}]};
    if(url==='/api/projects/'+ID+'/unlock') {
      granted=true;return {ok:true,json:async()=>({locked:false,encrypted:true})};
    }
    if(url==='/api/projects/'+ID+'/live')
      return {ok:true,json:async()=>({...MOVIE,encrypted:true})};
    throw Error('Unexpected insecure request: '+url);
  }));
  render(<FilmmakerHome/>);
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'Resume Working'}));
  fireEvent.click(screen.getByRole('button',{name:/Forest Documentary.*Locked/i}));
  const dialog=screen.getByRole('dialog',{name:'Unlock Movie'});
  fireEvent.change(within(dialog).getByLabelText(/Movie passphrase/),
    {target:{value:'Human-operator-private-passphrase-2026'}});
  fireEvent.click(within(dialog).getByRole('button',{name:'Unlock'}));
  await waitFor(()=>expect(calls.includes('/api/projects/'+ID+'/live')).toBe(true));
  expect(calls.includes('/api/projects/'+ID)).toBe(false);
 });

 it('keeps AI unavailability explicit rather than pretending to generate film',async()=>{
  server();
  render(<FilmmakerHome/>);
  expect((await screen.findByLabelText('AI connection status')).textContent)
    .toBe('AI unavailable');
 });
});
