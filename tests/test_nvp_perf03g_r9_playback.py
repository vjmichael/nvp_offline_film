import base64, hashlib, io, unittest, wave
from PIL import Image
from test_nvp_perf03g_r6_feature_reels import R6Base
from backend import nvp_g07_feature_playback as p
from backend import nvp_g07_feature_reels as r
from backend.nvp_g03_windows_vault import VaultError

class R9Playback(R6Base,unittest.TestCase):
    def test_continuous_picture_pcm_and_inventory(self):
        self.seed();done=self.run_all();f=self.f;args=(f.service,f.pid,2,f.digest,done['job_id'])
        meta=p.timeline(*args);self.assertEqual(meta['picture_frames'],180);self.assertFalse(meta['physical_gapless_device_acceptance_passed'])
        sha=hashlib.sha256();count=0
        for start in range(0,180,12):
            pictures=p.pictures(*args,start,12);self.assertEqual(pictures['source_sha256'],meta['source_sha256'])
            for i,item in enumerate(pictures['frames']):
                self.assertEqual(item['frame'],start+i)
                with Image.open(io.BytesIO(base64.b64decode(item['picture_base64']))) as im:im.load();self.assertEqual(im.size,(640,360))
                count+=1
            wav,headers=p.sound(*args,start*2000,24000);self.assertEqual(headers['X-NVP-Source-SHA256'],meta['source_sha256'])
            with wave.open(io.BytesIO(wav),'rb') as w:sha.update(w.readframes(w.getnframes()))
        self.assertEqual(count,180);self.assertEqual(sha.hexdigest(),done['pcm_sha256'])
        # An unaligned sample window crosses reel 0/1 exactly.
        wav,_=p.sound(*args,179999,3)
        data0=r.open_verified_reel(f.service,f.pid,done['job_id'],0);data1=r.open_verified_reel(f.service,f.pid,done['job_id'],1)
        expected=list(r._pcm(data0,90))[-1][-4:]+next(r._pcm(data1,90))[:8]
        with wave.open(io.BytesIO(wav),'rb') as w:self.assertEqual(w.readframes(3),expected)
        for family in ('takes','recordings'):
            after=None;seen=set()
            while True:
                page=p.inventory(f.service,f.pid,family,after,1);self.assertFalse(page['media_authenticated']);self.assertLessEqual(len(page['items']),1)
                for item in page['items']:self.assertNotIn(item['id'],seen);seen.add(item['id']);self.assertGreater(item['source_bytes'],0)
                after=page['next_after']
                if after is None:break
            self.assertGreater(len(seen),0)
        with self.assertRaises(PermissionError):p.pictures(f.service,f.pid,2,'f'*64,done['job_id'],0,1)
        with self.assertRaises(ValueError):p.pictures(*args,0,13)
        import test_nvp_perf03g_r8_working_movie as ui
        app=ui.FastAPI();window=ui.Window(f.pid);app.state.nvp_editorial_recovery_dialog=ui.NativeRecoveryDialog(window,ui.ORIGIN)
        class Access:
            def permitted(_,pid,token):return pid==f.pid and token==f.token
        ui.mount_section_routes(app,lambda:f.studio,lambda:f.store,lambda:Access(),'test_session')
        base=f'/api/projects/{f.pid}/live/edit/sections';path=f'{base}/playback/2/{f.digest}/{done["job_id"]}'
        with ui.TestClient(app,base_url=ui.ORIGIN,headers={'sec-fetch-site':'same-origin','x-nvp-director':'1'},cookies={'test_session':f.token}) as client:
            result=client.get(path+'/timeline');self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json(),meta)
            result=client.get(path+'/frames?start_frame=89&count=2');self.assertEqual(result.status_code,200,result.text);self.assertEqual([x['frame'] for x in result.json()['frames']],[89,90]);self.assertIn('no-store',result.headers['cache-control'])
            result=client.get(path+'/sound?start_sample=179999&count=3');self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.headers['x-nvp-audio-samples'],'3');self.assertEqual(result.content,wav)
            result=client.get(base+'/media-inventory?family=takes&limit=1');self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(client.get(path+'/frames?start_frame=0&count=13').status_code,422)
            self.assertEqual(client.get(path+'/timeline',headers={'sec-fetch-site':'cross-site'}).status_code,403)
            self.assertEqual(client.get(path+'/timeline',headers={'origin':'http://evil.test'}).status_code,403)
            window.url=ui.ORIGIN+'/postproduction.html?project='+'f'*32+'&encrypted=1'
            self.assertEqual(client.get(path+'/timeline').status_code,403)
        target=r._location(f.folder,f.key,done['job_id'],1)/'body.nvpsealed';raw=target.read_bytes();target.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaises(VaultError):p.sound(*args,179999,3)
