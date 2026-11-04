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
  it('never invents unknown VRAM or provider load progress',async()=>{
    globalThis.fetch.mockResolvedValue({ok:true,json:async()=>({
      ...data,sample:{...data.sample,gpus:[]},tasks:[]})});
    render(<ResourceActivityPanel pollMs={50000}/>);
    fireEvent.click(screen.getByRole('button',{name:/computer & production activity/i}));
    await waitFor(()=>expect(screen.getByText(/Unknown VRAM budget/i)).toBeTruthy());
    expect(screen.getByText(/Current external AI models are observed, not loaded or offloaded by NVP/i)).toBeTruthy();
  });
});
