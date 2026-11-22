"""Source-bound digital reference checks, never a physical calibration claim."""
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch

import numpy as np
from backend.nvp_dci_color_reference import verify_xyz12_reference, REVISION
from backend.nvp_wo4_xyz12_master import encode_linear_rgb_d65_to_xyz12

PROFILE = '2K_FLAT_24'
D65 = 'D65_UNADAPTED'
DCI = 'DCI_REFERENCE_BRADFORD'


def encode(raw, intent=DCI):
    # Small mathematical fixtures; true raster dimensions verified separately.
    with patch('backend.nvp_wo4_xyz12_master.PROFILES', {PROFILE: (len(raw)//12, 1, 24)}):
        return encode_linear_rgb_d65_to_xyz12(raw, profile=PROFILE,
            source_sha256=sha256(raw).hexdigest(), original_take_sha256='a'*64,
            creator_approved=True, output_white_intent=intent)


def audit(raw, candidate, *, intent=None, output=None, **changes):
    output = candidate['xyz12'] if output is None else output
    args = dict(width=len(raw)//12, height=1, source_sha256=sha256(raw).hexdigest(),
                xyz12_sha256=sha256(output).hexdigest(),
                output_white_intent=intent or candidate['output_white_intent'])
    args.update(changes)
    return verify_xyz12_reference(raw, output, **args)


class ColorReferenceTests(unittest.TestCase):
    def test_published_black_and_white_code_anchors(self):
        raw = struct.pack('<ffffff', 0, 0, 0, 1, 1, 1)
        # RP 431-2:2011 Table A-4 White-1/2; ST 428-1:2019 Annex B.
        for intent, expected in ((DCI, (3794, 3960, 3890)),
                                 (D65, (3883, 3960, 4092))):
            with self.subTest(intent=intent):
                candidate = encode(raw, intent)
                self.assertEqual(struct.unpack('>6H', candidate['xyz12']), (0,0,0)+expected)
                report = candidate['color_reference_audit']
                self.assertEqual(report, audit(raw, candidate))
                self.assertEqual(report['transform_revision'], REVISION)
                self.assertTrue(report['reference_math_verified'])
                self.assertFalse(report['independently_calibrated'])
                self.assertFalse(candidate['production_picture_accepted'])

    def test_srgb_primaries_and_neutral_fixed_golden_values(self):
        raw = struct.pack('<12f', 1,0,0,0,1,0,0,0,1,.18,.18,.18)
        # Independently derived from the declared primary xy and D65-to-DCI
        # Bradford adaptation, ST 428 transfer; not native P3 color patches.
        expected = {D65: (2817,2183,868,2666,3481,1747,2050,1441,3884,2008,2048,2116),
                    DCI: (2782,2165,823,2604,3501,1693,1954,1392,3682,1962,2048,2011)}
        for intent in expected:
            result = encode(raw, intent)
            self.assertEqual(struct.unpack('>12H', result['xyz12']), expected[intent])

    def test_gradient_monotonicity_shadow_and_highlight_detail(self):
        # Float32 exact inputs, sample uniform in code space to cover the
        # nonlinear shadows as well as bright highlights; no 8-bit collapse.
        gray = np.power(np.linspace(0, 1, 4096), 2.6).astype('<f4')
        raw = np.repeat(gray[:, None], 3, axis=1).tobytes()
        for intent in (D65, DCI):
            result = encode(raw, intent)
            codes = np.frombuffer(result['xyz12'], dtype='>u2').reshape(-1,3).astype(int)
            self.assertTrue((np.diff(codes, axis=0) >= 0).all())
            self.assertGreater(len(np.unique(codes[:,1])), 3900)
            self.assertGreater(len(np.unique(codes[-64:,1])), 60)
            self.assertGreater(len(np.unique(codes[:64,1])), 60)
            self.assertLessEqual(max(result['color_reference_audit']['maximum_quantization_error_code_xyz']), .50000001)

    def test_gamut_volume_diagnostic_is_not_a_hidden_gamut_mapping(self):
        raw = struct.pack('<6f',1,1,1,0,0,1)
        unadapted = encode(raw, D65)['color_reference_audit']
        adapted = encode(raw, DCI)['color_reference_audit']
        self.assertEqual(unadapted['ideal_p3_above_reference_drive_pixels'], 2)
        self.assertEqual(adapted['ideal_p3_outside_reference_volume_pixels'], 0)
        self.assertFalse(unadapted['gamut_mapping_applied'])

    def test_wrong_component_and_wrong_white_fail_even_after_rehash(self):
        raw = struct.pack('<3f', .9, .2, .4)
        candidate = encode(raw)
        codes = list(struct.unpack('>3H', candidate['xyz12']))
        tampered = struct.pack('>3H', codes[0]+2, codes[1], codes[2])
        with self.assertRaises(ValueError):
            audit(raw, candidate, output=tampered)
        with self.assertRaises(ValueError):
            audit(raw, candidate, intent=D65)
        with self.assertRaises(ValueError):
            audit(raw, candidate, output=struct.pack('>3H', *codes[::-1]))

    def test_valid_sha_is_not_proof_of_transform(self):
        raw = struct.pack('<3f', .3,.4,.5)
        candidate = encode(raw)
        with self.assertRaises(PermissionError):
            audit(raw, candidate, source_sha256='0'*64)
        with self.assertRaises(PermissionError):
            audit(raw, candidate, xyz12_sha256='0'*64)
        with self.assertRaises(PermissionError):
            audit(raw, candidate, output=candidate['xyz12'][:-2])
        with self.assertRaises(ValueError):
            audit(raw, candidate, output=struct.pack('>3H',4096,0,0))
        with self.assertRaises(ValueError):
            audit(raw, candidate, width=True)

    def test_late_block_invalid_source_or_changed_code_fails(self):
        width, height = 2048, 9
        raw = struct.pack('<3f',.1,.2,.3)*(width*height)
        candidate = encode(raw[:12])
        actual = candidate['xyz12']*(width*height)
        kw = dict(width=width, height=height, output_white_intent=DCI)
        report = verify_xyz12_reference(raw, actual, source_sha256=sha256(raw).hexdigest(),
                                       xyz12_sha256=sha256(actual).hexdigest(), **kw)
        self.assertEqual(report['pixels_checked'], width*height)
        for original, encoded in (
                (raw[:-12]+struct.pack('<3f',1.01,.2,.3), actual),
                (raw[:-12]+struct.pack('<3f',float('nan'),.2,.3), actual),
                (raw, actual[:-6]+b'\x00'*6)):
            with self.assertRaises(ValueError):
                verify_xyz12_reference(original, encoded, source_sha256=sha256(original).hexdigest(),
                                       xyz12_sha256=sha256(encoded).hexdigest(), **kw)

    def test_auditor_rejects_defective_producer_even_with_valid_source_identity(self):
        raw = struct.pack('<3f', .3,.4,.5)
        with patch('backend.nvp_wo4_xyz12_master.GAMMA', 2.2):
            with self.assertRaises(ValueError):
                encode(raw)
        with patch('backend.nvp_wo4_xyz12_master.RGB_D65_TO_XYZ', ((.5,0,0),(0,.5,0),(0,0,.5))):
            with self.assertRaises(ValueError):
                encode(raw)

    def test_actual_full_size_2k_and_4k_rasters(self):
        # Real profile dimensions, deterministic binary-fraction source values.
        from backend.nvp_wo3_j2k_audit import PROFILES
        for profile, intent in (('2K_FLAT_24',D65), ('4K_SCOPE_24',DCI)):
            width,height,_ = PROFILES[profile]
            x = np.arange(width,dtype=np.int32) % 1024
            rows = []
            for y in range(32):
                rows.append(np.column_stack((x/1024., np.full(width,y/32.),
                    (1023-x)/1024.)).astype('<f4').tobytes())
            raw = b''.join(rows[y%32] for y in range(height))
            digest = sha256(raw).hexdigest()
            result = encode_linear_rgb_d65_to_xyz12(raw,profile=profile,
                source_sha256=digest,original_take_sha256='a'*64,
                creator_approved=True,output_white_intent=intent)
            report = verify_xyz12_reference(raw,result['xyz12'],width=width,height=height,
                source_sha256=digest,xyz12_sha256=result['xyz12_sha256'],
                output_white_intent=intent)
            self.assertEqual(report, result['color_reference_audit'])
            self.assertEqual(report['pixels_checked'], width*height)
            self.assertEqual(report['maximum_integer_delta_xyz'], [0,0,0])
            self.assertFalse(report['independently_calibrated'])
            self.assertEqual(digest, sha256(raw).hexdigest())

    def test_dense_mixed_color_cube_matches_independent_reference(self):
        v = np.linspace(0.,1.,13,dtype='<f4')
        raw = np.stack(np.meshgrid(v,v,v,indexing='ij'),axis=-1).astype('<f4').tobytes()
        for intent in (D65, DCI):
            receipt = encode(raw,intent)['color_reference_audit']
            self.assertEqual(receipt['pixels_checked'],13**3)
            self.assertEqual(receipt['maximum_integer_delta_xyz'],[0,0,0])
            self.assertLessEqual(max(receipt['maximum_quantization_error_code_xyz']), .50000001)


if __name__ == '__main__':
    unittest.main()
