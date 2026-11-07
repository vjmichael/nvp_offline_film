/** WO2 bounded, cancellable, source-SHA-pinned native texture tile inspection.
 *
 * Never opens a URL or filesystem path. Only the approved native Take session
 * may return a tile, and no tile becomes an authoritative new source.
 */
export async function verifyOriginalTileDigest(packet){
  if(!packet||typeof packet.png_base64!=='string'||
     !/^[0-9a-f]{64}$/.test(packet.tile_sha256||'')||
     !globalThis.crypto?.subtle?.digest)
    throw Error('WebView2 native SHA-256 validation unavailable');
  const binary=atob(packet.png_base64);
  if(binary.length>1024*1024)
    throw Error('Original tile exceeds one MiB transport budget');
  const bytes=Uint8Array.from(binary,ch=>ch.charCodeAt(0));
  const digest=await globalThis.crypto.subtle.digest('SHA-256',bytes);
  const actual=Array.from(new Uint8Array(digest),
    x=>x.toString(16).padStart(2,'0')).join('');
  if(actual!==packet.tile_sha256)
    throw Error('Original PNG tile bytes changed after native authorization');
  return true;
}

export async function inspectOriginalTextureTiles({
  native,sessionId,asset,rig,texture,takeSha256,
  mipLevel=0,signal,onProgress,
}){
  const isRig=rig!=null;
  const method=isRig?'data_av_original_rig_texture_tile':
    'data_av_original_texture_tile';
  if(!native||typeof native[method]!=='function'||
     typeof sessionId!=='string'||sessionId.length<16||
     Boolean(asset)===Boolean(rig)||
     (!isRig&&(typeof asset.asset_id!=='string'||
       !Number.isInteger(asset.asset_revision)||asset.asset_revision<1||
       !/^[0-9a-f]{64}$/.test(asset.asset_document_sha256||'')))||
     (isRig&&(typeof rig.actor_path!=='string'||
       !rig.actor_path.startsWith('/World/')||
       !/^[0-9a-f]{64}$/.test(rig.skeleton_layer_sha256||'')))||
     !/^[0-9a-f]{64}$/.test(texture?.sha256||'')||
     !/^[0-9a-f]{64}$/.test(takeSha256||'')||
     !Number.isInteger(mipLevel)||mipLevel<0||mipLevel>3)
    throw Error('Approved original USD Take and PNG tile identity required');
  const canvas=document.createElement('canvas');
  const ctx=canvas.getContext('2d',{alpha:false});
  if(!ctx)throw Error('Disposable browser texture preview needs 2D canvas');
  let columns=null,rows=null,width=0,height=0;
  let processed=0;
  for(let y=0;rows===null||y<rows;y++){
    for(let x=0;columns===null||x<columns;x++){
      if(signal?.aborted)
        throw Error('Original source texture inspection cancelled');
      const reply=await native[method](sessionId,{
        ...(isRig?{
          actor_path:rig.actor_path,
          skeleton_layer_sha256:rig.skeleton_layer_sha256,
        }:{
          asset_id:asset.asset_id,
          asset_revision:asset.asset_revision,
          asset_document_sha256:asset.asset_document_sha256,
        }),
        texture_sha256:texture.sha256,
        mip_level:mipLevel,tile_x:x,tile_y:y,
      });
      if(reply?.format!=='nvp.original.usd_texture_tile.v1'||
         reply.source_modified!==false||
         reply.ffmpeg_used!==false||
         reply.derived_preview_only!==true||
         (isRig?(reply.actor_path!==rig.actor_path||
                  reply.skeleton_layer_sha256!==rig.skeleton_layer_sha256):
                reply.asset_document_sha256!==asset.asset_document_sha256)||
         reply.take_document_sha256!==takeSha256||
         reply.source_sha256!==texture.sha256||
         reply.mip_level!==mipLevel||
         reply.tile_x!==x||reply.tile_y!==y||
         !Number.isInteger(reply.tile_columns)||
         !Number.isInteger(reply.tile_rows)||
         !Number.isInteger(reply.level_width)||
         !Number.isInteger(reply.level_height)||
         reply.tile_columns<1||reply.tile_rows<1||
         reply.tile_columns>8||reply.tile_rows>8||
         reply.level_width>2048||reply.level_height>2048||
         reply.tile_width<1||reply.tile_width>256||
         reply.tile_height<1||reply.tile_height>256||
         !/^[0-9a-f]{64}$/.test(reply.tile_sha256||'')||
         typeof reply.png_base64!=='string'||
         reply.png_base64.length>1000000||
         !reply.png_base64.startsWith('iVBORw0KGgo'))
        throw Error('Texture tile failed original source identity check');
      if(columns===null){
        columns=reply.tile_columns;
        rows=reply.tile_rows;
        width=reply.level_width;
        height=reply.level_height;
        if(columns*rows>64||width<1||height<1)
          throw Error('Original texture tile coverage exceeds budget');
        canvas.width=width;canvas.height=height;
      }else if(columns!==reply.tile_columns||rows!==reply.tile_rows||
               width!==reply.level_width||height!==reply.level_height){
        throw Error('Source texture tile dimensions changed mid-inspection');
      }
      await verifyOriginalTileDigest(reply);
      if(signal?.aborted)
        throw Error('Original texture inspection cancelled');
      const tile=await new Promise((resolve,reject)=>{
        const image=new Image();
        image.onload=()=>resolve(image);
        image.onerror=()=>reject(Error('Approved source PNG tile decode failed'));
        image.src='data:image/png;base64,'+reply.png_base64;
      });
      if(signal?.aborted)throw Error('Original texture inspection cancelled');
      if(tile.width!==reply.tile_width||tile.height!==reply.tile_height||
         x*256+tile.width>width||y*256+tile.height>height)
        throw Error('Texture tile pixels do not fit the original extent');
      ctx.drawImage(tile,x*256,y*256);
      processed++;
      if(typeof onProgress==='function')
        onProgress({completed:processed,total:columns*rows});
    }
  }
  return {format:'nvp.wo2.derived_texture_inspection.v1',
    source_sha256:texture.sha256,
    take_document_sha256:takeSha256,
    source_rig_binding:isRig?rig:null,
    canvas,width,height,mip_level:mipLevel,
    tiles_verified:processed,source_modified:false,
    derived_preview_only:true,hardware_gpu_uploaded:false};
}
