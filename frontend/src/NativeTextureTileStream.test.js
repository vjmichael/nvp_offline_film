import {describe,it,expect,vi,afterEach} from 'vitest';
import {inspectOriginalTextureTiles} from './NativeTextureTileStream.js';

const asset={asset_id:'OriginalMesh',asset_revision:1,
  asset_document_sha256:'a'.repeat(64)};
const texture={sha256:'b'.repeat(64)};
const takeSha256='c'.repeat(64);
let originalImage=globalThis.Image;
const context=()=>({drawImage:vi.fn()});

afterEach(()=>{
  vi.restoreAllMocks();
  globalThis.Image=originalImage;
});

function nativeTile(overrides={}){
  return {
    format:'nvp.original.usd_texture_tile.v1',
    source_sha256:texture.sha256,
    take_document_sha256:takeSha256,
    asset_document_sha256:asset.asset_document_sha256,
    mip_level:0,tile_x:0,tile_y:0,
    tile_columns:1,tile_rows:1,
    level_width:2,level_height:2,
    tile_width:2,tile_height:2,
    tile_sha256:'d'.repeat(64),
    png_base64:'iVBORw0KGgoAAAA',
    derived_preview_only:true,source_modified:false,ffmpeg_used:false,
    ...overrides,
  };
}

describe('WO2 Take-scoped native mip tile stream',()=>{
  it('requests one original asset tile and assembles only an ephemeral image',async()=>{
    const drawn=context();
    vi.spyOn(HTMLCanvasElement.prototype,'getContext')
      .mockReturnValue(drawn);
    globalThis.Image=class{
      width=2;height=2;
      set src(value){
        if(!value.startsWith('data:image/png;base64,'))
          throw Error('Unexpected network image');
        queueMicrotask(()=>this.onload?.());
      }
    };
    const bridge={data_av_original_texture_tile:vi.fn(async()=>nativeTile())};
    const result=await inspectOriginalTextureTiles({
      native:bridge,sessionId:'s'.repeat(24),
      asset,texture,takeSha256,mipLevel:0});
    expect(result.tiles_verified).toBe(1);
    expect(result.source_modified).toBe(false);
    expect(result.hardware_gpu_uploaded).toBe(false);
    expect(drawn.drawImage).toHaveBeenCalledTimes(1);
    expect(bridge.data_av_original_texture_tile).toHaveBeenCalledWith(
      's'.repeat(24),{
        asset_id:'OriginalMesh',asset_revision:1,
        asset_document_sha256:asset.asset_document_sha256,
        texture_sha256:texture.sha256,mip_level:0,tile_x:0,tile_y:0,
      });
  });

  it('rejects forged original SHA, unbounded tile grid and cancellation',async()=>{
    const drawn=context();
    vi.spyOn(HTMLCanvasElement.prototype,'getContext')
      .mockReturnValue(drawn);
    const bridge={data_av_original_texture_tile:vi.fn(
      async()=>nativeTile({source_sha256:'0'.repeat(64)}))};
    await expect(inspectOriginalTextureTiles({
      native:bridge,sessionId:'s'.repeat(24),
      asset,texture,takeSha256})).rejects.toThrow(/identity check/);
    bridge.data_av_original_texture_tile.mockResolvedValue(
      nativeTile({tile_columns:9}));
    await expect(inspectOriginalTextureTiles({
      native:bridge,sessionId:'s'.repeat(24),
      asset,texture,takeSha256})).rejects.toThrow(/identity check/);
    const aborter=new AbortController();
    aborter.abort();
    await expect(inspectOriginalTextureTiles({
      native:bridge,sessionId:'s'.repeat(24),
      asset,texture,takeSha256,signal:aborter.signal,
    })).rejects.toThrow(/cancelled/);
  });
});
