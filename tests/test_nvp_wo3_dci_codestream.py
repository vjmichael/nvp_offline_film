"""DCI-P4A marker/rate-only fixtures. Never claim encoded or decoded picture."""
import struct
import unittest
import hashlib
from backend.nvp_dci_codestream import (inspect_cinema_codestream,ReelCodestreamAudit,
                MAX_FRAME_BYTES,MAX_2K_COMPONENT_BYTES)
from backend.nvp_wo3_j2k_audit import PROFILES,inspect_j2k_header


def marker(code, body):
    return bytes([255,code])+struct.pack('>H',len(body)+2)+body


def structural_frame(profile='2K_FLAT_24', *,width=None,height=None,levels=None,
                     lengths=None,cod=None,poc=None,tlm=None,main_extra=b'',tile_extra=b''):
    """Syntactically patterned marker fixture, NOT valid entropy packets."""
    w,h,_=PROFILES[profile]; w=w if width is None else width; h=h if height is None else height
    four=profile.startswith('4K_'); n=6 if four else 3
    d=(6 if four else 5) if levels is None else levels
    sizes=lengths or [80]*n
    siz=struct.pack('>H8IH',4 if four else 3,w,h,0,0,w,h,0,0,3)+bytes([11,1,1])*3
    if cod is None: cod=bytes([1,4,0,1,0,d,3,3,0,0,0x77]+[0x88]*d)
    if tlm is None: tlm=marker(0x55,b'\x00\x50'+b''.join(struct.pack('>BI',0,v) for v in sizes))
    if poc is None: poc=marker(0x5f,bytes([0,0,0,1,d,3,4,d,0,0,1,d+1,3,4])) if four else b''
    main=b'\xff\x4f'+marker(0x51,siz)+marker(0x52,cod)+marker(0x5c,b'\x22'+b'\x00\x01'*(1+3*d))+tlm+poc+main_extra
    parts=[]
    for i,size in enumerate(sizes):
        header=b'\xff\x90'+struct.pack('>HHIBB',10,0,size,i,n)+tile_extra+b'\xff\x93'
        parts.append(header+b'\x00'*(size-len(header)))
    return main+b''.join(parts)+b'\xff\xd9'


class DCICodestreamConstraints(unittest.TestCase):
    def test_exact_structure_2k_and_4k(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                raw=structural_frame(profile)
                r=inspect_cinema_codestream(raw,profile)
                self.assertEqual(r['bytes'],len(raw))
                self.assertEqual(r['raw_codestream_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(len(r['tile_part_bytes']),6 if profile.startswith('4K') else 3)
                self.assertEqual(r['declared_2k_component_bytes'],[80]*3)
                self.assertFalse(r['packet_membership_verified'])
                self.assertFalse(r['full_dci_codestream_conformity_verified'])
                self.assertFalse(r['dci_compliant'])
                self.assertFalse(inspect_j2k_header(raw,profile)['bitrate_verified'])

    def test_exact_frame_limit_and_one_byte_over(self):
        for profile in ('2K_FLAT_24','4K_SCOPE_24'):
            n=6 if profile.startswith('4K') else 3
            base=structural_frame(profile,lengths=[80]*n)
            difference=MAX_FRAME_BYTES-len(base)
            lengths=[80+difference//n]*n; lengths[-1]+=difference%n
            raw=structural_frame(profile,lengths=lengths)
            self.assertEqual(len(raw),MAX_FRAME_BYTES)
            inspect_cinema_codestream(raw,profile)
            lengths[-1]+=1
            with self.assertRaisesRegex(ValueError,'1,302,083'):
                inspect_cinema_codestream(structural_frame(profile,lengths=lengths),profile)

    def test_component_limits_in_2k_and_embedded_2k(self):
        for profile in ('2K_FLAT_24','4K_SCOPE_24'):
            n=6 if profile.startswith('4K') else 3
            sizes=[MAX_2K_COMPONENT_BYTES]+[80]*(n-1)
            inspect_cinema_codestream(structural_frame(profile,lengths=sizes),profile)
            sizes[0]+=1
            with self.assertRaisesRegex(ValueError,'component'):
                inspect_cinema_codestream(structural_frame(profile,lengths=sizes),profile)

    def test_missing_wrong_duplicate_tlm(self):
        for tlm in (b'',marker(0x55,b'\x00\x50'+struct.pack('>BI',0,79)*3),
                    marker(0x55,b'\x00\x50'+struct.pack('>BI',1,80)*3),
                    marker(0x55,b'\x01\x50'+struct.pack('>BI',0,80)*3),
                    marker(0x55,b'\x00\xd0'+struct.pack('>BI',0,80)*3),
                    marker(0x55,b'\x00\x50'+struct.pack('>BI',0,80)*4)):
            with self.subTest(tlm=tlm),self.assertRaises(ValueError):
                inspect_cinema_codestream(structural_frame(tlm=tlm),'2K_FLAT_24')

    def test_split_tlm_valid_order(self):
        tlm=marker(0x55,b'\x00\x40'+struct.pack('>I',80))+marker(0x55,b'\x01\x40'+struct.pack('>II',80,80))
        self.assertEqual(inspect_cinema_codestream(structural_frame(tlm=tlm),'2K_FLAT_24')['tile_part_bytes'],[80]*3)

    def test_illegal_coding_parameters(self):
        base=bytearray([1,4,0,1,0,5,3,3,0,0,0x77]+[0x88]*5)
        for index,value in ((0,0),(1,0),(3,2),(4,1),(5,6),(6,4),(7,2),(8,1),(9,1),(10,0x88),(12,0x77)):
            raw=base[:];raw[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):
                inspect_cinema_codestream(structural_frame(cod=bytes(raw)),'2K_FLAT_24')
        with self.assertRaises(ValueError):inspect_cinema_codestream(structural_frame('4K_SCOPE_24',levels=0),'4K_SCOPE_24')

    def test_poc_required_4k_forbidden_2k(self):
        for raw,profile in ((structural_frame('4K_SCOPE_24',poc=b''),'4K_SCOPE_24'),
                            (structural_frame('4K_SCOPE_24',poc=marker(0x5f,b'\x00'*14)),'4K_SCOPE_24'),
                            (structural_frame(poc=marker(0x5f,b'\x00'*14)),'2K_FLAT_24')):
            with self.assertRaisesRegex(ValueError,'POC'):inspect_cinema_codestream(raw,profile)

    def test_forbidden_or_unsupported_marker_and_tile_overrides(self):
        for code in (0x53,0x5d,0x5e,0x60,0x61,0x52,0x5c):
            with self.subTest(marker=code),self.assertRaises(ValueError):
                inspect_cinema_codestream(structural_frame(main_extra=marker(code,b'\x00')),'2K_FLAT_24')
        for code in (0x52,0x53,0x5c,0x5d,0x5f,0x61):
            with self.subTest(tile=code),self.assertRaises(ValueError):
                inspect_cinema_codestream(structural_frame(tile_extra=marker(code,b'\x00')),'2K_FLAT_24')

    def test_sot_lengths_order_count_tile_identity_and_eoc(self):
        raw=structural_frame(); i=raw.index(b'\xff\x90')
        for offset,replacement in ((2,b'\x00\x09'),(4,b'\x00\x01'),(6,b'\x00\x00\x00\x51'),(10,b'\x01'),(11,b'\x00'),(12,b'\xff\x90'),(14,b'\xff\xd9')):
            bad=raw[:i+offset]+replacement+raw[i+offset+len(replacement):]
            with self.subTest(offset=offset),self.assertRaises(ValueError):inspect_cinema_codestream(bad,'2K_FLAT_24')
        for bad in (raw[:-1],raw+b'junk',raw[:-2]+b'\xff\x93',raw[:i+30]):
            with self.assertRaises(ValueError):inspect_cinema_codestream(bad,'2K_FLAT_24')

    def test_complete_reel_order_budget_and_constant_wavelet_levels(self):
        raw=structural_frame(); other=structural_frame(main_extra=marker(0x64,b'\x00\x01x'))
        a=ReelCodestreamAudit('2K_FLAT_24'); a.add(raw)
        with self.assertRaises(ValueError):a.finish(2)
        a.add(other); r=a.finish(2)
        b=ReelCodestreamAudit('2K_FLAT_24');b.add(other);b.add(raw)
        self.assertNotEqual(r['ordered_codestream_digest'],b.finish(2)['ordered_codestream_digest'])
        self.assertFalse(r['full_dci_conformity_verified'])
        with self.assertRaisesRegex(ValueError,'Wavelet'):a.add(structural_frame(levels=4))

    def test_wrong_profile_and_header_only_refused(self):
        raw=structural_frame();i=raw.index(b'\xff\x90')
        with self.assertRaises(ValueError):inspect_cinema_codestream(raw,'4K_FLAT_24')
        head=raw[:i+12]+b'\x00'*24
        self.assertFalse(inspect_j2k_header(head,'2K_FLAT_24')['dci_compliant'])
        with self.assertRaises(ValueError):inspect_cinema_codestream(head,'2K_FLAT_24')

    def test_mxf_input_reaudits_bytes_despite_asserted_header_receipt(self):
        from backend.nvp_wo3_mxf_native import _frame_receipts
        raw=structural_frame()
        def bind(data):
            return {"format":"nvp.wo3.native_openjpeg_frame.v1","codestream":data,
                    "codestream_sha256":hashlib.sha256(data).hexdigest(),
                    "independent_header_constraints_verified":True,
                    "original_approved_presentation_sha256":"a"*64}
        self.assertEqual(_frame_receipts([bind(raw)],"2K_FLAT_24"),"a"*64)
        bad=raw[:-2]+b"\xff\x93"
        self.assertEqual(inspect_j2k_header(bad,"2K_FLAT_24")["width"],1998)
        with self.assertRaises(ValueError):_frame_receipts([bind(bad)],"2K_FLAT_24")

    def test_disk_spool_reaudits_exact_bytes(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from backend.nvp_wo4_picture_spool import verify_frame_file
        raw=structural_frame(); bad=raw+b"trailing"
        def fixture_identity(file, **kwargs):
            stat=Path(file).stat()
            return (stat.st_dev,stat.st_ino)
        with TemporaryDirectory() as temp, patch("backend.nvp_wo4_picture_spool._protected_path",side_effect=fixture_identity), patch("backend.nvp_wo4_pcm_stream._protected_path",side_effect=fixture_identity):
            # Only the Windows-specific path check is substituted; actual disk
            # reads, source digest and strict parser are exercised.
            path=Path(temp)/"frame.j2c"; path.write_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest()
            self.assertEqual(verify_frame_file(path,digest,"2K_FLAT_24"),len(raw))
            path.write_bytes(bad)
            with self.assertRaises(ValueError):
                verify_frame_file(path,hashlib.sha256(bad).hexdigest(),"2K_FLAT_24")

    def test_completed_reel_evidence_binds_exact_expected_frame_count(self):
        raw=structural_frame(); a=ReelCodestreamAudit("2K_FLAT_24")
        for _ in range(100):a.add(raw)
        self.assertEqual(a.finish(100)["frames_audited"],100)
        with self.assertRaises(ValueError):a.finish(99)

if __name__=='__main__':unittest.main()
