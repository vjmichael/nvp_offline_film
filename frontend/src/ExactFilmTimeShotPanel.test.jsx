import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
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
function mount(api){
  return render(<ExactFilmTimeShotPanel project={project} api={api}
    action={action} busy={false}/>);
}
describe('DA-01 precise Film Time desktop editor',()=>{
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
});
