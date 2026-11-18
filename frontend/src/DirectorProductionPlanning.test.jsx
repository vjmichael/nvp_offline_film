// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import DirectorProductionPlanning from './DirectorProductionPlanning.jsx';

const movie={id:'a'.repeat(32),revision:1,scenes:[]};
const source={object_id:'TakeOne',label:'Entrance',kind:'take',revision:1,document_sha256:'b'.repeat(64),changes:['retake']};
const proposal={project_id:movie.id,source_id:'TakeOne',source_revision:1,source_sha256:source.document_sha256,change_kind:'retake',intention:'Try a slower entrance',screenplay_scene_id:null};
const preview={project_id:movie.id,source,worker_authorized:false,planning_approval_available:true,preview_sha256:'c'.repeat(64),indexed_source_lineage:[source],indexed_downstream:[],story_context:{approved_facts:0}};
function native(){return {wo6_plan_catalog:vi.fn(async()=>({project_id:movie.id,sources:[source],saved_plans:[]})),wo6_plan_preview:vi.fn(async()=>preview),wo6_plan_save:vi.fn(async()=>({status:'DENIED',worker_authorized:false})),wo6_plan_read:vi.fn()};}
afterEach(()=>{cleanup();delete window.pywebview;});
async function open(api){const {container}=render(<DirectorProductionPlanning movie={movie} nativeBridge={api}/>);await waitFor(()=>expect(container.querySelector('details')).toBeTruthy());container.querySelector('details').open=true;fireEvent.click(screen.getByRole('button',{name:'Open Production Planning'}));await waitFor(()=>expect(screen.getByLabelText('Choose source')).toBeTruthy());fireEvent.change(screen.getByLabelText('Choose source'),{target:{value:'TakeOne'}});fireEvent.change(screen.getByLabelText('Creative intention'),{target:{value:proposal.intention}});}
it('uses native preview and refuses to claim a saved plan after denied consent',async()=>{const api=native();await open(api);expect(screen.queryByRole('button',{name:'Save Creative Plan'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Preview Changes'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Save Creative Plan'})).toBeTruthy());expect(api.wo6_plan_preview).toHaveBeenCalledWith(proposal);fireEvent.click(screen.getByRole('button',{name:'Save Creative Plan'}));await waitFor(()=>expect(screen.getByText('Plan not saved.')).toBeTruthy());expect(api.wo6_plan_save).toHaveBeenCalledWith({proposal,preview_sha256:preview.preview_sha256});});
it('changing an intention invalidates the preview and requires a new native request',async()=>{const api=native();await open(api);fireEvent.click(screen.getByRole('button',{name:'Preview Changes'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Save Creative Plan'})).toBeTruthy());fireEvent.change(screen.getByLabelText('Creative intention'),{target:{value:'Change the camera'}});expect(screen.queryByRole('button',{name:'Save Creative Plan'})).toBeNull();expect(api.wo6_plan_save).not.toHaveBeenCalled();});
it('does not expose a browser substitute or bypass protected movie scope',()=>{const api=native();const {container,rerender}=render(<DirectorProductionPlanning movie={movie}/>);expect(container.querySelector('details')).toBeNull();rerender(<DirectorProductionPlanning movie={{...movie,encrypted:true}} nativeBridge={api}/>);expect(container.querySelector('details')).toBeNull();expect(api.wo6_plan_catalog).not.toHaveBeenCalled();});

it('requires a saved plan and a separate native request for a new Take',async()=>{const api=native();const record={object_id:'PlanOne',document_sha256:'d'.repeat(64)};api.wo6_plan_catalog.mockResolvedValue({project_id:movie.id,sources:[source],saved_plans:[record]});api.wo6_plan_read.mockResolvedValue({record,data:{plan:{project_id:movie.id,request:proposal,source}},worker_authorized:false});api.wo6_retake_execute=vi.fn(async()=>({status:'VERIFIED_NEW_TAKE',project_id:movie.id,take_id:'NewTake',worker_executed:true,film_approved:false}));await open(api);expect(api.wo6_retake_execute).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Open Plan 1'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Create Separate Take'})).toBeTruthy());fireEvent.click(screen.getByRole('button',{name:'Create Separate Take'}));await waitFor(()=>expect(screen.getByText('New Take created. The original is unchanged; no movie has been rendered.')).toBeTruthy());expect(api.wo6_retake_execute).toHaveBeenCalledWith({project_id:movie.id,plan_id:'PlanOne',plan_sha256:record.document_sha256,request_id:expect.stringMatching(/^[0-9a-f]{32}$/)});});

it('requests cancellation of the exact live Take and waits for verified cancellation',async()=>{
  const api=native(),record={object_id:'PlanOne',document_sha256:'d'.repeat(64)};
  api.wo6_plan_catalog.mockResolvedValue({project_id:movie.id,sources:[source],saved_plans:[record]});
  api.wo6_plan_read.mockResolvedValue({record,data:{plan:{project_id:movie.id,request:proposal,source}},worker_authorized:false});
  let resolveExecution;
  api.wo6_retake_execute=vi.fn(()=>new Promise(resolve=>{resolveExecution=resolve;}));
  api.wo6_retake_cancel=vi.fn(async(pid,id)=>({project_id:pid,request_id:id,status:'CANCELLATION_REQUESTED'}));
  await open(api);
  fireEvent.click(screen.getByRole('button',{name:'Open Plan 1'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Create Separate Take'})).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'Create Separate Take'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Cancel Take'})).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'Cancel Take'}));
  await waitFor(()=>expect(screen.getByText('Cancellation requested. Waiting for the Take to stop.')).toBeTruthy());
  expect(api.wo6_retake_cancel).toHaveBeenCalledWith(movie.id,api.wo6_retake_execute.mock.calls[0][0].request_id);
  expect(screen.queryByText('Take cancelled. No new Take was created.')).toBeNull();
  resolveExecution({status:'CANCELLED',project_id:movie.id,new_take_created:false,film_approved:false});
  await waitFor(()=>expect(screen.getByText('Take cancelled. No new Take was created.')).toBeTruthy());
  expect(screen.queryByRole('button',{name:'Cancel Take'})).toBeNull();
});
