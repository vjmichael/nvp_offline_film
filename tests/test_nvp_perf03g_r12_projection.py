"""Actual protected metadata projection and repeated movie retrieval.

Public generated media/key; no device playback or native custody assertion.
"""
import base64
import gc
import hashlib
import io
import json
import os
import threading
import time
import unittest
import wave
from unittest.mock import patch

from backend import nvp_g07_feature_playback as playback
from backend import nvp_g07_playback_projection as projection
from backend import nvp_g07_feature_reels as reels
from backend import nvp_g03_payloads as payloads
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_feature_finish import review, analyze_approved
from backend.nvp_g09d_finishing import DEFAULT_COLOR
from test_nvp_perf03g_r4_protected_output import Fixture
from test_nvp_perf03g_r6_feature_reels import R6Base
from test_nvp_perf03g_r8_working_movie import finish


def rss_bytes():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[
                (field,ctypes.c_size_t) for field in ('PeakWorkingSetSize','WorkingSetSize',
                'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
        c=Counters();c.cb=ctypes.sizeof(c)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi=ctypes.WinDLL('psapi',use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):
            raise OSError(ctypes.get_last_error(),'Process memory unavailable')
        return c.WorkingSetSize
    with open('/proc/self/statm',encoding='ascii') as inp:
        return int(inp.read().split()[1])*os.sysconf('SC_PAGE_SIZE')


class MemorySample:
    """Sample resident memory (not allocator proof or isolated process peak)."""
    def __enter__(self):
        gc.collect();self.baseline=self.peak=rss_bytes();self.stop=threading.Event()
        def monitor():
            while not self.stop.wait(.01):self.peak=max(self.peak,rss_bytes())
        self.thread=threading.Thread(target=monitor,daemon=True);self.thread.start();return self
    def __exit__(self,*exc):
        self.stop.set();self.thread.join();gc.collect();self.tail=rss_bytes();self.peak=max(self.peak,self.tail)
    def report(self):
        return {k:getattr(self,k) for k in ('baseline','peak','tail')}


def service_for(f,token=None):
    token=f.token if token is None else token
    return EditorialSections(G07Editor(f.studio,live=f.store,token=token),access_guard=lambda:f.store._session(f.pid,token))


class ProjectionChecks(R6Base,unittest.TestCase):
    def test_exact_selection_invalidation_and_tamper(self):
        self.seed();done=self.run_all();f=self.f;job=done['job_id']
        request=(f.pid,2,f.digest,job)
        # Exercise both external metadata stores, not just inline SQLite rows.
        reviewed=payloads.review(f.store,f.pid,f.token,'edl')
        payloads.migrate(f.store,f.pid,f.token,'edl',None,reviewed['approval_digest'],human_approved=True)
        playback.timeline(f.service,*request)
        cache=f.store._playback_projection
        self.assertIsNotNone(cache);self.assertLessEqual(cache.bytes_used,projection.MAX_PROJECTED_BYTES)
        self.assertEqual(len(cache.parts),done['reel_count'])
        self.assertEqual({name.split('/')[0] for name,_ in cache.dependencies},{'editorial-pages','protected-objects'})
        with patch.object(f.store,'_read_db',side_effect=AssertionError('Warm playback reopened SQLite')),patch.object(reels,'_current',side_effect=AssertionError('Warm playback revisited all cuts')):
            expected=playback.paired(service_for(f),*request,179999,3)
            self.assertEqual([x['frame'] for x in expected['frames']],[89,90]);self.assertEqual(expected['source_sha256'],done['completion_sha256'])
        def corrupt(path):
            content=path.read_bytes();info=path.stat()
            path.write_bytes(content[:-1]+bytes([content[-1]^1]));os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
            try:
                with self.assertRaises(VaultError):playback.paired(service_for(f),*request,179999,3)
                self.assertIsNone(f.store._playback_projection)
            finally:path.write_bytes(content)
            playback.timeline(f.service,*request)
            self.assertEqual(playback.paired(service_for(f),*request,179999,3),expected)
        # Unchanged HEAD, same size and restored timestamps do not bypass the pin.
        corrupt(f.folder/'revisions'/cache.head['name'])
        for namespace in ('editorial-pages','protected-objects'):
            rel=next(name for name,_ in cache.dependencies if name.startswith(namespace+'/'))
            corrupt(f.folder/rel)
        # Malformed protected-objects directories must not bypass the strict reader.
        rel=next(name for name,_ in cache.dependencies if name.startswith('protected-objects/'))
        extra=(f.folder/rel).parent/'unexpected';extra.write_bytes(b'foreign')
        try:
            with self.assertRaises(VaultError):playback.paired(f.service,*request,0,1)
        finally:extra.unlink()
        # A new session must never consume an earlier session's projection.
        playback.timeline(f.service,*request);other='other-director-'+'a'*32
        f.store._keys[other]=(f.pid,f.key)
        with patch.object(f.store,'_read_db',wraps=f.store._read_db) as opened:
            self.assertEqual(playback.paired(service_for(f,other),*request,179999,3),expected)
            self.assertEqual(opened.call_count,1)
        self.assertEqual(f.store._playback_projection.scope[1],other)
        f.store.revoke(f.pid);self.assertIsNone(f.store._playback_projection)
        with self.assertRaises(VaultError):playback.paired(service_for(f,other),*request,179999,3)
        f.store._keys[f.token]=(f.pid,f.key)
        playback.timeline(f.service,*request)
        # Local HEAD publication invalidates proactively; unrelated valid changes
        # rebuild once; creative changes refuse the previous approved movie.
        f.editor._execute(f.pid,lambda db,movie:None,mutate=True)
        self.assertIsNone(f.store._playback_projection)
        with patch.object(f.store,'_read_db',wraps=f.store._read_db) as opened:
            self.assertEqual(playback.paired(service_for(f),*request,179999,3),expected)
            self.assertEqual(opened.call_count,1)
        self.finish.change(f.pid,1,'color',{**DEFAULT_COLOR,'exposure':.2})
        with self.assertRaises((PermissionError,RuntimeError,ValueError)):playback.paired(f.service,*request,0,1)
        self.assertIsNone(f.store._playback_projection)

    def test_projection_budget_falls_back_without_relaxing_validation(self):
        self.seed();done=self.run_all();f=self.f;args=(f.service,f.pid,2,f.digest,done['job_id'])
        playback.timeline(*args);expected=playback.paired(*args,0,24000)
        f.store._playback_projection=None
        with patch.object(projection,'MAX_PROJECTED_BYTES',1),patch.object(f.store,'_read_db',wraps=f.store._read_db) as opened:
            self.assertEqual(playback.paired(*args,0,24000),expected)
            self.assertEqual(playback.paired(*args,0,24000),expected)
            self.assertEqual(opened.call_count,2);self.assertIsNone(f.store._playback_projection)
        with patch.object(projection,'MAX_DEPENDENCIES',0):
            playback.timeline(*args);self.assertIsNone(f.store._playback_projection)
            self.assertEqual(playback.paired(*args,0,24000),expected)
        self.assertIsNone(f.store._playback_projection)


class SustainedReadback(R6Base,unittest.TestCase):
    def test_complete_seven_reel_readback_and_measured_memory(self):
        f=Fixture(self,count=32);self.f=f;finish(f)
        self.analysis=analyze_approved(f.service,f.pid,review(f.service,f.pid,2,f.digest),human_approved=True)
        def next_reel():return reels.review_next(f.service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=240)
        for end in (240,480,720,960,1200,1440,1524):self.assertEqual(self.execute(next_reel())['end_frame'],end)
        done=self.execute(next_reel());self.assertEqual(done['frames'],1524);self.assertEqual(done['reel_count'],7)
        args=(f.pid,2,f.digest,done['job_id']);reports={};digests={}
        # All requests use new service instances, as does the HTTP router.
        for mode in ('full','projected'):
            f.store._playback_projection=None
            with patch.object(projection,'MAX_PROJECTED_BYTES',0 if mode=='full' else 4*1024*1024):
                playback.timeline(service_for(f),*args)
                cached=f.store._playback_projection
                with patch.object(f.store,'_read_db',wraps=f.store._read_db) as opened,patch.object(reels,'_current',wraps=reels._current) as reviewed,patch.object(reels,'_read_body',wraps=reels._read_body) as reads,MemorySample() as memory:
                    picture=hashlib.sha256();audio=hashlib.sha256();frames=samples=windows=0;before=time.perf_counter()
                    for first in range(0,done['samples'],24000):
                        result=playback.paired(service_for(f),*args,first,min(24000,done['samples']-first));windows+=1
                        self.assertEqual(result['source_sha256'],done['completion_sha256']);self.assertEqual(result['start_sample'],samples)
                        for item in result['frames']:
                            self.assertEqual(item['frame'],frames);frames+=1
                            picture.update(base64.b64decode(item['picture_base64']))
                        with wave.open(io.BytesIO(base64.b64decode(result['audio_base64'])),'rb') as wav:
                            samples+=wav.getnframes();audio.update(wav.readframes(wav.getnframes()))
                        del result
                    elapsed=time.perf_counter()-before
                self.assertEqual((frames,samples),(done['frames'],done['samples']));self.assertEqual(audio.hexdigest(),done['pcm_sha256'])
                self.assertEqual(windows,127);self.assertEqual(opened.call_count,127 if mode=='full' else 0);self.assertEqual(reviewed.call_count,127 if mode=='full' else 0);self.assertEqual(reads.call_count,127)
                digests[mode]=(picture.hexdigest(),audio.hexdigest());reports[mode]={'seconds':elapsed,'windows':windows,'snapshot_deserializations':opened.call_count,'full_source_reviews':reviewed.call_count,'reel_reads':reads.call_count,'metadata_budget_estimate':0 if cached is None else cached.bytes_used,'rss_bytes':memory.report()}
        self.assertEqual(digests['full'],digests['projected']);self.assertIsNotNone(f.store._playback_projection)
        self.assertLessEqual(f.store._playback_projection.bytes_used,projection.MAX_PROJECTED_BYTES)
        print('R12_SUSTAINED_RETRIEVAL '+json.dumps(reports,sort_keys=True),flush=True)


class IncrementalInventory(unittest.TestCase):
    def test_adjacent_pages_exact_and_snapshot_bound(self):
        f=Fixture(self);f.migrate()
        original=f.editor._execute(f.pid,lambda db,movie:tuple(db.execute('SELECT * FROM g06_frozen_takes ORDER BY take_id LIMIT 1').fetchone()))
        reviewed=payloads.review(f.store,f.pid,f.token,'take')
        payloads.migrate(f.store,f.pid,f.token,'take',None,reviewed['approval_digest'],human_approved=True)
        def seed(db,movie):
            # Metadata scale fixture (not separately rendered originals).
            for n in range(4096):
                ident=f'{100000+n:032x}'
                db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,f.pid,'SC_abcdef012345',None,'native_microphone_pcm16le',b'\0\0',hashlib.sha256(b'\0\0').hexdigest(),48000,1,1,'2026-11-19'))
                db.execute('INSERT INTO g06_frozen_takes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,*original[1:]))
        f.editor._execute(f.pid,seed,mutate=True)
        reports={}
        for family in ('takes','recordings'):
            values={}
            for mode in ('full','projected'):
                cursor=None;pages=[];seen=set();f.store._inventory_projection=None
                with patch.object(projection,'INVENTORY_PAGES',0 if mode=='full' else 4),patch.object(f.store,'_read_db',wraps=f.store._read_db) as opened:
                    at=time.perf_counter()
                    for _ in range(8):
                        page=playback.inventory(service_for(f),f.pid,family,cursor,64)
                        self.assertEqual(len(page['items']),64);self.assertFalse(page['media_authenticated'])
                        for item in page['items']:
                            self.assertNotIn(item['id'],seen);seen.add(item['id'])
                        pages.append(page);cursor=page['next_after']
                    seconds=time.perf_counter()-at
                    self.assertEqual(opened.call_count,8 if mode=='full' else 2)
                values[mode]=pages
                reports[family+'_'+mode]={'seconds':seconds,'snapshot_deserializations':opened.call_count,'rows':len(seen),'pages':len(pages)}
            self.assertEqual(values['full'],values['projected']);cached=f.store._inventory_projection
            self.assertLessEqual(cached['bytes_used'],projection.MAX_INVENTORY_BYTES);self.assertLessEqual(len(cached['pages']),4)
            self.assertEqual(cached['scope'][2],family)
            # No mutable reference into prefetched metadata is returned.
            first=next(iter(cached['pages']));page=playback.inventory(service_for(f),f.pid,family,first,64)
            expected=page['items'][0]['id'];page['items'][0]['id']='0'*32
            self.assertEqual(playback.inventory(service_for(f),f.pid,family,first,64)['items'][0]['id'],expected)
        print('R12_INVENTORY_READBACK '+json.dumps(reports,sort_keys=True),flush=True)
        cached=f.store._inventory_projection;cursor=next(iter(cached['pages']));target=f.folder/'revisions'/cached['head']['name'];original_cipher=target.read_bytes()
        try:
            target.write_bytes(original_cipher[:-1]+bytes([original_cipher[-1]^1]))
            with self.assertRaises(VaultError):playback.inventory(service_for(f),f.pid,'recordings',cursor,64)
            self.assertIsNone(f.store._inventory_projection)
        finally:target.write_bytes(original_cipher)
        playback.inventory(f.service,f.pid,'recordings',None,64)
        # Valid new snapshot contains malformed metadata: cached page cannot mask it.
        f.editor._execute(f.pid,lambda db,movie:db.execute('UPDATE g03_pcm_pages SET size_bytes=1 WHERE project_id=?',(f.pid,)),mutate=True)
        self.assertIsNone(f.store._inventory_projection)
        with self.assertRaises(VaultError):playback.inventory(f.service,f.pid,'recordings',None,64)
        playback.inventory(f.service,f.pid,'takes',None,64);f.store.revoke(f.pid);self.assertIsNone(f.store._inventory_projection)
        with self.assertRaises(VaultError):playback.inventory(f.service,f.pid,'takes',None,64)
