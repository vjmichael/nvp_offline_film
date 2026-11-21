import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import NativeAudioPreviewPanel from './NativeAudioPreviewPanel.jsx';
const empty={available:true,items:[],next_after:null};
const one={...empty,items:[{source_id:'Voice',revision:2}]};
afterEach(()=>{cleanup();delete window.pywebview;});
describe('project audio preview',()=>{
 it('hides when managed audio is unavailable',async()=>{
  const catalog=vi.fn(async()=>({...empty,available:false}));
  window.pywebview={api:{audio_preview_catalog:catalog}};
  render(<NativeAudioPreviewPanel projectId="film"/>);
  await waitFor(()=>expect(catalog).toHaveBeenCalledWith('film',null));
  expect(screen.queryByRole('region',{name:'Sound previews'})).toBeNull();
 });
 it('uses exact project and source revision and reports refusal',async()=>{
  const start=vi.fn(async()=>({status:'CANCELLED'}));
  window.pywebview={api:{audio_preview_catalog:vi.fn(async()=>one),audio_preview_start:start}};
  render(<NativeAudioPreviewPanel projectId="film"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Prepare preview'}));
  await screen.findByText('No sound task was started.');
  expect(start).toHaveBeenCalledWith('film','Voice',2);
 });
 it('does not treat cancellation request as terminal',async()=>{
  let finish;
  const start=vi.fn(()=>new Promise(resolve=>{finish=resolve;}));
  const cancel=vi.fn(async()=>({status:'CANCELLATION_REQUESTED'}));
  window.pywebview={api:{audio_preview_catalog:vi.fn(async()=>one),audio_preview_start:start,audio_preview_cancel:cancel}};
  render(<NativeAudioPreviewPanel projectId="film"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Prepare preview'}));
  fireEvent.click(await screen.findByRole('button',{name:'Cancel sound task'}));
  await screen.findByText('Stopping sound work…');
  expect(cancel).toHaveBeenCalledWith('film');
  expect(screen.getByRole('button',{name:'Prepare preview'}).disabled).toBe(true);
  await act(async()=>finish({status:'INTERRUPTED'}));
  await screen.findByText('Sound work stopped. Check saved work before restarting.');
 });
});
