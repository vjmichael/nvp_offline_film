// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import AdaptiveShotBatchPanel from './AdaptiveShotBatchPanel.jsx';

afterEach(()=>{cleanup();vi.restoreAllMocks();});

function capacity({
  size=2,views=9,selected=3,previewWorkers=1,finalWorkers=0,
}={}){
  const groups=(count)=>Array.from({length:Math.ceil(count/size)},(_,i)=>({
    batch:i+1,first_shot_number:i*size+1,
    shot_count:Math.min(size,count-i*size),
  }));
  return {
    format:'nvp.film01s.read_only_batch_capacity_preview.v1',
    available_source_viewpoints:views,selected_final_shots:selected,
    batch_size_mode:'DIRECTOR',shots_per_batch:size,
    lowfi_preview_batches:groups(views),
    hifi_selected_shot_batches:groups(selected),
    safe_parallel_workers:{
      lofi:{safe_workers:previewWorkers,reason:'Safe measured resources'},
      hifi:{safe_workers:finalWorkers,reason:'Waiting for memory headroom'},
    },
    render_jobs_started:0,browser_has_no_native_render_authority:true,
    source_film_index_take_verified:false,
  };
}

describe('01S director camera batch controls',()=>{
  it('keeps editable batch size independent of safe concurrent workers',async()=>{
    const api=vi.fn(async(_path,_method,payload)=>
      capacity({size:payload.shots_per_batch,views:payload.viewpoint_count,
        selected:payload.selected_final_shots}));
    render(<AdaptiveShotBatchPanel api={api}/>);
    fireEvent.change(screen.getByLabelText('Shots per batch'),
      {target:{value:'12'}});
    fireEvent.change(screen.getByLabelText('Maximum concurrent render workers'),
      {target:{value:'1'}});
    fireEvent.click(screen.getByRole('button',{name:'Estimate shot batches'}));
    await waitFor(()=>expect(api).toHaveBeenCalledTimes(1));
    const [path,method,body]=api.mock.calls[0];
    expect(path).toBe('/system/shot-batch-estimate');
    expect(method).toBe('POST');
    expect(body).toMatchObject({shots_per_batch:12,
      parallel_worker_limit:1,viewpoint_count:9,selected_final_shots:3});
    expect(await screen.findByText(/Director-selected grouping: 12 shots per batch/)).toBeTruthy();
    expect(screen.getByText(/1 batches for 9 virtual views/)).toBeTruthy();
    expect(screen.getByText(/NVP estimates how much your PC/)).toBeTruthy();
    expect(screen.getByText(/not an accepted camera-roll source or a running/)).toBeTruthy();
  });

  it('does not claim a GPU exists without a verified backend',async()=>{
    const api=vi.fn(async()=>capacity({
      previewWorkers:0,finalWorkers:0,size:1}));
    render(<AdaptiveShotBatchPanel api={api}/>);
    fireEvent.change(screen.getByLabelText('Preferred render backend'),
      {target:{value:'gpu'}});
    fireEvent.click(screen.getByRole('button',{name:'Estimate shot batches'}));
    await waitFor(()=>expect(api).toHaveBeenCalledTimes(1));
    expect(api.mock.calls[0][2].renderer).toBe('gpu');
    expect(api.mock.calls[0][2].gpu_device_id).toBe('unverified-gpu');
    // CPU preview has measured headroom, but the hi-fi worker is blocked.
    // Never present unverified GPU capacity as separately measured.
    expect(screen.getAllByText(/Safe measured resources/).length).toBe(1);
    expect(screen.getAllByText(/Waiting for memory headroom/).length).toBe(1);
    expect(screen.getAllByText(/0 native workers/).length).toBe(2);
  });

  it('refuses invalid final shot counts before any server call',()=>{
    const api=vi.fn();
    render(<AdaptiveShotBatchPanel api={api}/>);
    fireEvent.change(screen.getByLabelText('Final selected shot count'),
      {target:{value:'25'}});
    fireEvent.click(screen.getByRole('button',{name:'Estimate shot batches'}));
    expect(screen.getByRole('alert').textContent).toMatch(
      /Choose 1–96 viewpoints/);
    expect(api).not.toHaveBeenCalled();
  });
});
