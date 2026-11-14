import React from 'react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import ActorPerformancePanel from './ActorPerformancePanel.jsx';

afterEach(cleanup);
const pid='a'.repeat(32),sha='b'.repeat(64);
const cast={
  format:'nvp.p1bc.native_actor_cast.v1',project_id:pid,
  sources_immutable:true,voices_synthesized:false,
  actors:[{actor_id:'ActorLead',display_name:'Lead',
           actor_sha256:'c'.repeat(64)}],
  takes:[{take_id:'TakeLead',take_sha256:sha,
    cast:[{actor_id:'ActorLead',path:'/World/Lead'}],
    original_dialogue:[{
      event_id:'LineOne',actor_id:'ActorLead',
      usd_prim_path:'/World/Lead',
      start_tick:'0',end_tick:'7056000000',
      original_pcm_sha256:'d'.repeat(64),
    }]}],
};
function bridge(){
  return {
    data_av_actor_cast:vi.fn(async()=>cast),
    data_av_actor_register:vi.fn(async request=>({
      format:'nvp.p1bc.native_actor_registration.v1',
      status:'ACTOR_ID_REGISTERED',actor_id:request.actor_id,
      actor_sha256:'e'.repeat(64),
      source_modified:false,voice_synthesized:false,
    })),
    data_av_actor_dialogue_bind:vi.fn(async request=>({
      format:'nvp.p1bc.native_original_dialogue.v1',
      status:'ORIGINAL_DIALOGUE_BOUND',
      dialogue_id:request.dialogue_id,dialogue_sha256:'f'.repeat(64),
      take_modified:false,voice_synthesized:false,
    })),
    data_av_actor_dialogue_at:vi.fn(async request=>({
      format:'nvp.p1bc.native_original_dialogue_tick.v1',
      source_modified:false,film_master_approved:false,
      result:{actor_id:'ActorLead',usd_prim_path:'/World/Lead',
        time_tick:request.tick,dialogue_active:true,
        native_scene_rig_binding_verified:true,
        native_skin_deformation_evaluated:true,source_skin_vertex_count:4,
        voice_synthesized:false,lip_sync_generated:false},
    })),
  };
}
describe('P1-B/C original ActorID/rigged source dialogue native GUI',()=>{
  it('binds only source-matched event using separate OS-owned operations',async()=>{
    const native=bridge();
    render(<ActorPerformancePanel projectId={pid} native={native}/>);
    await screen.findByText(/rigged USD Takes with checked ActorID bindings/);
    fireEvent.change(screen.getByLabelText('New unique dialogue attribution identity'),
      {target:{value:'LeadDialog0001'}});
    fireEvent.click(screen.getByText('Ask native director to bind original speaker'));
    await waitFor(()=>expect(native.data_av_actor_dialogue_bind).toHaveBeenCalledOnce());
    const data=native.data_av_actor_dialogue_bind.mock.calls[0][0];
    expect(data).toEqual({project_id:pid,dialogue_id:'LeadDialog0001',
      actor_id:'ActorLead',take_id:'TakeLead',event_id:'LineOne'});
    expect(data.creator_approved).toBeUndefined();
    expect(data.source_path).toBeUndefined();
    fireEvent.change(screen.getByLabelText('Read exact Film Time tick'),
      {target:{value:'3528000000'}});
    fireEvent.click(screen.getByText('Verify ActorID, original voice and rig at tick'));
    await waitFor(()=>expect(native.data_av_actor_dialogue_at).toHaveBeenCalledWith({
      project_id:pid,dialogue_id:'LeadDialog0001',
      revision:1,tick:'3528000000',
    }));
    expect(screen.getByText(/original dialogue active/)).toBeTruthy();
  });
  it('registers actor with no browser-supplied OS approval',async()=>{
    const native=bridge();
    render(<ActorPerformancePanel projectId={pid} native={native}/>);
    await screen.findByText(/rigged USD Takes with checked ActorID bindings/);
    fireEvent.change(screen.getByLabelText('Character name'),
      {target:{value:'New Actor'}});
    fireEvent.click(screen.getByText('Ask native director to register ActorID'));
    await waitFor(()=>expect(native.data_av_actor_register).toHaveBeenCalledOnce());
    const request=native.data_av_actor_register.mock.calls[0][0];
    expect(request).toEqual({project_id:pid,actor_id:'ActorLead',
                              display_name:'New Actor'});
    expect(request.approval).toBeUndefined();
    expect(request.asset_file).toBeUndefined();
  });
  it('refuses foreign source catalog and does not grant actor write',async()=>{
    const native=bridge();
    native.data_av_actor_cast.mockResolvedValueOnce({
      ...cast,project_id:'f'.repeat(32),
    });
    render(<ActorPerformancePanel projectId={pid} native={native}/>);
    expect((await screen.findByRole('alert')).textContent)
      .toMatch(/not verified/);
    expect(native.data_av_actor_dialogue_bind).not.toHaveBeenCalled();
    expect(native.data_av_actor_register).not.toHaveBeenCalled();
  });
  it('does not create dialogue from missing registered actor scene binding',async()=>{
    const native=bridge();
    native.data_av_actor_cast.mockResolvedValueOnce({...cast,takes:[]});
    render(<ActorPerformancePanel projectId={pid} native={native}/>);
    await screen.findByText(/No ActorID-bound original rigged Takes/);
    expect(screen.getByText('Ask native director to bind original speaker').disabled)
      .toBe(true);
    expect(native.data_av_actor_dialogue_bind).not.toHaveBeenCalled();
  });
  it('never supplies host paths or private model/voice credentials to JS',async()=>{
    const native=bridge();
    render(<ActorPerformancePanel projectId={pid} native={native}/>);
    await screen.findByText(/rigged USD Takes with checked ActorID bindings/);
    expect(screen.getByText(/No voice cloned or generated/)).toBeTruthy();
    expect(screen.queryByLabelText('Native executable path')).toBeNull();
    expect(native.data_av_actor_register).not.toHaveBeenCalled();
    expect(native.data_av_actor_dialogue_at).not.toHaveBeenCalled();
  });
});
