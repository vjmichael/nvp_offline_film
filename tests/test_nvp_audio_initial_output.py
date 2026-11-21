"""Actual filesystem and abrupt publisher exits for SEC-06-R6 initial output."""
import hashlib, os, pathlib, struct, subprocess, sys, tempfile, unittest, wave
from backend.nvp_audio_initial_output import initial_bytes, publish_initial


@unittest.skipUnless(sys.platform=='linux','Linux initial-output publication')
class InitialOutput(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name); self.target=self.root/'mix';self.evidence=self.root/'evidence';self.evidence.mkdir(mode=0o700)
        src=self.root/'voice.wav'
        with wave.open(str(src),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(struct.pack('<hh',10,-10)*48000)
        self.spec={'plan':{'stems':[{'stem_id':'voice','kind':'dialogue','clips':[{'out_start':0,'out_end':48000,'source_start':0,'fade_in':0,'fade_out':0,'gain_milli':1000}]}]},'sources':{'voice':str(src)},'source_sha256':{'voice':hashlib.sha256(src.read_bytes()).hexdigest()},'total_samples':48000,'directory':str(self.target)}
        self.raw=initial_bytes(self.spec);self.sha=hashlib.sha256(self.raw).hexdigest()
    def publish(self,recovering=False):publish_initial(self.spec,self.sha,self.evidence,recovering=recovering)
    def check(self):
        self.assertEqual((self.target/'checkpoint.json').read_bytes(),self.raw)
        self.assertEqual([p.name for p in self.target.iterdir()],['checkpoint.json'])
        self.assertEqual((self.target/'checkpoint.json').stat().st_nlink,1)
    def test_fresh_and_replay(self):
        self.publish();self.check();self.publish(True);self.check()
        with self.assertRaises(PermissionError):self.publish()
    def test_empty_and_partial_stage(self):
        self.target.mkdir(mode=0o700);p=self.target/'checkpoint.json.new';part=self.raw[:43];p.write_bytes(part)
        self.publish(True);self.check()
        self.assertEqual((self.evidence/('initial-stage-'+hashlib.sha256(part).hexdigest()+'.bin')).read_bytes(),part)
    def test_actual_child_dies_after_link(self):
        import json
        code='''import os,sys,json\nfrom backend.nvp_audio_initial_output import publish_initial\nlink=os.link\ndef crash(*a,**k):\n link(*a,**k);os._exit(79)\nos.link=crash\npublish_initial(json.loads(sys.argv[1]),sys.argv[2],sys.argv[3])'''
        r=subprocess.run([sys.executable,'-c',code,json.dumps(self.spec),self.sha,str(self.evidence)],timeout=15)
        self.assertEqual(r.returncode,79);self.assertEqual((self.target/'checkpoint.json').stat().st_nlink,2)
        self.publish(True);self.check()
    def test_wrong_stage_and_foreign_links_refused(self):
        self.target.mkdir(mode=0o700);p=self.target/'checkpoint.json.new';p.write_bytes(b'foreign')
        with self.assertRaises(PermissionError):self.publish(True)
        self.assertEqual(p.read_bytes(),b'foreign');p.write_bytes(self.raw);os.link(p,self.root/'foreign')
        with self.assertRaises(PermissionError):self.publish(True)
        self.assertFalse((self.target/'checkpoint.json').exists())
    def test_no_canonical_overwrite(self):
        self.target.mkdir(mode=0o700);p=self.target/'checkpoint.json';p.write_bytes(self.raw[:43])
        with self.assertRaises(PermissionError):self.publish(True)
        self.assertEqual(p.read_bytes(),self.raw[:43])
    def test_changed_hash_and_source_refused(self):
        with self.assertRaises(PermissionError):publish_initial(self.spec,'0'*64,self.evidence)
        with open(self.spec['sources']['voice'],'ab') as f:f.write(b'x')
        with self.assertRaises(PermissionError):self.publish()
        self.assertFalse(self.target.exists())
