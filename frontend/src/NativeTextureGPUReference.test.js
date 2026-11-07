import {describe,it,expect} from 'vitest';
import {compareGPUTexturePixels} from './NativeTextureGPUReference.js';

function pixels(){
  const out=new Uint8Array(4*4*4);
  const color=(x,y)=>{
    const left=x<2,bottom=y<2;
    if(left&&bottom)return [255,0,0];
    if(!left&&bottom)return [0,0,255];
    if(left&&!bottom)return [0,255,0];
    return [255,255,255];
  };
  for(let y=0;y<4;y++)for(let x=0;x<4;x++){
    const base=(y*4+x)*4;
    out.set([...color(x,y),255],base);
  }
  return out;
}

describe('WO2 GPU texture acceptance receipt policy',()=>{
  it('compares four independent corners in the same bottom-origin USD UV fixture',()=>{
    const receipt=compareGPUTexturePixels(pixels());
    expect(receipt.passed).toBe(true);
    expect(receipt.max_channel_error).toBe(0);
    expect(receipt.full_usd_material_parity_proven).toBe(false);
    expect(receipt.physical_display_calibrated).toBe(false);
  });
  it('fails altered GPU pixels and cannot accept invented empty output',()=>{
    const data=pixels();
    data[0]=0;
    const result=compareGPUTexturePixels(data);
    expect(result.passed).toBe(false);
    expect(result.max_channel_error).toBe(255);
    expect(()=>compareGPUTexturePixels(new Uint8Array(3))).toThrow();
    expect(()=>compareGPUTexturePixels(pixels(),{tolerance:255})).toThrow();
  });
});
