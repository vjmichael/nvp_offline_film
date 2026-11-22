import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import NativeAudioRecoveryPanel from './NativeAudioRecoveryPanel.jsx';

afterEach(()=>{cleanup();delete window.pywebview;});
const empty={available:true,items:[],held:0,more:false,next_page:null};
describe('native managed audio recovery panel',()=>{
  it('is absent when no managed authority is available',async()=>{
    window.pywebview={api:{audio_recovery_catalog:vi.fn(async()=>({...empty,available:false}))}};
    render(<NativeAudioRecoveryPanel/>);
    await waitFor(()=>expect(window.pywebview.api.audio_recovery_catalog).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Interrupted sound work')).toBeNull();
  });
  it('checks saved work without promising new rendering',async()=>{
    const selection='a'.repeat(48);
    const catalog=vi.fn().mockResolvedValueOnce({...empty,items:[{selection,can_recover:true,can_abandon:false}]}).mockResolvedValue(empty);
    const act=vi.fn(async()=>({status:'RECOVERED'}));
    window.pywebview={api:{audio_recovery_catalog:catalog,audio_recovery_act:act}};
    render(<NativeAudioRecoveryPanel/>);
    fireEvent.click(await screen.findByRole('button',{name:'Check saved audio'}));
    await screen.findByText('Saved sound work was recovered. No new rendering was started.');
    expect(act).toHaveBeenCalledWith(selection,'recover');
    expect(screen.queryByRole('button',{name:'End interrupted task'})).toBeNull();
  });
  it('requests only the reviewed end action after explicit selection',async()=>{
    const selection='b'.repeat(48);
    const report={...empty,items:[{selection,can_recover:false,can_abandon:true}]};
    const act=vi.fn(async()=>({status:'CANCELLED'}));
    window.pywebview={api:{audio_recovery_catalog:vi.fn(async()=>report),audio_recovery_act:act}};
    render(<NativeAudioRecoveryPanel/>);
    fireEvent.click(await screen.findByRole('button',{name:'End interrupted task'}));
    await screen.findByText('No changes were made.');
    expect(act).toHaveBeenCalledWith(selection,'abandon');
    expect(screen.queryByRole('button',{name:'Check saved audio'})).toBeNull();
  });
});
