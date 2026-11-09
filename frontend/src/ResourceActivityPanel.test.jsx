// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import ResourceActivityPanel from './ResourceActivityPanel.jsx';

const data={
  format:'nvp.system.resource_activity.v1',
  sample:{ram_total_mb:32768,ram_available_mb:16000,memory_psi_full10:null,
    gpus:[{device_id:'dxgi:0',name:'AMD Radeon',source:'windows_dxgi_process_budget',
      budget_mb:32000,used_mb:12000,free_mb:20000,globally_measured:false}]},
  tasks:[
    {id:'render_1',kind:'blender',title:'Render scene 1',state:'ACTIVE',phase:'rendering',
      detail:'Blender working',completed_fraction:null},
    {id:'load_1',kind:'ai_loading',title:'Load AI model',state:'ACTIVE',phase:'loading_model',
      detail:'Provider measured load',completed_fraction:.5},
    {id:'queued_1',kind:'blender',title:'Scene 2',state:'QUEUED',phase:'waiting_for_resources',
      detail:'Waiting for GPU memory headroom',completed_fraction:null,queue_lane:'interactive'}
  ]
};

describe('NVP real computer/task activity UX',()=>{
  beforeEach(()=>{globalThis.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>data});});
  afterEach(()=>{cleanup();vi.restoreAllMocks();});
  it('shows RAM/DXGI labeling and measured vs indeterminate progress',async()=>{
    render(<ResourceActivityPanel pollMs={50000}/>);
    fireEvent.click(screen.getByRole('button',{name:/computer & production activity/i}));
    await waitFor(()=>expect(screen.getByText('Render scene 1')).toBeTruthy());
    expect(screen.getByText(/DXGI budget for NVP process—not global free VRAM/)).toBeTruthy();
    expect(screen.getByRole('progressbar',{name:/Load AI model measured progress/i}).value).toBe(50);
    expect(screen.getByRole('progressbar',{name:/Render scene 1 working; percent unknown/i}).hasAttribute('value')).toBe(false);
    expect(screen.getByText(/Not started. NVP is preserving computer memory headroom/i)).toBeTruthy();
    expect(screen.getByText('Waiting for GPU memory headroom')).toBeTruthy();
    expect(screen.getByText(/Priority: interactive/)).toBeTruthy();
  });
  it('shows NVP-owned worker measurements separately from external AI usage',async()=>{
    const owned={
      format:'nvp.resources.owned_process_report.v1',
      host_process_rss_mb:124.5,
      running_workers_observed_rss_mb:512.25,
      unmeasured_running_worker_count:0,
      owned_workers:[{job_id:'nativeCycles_A',
        state:'OBSERVING',observed_rss_mb:512.25,
        observed_cpu_percent_one_core_100:93.7,
        per_process_gpu_memory_mb:null,warning:null}],
    };
    globalThis.fetch.mockResolvedValue({ok:true,
      json:async()=>({...data,nvp_owned_process_usage:owned})});
    render(<ResourceActivityPanel pollMs={50000}/>);
    fireEvent.click(screen.getByRole('button',
      {name:/computer & production activity/i}));
    expect(await screen.findByText('nativeCycles_A')).toBeTruthy();
    expect(screen.getByText(/NVP host RAM: 124.5 MiB/)).toBeTruthy();
    expect(screen.getByText(/Tracked worker RAM: 512.3 MiB/)).toBeTruthy();
    expect(screen.getByText(/RAM 512.3 MiB/)).toBeTruthy();
    expect(screen.getByText(/CPU 94% of one core/)).toBeTruthy();
    expect(screen.getByText(/Lu can read this/)).toBeTruthy();
  });

  it('never invents unknown VRAM or provider load progress',async()=>{
    globalThis.fetch.mockResolvedValue({ok:true,json:async()=>({
      ...data,sample:{...data.sample,gpus:[]},tasks:[]})});
    render(<ResourceActivityPanel pollMs={50000}/>);
    fireEvent.click(screen.getByRole('button',{name:/computer & production activity/i}));
    await waitFor(()=>expect(screen.getByText(/Unknown VRAM budget/i)).toBeTruthy());
    expect(screen.getByText(/Current external AI models are observed, not loaded or offloaded by NVP/i)).toBeTruthy();
  });
});
