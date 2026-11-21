// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import ProductionAuthoringPanel from './ProductionAuthoringPanel.jsx';

const project={
  id:'film_a',revision:3,
  scenes:[{id:'SC_001',number:1,heading:'INT. SET - DAY'}]
};
const world={
  revision:4,stale:false,proposals:[],
  manifest:{room_m:[8,6,3],instances:[],world_digest_sha256:'c'.repeat(64)}
};
const sourceProof={
  format:'nvp.production.proxy_render_preflight.v1',
  project_id:'film_a',scene_id:'SC_001',project_revision:3,
  world_revision:4,world_base_plan_revision:2,
  instance_count:0,world_sha256:'a'.repeat(64),
  blender_script_sha256:'b'.repeat(64),native_approval:'not_granted',
  resource_admission:'not_checked',execution:'not_started',
};

function mockedApi(selectedWorld=world){
  return vi.fn(async (url)=>{
    if(url.endsWith('/render-preflight'))return sourceProof;
    if(url.endsWith('/world'))return selectedWorld;
    if(url.endsWith('/dialogue'))return {dialogue:[]};
    if(url.endsWith('/blocking'))return [];
    if(url.endsWith('/cameras'))return [];
    if(url.endsWith('/assets'))return [];
    if(url.endsWith('/meshes'))return [];
    if(url.endsWith('/blender-availability'))return {available:false};
    throw new Error('Unexpected API call '+url);
  });
}

describe('Creator-visible NVP scene render preflight',()=>{
  afterEach(()=>{cleanup();vi.restoreAllMocks();});

  it('shows exact proxy hashes and never dispatches a native render',async()=>{
    const api=mockedApi();
    render(<ProductionAuthoringPanel project={project} api={api}
        action={callback=>callback()} busy={false}/>);
    const button=await screen.findByRole('button',{name:'Inspect render preflight'});
    await waitFor(()=>expect(button.disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(()=>expect(screen.getByText('Source preview — Blender not started')).toBeTruthy());
    expect(screen.getByText('a'.repeat(64))).toBeTruthy();
    expect(screen.getByText('b'.repeat(64))).toBeTruthy();
    expect(screen.getByText(/Native authorization: not granted/)).toBeTruthy();
    expect(api.mock.calls.some(([url])=>url.endsWith('/render-preflight'))).toBe(true);
    expect(api.mock.calls.every(([,method])=>!method||method==='GET')).toBe(true);
  });

  it('refuses preflight button when source world is stale',async()=>{
    const api=mockedApi({...world,stale:true,manifest:undefined});
    render(<ProductionAuthoringPanel project={project} api={api}
        action={callback=>callback()} busy={false}/>);
    const button=await screen.findByRole('button',{name:'Inspect render preflight'});
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(api.mock.calls.some(([url])=>url.endsWith('/render-preflight'))).toBe(false);
  });
});
