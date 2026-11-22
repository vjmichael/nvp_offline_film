"""Independent output-referred XYZ12 reference audit for the NVP SDR subset.

Derives the RGB and P3 matrices from xy primaries and white coordinates, rather
than importing the producer's matrices or transfer. ST 428-1:2019 §4.3, Annex B;
RP 431-2:2011 reference primaries/white. Numerical verification is NOT display
calibration, an OCIO/ACES rendering transform or an approval of a creative grade.
All tristimulus measurements here are relative to screen black.
"""
from __future__ import annotations

from hashlib import sha256

FORMAT = 'nvp.dci.xyz12_reference_audit.v1'
REVISION = 'linear-srgb-xy-d65-st428-2019-v2'
_CHUNK = 16384
# Floating-point arithmetic allowance at exact half-code boundaries only;
# not a picture quality, perceptual or projector acceptance threshold.
_HALF_CODE_EPS = 1e-8
_WHITE = {'D65_UNADAPTED': (0.3127, 0.3290),
          'DCI_REFERENCE_BRADFORD': (0.314, 0.351)}


def _xy_white(xy):
    import numpy as np
    x, y = xy
    return np.array([x / y, 1., (1. - x - y) / y], dtype=np.float64)


def _from_primaries(primaries, white):
    import numpy as np
    xy = np.asarray(primaries, dtype=np.float64).T
    columns = np.vstack((xy, 1. - xy.sum(axis=0)))
    return columns * np.linalg.solve(columns, _xy_white(white))


def _matrices(intent):
    import numpy as np
    source = _from_primaries(((.64, .33), (.30, .60), (.15, .06)),
                            _WHITE['D65_UNADAPTED'])
    if intent == 'DCI_REFERENCE_BRADFORD':
        cone = np.array(((.8951, .2664, -.1614), (-.7502, 1.7135, .0367),
                         (.0389, -.0685, 1.0296)))
        ratio = (cone @ _xy_white(_WHITE[intent]) /
                 (cone @ _xy_white(_WHITE['D65_UNADAPTED'])))
        source = np.linalg.solve(cone, ratio[:, None] * (cone @ source))
    p3 = _from_primaries(((.680, .320), (.265, .690), (.150, .060)),
                        _WHITE['DCI_REFERENCE_BRADFORD'])
    return source, np.linalg.inv(p3)


def verify_xyz12_reference(source_float32: bytes, xyz12: bytes, *, width: int,
                           height: int, source_sha256: str, xyz12_sha256: str,
                           output_white_intent: str) -> dict:
    """Verify all source-bound pixels, not only the encoded white or raster hash.

    Trusted caller supplies dimensions and digests from the approved operation;
    a numerical receipt is not authorization. The same function can be used by
    an independent readback reviewer supplied with the original source bytes.
    Working scratch is bounded by _CHUNK; no full-frame float64 expansion.
    P3 counts describe an ideal 48-nit target only. Out-of-target samples are
    exposed for a creator's review, not clipped, adapted again or called invalid
    ST 428-1 XYZ merely because an ideal P3 projector cannot reproduce them.
    """
    if (type(width) is not int or type(height) is not int or
            not 1 <= width <= 4096 or not 1 <= height <= 2160 or
            type(output_white_intent) is not str or output_white_intent not in _WHITE):
        raise ValueError('Unsupported reference dimensions or white intent')
    pixels = width * height
    for raw, samplesize, digest in ((source_float32, 12, source_sha256),
                                    (xyz12, 6, xyz12_sha256)):
        if (type(raw) is not bytes or len(raw) != pixels * samplesize or
                type(digest) is not str or sha256(raw).hexdigest() != digest):
            raise PermissionError('Reference raster identity or length mismatch')
    import numpy as np  # Numeric verification, never a metadata import prerequisite.
    source = np.frombuffer(source_float32, dtype='<f4').reshape(-1, 3)
    codes = np.frombuffer(xyz12, dtype='>u2').reshape(-1, 3)
    transform, p3_inverse = _matrices(output_white_intent)
    code_max = np.zeros(3)
    quantized_max = np.zeros(3, dtype=np.int64)
    sum_abs = np.zeros(3)
    sum_sq = np.zeros(3)
    max_nits = np.zeros(3)
    p3_lo_count = p3_hi_count = p3_out_count = boundary_count = 0
    for offset in range(0, pixels, _CHUNK):
        s = source[offset:offset + _CHUNK].astype(np.float64)
        actual = codes[offset:offset + _CHUNK].astype(np.int64)
        if not np.isfinite(s).all() or (s < 0).any() or (s > 1).any():
            raise ValueError('Invalid output-referred RGB: creator grading required')
        if (actual > 4095).any():
            raise ValueError('Illegal XYZ12 code value')
        relative = s @ transform.T
        target = relative * 48.
        if not np.isfinite(target).all() or (target < 0).any() or (target > 52.37).any():
            raise ValueError('Reference tristimulus outside supported encoding domain')
        ideal = 4095. * np.power(target / 52.37, 1. / 2.6)
        nearest = np.floor(ideal + .5).astype(np.int64)
        delta = np.abs(actual - ideal)
        # At exact mathematical ties the rule is half up. A platform-level
        # floating rounding difference can only be tolerated within 1e-8 code
        # units of a tie; record all such disagreements rather than hiding them.
        if (delta > .5 + _HALF_CODE_EPS).any():
            raise ValueError(f'Independent XYZ12 reference mismatch in block {offset}')
        boundary_count += int(np.count_nonzero(actual != nearest))
        quantized_max = np.maximum(quantized_max, np.abs(actual - nearest).max(axis=0))
        code_max = np.maximum(code_max, delta.max(axis=0))
        reconstructed = 52.37 * np.power(actual / 4095., 2.6)
        error = reconstructed - target
        sum_abs += np.abs(error).sum(axis=0)
        sum_sq += (error * error).sum(axis=0)
        max_nits = np.maximum(max_nits, np.abs(error).max(axis=0))
        p3 = relative @ p3_inverse.T
        low = (p3 < -1e-10).any(axis=1)
        high = (p3 > 1. + 1e-10).any(axis=1)
        p3_lo_count += int(low.sum())
        p3_hi_count += int(high.sum())
        p3_out_count += int((low | high).sum())
    return {
        'format': FORMAT, 'transform_revision': REVISION,
        'source_sha256': source_sha256, 'xyz12_sha256': xyz12_sha256,
        'width': width, 'height': height, 'pixels_checked': pixels,
        'output_white_intent': output_white_intent,
        'reference_white_xy': list(_WHITE[output_white_intent]),
        'reference_white_nits': 48., 'reference_math_verified': True,
        'maximum_quantization_error_code_xyz': code_max.tolist(),
        'maximum_integer_delta_xyz': quantized_max.tolist(),
        'near_tie_component_disagreements': boundary_count,
        'maximum_xyz_tristimulus_error_cd_m2': max_nits.tolist(),
        'mean_absolute_xyz_tristimulus_error_cd_m2': (sum_abs / pixels).tolist(),
        'rms_xyz_tristimulus_error_cd_m2': np.sqrt(sum_sq / pixels).tolist(),
        'ideal_p3_negative_channel_pixels': p3_lo_count,
        'ideal_p3_above_reference_drive_pixels': p3_hi_count,
        'ideal_p3_outside_reference_volume_pixels': p3_out_count,
        'gamut_mapping_applied': False,
        'independently_calibrated': False, 'production_picture_accepted': False,
    }
