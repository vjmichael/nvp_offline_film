"""Independent decoder numerical evidence, not source/color or ISO certification."""
from hashlib import sha256
from math import sqrt, log10
import numpy as np

MAX_RASTER_BYTES=4096*2160*6

def compare_xyz12(primary,secondary):
    if (type(primary) is not bytes or type(secondary) is not bytes or
        not 6<=len(primary)<=MAX_RASTER_BYTES or len(primary)%6 or len(primary)!=len(secondary)):
        raise ValueError('Exact matching bounded XYZ12 rasters required')
    largest=np.zeros(3,dtype=np.int64)
    summed=np.zeros(3,dtype=np.int64)
    different=np.zeros(3,dtype=np.int64)
    squared=np.zeros(3,dtype=np.int64)
    signed=np.zeros(3,dtype=np.int64)
    # 96 KiB of each raster per chunk; signed widening avoids uint16 wrap.
    # Native NumPy loops keep per-component accumulation bounded even for 4K.
    for start in range(0,len(primary),98304):
        a=np.frombuffer(primary,dtype='>u2',count=min(98304,len(primary)-start)//2,offset=start).reshape(-1,3)
        b=np.frombuffer(secondary,dtype='>u2',count=a.size,offset=start).reshape(-1,3)
        if np.any(a>4095) or np.any(b>4095):
            raise ValueError('Non-12-bit decoded sample')
        delta=b.astype(np.int32)-a.astype(np.int32)
        d=np.abs(delta)
        squared+=(delta*delta).sum(axis=0,dtype=np.int64)
        signed+=delta.sum(axis=0,dtype=np.int64)
        largest=np.maximum(largest,d.max(axis=0))
        summed+=d.sum(axis=0,dtype=np.int64)
        different+=np.count_nonzero(d,axis=0)
    largest,summed,different=largest.tolist(),summed.tolist(),different.tolist()
    pixels=len(primary)//6
    return {'primary_decoded_sha256':sha256(primary).hexdigest(),
            'secondary_decoded_sha256':sha256(secondary).hexdigest(),
            'pixels_compared':pixels,'max_absolute_delta_xyz':largest,
            'sum_absolute_delta_xyz':summed,'different_samples_xyz':different,
            'mean_absolute_delta_xyz':[x/pixels for x in summed],
            'sum_squared_delta_xyz':squared.tolist(),
            'sum_signed_delta_xyz':signed.tolist(),
            **_derived(pixels,squared.tolist(),signed.tolist()),
            'exact_decoder_agreement':not any(largest),
            'normative_decoder_tolerance_verified':False}


def _derived(pixels, squared, signed):
    # PSNR of identical components is unbounded, represented as null in JSON.
    return {'rmse_xyz':[sqrt(x/pixels) for x in squared],
            'mean_signed_delta_xyz':[x/pixels for x in signed],
            'psnr_db_xyz':[10*log10(4095**2*pixels/x) if x else None for x in squared]}


def summarize_xyz12(rows, *, expected_frames, pixels_per_frame):
    """Aggregate exact integer error totals; never average per-frame PSNRs.

    Python integers preserve multi-reel errors beyond a signed 64-bit total.
    Only internally produced full-raster comparison receipts are admitted.
    """
    if type(expected_frames) is not int or expected_frames<1 or type(pixels_per_frame) is not int or not 1<=pixels_per_frame<=MAX_RASTER_BYTES//6:
        raise ValueError('Exact positive comparison coverage required')
    keys=('max_absolute_delta_xyz','sum_absolute_delta_xyz','different_samples_xyz',
          'sum_squared_delta_xyz','sum_signed_delta_xyz')
    totals={k:[0,0,0] for k in keys}
    n=0
    for r in rows:
        if r['pixels_compared']!=pixels_per_frame or n>=expected_frames:
            raise ValueError('Incomplete or excess comparison coverage')
        for k in keys:
            vals=r[k]
            if type(vals) is not list or len(vals)!=3 or any(type(v) is not int for v in vals):
                raise ValueError('Invalid component totals')
            for c,v in enumerate(vals):
                bound={'max_absolute_delta_xyz':4095,'sum_absolute_delta_xyz':4095*pixels_per_frame,
                       'different_samples_xyz':pixels_per_frame,'sum_squared_delta_xyz':4095**2*pixels_per_frame,
                       'sum_signed_delta_xyz':4095*pixels_per_frame}[k]
                if not (-bound if k=='sum_signed_delta_xyz' else 0)<=v<=bound:
                    raise ValueError('Out-of-domain component total')
                if k==keys[0]:totals[k][c]=max(totals[k][c],v)
                else:totals[k][c]+=v
        n+=1
    if n!=expected_frames:raise ValueError('Incomplete comparison coverage')
    pixels=n*pixels_per_frame
    return {'frames_compared':n,'pixels_compared':pixels,**totals,
            'mean_absolute_delta_xyz':[v/pixels for v in totals[keys[1]]],
            **_derived(pixels,totals[keys[3]],totals[keys[4]]),
            'exact_agreement':not any(totals[keys[0]]),'normative_tolerance_verified':False}
