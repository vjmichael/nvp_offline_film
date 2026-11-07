import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import DataFirstWorldViewport,{
  approximateKelvinRGB,
} from './DataFirstWorldViewport.jsx';
import {defaultWO2Look} from './WO2PresentationLook.js';

afterEach(()=>cleanup());

describe('WO2 creator-first cinematic controls',()=>{
  it('keeps cinematic proposals unapproved and sends non-destructive look to parent',()=>{
    const onLookChange=vi.fn();
    render(<DataFirstWorldViewport
      objects={[]} tick="0" nativeSchemas={[]}
      presentationLook={defaultWO2Look()}
      onLookChange={onLookChange}/>);
    fireEvent.click(screen.getByRole('button',{name:/Dramatic lighting/i}));
    expect(onLookChange).toHaveBeenCalled();
    const result=onLookChange.mock.lastCall[0];
    expect(result.camera.exposure_ev).toBeLessThan(0);
    expect(result.lighting.shadows).toBe(true);
    expect(result.materials).toEqual({});
    expect(screen.getByLabelText('WO2 environment')).toBeTruthy();
    expect(screen.getByLabelText('WO2 texture filtering')).toBeTruthy();
  });

  it('only offers transmission and source UV transforms for actual USD actors',()=>{
    const actor={
      path:'/World/Actor',semantic_role:'actor',
      shape:'mesh',size_m:2,source_material:{
        texture:{sha256:'a'.repeat(64)},pbr_maps:{
          roughness:{sha256:'b'.repeat(64)},
        },
      },
    };
    const onLookChange=vi.fn();
    render(<DataFirstWorldViewport
      objects={[actor]} tick="0" nativeSchemas={[]}
      presentationLook={defaultWO2Look()}
      onLookChange={onLookChange}/>);
    fireEvent.change(screen.getByLabelText('WO2 physical material actor'),
      {target:{value:'/World/Actor'}});
    fireEvent.change(screen.getByLabelText('WO2 material transmission'),
      {target:{value:'0.6'}});
    const material=onLookChange.mock.lastCall[0].materials['/World/Actor'];
    expect(material.transmission).toBe(.6);
    expect(material.ior).toBe(1.5);
    expect(screen.getByLabelText('WO2 source UV channel')).toBeTruthy();
  });

  it('models Kelvin source lights with bounded nonnegative RGB',()=>{
    for(const kelvin of [1800,3200,5600,10000]){
      const rgb=approximateKelvinRGB(kelvin);
      expect(rgb).toHaveLength(3);
      expect(rgb.every(x=>x>=0&&x<=1)).toBe(true);
    }
    expect(()=>approximateKelvinRGB(Infinity)).toThrow(/temperature/);
    expect(()=>approximateKelvinRGB(-100)).toThrow(/temperature/);
  });
});
