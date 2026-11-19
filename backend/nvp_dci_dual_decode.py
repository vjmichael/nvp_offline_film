"""Independent decoder numerical evidence, not source/color or ISO certification."""
from hashlib import sha256
import numpy as np

MAX_RASTER_BYTES=4096*2160*6

def compare_xyz12(primary,secondary):
    if (type(primary) is not bytes or type(secondary) is not bytes or
        not 6<=len(primary)<=MAX_RASTER_BYTES or len(primary)%6 or len(primary)!=len(secondary)):
        raise ValueError('Exact matching bounded XYZ12 rasters required')
    largest=np.zeros(3,dtype=np.int64)
    summed=np.zeros(3,dtype=np.int64)
    different=np.zeros(3,dtype=np.int64)
    # 96 KiB of each raster per chunk; signed widening avoids uint16 wrap.
    # Native NumPy loops keep per-component accumulation bounded even for 4K.
    for start in range(0,len(primary),98304):
        a=np.frombuffer(primary,dtype='>u2',count=min(98304,len(primary)-start)//2,offset=start).reshape(-1,3)
        b=np.frombuffer(secondary,dtype='>u2',count=a.size,offset=start).reshape(-1,3)
        if np.any(a>4095) or np.any(b>4095):
            raise ValueError('Non-12-bit decoded sample')
        d=np.abs(a.astype(np.int32)-b.astype(np.int32))
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
            'exact_decoder_agreement':not any(largest),
            'normative_decoder_tolerance_verified':False}
