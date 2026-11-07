/** WO2 bounded, cancellable, source-SHA-pinned native texture tile inspection.
 *
 * Never opens a URL or filesystem path. Only the approved native Take session
 * may return a tile, and no tile becomes an authoritative new source.
 */
export async function inspectOriginalTextureTiles({
  native,sessionId,asset,texture,takeSha256,
  mipLevel=0,signal,onProgress,
}){
  if(!native||typeof native.data_av_original_texture_tile!=='function'||
     typeof sessionId!=='string'||sessionId.length<16||
     !asset||typeof asset.asset_id!=='string'||
     !Number.isInteger(asset.asset_revision)||asset.asset_revision<1||
     !/^[0-9a-f]{64}$/.test(asset.asset_document_sha256||'')||
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
      const reply=await native.data_av_original_texture_tile(sessionId,{
        asset_id:asset.asset_id,
        asset_revision:asset.asset_revision,
        asset_document_sha256:asset.asset_document_sha256,
        texture_sha256:texture.sha256,
        mip_level:mipLevel,tile_x:x,tile_y:y,
      });
      if(reply?.format!=='nvp.original.usd_texture_tile.v1'||
         reply.source_modified!==false||
         reply.ffmpeg_used!==false||
         reply.derived_preview_only!==true||
         reply.asset_document_sha256!==asset.asset_document_sha256||
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
    canvas,width,height,mip_level:mipLevel,
    tiles_verified:processed,source_modified:false,
    derived_preview_only:true,hardware_gpu_uploaded:false};
}
