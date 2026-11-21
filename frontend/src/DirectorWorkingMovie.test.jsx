import React from 'react';
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import DirectorWorkingMovie from './DirectorWorkingMovie.jsx';
const projectId='a'.repeat(32),edit={revision:2,active_digest:'b'.repeat(64)};
const response=(id,state,extra={})=>({project_id:projectId,operation_id:id,revision:2,active_digest:edit.active_digest,state,final_movie_exported:false,...extra});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('requires explicit clicks for preparation and continuation; no browser approval or worker authority',async()=>{
 let n=0;const api=vi.fn(async(url,method,body)=>response(body.operation_id,++n===1?'prepared':'complete',{saved_frames:n===1?0:48,total_frames:48}));
 render(<DirectorWorkingMovie projectId={projectId} edit={edit} api={api}/>);fireEvent.click(screen.getByText('Working movie'));fireEvent.click(screen.getByRole('button',{name:'Prepare or continue working movie'}));await screen.findByText(/Sound preparation complete/);expect(api).toHaveBeenCalledTimes(1);expect(Object.keys(api.mock.calls[0][2]).sort()).toEqual(['digest','operation_id','revision']);fireEvent.click(screen.getByRole('button',{name:'Continue working movie'}));await screen.findByText(/This is not a final export/);expect(api).toHaveBeenCalledTimes(2);
});
it('requests a real host stop, waits for terminal acknowledgement and does not auto-resume',async()=>{
 let finish,id;const api=vi.fn((url,method,body)=>{if(url.endsWith('/feature-stop'))return Promise.resolve({project_id:projectId,operation_id:body.operation_id,stop_requested:true});if(url.endsWith('/feature-status'))return Promise.resolve({active:false});id=body.operation_id;return new Promise(r=>finish=r);});
 render(<DirectorWorkingMovie projectId={projectId} edit={edit} api={api}/>);fireEvent.click(screen.getByText('Working movie'));fireEvent.click(screen.getByRole('button',{name:'Prepare or continue working movie'}));fireEvent.click(screen.getByRole('button',{name:'Stop'}));await screen.findByText(/waiting for the current work/);expect(api.mock.calls[1][2]).toEqual({operation_id:id});expect(screen.getByRole('button',{name:'Prepare or continue working movie'}).disabled).toBe(true);finish(response(id,'stopped'));await screen.findByText(/Verified parts remain saved/);expect(api.mock.calls.filter(c=>c[0].endsWith('/feature-step'))).toHaveLength(1);
});
it('rejects a mismatched or incomplete completion receipt',async()=>{
 const api=vi.fn(async(url,method,body)=>response(body.operation_id,'complete',{saved_frames:1,total_frames:48}));render(<DirectorWorkingMovie projectId={projectId} edit={edit} api={api}/>);fireEvent.click(screen.getByText('Working movie'));fireEvent.click(screen.getByRole('button',{name:'Prepare or continue working movie'}));await screen.findByText(/production needs review/);expect(screen.queryByText(/Working movie verified/)).toBeNull();
});

it('opens the existing finishing controls for a chapter edit without invoking the legacy finite export or cinema preview',async()=>{
 const api=vi.fn();const doc={revision:1,approved_for_current_film:true,source_changed:false,draft:{color:{exposure:0,contrast:1,saturation:1,lift:0,warmth:0},audio:{target_lufs:-18,peak_ceiling_dbfs:-1.5,fade_in_seconds:0,fade_out_seconds:0},finishing_intent:'working',notes:''},levels:['working'],history:[]};
 const f=vi.fn(async()=>({ok:true,json:async()=>doc}));vi.stubGlobal('fetch',f);
 render(<DirectorWorkingMovie projectId={projectId} edit={edit} api={api}/>);fireEvent.click(screen.getByText('Working movie'));fireEvent.click(screen.getByRole('button',{name:'Review picture and sound'}));await screen.findByText('Approved for this film');expect(f).toHaveBeenCalledTimes(1);expect(f.mock.calls[0][0]).toBe(`/api/projects/${projectId}/live/finish`);expect(screen.queryByRole('button',{name:'Show Finished Picture'})).toBeNull();expect(screen.getByRole('button',{name:'Prepare or continue working movie'}).disabled).toBe(true);fireEvent.click(screen.getByRole('button',{name:'Close picture and sound'}));expect(screen.getByRole('button',{name:'Prepare or continue working movie'}).disabled).toBe(false);expect(api).not.toHaveBeenCalled();
});
it('opens verified playback and pages original production material without downloading originals',async()=>{
 const job='c'.repeat(64),first='d'.repeat(32),second='e'.repeat(32);
 const api=vi.fn(async(url,method,body)=>url.includes('media-inventory')?{project_id:projectId,family:'takes',media_authenticated:false,items:[{id:url.includes('after=')?second:first,scene_id:'Scene 1',source_bytes:1048576}],next_after:url.includes('after=')?null:first}:response(body.operation_id,'complete',{saved_frames:48,total_frames:48,job_id:job}));
 const fetcher=vi.fn(async()=>({ok:true,json:async()=>({fps:24,sample_rate:48000,picture_frames:48,audio_samples:96000,duration_seconds:2,reels:2,source_sha256:'f'.repeat(64)})}));vi.stubGlobal('fetch',fetcher);
 render(<DirectorWorkingMovie projectId={projectId} edit={edit} api={api}/>);fireEvent.click(screen.getByText('Working movie'));expect(screen.queryByRole('button',{name:'Watch working movie'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Prepare or continue working movie'}));fireEvent.click(await screen.findByRole('button',{name:'Watch working movie'}));await screen.findByRole('button',{name:'Play Film'});expect(fetcher.mock.calls[0][0]).toContain(`/playback/2/${edit.active_digest}/${job}/timeline`);
 fireEvent.click(screen.getByText('Production material'));fireEvent.click(screen.getByRole('button',{name:'Filmed takes'}));await screen.findByText(/dddddddd/);fireEvent.click(screen.getByRole('button',{name:'Next page'}));await screen.findByText(/eeeeeeee/);expect(api.mock.calls.at(-1)[0]).toContain('after='+first);
});
