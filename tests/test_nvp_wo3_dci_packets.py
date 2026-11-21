"""Tier-2 negative/geometry tests; synthetic empties are not decoded movie evidence."""
import os
from pathlib import Path
import struct
import unittest
from backend.nvp_dci_codestream import inspect_cinema_codestream
from backend.nvp_dci_packets import inspect_cinema_packets, ReelPacketAudit, _Bits, _passes, _Tree
from test_nvp_wo3_dci_codestream import structural_frame

# Independently specified packet counts for the canonical default resolutions.
COUNTS={'2K_FLAT_24':[59]*3,'2K_FULL_24':[59]*3,'2K_SCOPE_24':[45]*3,
        '4K_SCOPE_24':[45]*3+[112]*3,'4K_FULL_24':[59]*3+[144]*3,
        '4K_FLAT_24':[59]*3+[144]*3}

def empty_frame(profile, counts=None):
    return structural_frame(profile,lengths=[14+n for n in (counts or COUNTS[profile])])

class Tier2Tests(unittest.TestCase):
    def test_all_six_geometries_and_exact_packet_counts(self):
        for p,counts in COUNTS.items():
            with self.subTest(profile=p):
                raw=empty_frame(p); r=inspect_cinema_packets(raw,p)
                self.assertTrue(r['packet_coverage_verified'])
                self.assertEqual([v['packets'] for v in r['packet_parts']],counts)
                self.assertEqual([v['component'] for v in r['packet_parts']],list(range(3))*(2 if p.startswith('4K') else 1))
                self.assertEqual(sum(v['packet_body_bytes'] for v in r['packet_parts']),0)
                self.assertFalse(r['entropy_decoded']); self.assertFalse(r['dci_compliant'])
    def test_marker_pass_does_not_imply_packet_pass(self):
        for p in COUNTS:
            for delta in (-1,1):
                n=COUNTS[p][:];n[-1]+=delta;raw=empty_frame(p,n)
                inspect_cinema_codestream(raw,p)
                with self.subTest(profile=p,delta=delta),self.assertRaises(ValueError):
                    inspect_cinema_packets(raw,p)
    def test_same_total_bytes_wrong_tile_part_coverage(self):
        for p in ('2K_FLAT_24','4K_SCOPE_24'):
            n=COUNTS[p][:];n[0]+=1;n[-1]-=1;raw=empty_frame(p,n)
            self.assertEqual(len(raw),len(empty_frame(p)))
            inspect_cinema_codestream(raw,p)
            with self.assertRaises(ValueError):inspect_cinema_packets(raw,p)
    def test_cross_4k_resolution_group_wrong_sizes(self):
        p='4K_SCOPE_24'; raw=empty_frame(p,[112]*3+[45]*3)
        inspect_cinema_codestream(raw,p)
        with self.assertRaises(ValueError):inspect_cinema_packets(raw,p)
    def test_padding_and_overlong_zero_bitplane(self):
        p='2K_FLAT_24';raw=bytearray(empty_frame(p));start=raw.index(b'\xff\x90')+14
        raw[start]=1 # empty bit with nonzero padding
        inspect_cinema_codestream(bytes(raw),p)
        with self.assertRaisesRegex(ValueError,'padding'):inspect_cinema_packets(bytes(raw),p)
        raw[start]=0xe0 # present + root + leaf inclusion; zero QCD capacity
        with self.assertRaises(ValueError):inspect_cinema_packets(bytes(raw),p)
    def test_bitstuffing_and_pass_code_boundaries(self):
        def stuff(bits):
            output=bytearray(); offset=0
            while offset<len(bits):
                n=7 if output and output[-1]==255 else 8
                output.append(int(bits[offset:offset+n].ljust(n,'0'),2));offset+=n
            return bytes(output)
        cases=[('0',1),('10',2),('1100',3),('1101',4),('1110',5),
               ('1111'+'00000',6),('1111'+'11110',36),
               ('1111'+'11111'+'0000000',37),('1111'+'11111'+'1111111',164)]
        for code,expected in cases:
            encoded=stuff(code)
            self.assertEqual(_passes(_Bits(encoded,0,len(encoded))),expected)
        b=_Bits(b'\xff\x80',0,2);b.read(8)
        with self.assertRaisesRegex(ValueError,'stuffing'):b.read()
        b=_Bits(b'\xff\x00',0,2);b.read(8);self.assertEqual(b.align(),2)
        b=_Bits(b'\xff',0,1);b.read(8)
        with self.assertRaisesRegex(ValueError,'stuffing'):b.align()
    def test_tag_tree_shared_parent_and_leaf(self):
        t=_Tree(2,1);b=_Bits(b'\xa0',0,1) # root=0, first leaf>=1, second leaf=0
        self.assertFalse(t.below(0,0,1,b));self.assertTrue(t.below(1,0,1,b))
    def test_reel_digest_order_and_failed_add_atomicity(self):
        p='2K_FLAT_24';a=empty_frame(p);b=structural_frame(p,lengths=[73]*3,main_extra=b'\xff\x64\x00\x04\x00\x01')
        r=ReelPacketAudit(p);r.add(a)
        with self.assertRaises(ValueError):r.add(structural_frame(p))
        with self.assertRaises(ValueError):r.finish(2)
        r.add(b);x=r.finish(2);s=ReelPacketAudit(p);s.add(b);s.add(a)
        self.assertNotEqual(x['ordered_packet_map_digest'],s.finish(2)['ordered_packet_map_digest'])
        self.assertEqual(x['packets_audited'],354)
        self.assertFalse(x['full_dci_conformity_verified'])
    @unittest.skipUnless(os.environ.get('NVP_P4B_FIXTURES'),'Optional real local fixture directory')
    def test_real_native_patterned_frames_and_corrupt_packet_headers(self):
        root=Path(os.environ['NVP_P4B_FIXTURES'])
        for name,p in [('2k','2K_FLAT_24'),('2k-full','2K_FULL_24'),('2k-scope','2K_SCOPE_24'),('4k','4K_SCOPE_24'),('4k-flat','4K_FLAT_24'),('4k-full','4K_FULL_24')]:
            raw=(root/(name+'.j2c')).read_bytes();r=inspect_cinema_packets(raw,p)
            self.assertEqual(r['packets_audited'],sum(COUNTS[p]));self.assertGreater(sum(x['included_codeblocks'] for x in r['packet_parts']),0)
            i=r['main_header_bytes']+14;bad=raw[:i]+b'\x00'+raw[i+1:]
            with self.assertRaises(ValueError):inspect_cinema_packets(bad,p)

if __name__=='__main__':unittest.main()
