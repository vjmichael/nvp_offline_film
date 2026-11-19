import React from 'react';
import {render, screen, fireEvent, cleanup} from '@testing-library/react';
import {afterEach, it, expect, vi} from 'vitest';
import {DirectorPagedMedia,DirectorDeliveryReview,DirectorStorageReview} from './DirectorPagedMedia.jsx';
const pid='a'.repeat(32), digest='b'.repeat(64), id='c'.repeat(32), edit={revision:3,active_digest:digest,duration_tick:'14112000000',clip_count:1};
const selection={index:0,start_tick:'0'};
const sample={format:'nvp.g07.picture_preview.v1',project_id:pid,revision:3,active_digest:digest,position_tick:'0',preview_is_sampled_native_openusd:true,final_video_rendered:false,shots:[{}]};
afterEach(cleanup);
it('opens exact cut scope and rejects substituted original', async()=>{
 const api=vi.fn(async()=>sample);const props={projectId:pid,encrypted:true,edit,api,renderPicture:({sample})=><span>{sample?'Original sample':'No sample'}</span>};
 const {rerender}=render(<DirectorPagedMedia {...props}/>);expect(api).not.toHaveBeenCalled();rerender(<DirectorPagedMedia {...props} selection={selection}/>);await screen.findByText('Original sample');expect(api.mock.calls[0].slice(0,3)).toEqual([`/api/projects/${pid}/live/edit/sections/picture`,'POST',{revision:3,digest,tick:'0'}]);
 const bad=vi.fn(async()=>({...sample,active_digest:'f'.repeat(64)}));rerender(<DirectorPagedMedia {...props} api={bad} selection={selection}/>);await screen.findByRole('alert');expect(screen.queryByText('Original sample')).toBeNull();
});
it('timing review does not claim export or rendering',async()=>{
 const api=vi.fn(async()=>({format:'nvp.g07.paged_delivery_source.v1',project_id:pid,revision:3,active_digest:digest,clip_count:1,render_approved:false,media_verified:false,final_movie_exported:false}));render(<DirectorDeliveryReview projectId={pid} encrypted edit={edit} api={api}/>);fireEvent.click(screen.getByRole('button',{name:'Check cut timing'}));await screen.findByText(/Final picture, sound and export still need verification/);expect(api.mock.calls[0][2]).toEqual({revision:3,digest});
});
it('recovery chooses only a missing indexed section, never supplies a path or approval',async()=>{
 const page={format:'nvp.g07.storage_status.v1',project_id:pid,revision:3,render_approved:false,items:[{section_id:id,status:'missing'},{section_id:'d'.repeat(32),status:'needs_review'}]};let recovered=false;
 const api=vi.fn(async(url)=>url.endsWith('/recover')?(recovered=true,{revision:3,section_id:id,restored:true,cancelled:false,render_approved:false}):({...page,items:recovered?[]:page.items}));render(<DirectorStorageReview projectId={pid} api={api}/>);fireEvent.click(screen.getByText('Movie recovery'));fireEvent.click(screen.getByRole('button',{name:'Check saved sections'}));await screen.findByText(/Existing damaged material/);expect(screen.getAllByRole('button',{name:'Choose backup'})).toHaveLength(1);fireEvent.click(screen.getByRole('button',{name:'Choose backup'}));await screen.findByText(/saved section was recovered/);expect(api.mock.calls[1][2]).toEqual({section_id:id,revision:3});expect(screen.queryByRole('button',{name:'Choose backup'})).toBeNull();
});
it('creates an encrypted backup using only the native folder dialog',async()=>{
 const api=vi.fn(async()=>({format:'nvp.g03.live_movie_backup.v1',project_id:pid,backup_created:true,original_unchanged:true,cancelled:false}));render(<DirectorStorageReview projectId={pid} api={api}/>);fireEvent.click(screen.getByText('Movie recovery'));fireEvent.click(screen.getByRole('button',{name:'Create movie backup'}));await screen.findByText(/Verified encrypted movie backup saved/);expect(api.mock.calls[0][2]).toEqual({});
});
it('saves a review clip with exact frame range, not final export permission',async()=>{
 const api=vi.fn(async(url)=>url.endsWith('/picture')?sample:{format:'nvp.g07.protected_review_reel.v1',project_id:pid,revision:3,reel_id:id,verified:true,protected:true,whole_movie_exported:false,start_frame:0,frame_count:48,cancelled:false});render(<DirectorPagedMedia projectId={pid} encrypted edit={edit} selection={selection} api={api} renderPicture={()=>null}/>);fireEvent.click(screen.getByText('Review clip'));fireEvent.click(screen.getByRole('button',{name:'Save review clip'}));await screen.findByText(/Review clip saved inside/);expect(api.mock.calls.find(c=>c[0].endsWith('/review-clip'))[2]).toEqual({revision:3,digest,first_frame:0,frame_count:48});expect(screen.getByRole('button',{name:'Save review copy'})).toBeTruthy();
});
it('reopens saved working clip metadata and uses the separate native copy action',async()=>{
 const format='nvp.g07.protected_review_reel.v1';const api=vi.fn(async url=>url.endsWith('/copy-review-clip')?{format,project_id:pid,revision:3,reel_id:id,copy_saved:true,cancelled:false}:{format,project_id:pid,revision:3,whole_movie_exported:false,reopened:false,items:[{reel_id:id,start_frame:24,frame_count:48,state:'saved'}],next_after:null});render(<DirectorDeliveryReview projectId={pid} encrypted edit={edit} api={api}/>);fireEvent.click(screen.getByText('Saved review clips'));fireEvent.click(screen.getByRole('button',{name:'Show saved clips'}));const button=await screen.findByRole('button',{name:'Save copy'});fireEvent.click(button);await screen.findByText('Review copy saved.');expect(api.mock.calls[1][2]).toEqual({revision:3,digest,reel_id:id});
});
