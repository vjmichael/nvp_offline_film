import {describe,it,expect} from 'vitest';
import {
  WO2_LOOK_FORMAT,defaultWO2Look,validateWO2Look,
  suggestWO2Look,textureChannelLook,physicalMaterialLook,
} from './WO2PresentationLook.js';

const roles={
  '/World/Actor':'actor','/World/Window':'prop',
  '/World/Camera':'camera',
};

describe('WO2 A–E creator look contracts and safe assistant proposals',()=>{
  it('supports all source-preserving creative controls in a typed look',()=>{
    const look=defaultWO2Look();
    look.environment.preset='golden_hour';
    look.camera.depth_of_field=true;
    look.camera.f_stop=2;
    look.camera.focus_distance_m=3.5;
    look.materials['/World/Window']={
      opacity:.75,transmission:.9,ior:1.52,thickness_m:.01};
    look.textures.transforms['/World/Actor']={
      base_color:{repeat:[2,3],offset:[.2,.1],rotation_deg:45}};
    const checked=validateWO2Look(look,roles);
    expect(checked).toEqual(look);
    expect(textureChannelLook(checked,'/World/Actor','base_color')
      .rotation_deg).toBe(45);
    expect(physicalMaterialLook(checked,'/World/Window')
      .transmission).toBe(.9);
    checked.camera.exposure_ev=2;
    expect(look.camera.exposure_ev).toBe(0);
    expect(WO2_LOOK_FORMAT).toMatch(/source_bound_presentation/);
  });

  it('refuses arbitrary shader paths, forged assets and NaN optics',()=>{
    const look=defaultWO2Look();
    look.materials['/Private/Untrusted']={
      opacity:1,transmission:1,ior:1.5,thickness_m:0};
    expect(()=>validateWO2Look(look,roles)).toThrow(/not source-authorized/);
    delete look.materials['/Private/Untrusted'];
    look.environment.preset='https://evil.example/exr';
    expect(()=>validateWO2Look(look,roles)).toThrow(/environment/);
    look.environment.preset='neutral_studio';
    look.camera.f_stop=NaN;
    expect(()=>validateWO2Look(look,roles)).toThrow(/camera/);
    look.camera.f_stop=4;
    look.textures.transforms['/World/Camera']={
      normal:{repeat:[1,1],offset:[0,0],rotation_deg:0}};
    expect(()=>validateWO2Look(look,roles)).toThrow(/source USD/);
  });

  it('offers helpful cinematic intents but never self-approves sources',()=>{
    for(const mood of ['natural','dramatic','warm','night','product']){
      const proposal=suggestWO2Look(mood,roles);
      expect(proposal.look).toEqual(validateWO2Look(proposal.look,roles));
      expect(proposal.persisted).toBe(false);
      expect(proposal.creator_approved).toBe(false);
      expect(proposal.original_source_modified).toBe(false);
    }
    expect(suggestWO2Look('night',roles).look.environment.preset)
      .toBe('moonlight');
    expect(suggestWO2Look('dramatic',roles).look.camera.exposure_ev)
      .toBeLessThan(0);
    expect(()=>suggestWO2Look('execute arbitrary script',roles))
      .toThrow(/Unknown/);
  });
});
