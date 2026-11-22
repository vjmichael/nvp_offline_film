"""DA-05: standalone miniaudio imported WAV source custody and bounded seek."""
from pathlib import Path
import hashlib
import math
import struct
import tempfile
import unittest
import wave

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_imported_audio import OriginalAudioImport

class NativeOriginalAudioImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-no-ffmpeg-audio-")
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"studio.sqlite3")
        self.pid=self.studio.create_project(
            "Creator-supplied original WAV","Not a flattened film")["id"]
        self.index=FilmIndex(self.studio)
        self.original=root/"music.wav"
        self.pcm=struct.pack("<"+"h"*12000,*[
            int(11000*math.sin(2*math.pi*220*i/48000))
            for i in range(6000) for _ in range(2)
        ])
        with wave.open(str(self.original),"wb") as w:
            w.setnchannels(2)
            w.setframerate(48000)
            w.setsampwidth(2)
            w.writeframes(self.pcm)
        self.hash=hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.importer=OriginalAudioImport(
            self.index,trusted_native_picker=lambda:self.original)

    def test_original_file_retained_while_seek_reads_small_pcm_windows(self):
        saved=self.importer.register_from_picker(self.pid,"MusicOriginal")
        self.assertEqual(saved["kind"],"audio")
        item=self.index.read_revision(self.pid,"MusicOriginal",1)
        self.assertEqual(item["data"]["source_media_sha256"],self.hash)
        self.assertEqual(item["data"]["original_codec"],"wav")
        self.assertFalse(item["data"]["converted_soundtrack"])
        piece=self.importer.read_window(self.pid,"MusicOriginal",1,300,1024)
        self.assertEqual(piece["format"],"nvp.imported_sound_pcm_window.v1")
        self.assertEqual(piece["pcm"],self.pcm[300*4:(300+1024)*4])
        self.assertEqual(piece["sample_count"],1024)
        self.assertFalse(piece["ffmpeg_used"])
        self.assertEqual(hashlib.sha256(
            self.original.read_bytes()).hexdigest(),self.hash)
        self.assertEqual(self.index.verify_media_file(
            self.pid,self.hash)["sha256"],self.hash)

    def test_native_picker_absence_and_changed_stored_original_fail_closed(self):
        refused=OriginalAudioImport(self.index,trusted_native_picker=lambda:None)
        with self.assertRaises(PermissionError):
            refused.register_from_picker(self.pid,"DeniedOriginal")
        self.importer.register_from_picker(self.pid,"MusicOriginal")
        stored=self.index._blob_path(self.pid,self.hash)
        original=stored.read_bytes()
        stored.write_bytes(original[:-2]+b"\x00\x00")
        try:
            with self.assertRaises(RuntimeError):
                self.importer.read_window(
                    self.pid,"MusicOriginal",1,0,128)
        finally:
            stored.write_bytes(original)

    def test_decoder_never_materializes_unbounded_request(self):
        self.importer.register_from_picker(self.pid,"MusicOriginal")
        with self.assertRaises(ValueError):
            self.importer.read_window(
                self.pid,"MusicOriginal",1,0,8192)
        with self.assertRaises(ValueError):
            self.importer.read_window(
                self.pid,"MusicOriginal",1,0,0)


if __name__=="__main__":
    unittest.main()
