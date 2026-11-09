// @vitest-environment jsdom
import React from 'react';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import CameraRailGizmo from './CameraRailGizmo.jsx';

afterEach(()=>{cleanup();vi.restoreAllMocks();});
const nodes=[
  {tick:0,position_m:[0,-7,4],target_m:[0,0,1],
    tangent_in_mps:[0,0,0],tangent_out_mps:[0,0,0]},
  {tick:7056000000,position_m:[1,-5,4],target_m:[0,0,1],
    tangent_in_mps:[0,0,0],tangent_out_mps:[0,0,0]}];
const source={
  source_guided_frames:[{original_actor_views:[{
    actor_id:'OriginalActorID',center_world_m:[0,0,1],
    bounds_world_m:[[-1,-1,0],[1,1,2]]}]}]
};

describe('CAM-FX-03 native-metres projected 3D rail editing',()=>{
  it('projects only verified ActorID bounds and keeps keyboard altitude edits on rail handles',()=>{
    const changed=vi.fn();
    render(<CameraRailGizmo nodes={nodes} origin={[0,0,0]}
      onNodesChange={changed} guidance={source}/>);
    expect(screen.getByText(/ActorID OriginalActorID/)).toBeTruthy();
    const button=screen.getByRole('button',{
      name:'3D drag camera handle 1'});
    fireEvent.keyDown(button,{key:'PageUp'});
    expect(changed).toHaveBeenCalled();
    const next=changed.mock.calls.at(-1)[0];
    expect(next[0].position_m).toEqual([0,-7,4.25]);
    expect(nodes[0].position_m).toEqual([0,-7,4]);
    expect(next[1].position_m).toEqual([1,-5,4]);
  });

  it('moves source-coordinate 3D handles through pointer drag without changing actor geometry',()=>{
    const changed=vi.fn();
    const {container}=render(<CameraRailGizmo nodes={nodes}
      origin={[100,20,0]} onNodesChange={changed} guidance={source}/>);
    const svg=container.querySelector('svg');
    vi.spyOn(svg,'getBoundingClientRect').mockReturnValue({
      left:0,top:0,right:780,bottom:430,width:780,height:430});
    const button=screen.getByRole('button',{
      name:'3D drag camera handle 2'});
    button.setPointerCapture=vi.fn();
    fireEvent.pointerDown(button,{
      pointerId:1,clientX:290,clientY:200,button:0});
    fireEvent.pointerMove(svg,{
      pointerId:1,clientX:318,clientY:200});
    expect(changed).toHaveBeenCalled();
    const next=changed.mock.calls.at(-1)[0];
    expect(next[1].position_m[0]).not.toBe(nodes[1].position_m[0]);
    expect(next[0].position_m).toEqual([0,-7,4]);
    expect(source.source_guided_frames[0].original_actor_views[0]
      .center_world_m).toEqual([0,0,1]);
  });

  it('disables edits while native model proposal is in progress and never invents source actor boxes',()=>{
    const changed=vi.fn();
    render(<CameraRailGizmo nodes={nodes} origin={[0,0,0]}
      onNodesChange={changed} guidance={null} disabled={true}/>);
    expect(screen.queryByText(/ActorID OriginalActorID/)).toBeNull();
    fireEvent.keyDown(screen.getByRole('button',{
      name:'3D drag camera handle 1'}),{key:'PageUp'});
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByText(/Without such a receipt/)).toBeTruthy();
  });

  it('keeps projection orbit and zoom separate from actual source coordinates',()=>{
    const changed=vi.fn();
    render(<CameraRailGizmo nodes={nodes} origin={[0,0,0]}
      onNodesChange={changed} guidance={null}/>);
    fireEvent.change(screen.getByLabelText('3D rail orbit yaw'),{
      target:{value:'95'}});
    fireEvent.change(screen.getByLabelText('3D rail scene zoom'),{
      target:{value:'30'}});
    expect(screen.getByText(/3D orbit 95°/)).toBeTruthy();
    expect(changed).not.toHaveBeenCalled();
  });
});
