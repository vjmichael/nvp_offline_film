"""Portable source and provenance denial tests; never a native decoder claim."""
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import struct
import unittest
from backend.nvp_dci_dual_decode import compare_xyz12,summarize_xyz12
from backend.nvp_wo3_codec_bundle_provenance import (DUAL_QUALIFICATION_FORMAT,
    DUAL_QUALIFICATION_REQUIRED, verify_native_codec_bundle)
from tools.nvp_dci_patch_openjpeg import patch_bytes, ANCHOR, GUARD, TARGET

class DCIQualificationTests(unittest.TestCase):
    def test_pinned_patch_unique_anchor(self):
        self.assertEqual(TARGET,1298000)
        self.assertEqual(patch_bytes(b'prefix\n'+ANCHOR),b'prefix\n'+GUARD+ANCHOR)
        self.assertIn(b'OPJ_CINEMA_24_CS',GUARD)
        for raw in (b'',ANCHOR*2,GUARD+ANCHOR):
            with self.assertRaises(ValueError):patch_bytes(raw)
    def test_component_deltas_and_exact_identity(self):
        a=struct.pack('>6H',0,1,4095,3,4,5);b=struct.pack('>6H',0,3,4094,7,4,5)
        r=compare_xyz12(a,b)
        self.assertEqual(r['max_absolute_delta_xyz'],[4,2,1]);self.assertEqual(r['different_samples_xyz'],[1,1,1])
        self.assertEqual(r['mean_absolute_delta_xyz'],[2,1,.5]);self.assertFalse(r['exact_decoder_agreement'])
        self.assertTrue(compare_xyz12(a,a)['exact_decoder_agreement'])
        self.assertFalse(r['normative_decoder_tolerance_verified'])
        for bad in (b'',b'123',a+b'123456',struct.pack('>6H',4096,0,0,0,0,0)):
            with self.assertRaises(ValueError):compare_xyz12(a,bad)
    def test_squared_signed_and_peak_metrics(self):
        a=struct.pack('>6H',1,2,3,4,5,6)
        b=struct.pack('>6H',3,1,3,2,6,6)
        r=compare_xyz12(a,b)
        self.assertEqual(r['sum_squared_delta_xyz'],[8,2,0])
        self.assertEqual(r['sum_signed_delta_xyz'],[0,0,0])
        self.assertEqual(r['rmse_xyz'],[2.,1.,0.])
        self.assertEqual(r['psnr_db_xyz'][2],None)
        self.assertAlmostEqual(r['psnr_db_xyz'][0],66.22448,places=4)
        other=compare_xyz12(a,a)
        agg=summarize_xyz12([r,other],expected_frames=2,pixels_per_frame=2)
        self.assertEqual(agg['sum_squared_delta_xyz'],[8,2,0])
        self.assertEqual(agg['pixels_compared'],4)
        self.assertAlmostEqual(agg['rmse_xyz'][0],2**.5)
        for rows,n,pixels in (([r],2,2),([r,other],1,2),([r],1,3)):
            with self.assertRaises(ValueError):summarize_xyz12(rows,expected_frames=n,pixels_per_frame=pixels)

    def test_reference_ledger_mismatch(self):
        from backend.nvp_wo3_independent_essence import _reference_ledger,_read_reference
        a=struct.pack('>3H',0,4095,1);digest=sha256(a).hexdigest()
        read=lambda _:a
        original=[digest]
        self.assertEqual(_reference_ledger(original,read,1),(digest,))
        self.assertEqual(_read_reference(read,digest,1,1),a)
        for corrupt in (lambda _:b'x'*6,lambda _:a+b'x',lambda _:bytearray(a)):
            with self.assertRaises(PermissionError):_read_reference(corrupt,digest,1,1)
        for hashes,reader,count in ((original,None,1),(None,read,1),(original,read,2),(['x'],read,1)):
            with self.assertRaises(PermissionError):_reference_ledger(hashes,reader,count)

    def test_jasper_build_outside_pinned_source(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/nvp-wo3-dcp-native.yml').read_text()
        self.assertIn('Join-Path $env:RUNNER_TEMP "nvp-jasper-qualification-build"',workflow)
        self.assertIn('cmake -S deps/jasper -B $jasperBuild',workflow)
        self.assertIn('cmake --build $jasperBuild',workflow)
        self.assertNotIn('deps/jasper/build',workflow)
        self.assertNotIn('ALLOW_IN_SOURCE_BUILD',workflow)

    def test_component_chunk_boundary_and_wide_accumulator(self):
        # Maximum 4K raster: channel sum exceeds a signed 32-bit counter.
        count=4096*2160
        a=struct.pack('>3H',4095,0,4095)*count
        b=struct.pack('>3H',0,4095,4094)*count
        r=compare_xyz12(a,b)
        self.assertEqual(r['pixels_compared'],count)
        self.assertEqual(r['max_absolute_delta_xyz'],[4095,4095,1])
        self.assertEqual(r['sum_absolute_delta_xyz'],[4095*count,4095*count,count])
        self.assertEqual(r['different_samples_xyz'],[count]*3)
        self.assertEqual(r['mean_absolute_delta_xyz'],[4095.,4095.,1.])
        self.assertEqual(r['sum_squared_delta_xyz'],[4095**2*count,4095**2*count,count])
        self.assertEqual(r['sum_signed_delta_xyz'],[-4095*count,4095*count,-count])
        # Reject over-precision beyond a chunk boundary, not just its prefix.
        with self.assertRaises(ValueError):
            compare_xyz12(a,b[:-6]+struct.pack('>3H',4096,0,0))

    def test_secondary_finite_argv(self):
        from backend.nvp_wo3_native_codecs import _approved_arguments
        role='JasPer-nvp_decode'
        good=['-i','p_000012.j2c','-o','jasper_000012.ppm']
        self.assertEqual(_approved_arguments(role,good),good)
        for bad in (good+['-v'],['-i','../p_000012.j2c','-o',good[3]],
                    ['-i',good[1],'-o','jasper_000013.ppm'],
                    ['-i',good[1],'-o','xyz_000012.ppm']):
            with self.assertRaises(PermissionError):_approved_arguments(role,bad)
    def test_dual_roster_not_release_authority_and_alias_denied(self):
        with TemporaryDirectory() as d:
            path=Path(d); tools={}
            for i,(role,(prod,license_id)) in enumerate(DUAL_QUALIFICATION_REQUIRED.items()):
                name='nvp_jasper_decode.exe' if role=='jasper-decoder' else role+'.exe'
                raw=bytes([i+1])*300; notice=prod+'.LICENSE'; text=prod.encode()*100
                (path/name).write_bytes(raw);(path/notice).write_bytes(text)
                tools[role]={'product':prod,'license':license_id,'filename':name,'sha256':sha256(raw).hexdigest(),
                    'license_notice':notice,'license_sha256':sha256(text).hexdigest()}
            m={'format':DUAL_QUALIFICATION_FORMAT,'tools':tools}
            with self.assertRaises(PermissionError):verify_native_codec_bundle(path,m)
            self.assertEqual(len(verify_native_codec_bundle(path,m,allow_dual_qualification=True)['tools']),6)
            orig=tools['openjpeg-decoder']; second=tools['jasper-decoder']
            (path/second['filename']).write_bytes((path/orig['filename']).read_bytes());second['sha256']=orig['sha256']
            with self.assertRaises(PermissionError):verify_native_codec_bundle(path,m,allow_dual_qualification=True)

if __name__=='__main__':unittest.main()
