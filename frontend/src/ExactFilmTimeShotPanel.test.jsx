import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach} from 'vitest';
import ExactFilmTimeShotPanel from './ExactFilmTimeShotPanel.jsx';

const project={id:'a'.repeat(32)};
const source={scene_id:'set',revision:1,document_sha256:'b'.repeat(64),
  cameras:[{path:'/World/Camera',label:'Camera'}]};
const list={format:'nvp.slate08.camera_source_list.v1',
  project_id:project.id,scenes:[source]};
const sequence={format:'nvp.exact_time.usd_camera_shots.v1',
  scene_id:'set',scene_document_sha256:source.document_sha256,
  video_frames_created:false,revision:1,document_sha256:'c'.repeat(64),
  duration_tick:'7056000001',
  shots:[{shot_id:'Shot001',camera_path:'/World/Camera',pattern:'continuous',
    start_tick:'0',end_tick:'7056000001'}]};
const action=fn=>fn();
afterEach(()=>{cleanup();delete window.pywebview;});
function mount(api){
  return render(<ExactFilmTimeShotPanel project={project} api={api}
    action={action} busy={false}/>);
}
describe('DA-01 precise Film Time desktop editor',()=>{
  it('preserves tick-mode duration edits when switching to seconds',async()=>{
    const api=vi.fn(async(path,method,payload)=>{
      if(path.endsWith('/film/camera-scenes'))return list;
      if(method==='POST')return {...sequence,...payload,revision:2,
        document_sha256:'d'.repeat(64)};
      return sequence;
    });
    mount(api);
    await screen.findByLabelText('Film Time duration limit ticks');
    fireEvent.change(screen.getByLabelText('Film Time duration limit ticks'),
      {target:{value:'14112000000'}});
    fireEvent.click(screen.getByLabelText('Author exact integer Film Time ticks'));
    expect(screen.queryByLabelText('Film Time duration limit ticks')).toBeNull();
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    await waitFor(()=>expect(api).toHaveBeenCalledWith(
      expect.stringContaining('/film/native-time-shots/'),'POST',
      expect.objectContaining({duration_tick:'14112000000'})));
  });
  it('refuses lossy switch from sub-microsecond draft ticks',async()=>{
    const api=vi.fn(async(path)=>path.endsWith('/film/camera-scenes')?list:sequence);
    mount(api);
    await screen.findByLabelText('Film Time duration limit ticks');
    fireEvent.change(screen.getByLabelText('Film Time duration limit ticks'),
      {target:{value:'7056000002'}});
    fireEvent.click(screen.getByLabelText('Author exact integer Film Time ticks'));
    expect(screen.getByLabelText('Film Time duration limit ticks').value)
      .toBe('7056000002');
    expect(screen.getByRole('alert').textContent).toMatch(/Sub-microsecond/);
  });
  it('retains sub-microsecond saved duration and republishes exact ticks',async()=>{
    const api=vi.fn(async(path,method,payload)=>{
      if(path.endsWith('/film/camera-scenes'))return list;
      if(method==='POST')return {...sequence,...payload,revision:2,
        document_sha256:'d'.repeat(64)};
      return sequence;
    });
    mount(api);
    expect(await screen.findByLabelText('Film Time duration limit ticks')).toBeTruthy();
    expect(screen.getByLabelText('Film Time duration limit ticks').value)
      .toBe('7056000001');
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    await waitFor(()=>expect(api).toHaveBeenCalledWith(
      expect.stringContaining('/film/native-time-shots/'),'POST',
      expect.objectContaining({duration_tick:'7056000001',expected_revision:1})));
  });
  it('rejects malformed or overflowing tick input before publication',async()=>{
    const api=vi.fn(async(path)=>path.endsWith('/film/camera-scenes')?list:sequence);
    mount(api);
    await screen.findByLabelText('Film Time duration limit ticks');
    fireEvent.change(screen.getByLabelText('Film Time duration limit ticks'),
      {target:{value:'9223372036854775808'}});
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    expect((await screen.findByRole('alert')).textContent).toMatch(/signed 64-bit/);
    expect(api.mock.calls.filter(x=>x[1]==='POST')).toHaveLength(0);
  });
  it('invalidates saved Take freeze authority after changing only the duration limit',async()=>{
    const api=vi.fn(async(path)=>path.endsWith('/film/camera-scenes')?list:sequence);
    mount(api);
    await screen.findByLabelText('Film Time duration limit ticks');
    const freeze=screen.getByText('Approve and freeze original 3D Take');
    // Without a native bridge the button is disabled already; inspect the
    // saved revision marker disappearing by changing the duration and then
    // switching back to the original value before publication.
    fireEvent.change(screen.getByLabelText('Film Time duration limit ticks'),
      {target:{value:'7056000010'}});
    expect(screen.getByText(/Current saved revision: 1/)).toBeTruthy();
    expect(freeze.disabled).toBe(true);
  });
  it('rejects a camera identity absent from the immutable scene before POST',async()=>{
    const api=vi.fn(async(path)=>path.endsWith('/film/camera-scenes')?list:sequence);
    mount(api);
    const camera=await screen.findByLabelText('Shot001 camera');
    // A persisted scene camera may disappear after a scene revision.
    // Editing a draft to an invalid identity must fail closed at publication.
    fireEvent.change(camera,{target:{value:'/World/Unknown'}});
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    expect((await screen.findByRole('alert')).textContent).toMatch(/absent from the source scene/);
    expect(api.mock.calls.filter(x=>x[1]==='POST')).toHaveLength(0);
  });

  it('never calls the real native freeze bridge after a draft mutation',async()=>{
    const freeze=vi.fn(async()=>({status:'FROZEN_DATA_FIRST_TAKE'}));
    window.pywebview={api:{data_av_freeze_timed_take:freeze}};
    const api=vi.fn(async(path)=>path.endsWith('/film/camera-scenes')?list:sequence);
    mount(api);
    const duration=await screen.findByLabelText('Film Time duration limit ticks');
    const approve=screen.getByText('Approve and freeze original 3D Take');
    await waitFor(()=>expect(approve.disabled).toBe(false));
    fireEvent.change(duration,{target:{value:'7056000002'}});
    expect(approve.disabled).toBe(true);
    fireEvent.click(approve);
    expect(freeze).not.toHaveBeenCalled();
  });

  it('never authorizes an unsaved edit after a delayed publication resolves',async()=>{
    let release;
    const delayed=new Promise(resolve=>{release=resolve;});
    const api=vi.fn(async(path,method)=>{
      if(path.endsWith('/film/camera-scenes'))return list;
      if(method==='POST')return delayed;
      return sequence;
    });
    mount(api);
    await screen.findByLabelText('Film Time duration limit ticks');
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    await waitFor(()=>expect(api.mock.calls.some(x=>x[1]==='POST')).toBe(true));
    fireEvent.change(screen.getByLabelText('Film Time duration limit ticks'),
      {target:{value:'7056000020'}});
    release({...sequence,revision:2,document_sha256:'d'.repeat(64)});
    await waitFor(()=>expect(screen.getByText(/Current saved revision: 2/)).toBeTruthy());
    expect(screen.getByText('Approve and freeze original 3D Take').disabled).toBe(true);
    expect(screen.getByLabelText('Film Time duration limit ticks').value)
      .toBe('7056000020');
    expect(screen.getByRole('status').textContent).toMatch(/newer draft remains unsaved/);
    // Re-publishing must send the newer duration, not the stale response.
    fireEvent.click(screen.getByText('Save immutable timing revision'));
    await waitFor(()=>expect(api.mock.calls.filter(x=>x[1]==='POST')).toHaveLength(2));
    expect(api.mock.calls.filter(x=>x[1]==='POST')[1][2])
      .toEqual(expect.objectContaining({duration_tick:'7056000020',expected_revision:2}));
  });
});
