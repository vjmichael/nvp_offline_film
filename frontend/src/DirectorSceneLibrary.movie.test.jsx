import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import DirectorSceneLibrary from './DirectorSceneLibrary.jsx';

// Keep the test about the G04 UI contract, not unrelated real USD staging.
vi.mock('./DirectorWorldStage.jsx',()=>({default:()=>null}));

const ID='a'.repeat(32);
const NOTE_KEYS=['description','location','time_of_day','era','season',
 'weather','action','performers','dialogue','director_note'];
const notes=Object.fromEntries(NOTE_KEYS.map(x=>[x,'']));
const movie={id:ID,title:'Two Scene Film',revision:1,screenplay:'INT. ROOM - DAY',
 encrypted:false};

function scene(n) {
 return {id:'SC_'+String(n).padStart(12,'0'),
  number:n,heading:n===1?'INT. ROOM - DAY':'EXT. GARDEN - NIGHT',
  origin:'script_derived',source_sha256:'d'.repeat(64),
  script_excerpt:'INT. ROOM - DAY',script_lines:{start:n,end:n+2},
  notes:{...notes},notes_revision:0,notes_history:[],cast:[],
  dialogue:[],proposals:[],questions:[],location:'',time_of_day:''};
}
function view(count=2){
 return {format:'nvp.g04.director_preproduction.v1',project_id:ID,
  screenplay_revision:1,screenplay_sha256:'e'.repeat(64),mode:'script',
  scenes:Array.from({length:count},(_,i)=>scene(i+1)),
  bible:{story:'',cast:[],locations:[],props:[],facts:[],continuity:[],
   scene_settings:[],approved_story:[],speakers_to_review:[]},
  screenplay_drafts:[],title_conflict:null};
}
function serve({encrypted=false,available=true,count=2}={}){
 const calls=[];
 const base='/api/projects/'+ID+(encrypted?'/live':'')+'/preproduction';
 const original=view(count);
 const fetcher=vi.fn(async (url,options={})=>{
  calls.push({url,options});
  if(url==='/api/creative/models')
   return {ok:true,json:async()=>({state:available?'available':'unavailable'})};
  if(url===base&&(!options.method||options.method==='GET'))
   return {ok:true,json:async()=>original};
  if(url===base+'/movie/suggestions'&&options.method==='POST'){
   return {ok:true,json:async()=>({...original,
    movie_breakdown:{status:'UNAPPROVED_PROPOSAL',
     creator_approval_granted:false,native_worker_authorized:false,
     partial_publication_performed:false},
    scenes:original.scenes.map(x=>({...x,proposals:[{
      id:'f'.repeat(32),category:'prop',value:'Unapproved set idea',
      status:'proposed',stale:false}]}))})};
  }
  throw new Error('Unexpected request: '+url);
 });
 vi.stubGlobal('fetch',fetcher);
 return {calls,base};
}

describe('PLAN-03/04 director whole-movie proposals',()=>{
 afterEach(()=>{cleanup();vi.unstubAllGlobals()});

 it('requests one bounded whole-movie snapshot without approving ideas',async()=>{
  const {calls,base}=serve();
  render(<DirectorSceneLibrary movie={movie} onScript={()=>{}} onFilm={()=>{}}/>);
  const button=await screen.findByRole('button',{name:'Suggest Ideas for All Scenes'});
  await waitFor(()=>expect(button.disabled).toBe(false));
  fireEvent.click(button);
  await waitFor(()=>expect(calls.some(x=>x.url===base+'/movie/suggestions')).toBe(true));
  const request=calls.find(x=>x.url===base+'/movie/suggestions');
  expect(request.options.method).toBe('POST');
  expect(JSON.parse(request.options.body)).toEqual({expected_screenplay_revision:1});
  expect(calls.filter(x=>x.url.includes('/decision'))).toHaveLength(0);
  expect(await screen.findByText(/Nothing was approved or filmed/)).toBeTruthy();
  expect(screen.getAllByText(/Suggested · awaiting your decision/).length).toBeGreaterThan(0);
 });

 it('uses the same protected-film route and never exposes a model endpoint',async()=>{
  const {calls,base}=serve({encrypted:true});
  render(<DirectorSceneLibrary movie={{...movie,encrypted:true}}
    onScript={()=>{}} onFilm={()=>{}}/>);
  const button=await screen.findByRole('button',{name:'Suggest Ideas for All Scenes'});
  await waitFor(()=>expect(button.disabled).toBe(false));
  fireEvent.click(button);
  await waitFor(()=>expect(calls.some(x=>x.url===base+'/movie/suggestions')).toBe(true));
  expect(calls.some(x=>/localhost|\/v1\/completions|\/worker\//.test(x.url))).toBe(false);
 });

 it('does not request a model when unavailable or outside eight-scene scope',async()=>{
  const unavailable=serve({available:false});
  render(<DirectorSceneLibrary movie={movie} onScript={()=>{}} onFilm={()=>{}}/>);
  const disabled=await screen.findByRole('button',{name:'Suggest Ideas for All Scenes'});
  expect(disabled.disabled).toBe(true);
  expect(unavailable.calls.filter(x=>x.url.endsWith('/movie/suggestions'))).toHaveLength(0);
  cleanup();
  vi.unstubAllGlobals();
  serve({count:9});
  render(<DirectorSceneLibrary movie={movie} onScript={()=>{}} onFilm={()=>{}}/>);
  await screen.findByText('Set Up Scenes');
  expect(screen.queryByRole('button',{name:'Suggest Ideas for All Scenes'})).toBeNull();
 });
});
