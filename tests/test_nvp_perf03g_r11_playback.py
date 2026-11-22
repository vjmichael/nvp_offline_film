"""Actual encrypted paired media; metadata scale, not device playback."""
import base64, hashlib, io, json, time, unittest, wave
from unittest.mock import patch
from backend import nvp_g07_feature_playback as p, nvp_g07_feature_reels as r
from backend.nvp_g03_windows_vault import VaultError
from test_nvp_perf03g_r6_feature_reels import R6Base
from test_nvp_perf03g_r4_protected_output import Fixture

class PairedPlayback(R6Base,unittest.TestCase):
    def test_exact_pair_and_work_reduction(self):
        self.enterContext(patch.object(p.projection,'MAX_PROJECTED_BYTES',0))
        self.seed();done=self.run_all();f=self.f;args=(f.service,f.pid,2,f.digest,done['job_id'])
        self.assertTrue(p.timeline(*args)['paired_windows'])
        measurements={};expected=[]
        with patch.object(r,'_read_body',wraps=r._read_body) as reads,patch.object(f.service,'_run',wraps=f.service._run) as snapshots:
            at=time.perf_counter()
            for first in range(0,180,12):
                picture=p.pictures(*args,first,12);sound,_=p.sound(*args,first*2000,24000)
                expected.append((picture,sound))
            measurements['separate']={'seconds':time.perf_counter()-at,'snapshots':snapshots.call_count,'reel_reads':reads.call_count}
            reads.reset_mock();snapshots.reset_mock();at=time.perf_counter();digest=hashlib.sha256()
            for index,first in enumerate(range(0,180,12)):
                result=p.paired(*args,first*2000,24000);picture,sound=expected[index]
                self.assertEqual(result['frames'],picture['frames']);self.assertEqual(result['source_sha256'],picture['source_sha256']);self.assertEqual(base64.b64decode(result['audio_base64']),sound)
                with wave.open(io.BytesIO(sound),'rb') as w:digest.update(w.readframes(w.getnframes()))
            measurements['paired']={'seconds':time.perf_counter()-at,'snapshots':snapshots.call_count,'reel_reads':reads.call_count}
        self.assertEqual(digest.hexdigest(),done['pcm_sha256']);self.assertEqual(measurements['separate']['snapshots'],30);self.assertEqual(measurements['paired']['snapshots'],15);self.assertEqual(measurements['separate']['reel_reads'],32);self.assertEqual(measurements['paired']['reel_reads'],16)
        print('R11_PAIRED_BENCHMARK '+json.dumps(measurements,sort_keys=True),flush=True)
        paired=p.paired(*args,179999,3);self.assertEqual([x['frame'] for x in paired['frames']],[89,90]);self.assertEqual(base64.b64decode(paired['audio_base64']),p.sound(*args,179999,3)[0])
        self.assertEqual(p.paired(*args,359999,1)['sample_count'],1)
        with self.assertRaises(ValueError):p.paired(*args,1,24000)
        with self.assertRaises(PermissionError):p.paired(f.service,f.pid,2,'f'*64,done['job_id'],0,1)
        import test_nvp_perf03g_r8_working_movie as ui
        app=ui.FastAPI();window=ui.Window(f.pid);app.state.nvp_editorial_recovery_dialog=ui.NativeRecoveryDialog(window,ui.ORIGIN)
        class Access:
            def permitted(_,pid,token):return pid==f.pid and token==f.token
        ui.mount_section_routes(app,lambda:f.studio,lambda:f.store,lambda:Access(),'test_session')
        path=f'/api/projects/{f.pid}/live/edit/sections/playback/2/{f.digest}/{done["job_id"]}/paired?start_sample=179999&count=3'
        with ui.TestClient(app,base_url=ui.ORIGIN,headers={'sec-fetch-site':'same-origin','x-nvp-director':'1'},cookies={'test_session':f.token}) as client:
            response=client.get(path);self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json(),paired);self.assertIn('no-store',response.headers['cache-control']);self.assertEqual(client.get(path,headers={'sec-fetch-site':'cross-site'}).status_code,403)
            window.url=ui.ORIGIN+'/postproduction.html?project='+'f'*32+'&encrypted=1';self.assertEqual(client.get(path).status_code,403)
        target=r._location(f.folder,f.key,done['job_id'],1)/'body.nvpsealed';raw=target.read_bytes();target.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaises(VaultError):p.paired(*args,179999,3)

class InventoryScale(unittest.TestCase):
    def test_bounded_inventory(self):
        self.enterContext(patch.object(p.projection,'INVENTORY_PAGES',0))
        f=Fixture(self);f.migrate()
        from backend import nvp_g03_payloads as payloads
        original_take=f.editor._execute(f.pid,lambda db,movie:tuple(db.execute('SELECT * FROM g06_frozen_takes ORDER BY take_id LIMIT 1').fetchone()))
        before=p.inventory(f.service,f.pid,'takes',limit=64)
        reviewed=payloads.review(f.store,f.pid,f.token,'take')
        payloads.migrate(f.store,f.pid,f.token,'take',None,reviewed['approval_digest'],human_approved=True)
        self.assertEqual(p.inventory(f.service,f.pid,'takes',limit=64),before)
        def seed(db,movie):
            # Repeated synthetic metadata, no claim of genuine independent original Takes.
            for n in range(4096):
                ident=f'{100000+n:032x}'
                db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,f.pid,'SC_abcdef012345',None,'native_microphone_pcm16le',b'\0\0',hashlib.sha256(b'\0\0').hexdigest(),48000,1,1,'2026-11-19'))
                db.execute('INSERT INTO g06_frozen_takes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,*original_take[1:]))
        f.editor._execute(f.pid,seed,mutate=True)
        original=f.service._run;traces=[]
        def traced(pid,action,**kw):
            def wrapped(db,movie):
                db.set_trace_callback(traces.append)
                try:return action(db,movie)
                finally:db.set_trace_callback(None)
            return original(pid,wrapped,**kw)
        report={}
        with patch.object(f.service,'_run',side_effect=traced):
            for family in ('takes','recordings'):
                traces.clear();at=time.perf_counter();page=p.inventory(f.service,f.pid,family,limit=64);elapsed=time.perf_counter()-at
                queries=[q for q in traces if q.lstrip().upper().startswith('SELECT')];self.assertEqual(len(page['items']),64);self.assertEqual(len({x['id'] for x in page['items']}),64);self.assertIsNotNone(page['next_after']);self.assertLessEqual(len(queries),4)
                report[family]={'first_page_seconds':elapsed,'metadata_selects':len(queries),'rows':64}
                tail=p.inventory(f.service,f.pid,family,after=f'{103900:032x}',limit=64)
                self.assertEqual(len(tail['items']),64);self.assertTrue(any(x['id']==f'{103901:032x}' for x in tail['items']));self.assertTrue(all(x['source_bytes']>0 for x in page['items']));self.assertFalse(page['media_authenticated'])
        print('R11_INVENTORY_BENCHMARK '+json.dumps(report,sort_keys=True),flush=True)
        f.editor._execute(f.pid,lambda db,movie:db.execute('UPDATE g03_pcm_pages SET size_bytes=1 WHERE project_id=?',(f.pid,)),mutate=True)
        with self.assertRaises(VaultError):p.inventory(f.service,f.pid,'recordings',limit=64)
        f.editor._execute(f.pid,lambda db,movie:db.execute('UPDATE g03_r5_take_payloads SET size_bytes=0 WHERE project_id=?',(f.pid,)),mutate=True)
        with self.assertRaises(VaultError):p.inventory(f.service,f.pid,'takes',limit=64)
