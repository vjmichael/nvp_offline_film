/** WO2-A–E: typed non-destructive OpenUSD presentation look.
 *
 * This module does not write scene meshes, Digital Takes, PNGs, USD layers or
 * permit arbitrary shader programs. Native FilmIndex owns approved revisions.
 * Local suggestions remain disposable until a real desktop approval.
 */
export const WO2_LOOK_FORMAT='nvp.wo2.source_bound_presentation_look.v1';
export const WO2_ENVIRONMENTS=Object.freeze([
  'neutral_studio','soft_daylight','golden_hour','moonlight']);
export const WO2_MOODS=Object.freeze([
  'natural','dramatic','warm','night','product']);

export function defaultWO2Look(){
  return {
    lighting:{shadows:true,shadow_resolution:1024,shadow_softness:2,
      direct_intensity:2.5,ambient_intensity:.7},
    environment:{preset:'neutral_studio',intensity:1,reflections:1},
    camera:{exposure_ev:0,tone_curve:'filmic_preview',
      depth_of_field:false,f_stop:4,focus_distance_m:5},
    textures:{filter:'trilinear',anisotropy:4,transforms:{}},
    materials:{},
  };
}
const finite=(v,min,max)=>typeof v==='number'&&
  Number.isFinite(v)&&v>=min&&v<=max;
const keys=(value,expected)=>value&&typeof value==='object'&&
  !Array.isArray(value)&&Object.keys(value).length===expected.length&&
  expected.every(k=>Object.prototype.hasOwnProperty.call(value,k));
const pair=(x,min,max)=>Array.isArray(x)&&x.length===2&&
  x.every(v=>finite(v,min,max));
export function validateWO2Look(value,roles={}){
  if(!keys(value,['lighting','environment','camera','textures','materials']))
    throw Error('Malformed bounded original scene presentation look');
  const {lighting:l,environment:e,camera:c,textures:t,materials:m}=value;
  if(!keys(l,['shadows','shadow_resolution','shadow_softness',
              'direct_intensity','ambient_intensity'])||
     typeof l.shadows!=='boolean'||
     ![512,1024,2048].includes(l.shadow_resolution)||
     !finite(l.shadow_softness,0,12)||
     !finite(l.direct_intensity,0,12)||
     !finite(l.ambient_intensity,0,4))
    throw Error('Untrusted light and shadow presentation');
  if(!keys(e,['preset','intensity','reflections'])||
     !WO2_ENVIRONMENTS.includes(e.preset)||
     !finite(e.intensity,0,4)||!finite(e.reflections,0,3))
    throw Error('Untrusted environment presentation');
  if(!keys(c,['exposure_ev','tone_curve','depth_of_field',
              'f_stop','focus_distance_m'])||
     !finite(c.exposure_ev,-8,8)||
     !['linear','filmic_preview'].includes(c.tone_curve)||
     typeof c.depth_of_field!=='boolean'||
     !finite(c.f_stop,1,22)||!finite(c.focus_distance_m,.1,10000))
    throw Error('Untrusted source camera preview');
  if(!keys(t,['filter','anisotropy','transforms'])||
     !['nearest','bilinear','trilinear'].includes(t.filter)||
     ![1,2,4,8,16].includes(t.anisotropy)||
     !t.transforms||typeof t.transforms!=='object'||
     Array.isArray(t.transforms)||
     Object.keys(t.transforms).length>32)
    throw Error('Untrusted original source texture filtering');
  for(const [path,channels] of Object.entries(t.transforms)){
    if(!['actor','prop','environment'].includes(roles[path])||
       !channels||typeof channels!=='object'||Array.isArray(channels)||
       !Object.keys(channels).length||Object.keys(channels).length>6)
      throw Error('Texture transform not bound to source USD actor');
    for(const [channel,uv] of Object.entries(channels)){
      if(!['base_color','roughness','metallic','emission',
           'normal','opacity'].includes(channel)||
         !keys(uv,['repeat','offset','rotation_deg'])||
         !pair(uv.repeat,.01,64)||!pair(uv.offset,-64,64)||
         !finite(uv.rotation_deg,-360,360))
        throw Error('Unsupported source texture UV presentation');
    }
  }
  if(!m||typeof m!=='object'||Array.isArray(m)||
     Object.keys(m).length>32)
    throw Error('Untrusted source material presentation');
  for(const [path,mat] of Object.entries(m)){
    if(!['actor','prop','environment'].includes(roles[path])||
       !keys(mat,['opacity','transmission','ior','thickness_m'])||
       !finite(mat.opacity,0,1)||!finite(mat.transmission,0,1)||
       !finite(mat.ior,1,2.5)||!finite(mat.thickness_m,0,10))
      throw Error('Physical presentation material not source-authorized');
  }
  return structuredClone(value);
}
export function suggestWO2Look(mood,roles={}){
  if(!WO2_MOODS.includes(mood))throw Error('Unknown cinematic intent');
  const look=defaultWO2Look();
  if(mood==='dramatic'){
    look.lighting.direct_intensity=4;
    look.lighting.ambient_intensity=.28;
    look.camera.exposure_ev=-.6;
  }else if(mood==='warm'){
    look.environment.preset='golden_hour';
    look.lighting.direct_intensity=2.8;
  }else if(mood==='night'){
    look.environment.preset='moonlight';
    look.camera.exposure_ev=-1;
    look.lighting.ambient_intensity=.3;
    look.lighting.direct_intensity=.8;
  }else if(mood==='product'){
    look.environment.reflections=1.5;
    look.lighting.shadow_softness=4;
  }
  return {
    format:'nvp.wo2.creator_look_proposal.v1',
    intent:mood,look:validateWO2Look(look,roles),
    persisted:false,creator_approved:false,
    original_source_modified:false,
  };
}
export function textureChannelLook(look,path,channel){
  return look.textures.transforms[path]?.[channel]||{
    repeat:[1,1],offset:[0,0],rotation_deg:0};
}
export function physicalMaterialLook(look,path){
  return look.materials[path]||{
    opacity:1,transmission:0,ior:1.5,thickness_m:0};
}
