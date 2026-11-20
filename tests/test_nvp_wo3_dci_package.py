"""Independent package grammar, rehashed mutations, and writer tests.

All MXF bytes here are deliberately metadata-only fixtures, never native proof.
"""
from hashlib import sha1,sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from xml.etree import ElementTree as ET
import base64
import os
import unittest
from backend.nvp_dci_package import inspect_cinema_package
from backend.nvp_wo3_dcp_package import _compose_xml
from backend.nvp_wo4_file_dcp import _xml_package,_memory_digest
from backend.nvp_wo4_multireel import _make_xml
from backend.nvp_wo3_dcp_structure import NS_AM,NS_PKL,NS_CPL,inspect_dcp_structure

ISSUED='2026-11-19T12:00:00+00:00'
def q(ns,name):return '{'+ns+'}'+name

def uid():return str(uuid4())

class PackageProfile(unittest.TestCase):
    def setUp(self):
        d=TemporaryDirectory();self.addCleanup(d.cleanup);self.root=Path(d.name).resolve()
        self.ids={k:uid() for k in ('cpl','pkl','assetmap','picture','sound','reel')}
        self.media={'picture.mxf':b'picture placeholder' * 16,'sound.mxf':b'sound placeholder' * 16}

    def write(self,files):
        for name,raw in files.items():(self.root/name).write_bytes(raw)

    def single(self,frames=24):
        files=dict(self.media);meta={k:_memory_digest(v) for k,v in files.items()}
        files.update(_xml_package(title='Test',issued=ISSUED,ids=self.ids,profile='2K_FLAT_24',frames=frames,metadata=meta))
        self.write(files)
        return files

    def multiple(self):
        files={};parts=[];expected=[];start=0
        for i,frames in enumerate([24,25,48]):
            p={'reel_uuid':uid(),'frames':frames,'picture':{'asset_uuid':uid()},'sound':{'asset_uuid':uid()}};parts.append(p)
            expected.append({'reel_uuid':p['reel_uuid'],'frames':frames,'start_frame':start,'picture_uuid':p['picture']['asset_uuid'],'sound_uuid':p['sound']['asset_uuid']});start+=frames
            for typ in ('picture','sound'):files[f'{typ}_{i:04d}.mxf']=(typ+str(i)).encode()*40
        meta={k:_memory_digest(v) for k,v in files.items()};files.update(_make_xml(parts,{k:self.ids[k] for k in ('cpl','pkl','assetmap')},'Test',ISSUED,meta,'4K_SCOPE_24'));self.write(files)
        return expected

    def alter(self,name,fn):
        p=self.root/name;tree=ET.parse(p);fn(tree.getroot());tree.write(p,encoding='utf-8',xml_declaration=True)
        self.rehash()

    def rehash(self):
        p=self.root/'PKL.xml';tree=ET.parse(p)
        for row in tree.getroot().find(q(NS_PKL,'AssetList')):
            data=(self.root/row.findtext(q(NS_PKL,'OriginalFileName'))).read_bytes()
            row.find(q(NS_PKL,'Hash')).text=base64.b64encode(sha1(data).digest()).decode()
            row.find(q(NS_PKL,'Size')).text=str(len(data))
        tree.write(p,encoding='utf-8',xml_declaration=True)
        p=self.root/'ASSETMAP.xml';tree=ET.parse(p)
        for chunk in tree.getroot().iter(q(NS_AM,'Chunk')):
            chunk.find(q(NS_AM,'Length')).text=str((self.root/chunk.findtext(q(NS_AM,'Path'))).stat().st_size)
        tree.write(p,encoding='utf-8',xml_declaration=True)

    def audit(self,**kw):return inspect_cinema_package(self.root,**kw)
    def test_file_backed_writer(self):
        self.single();r=self.audit(expected_profile='2K_FLAT_24',require_minimum_track=True)
        self.assertEqual(r['total_frames'],24);self.assertTrue(r['nvp_unsigned_xml_profile_verified']);self.assertFalse(r['official_smpte_xsd_verified']);self.assertFalse(r['mxf_descriptor_crosscheck_verified']);self.assertFalse(r['production_dcp_accepted'])
        self.assertEqual(set(r['metadata_sha256']),{'PKL.xml','ASSETMAP.xml','VOLINDEX.xml','CPL.xml'})
    def test_reduced_flat_fixture_and_new_single_reel_checkpoint(self):
        from unittest.mock import patch
        from backend.nvp_wo3_j2k_audit import PROFILES
        from backend.nvp_dci_packets import inspect_cinema_packets
        from test_nvp_wo3_dci_codestream import structural_frame
        from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
        reel={"profile":"2K_FLAT_24","picture_uuid":self.ids["picture"],"frame_count":3}
        delivery={"reel_uuid":self.ids["reel"],"sound_uuid":self.ids["sound"]}
        with patch.dict(PROFILES,{"2K_FLAT_24":(2,1,24)}):
            self.single(frames=3)
            self.assertTrue(inspect_cinema_packets(structural_frame(lengths=[20]*3),"2K_FLAT_24")["packet_membership_verified"])
            self.assertEqual(inspect_dcp_structure(self.root)["status"],"STRUCTURE_AND_SHA_VERIFIED")
            with self.assertRaisesRegex(ValueError,"aspect ratio"):
                CinemaDeliveryJournal._audit_new_package(self.root,reel,delivery)
        with patch.dict(PROFILES,{"2K_FLAT_24":(37,20,24)}):
            self.single(frames=3)
            self.assertTrue(inspect_cinema_packets(structural_frame(lengths=[20]*3),"2K_FLAT_24")["packet_membership_verified"])
            verified=CinemaDeliveryJournal._audit_new_package(self.root,reel,delivery)
            self.assertEqual(verified["screen_aspect_ratio"],[37,20])
            self.assertFalse(verified["all_tracks_minimum_one_second_verified"])
            self.assertFalse(verified["production_dcp_accepted"])
        self.assertEqual(CinemaDeliveryJournal._audit_new_package(self.root,reel,delivery)["screen_aspect_ratio"],[37,20])
        self.alter('CPL.xml',lambda x:setattr(next(x.iter(q(NS_CPL,'ScreenAspectRatio'))),'text','2 1'))
        self.assertEqual(inspect_dcp_structure(self.root)["status"],"STRUCTURE_AND_SHA_VERIFIED")
        with self.assertRaises(ValueError):
            CinemaDeliveryJournal._audit_new_package(self.root,reel,delivery)

    def test_new_feature_checkpoint_rejects_rehashed_wrong_aspect_and_order(self):
        from backend.nvp_wo4_feature_journal import FeatureJournal
        expected=self.multiple()
        manifest={"profile":"4K_SCOPE_24","reels":[{
            "reel_uuid":row["reel_uuid"],"frames":row["frames"],
            "picture":{"asset_uuid":row["picture_uuid"]},
            "sound":{"asset_uuid":row["sound_uuid"]}} for row in expected]}
        report=FeatureJournal._audit_new_feature_package(self.root,manifest)
        self.assertEqual(report["reel_manifest"],expected)
        self.assertFalse(report["production_dcp_accepted"])
        with self.assertRaises(ValueError):
            FeatureJournal._audit_new_feature_package(self.root,{**manifest,"reels":manifest["reels"][::-1]})
        self.alter('CPL.xml',lambda x:setattr(next(x.iter(q(NS_CPL,'ScreenAspectRatio'))),'text','2 1'))
        self.assertEqual(inspect_dcp_structure(self.root)["status"],"STRUCTURE_AND_SHA_VERIFIED")
        with self.assertRaises(ValueError):
            FeatureJournal._audit_new_feature_package(self.root,manifest)

    def test_original_in_memory_writer(self):
        files,ids=_compose_xml({'asset_uuid':self.ids['picture'],'frame_count':24,'profile':'2K_FLAT_24','bytes':self.media['picture.mxf']},{'asset_uuid':self.ids['sound'],'frame_count':24,'bytes':self.media['sound.mxf']},title='Test',issued=ISSUED)
        self.write(files);self.assertEqual(self.audit()['total_frames'],24)
    def test_multireel_exact_authority(self):
        expected=self.multiple();r=self.audit(expected_profile='4K_SCOPE_24',expected_reels=expected,require_minimum_track=True)
        self.assertEqual(r['total_frames'],97);self.assertEqual(r['reel_manifest'],expected)
        with self.assertRaises(ValueError):self.audit(expected_reels=expected[::-1])
        self.alter('CPL.xml',lambda x:x.find(q(NS_CPL,'ReelList')).append(x.find(q(NS_CPL,'ReelList'))[0]))
        with self.assertRaises(ValueError):self.audit()
    def test_minimum_is_not_legacy_pilot(self):
        self.single(frames=3);self.assertFalse(self.audit()['all_tracks_minimum_one_second_verified'])
        with self.assertRaises(ValueError):self.audit(require_minimum_track=True)
    def test_required_fields_and_wrong_sequence_even_if_rehashed(self):
        for name in ('ContentVersion','RatingList','ContentTitleText'):
            with self.subTest(name=name):
                self.single();self.alter('CPL.xml',lambda x:x.remove(x.find(q(NS_CPL,name))))
                self.assertTrue(inspect_dcp_structure(self.root)['metadata_and_asset_hashes_verified'])
                with self.assertRaises(ValueError):self.audit()
        self.single();self.alter('ASSETMAP.xml',lambda x:x.append(x.find(q(NS_AM,'Creator'))))
        with self.assertRaises(ValueError):self.audit()
    def test_frame_rate_and_aspect_and_hash(self):
        for field,value in [('FrameRate','25 1'),('ScreenAspectRatio','0 1'),('Hash','AAAAAAAAAAAAAAAAAAAAAAAAAAA=')]:
            with self.subTest(field=field):
                self.single();self.alter('CPL.xml',lambda x:setattr(next(x.iter(q(NS_CPL,field))),'text',value))
                with self.assertRaises(ValueError):self.audit()
        self.single()
        with self.assertRaises(ValueError):self.audit(expected_profile='4K_SCOPE_24')
    def test_rehashed_payload_attack_cpl_binding(self):
        self.single();(self.root/'picture.mxf').write_bytes(b'x'*256);self.rehash()
        self.assertTrue(inspect_dcp_structure(self.root)['metadata_and_asset_hashes_verified'])
        with self.assertRaisesRegex(ValueError,'CPL track hash'):self.audit()
    def test_unknown_nodes_namespaces_attributes_and_dates(self):
        for fn in [lambda x:ET.SubElement(x,'{urn:foreign}Foo'),lambda x:x.set('extra','yes'),lambda x:setattr(x.find(q(NS_CPL,'IssueDate')),'text','2026-02-31T00:00:00Z')]:
            self.single();self.alter('CPL.xml',fn)
            with self.assertRaises(ValueError):self.audit()
    def test_volume_and_extra_entry(self):
        self.single();(self.root/'VOLINDEX.xml').write_bytes(b'<bad/>')
        with self.assertRaises(ValueError):self.audit()
        self.single();(self.root/'foreign.mxf').write_bytes(b'extra')
        with self.assertRaises(ValueError):self.audit()
    def test_hardlink_denied(self):
        self.single();alias=self.root.parent/(uid()+'.mxf')
        try:
            os.link(self.root/'picture.mxf',alias)
        except OSError:self.skipTest('host refuses hardlink')
        self.addCleanup(alias.unlink)
        with self.assertRaises(ValueError):self.audit()
    def test_dtd_and_processing_instruction_denial(self):
        self.single();p=self.root/'CPL.xml';p.write_bytes(p.read_bytes().replace(b'?>',b'?><?bad data?>',1));self.rehash()
        with self.assertRaises(ValueError):self.audit()
        self.single();p.write_bytes(b'<!DOCTYPE cpl>'+p.read_bytes());self.rehash()
        with self.assertRaises(ValueError):self.audit()

    def test_native_descriptor_shape_and_negative_cases(self):
        from backend.nvp_dci_package import verify_native_track_descriptor
        props={'label_set_type':'SMPTE','assetuuid':self.ids['picture'],'editrate':'24/1','containerduration':'24','storedwidth':'1998','storedheight':'1080'}
        args={'kind':'picture','asset_id':self.ids['picture'],'frames':24,'profile':'2K_FLAT_24'}
        self.assertTrue(verify_native_track_descriptor(props,**args))
        for field,val in [('storedwidth','2048'),('containerduration','25'),('assetuuid',uid())]:
            with self.assertRaises((RuntimeError,ValueError)):verify_native_track_descriptor({**props,field:val},**args)
        props={'label_set_type':'SMPTE','assetuuid':self.ids['sound'],'editrate':'24/1','containerduration':'24','audiosamplingrate':'48000/1','quantizationbits':'24','channelcount':'6'}
        self.assertTrue(verify_native_track_descriptor(props,kind='sound',asset_id=self.ids['sound'],frames=24,profile='2K_FLAT_24',channels=6))
        with self.assertRaises(ValueError):verify_native_track_descriptor(props,kind='sound',asset_id=self.ids['sound'],frames=24,profile='2K_FLAT_24',channels=8)

    def test_reviewed_git_blob_extraction_ignores_worktree_conversion(self):
        # Real Git object read; test-only pins for synthetic schemas. A CRLF
        # checkout fails the original byte pin, but extraction is byte-exact.
        import subprocess
        from unittest.mock import patch
        from tools import nvp_dci_schema_ci as tool
        from backend import nvp_dci_package_xsd as mod
        with TemporaryDirectory() as temp:
            root=Path(temp);repo=root/'repo';repo.mkdir();(repo/'xsd').mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.STDOUT)
            git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            git('config','core.autocrlf','false')
            (repo/'.gitattributes').write_bytes(b'*.xsd text eol=lf\n')
            pins={}
            for i,ns in enumerate(mod.MIRROR_SCHEMAS):
                name=f'test-{i}.xsd';raw=f'<schema ns="{ns}"/>\n'.encode()
                (repo/'xsd'/name).write_bytes(raw);pins[ns]=(name,mod._blob(raw))
            git('add','.');git('commit','-qm','synthetic reviewed fixture')
            commit=git('rev-parse','HEAD').strip().decode('ascii')
            for name,digest in pins.values():
                path=repo/'xsd'/name;path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
                self.assertNotEqual(mod._blob(path.read_bytes()),digest)
            out=root/'exact'
            with patch.object(tool,'REVIEWED_MIRROR_COMMIT',commit),patch.object(tool,'MIRROR_SCHEMAS',pins):
                self.assertEqual(tool.materialize_reviewed_mirror(repo,out),out)
                for name,digest in pins.values():self.assertEqual(mod._blob((out/name).read_bytes()),digest)
                with self.assertRaises(FileExistsError):tool.materialize_reviewed_mirror(repo,out)
                bad=dict(pins);ns=next(iter(bad));bad[ns]=(bad[ns][0],'0'*40)
                with patch.object(tool,'MIRROR_SCHEMAS',bad),self.assertRaises(PermissionError):
                    tool.materialize_reviewed_mirror(repo,root/'bad')
                self.assertFalse((root/'bad').exists())
            with self.assertRaises(PermissionError):tool.materialize_reviewed_mirror(repo,root/'wrong')
            self.assertFalse((root/'wrong').exists())

    def test_xsd_loader_rejects_unreviewed_schema_before_validation(self):
        from backend.nvp_dci_package_xsd import validate_official_package_xsd,SCHEMAS
        self.single()
        d=TemporaryDirectory();self.addCleanup(d.cleanup);schema_root=Path(d.name)
        for name,_ in SCHEMAS.values():(schema_root/name).write_text('<bad/>')
        with self.assertRaisesRegex(PermissionError,'schema blob mismatch'):validate_official_package_xsd(self.root,schema_root)

    def test_xsd_engine_import_resolution_and_schema_denial_synthetic_only(self):
        # Actual libxml2 XMLSchema engine with deliberately tiny TEST schemas.
        # Test-only pins are patched in process, not a production receipt.
        from unittest.mock import patch
        from lxml import etree
        from backend import nvp_dci_package_xsd as mod
        from hashlib import sha1
        self.single()
        d=TemporaryDirectory();self.addCleanup(d.cleanup);schema_root=Path(d.name)
        def schema(ns,body):
            return (f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="{ns}" elementFormDefault="qualified">'+body+'</xs:schema>').encode()
        leaves={NS_AM:schema(NS_AM,'<xs:element name="AssetMap" type="xs:anyType"/><xs:element name="VolumeIndex" type="xs:anyType"/>'),NS_PKL:schema(NS_PKL,'<xs:element name="PackingList" type="xs:anyType"/>'),NS_CPL:schema(NS_CPL,f'<xs:import namespace="{mod.DS}" schemaLocation="https://must-not-connect.invalid/anything"/><xs:element name="CompositionPlaylist" type="xs:anyType"/>'),mod.DS:schema(mod.DS,'<xs:element name="Test" type="xs:string"/>'),mod.XML:schema(mod.XML,'<xs:attribute name="lang" type="xs:language"/>')}
        def write_pins():
            pins={}
            for i,(ns,data) in enumerate(leaves.items()):
                name=f'test-{i}.xsd';(schema_root/name).write_bytes(data);pins[ns]=(name,mod._blob(data))
            return pins
        with patch.object(mod,'MIRROR_SCHEMAS',write_pins()):
            result=mod.validate_official_package_xsd(self.root,schema_root,source_set='LIBDCP_REVIEWED_MIRROR')
            self.assertFalse(result['official_smpte_xsd_verified'])
            self.assertFalse(result['production_dcp_accepted'])
        # Restriction rejects a valid local grammar package and independently proves XSD failure.
        leaves[NS_CPL]=schema(NS_CPL,'<xs:element name="CompositionPlaylist" type="xs:string"/>')
        with patch.object(mod,'MIRROR_SCHEMAS',write_pins()):
            with self.assertRaises(etree.DocumentInvalid):mod.validate_official_package_xsd(self.root,schema_root,source_set='LIBDCP_REVIEWED_MIRROR')
        leaves[NS_CPL]=schema(NS_CPL,'<xs:include schemaLocation="file:///etc/passwd"/>')
        with patch.object(mod,'MIRROR_SCHEMAS',write_pins()):
            with self.assertRaises(PermissionError):mod.validate_official_package_xsd(self.root,schema_root,source_set='LIBDCP_REVIEWED_MIRROR')

if __name__=='__main__':unittest.main()
