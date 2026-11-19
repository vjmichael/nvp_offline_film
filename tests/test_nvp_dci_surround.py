import io
from hashlib import sha256
import unittest
import wave
import numpy as np
from backend.nvp_dci_surround import SOURCE_CHANNELS, route_block, write_mapped_reel, verify_surround_reels, inspect_mxf_sound_metadata, MCA_EXPRESSION


def source_fixture(channels, frames):
    # Each channel and time point has a distinct signed ramp; no periodic
    # repeat at reel boundaries. Include full legal signed PCM24 extremes.
    t=np.arange(frames,dtype=np.int64)[:,None]
    c=np.arange(channels,dtype=np.int64)[None,:]
    vals=((t*73+c*105123+19)%16777216-8388608).astype(np.int32)
    vals[0,0]=-8388608; vals[-1,-1]=8388607
    return np.stack([((vals>>shift)&255).astype(np.uint8) for shift in (0,8,16)],axis=-1).tobytes()


def digest(data):return sha256(data).hexdigest()


def payload(wav):
    with wave.open(io.BytesIO(wav),'rb') as w:return w.readframes(w.getnframes())


def wav_with_pcm(raw):
    f=io.BytesIO()
    with wave.open(f,'wb') as w:
        w.setnchannels(16);w.setsampwidth(3);w.setframerate(48000);w.writeframes(raw)
    return f.getvalue()


class SurroundTests(unittest.TestCase):
    def setup_case(self, profile):
        labels=SOURCE_CHANNELS[profile]
        src=source_fixture(len(labels),96000)
        ledger=[]; wavs={}
        for i in range(2):
            chunk=src[i*48000*len(labels)*3:(i+1)*48000*len(labels)*3]
            f=io.BytesIO()
            receipt=write_mapped_reel(io.BytesIO(chunk),f,profile=profile,labels=labels,edit_units=24,source_sha256=digest(chunk))
            name=f'reel-{i}';wavs[name]=f.getvalue()
            ledger.append(dict(id=name,first_edit_unit=i*24,edit_units=24,mapped_pcm_sha256=receipt['mapped_pcm_sha256']))
        return src,labels,ledger,wavs
    def audit(self,profile,src,labels,ledger,wavs,**kwargs):
        options=dict(profile=profile,labels=labels,source_sha256=digest(src),total_edit_units=48,reels=ledger,open_reel=lambda name:io.BytesIO(wavs[name]))
        options.update(kwargs)
        return verify_surround_reels(io.BytesIO(src),**options)
    def test_full_two_reel_51_and_71(self):
        for profile,silent in [('5.1',list(range(7,17))),('7.1DS',[7,8,9,10,13,14,15,16])]:
            with self.subTest(profile=profile):
                src,labels,l,w=self.setup_case(profile)
                receipt=self.audit(profile,src,labels,l,w)
                self.assertEqual(receipt['silent_slots'],silent)
                self.assertEqual(receipt['samples_per_channel'],96000)
                self.assertEqual(receipt['reels'][0]['end_sample_exclusive'],receipt['reels'][1]['first_sample'])
                self.assertEqual(receipt['ordered_mapped_pcm_sha256'],digest(payload(w['reel-0'])+payload(w['reel-1'])))
                self.assertFalse(receipt['mxf_channel_metadata_verified'])
    def test_reserved_slot_injection_even_with_new_digest(self):
        src,labels,l,w=self.setup_case('7.1DS');p=bytearray(payload(w['reel-1']));p[8*3]=1
        w['reel-1']=wav_with_pcm(p);l[1]['mapped_pcm_sha256']=digest(p)
        with self.assertRaises(ValueError): self.audit('7.1DS',src,labels,l,w)
    def test_swap_rears_even_with_new_digest(self):
        src,labels,l,w=self.setup_case('7.1DS');p=np.frombuffer(payload(w['reel-1']),dtype=np.uint8).copy().reshape(-1,16,3);p[:,[10,11]]=p[:,[11,10]]
        w['reel-1']=wav_with_pcm(p.tobytes());l[1]['mapped_pcm_sha256']=digest(p.tobytes())
        with self.assertRaises(ValueError):self.audit('7.1DS',src,labels,l,w)
    def test_repeated_boundary_sample(self):
        src,labels,l,w=self.setup_case('5.1');p=bytearray(payload(w['reel-1']));p[:48]=payload(w['reel-0'])[-48:];w['reel-1']=wav_with_pcm(p);l[1]['mapped_pcm_sha256']=digest(p)
        with self.assertRaises(ValueError):self.audit('5.1',src,labels,l,w)
    def test_bad_scope(self):
        src,labels,l,w=self.setup_case('5.1')
        for edits in ([l[1],l[0]],[l[0],l[0]],[l[0],dict(l[1],first_edit_unit=25)],[l[0],dict(l[1],first_edit_unit=23)],l[:1]):
            with self.subTest(edits=edits):
                with self.assertRaises(ValueError):self.audit('5.1',src,labels,edits,w)
        with self.assertRaises(PermissionError):self.audit('5.1',src,labels,l,w,source_sha256='0'*64)
        l[1]['mapped_pcm_sha256']='0'*64
        with self.assertRaises(PermissionError):self.audit('5.1',src,labels,l,w)
    def test_bad_source_and_input_labels(self):
        with self.assertRaises(ValueError):route_block(b'\0'*24,'7.1DS',['L','R','C','LFE','Ls','Rs','Lrs','Rrs'])
        with self.assertRaises(ValueError):route_block(b'\0'*17,'5.1',SOURCE_CHANNELS['5.1'])
        with self.assertRaises(ValueError):route_block(b'\0'*(4097*18),'5.1',SOURCE_CHANNELS['5.1'])
        with self.assertRaises(ValueError):write_mapped_reel(io.BytesIO(b''),io.BytesIO(),profile='5.1',labels=SOURCE_CHANNELS['5.1'],edit_units=24,source_sha256='a'*64)
    def test_metadata_and_exact_native_grammar(self):
        from backend.nvp_wo3_native_codecs import _approved_arguments
        for profile in SOURCE_CHANNELS:
            group='51' if profile=='5.1' else '71'
            group_id='a'*32
            slots=[(1,'L',1),(2,'R',2),(3,'C',3),(4,'LFE',4)]+([(5,'Ls',5),(6,'Rs',6)] if group=='51' else [(5,'Lss',7),(6,'Rss',8),(11,'Lrs',9),(12,'Rrs',10)])
            lines=['[060e2b34]  len:  100 (WaveAudioDescriptor)','  ChannelAssignment = 060e2b340401010b0402021003010400','  ChannelCount = 16','  QuantizationBits = 24','  AudioSamplingRate = 48000/1','[060e2b34]  len:  100 (SoundfieldGroupLabelSubDescriptor)',f'  MCATagSymbol = sg{group}',f'  MCALinkID = {group_id}',f'  MCALabelDictionaryID = 060e2b340401010d0302020{1 if group=="51" else 2}00000000']
            for slot,label,n in slots:
                lines += ['[060e2b34]  len:  100 (AudioChannelLabelSubDescriptor)',f'  MCAChannelID = {slot}',f'  MCATagSymbol = ch{label}',f'  MCALinkID = {slot:032x}',f'  MCALabelDictionaryID = 060e2b340401010d030201{n:02x}00000000',f'  SoundfieldGroupLinkID = {group_id}']
            payload='\n'.join(lines).encode()
            self.assertTrue(inspect_mxf_sound_metadata(payload,profile)['configuration_4_verified'])
            for altered in [payload.replace(b'ChannelCount = 16',b'ChannelCount = 8'),payload.replace(b'03010400',b'03010500'),payload.replace(b'MCAChannelID = 1\n',b'MCAChannelID = 7\n'),payload.replace(b'SoundfieldGroupLinkID = '+b'a'*32,b'SoundfieldGroupLinkID = '+b'b'*32),payload.replace(b'MCATagSymbol = chL\n',b'MCATagSymbol = chR\n')]:
                with self.assertRaises(ValueError): inspect_mxf_sound_metadata(altered,profile)
            argv=['-L','-a','a'*32,'-p','24','-d','24','-w','-m',MCA_EXPRESSION[profile],'source.wav','sound.mxf']
            self.assertEqual(_approved_arguments('ASDCP-asdcp_wrap',argv),argv)
            self.assertEqual(_approved_arguments('ASDCP-asdcp_info',['-i','-d','-H','sound.mxf']),['-i','-d','-H','sound.mxf'])
            for i,v in ((9,'71(L,R)'),(10,'../source.wav'),(6,'3'),(7,'-k')):
                bad=argv[:];bad[i]=v
                with self.assertRaises(PermissionError):_approved_arguments('ASDCP-asdcp_wrap',bad)

    def test_each_channel_impulse_independently(self):
        for profile,slots in [('5.1',[0,1,2,3,4,5]),('7.1DS',[0,1,2,3,4,5,10,11])]:
            for index,slot in enumerate(slots):
                b=bytearray(len(slots)*3);b[index*3:index*3+3]=b'\xff\xff\x7f'
                out=route_block(bytes(b),profile,SOURCE_CHANNELS[profile]);goal=bytearray(48);goal[slot*3:slot*3+3]=b'\xff\xff\x7f'
                self.assertEqual(out,bytes(goal))

if __name__=='__main__':unittest.main()
