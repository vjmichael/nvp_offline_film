"""NVP-DATA-01: real persisted film index, source hash and invalidation tests."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.nvp_film_index import FilmIndex, MAX_JSON_BYTES
from backend.nvp_production_scene import ProductionScene
from backend.nvp_studio import Studio


SCRIPT = """INT. TEST ROOM - NIGHT

MARA
Where did you put the photograph?
"""


class FilmIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "film.sqlite3"
        self.studio = Studio(self.db)
        self.film = FilmIndex(self.studio)
        self.pid = self.studio.create_project("Data First","Capture the source, not just pixels")["id"]
        self.other = self.studio.create_project("Another Film","Isolation must be enforced")["id"]

    def tearDown(self):
        self.temp.cleanup()

    def record(self, obj_id, kind, data=None, *, deps=None, expected=0, pid=None):
        return self.film.register_revision(pid or self.pid, obj_id, kind,
                  data or {"detail":obj_id}, expected_revision=expected,
                  dependencies=deps or [])

    @staticmethod
    def edge(obj, revision=1, role="scene"):
        return {"object_id":obj, "revision":revision, "role":role}

    def test_immutable_content_addressed_bytes_survive_restart(self):
        data=b"frame data\x00" * 9
        sha=self.film.put_blob(self.pid,data,"application/octet-stream")
        self.assertEqual(sha,hashlib.sha256(data).hexdigest())
        self.assertEqual(self.film.get_blob(self.pid,sha),data)
        reopened=FilmIndex(Studio(self.db))
        self.assertEqual(reopened.get_blob(self.pid,sha),data)
        self.assertEqual(reopened.put_blob(self.pid,data),sha)
        with self.assertRaises(KeyError):
            reopened.get_blob(self.other,sha)

    def test_blob_corruption_and_symlink_refused(self):
        sha=self.film.put_blob(self.pid,b"legitimate")
        path=self.film._blob_path(self.pid,sha)
        path.write_bytes(b"replaced")
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            self.film.get_blob(self.pid,sha)
        with self.assertRaisesRegex(RuntimeError,"corrupted"):
            self.film.put_blob(self.pid,b"legitimate")

        second=self.film.put_blob(self.pid,b"another")
        another=self.film._blob_path(self.pid,second)
        another.unlink()
        another.symlink_to(path)
        with self.assertRaisesRegex(RuntimeError,"symlink"):
            self.film.get_blob(self.pid,second)

    def test_source_revision_immutable_optimistic_and_reloaded(self):
        source={"scene":"diner","props":["key","cup"],"camera":{"x":3}}
        first=self.record("scene_diner","scene",source)
        source["props"].append("weapon")
        saved=self.film.read_revision(self.pid,"scene_diner",1)
        self.assertEqual(saved["data"]["props"],["key","cup"])
        self.assertEqual(first["document_sha256"],saved["document_sha256"])
        self.assertEqual(saved["parent_revision"],None)
        second=self.record("scene_diner","scene",
                           {"scene":"diner","props":["key","cup","weapon"]},
                           expected=1)
        self.assertEqual(second["revision"],2)
        with self.assertRaisesRegex(RuntimeError,"conflict"):
            self.record("scene_diner","scene",{"revision":"stale"},expected=1)
        with self.assertRaisesRegex(RuntimeError,"kind"):
            self.record("scene_diner","actor",{"role":"wrong"},expected=2)
        reloaded=FilmIndex(Studio(self.db))
        self.assertEqual(reloaded.read_revision(self.pid,"scene_diner")["revision"],2)
        self.assertEqual(reloaded.read_revision(self.pid,"scene_diner",1)["data"]["props"],["key","cup"])
        self.assertEqual([x["revision"] for x in reloaded.history(self.pid,"scene_diner")],[1,2])
        self.assertEqual(reloaded.list_objects(self.pid,kind="scene")[0]["head_revision"],2)

    def test_frozen_take_is_one_commit_per_identity(self):
        self.record("scene_one","scene")
        first=self.record("take_001","take",{"shot_id":"S01","frame_start":1,
                      "frame_end":120},deps=[self.edge("scene_one")])
        self.assertEqual(first["kind"],"take")
        with self.assertRaisesRegex(RuntimeError,"cannot be revised"):
            self.record("take_001","take",{"shot_id":"S01","frame_end":121},
                        deps=[self.edge("scene_one")],expected=1)
        second=self.record("take_002","take",{"shot_id":"S01","frame_start":1,
                           "frame_end":121},deps=[self.edge("scene_one")])
        self.assertNotEqual(second["document_sha256"],first["document_sha256"])
        self.assertEqual(self.film.read_revision(self.pid,"take_001")["data"]["frame_end"],120)

    def test_typed_lineage_and_bounded_selective_impact(self):
        self.record("wardrobe_01","asset",{"color":"brown"})
        self.record("unrelated_sound","audio",{"wave":"sFX-1"})
        self.record("scene_12","scene",{"set":"diner"},deps=[self.edge("wardrobe_01",role="asset")])
        self.record("take_04","take",{"frames":120},deps=[self.edge("scene_12",role="scene")])
        self.record("presentation_a","presentation",{"style":"film noir"},
                    deps=[self.edge("take_04",role="source_take")])
        self.record("presentation_b","presentation",{"style":"anime"},
                    deps=[self.edge("take_04",role="source_take")])
        self.record("edit_01","edit",{"selected":"presentation_a"},
                    deps=[self.edge("presentation_a",role="presentation")])
        self.record("master_01","master",{"format":"mp4"},
                    deps=[self.edge("edit_01",role="timeline")])
        affected=self.film.impact(self.pid,"wardrobe_01",1)
        self.assertEqual({x["object_id"] for x in affected},
                         {"scene_12","take_04","presentation_a","presentation_b",
                          "edit_01","master_01"})
        self.assertEqual(self.film.impact(self.pid,"unrelated_sound",1),[])
        self.assertEqual({x["object_id"] for x in
                          self.film.direct_dependents(self.pid,"take_04",1)},
                         {"presentation_a","presentation_b"})
        newer=self.record("wardrobe_01","asset",{"color":"black"},expected=1)
        self.assertEqual(newer["revision"],2)
        self.assertEqual(self.film.impact(self.pid,"wardrobe_01",2),[])
        self.assertEqual(self.film.read_revision(self.pid,"master_01")["data"]["format"],"mp4")
        self.assertEqual(self.film.read_revision(self.pid,"wardrobe_01",1)["data"]["color"],"brown")

    def test_unregistered_dependencies_cross_project_and_invalid_ids_refused(self):
        self.record("scene_01","scene")
        self.record("scene_01","scene",{"identical_id":"another_film"},pid=self.other)
        with self.assertRaisesRegex(KeyError,"Dependency revision"):
            self.record("take_missing","take",deps=[self.edge("unknown")])
        with self.assertRaisesRegex(KeyError,"Dependency revision"):
            self.record("take_future","take",deps=[self.edge("scene_01",3)])
        with self.assertRaisesRegex(KeyError,"Source revision"):
            self.film.direct_dependents(self.other,"scene_01",99)
        self.record("alien_take","take",{"foreign_project":"no"},
                    deps=[self.edge("scene_01")],pid=self.other)
        self.assertEqual(self.film.impact(self.pid,"scene_01",1),[])
        self.assertEqual(self.film.impact(self.other,"scene_01",1),
                         [{"object_id":"alien_take","revision":1}])
        with self.assertRaises(KeyError):
            self.film.read_revision(self.other,"alien_take",2)
        with self.assertRaises(KeyError):
            self.film.read_revision(self.other,"take_missing")
        for invalid in ("../escape","asset/../../other","", "object with spaces","a"*81):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.record(invalid,"scene")
        with self.assertRaises(ValueError):
            self.record("scene2","invalid_kind")

    def test_duplicate_self_and_invalid_edges_fail_closed(self):
        self.record("scene_01","scene")
        valid=self.edge("scene_01")
        for deps in [
            [valid,valid],
            [self.edge("unregistered",0)],
            [{"object_id":"../bad","revision":1,"role":"scene"}],
            [{"object_id":"scene_01","revision":True,"role":"scene"}],
            [{"object_id":"scene_01","revision":1,"role":"shady"}],
            [{"object_id":"scene_01","revision":1}],
            [self.edge("take_bad","1")],
        ]:
            with self.subTest(deps=deps),self.assertRaises(ValueError):
                self.record("take_bad","take",deps=deps)
        with self.assertRaises(ValueError):
            self.record("self_thing","scene",deps=[self.edge("self_thing")])

    def test_refuse_nan_non_json_and_oversized_payloads(self):
        with self.assertRaises(ValueError):
            self.record("bad_n","scene",{"x":float("nan")})
        with self.assertRaises(TypeError):
            self.record("bad_b","scene",{"what":b"not JSON"})
        with self.assertRaises(ValueError):
            self.record("bad_large","scene",{"payload":"x"*MAX_JSON_BYTES})
        with self.assertRaises(ValueError):
            self.film.put_blob(self.pid,bytearray(b"bytes-like"))
        with self.assertRaises(ValueError):
            self.film.put_blob("../evil",b"secret")
        with self.assertRaises(ValueError):
            self.film.put_blob(self.pid,b"source",media_type="bad\r\nmime")

    def test_database_edge_tamper_refused_on_read(self):
        self.record("asset_01","asset")
        item=self.record("scene_01","scene",deps=[self.edge("asset_01",role="asset")])
        with self.studio._connection() as db:
            db.execute("""DELETE FROM film_dependencies
                WHERE project_id=? AND source_id=?""",(self.pid,"scene_01"))
        with self.assertRaisesRegex(RuntimeError,"disagree"):
            self.film.read_revision(self.pid,"scene_01")
        self.assertEqual(self.film.get_blob(self.pid,item["document_sha256"]).__class__,bytes)

    def test_integration_indexes_actual_approved_production_layout(self):
        proj=self.studio.save_screenplay(self.pid,SCRIPT,0)
        sid=proj["scenes"][0]["id"]
        prod=ProductionScene(self.studio)
        chair=prod.create_asset(self.pid,{"name":"MARA","category":"character",
                          "dimensions":[0.6,0.6,1.7],"anchors":{}})
        stage=prod.stage_scene(self.pid,sid,[8,6,3])
        self.assertEqual(stage["unresolved_cast"],[])
        stage=prod.solve_scene(self.pid,sid,stage["plan_revision"])
        stage=prod.approve_scene(self.pid,sid,stage["plan_revision"])
        manifest=prod.export_manifest(self.pid,sid)
        asset=self.record("asset_mara","asset",{"asset_id":chair["asset_id"],
                          "approved_spec":chair})
        scene=self.record("scene_primary","scene",{"approved_proxy_manifest":manifest},
                          deps=[self.edge("asset_mara",role="asset")])
        reopened=FilmIndex(Studio(self.db))
        saved=reopened.read_revision(self.pid,"scene_primary")
        self.assertEqual(saved["data"]["approved_proxy_manifest"],manifest)
        self.assertEqual(saved["dependencies"][0]["object_id"],"asset_mara")
        self.assertEqual(reopened.direct_dependents(self.pid,"asset_mara",1),
                         [{"object_id":"scene_primary","revision":1}])
        self.assertEqual(scene["revision"],1)
        self.assertEqual(asset["revision"],1)

if __name__=="__main__":
    unittest.main()
