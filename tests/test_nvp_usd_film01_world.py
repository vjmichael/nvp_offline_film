"""USD-FILM-01: genuine project-owned OpenUSD film world composition tests.

Reopens real FilmIndex scene/asset sources and exercises native USD payload
LoadNone/Load/Unload, references, look variants, and PointInstancer. A Take
remains immutable while a world changes. No mesh approximation or mock USD.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pxr import Usd, UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_usd_film01_world import (
    FORMAT, MAX_INSTANCES, MAX_SETS, OpenUSDWorldComposer,
)

T = TICKS_PER_SECOND


class NativeFilmWorld01(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "nvp-studio.sqlite"
        self.studio = Studio(self.db)
        self.pid = self.studio.create_project(
            "Persistent virtual filmmaking set", "")["id"]
        self.index = FilmIndex(self.studio)
        self.assets = OpenUSDAssetRegistry(self.index)
        self.scenes = OpenUSDSceneBridge(self.index)
        self.world = OpenUSDWorldComposer(self.index)
        for name, shape, size in (
            ("Crate", "cube", 2),
            ("SmallCrate", "cube", 1),
            ("Tree", "sphere", 1),
            ("TallProp", "cube", 4),
        ):
            self.assets.publish(self.pid, name, shape=shape, size_m=size)
        self.scenes.publish(
            self.pid, "Street", native_schemas=True,
            prims=[
                {"path":"/World/Camera","role":"camera",
                 "position":[0,4,10]},
                {"path":"/World/StreetLamp","role":"light",
                 "position":[-4,2,8]},
                {"path":"/World/StageActor","role":"actor",
                 "position":[2,0,0]},
            ], curves=[])
        self.scenes.publish(
            self.pid, "Interior", native_schemas=True,
            prims=[
                {"path":"/World/InteriorCamera","role":"camera",
                 "position":[0,2,5]},
                {"path":"/World/Table","role":"prop",
                 "position":[1,0,0]},
            ], curves=[])
        self.sets = [
            {"name":"Outside","scene_id":"Street","scene_revision":1},
            {"name":"Inside","scene_id":"Interior","scene_revision":1},
        ]
        self.props = [
            {"name":"Box","asset_id":"Crate","asset_revision":1,
             "position_m":[0,0,0],"load":"reference"},
            {"name":"TemporaryBox","asset_id":"SmallCrate","asset_revision":1,
             "position_m":[3,0,0],"load":"payload"},
        ]
        self.variants = [
            {"name":"Facade","position_m":[8,0,0],"selected":"Low",
             "options":[
                 {"name":"Low","asset_id":"Crate","asset_revision":1},
                 {"name":"High","asset_id":"TallProp","asset_revision":1},
             ]},
        ]
        self.instancers = [
            {"name":"Trees","asset_id":"Tree","asset_revision":1,
             "positions_m":[[float(n*2),20.,0.] for n in range(80)]},
        ]

    def publish(self, world_id="TownWorld", expected_revision=0, **overrides):
        args=dict(
            sets=deepcopy(self.sets), props=deepcopy(self.props),
            variants=deepcopy(self.variants),
            instancers=deepcopy(self.instancers),
            expected_revision=expected_revision)
        args.update(overrides)
        return self.world.publish(self.pid,world_id,**args)

    def test_real_lazy_scene_payloads_and_original_authored_camera(self):
        record = self.publish()
        self.assertEqual(record["revision"],1)
        with self.world.open(self.pid,"TownWorld",1) as session:
            self.assertEqual(session.record["document_sha256"],
                             record["document_sha256"])
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Sets/Outside").IsLoaded())
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Sets/Inside").IsLoaded())
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Sets/Outside/StageActor").IsValid())
            self.assertTrue(session.stage.GetPrimAtPath(
                "/World/Props/Box/Geometry").IsA(UsdGeom.Cube))
            self.assertTrue(session.stage.GetPrimAtPath(
                "/World/Props/TemporaryBox").IsValid())
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Props/TemporaryBox").IsLoaded())
            self.assertEqual(session.load_props(["TemporaryBox"])["operation"],
                             "load_props")
            self.assertTrue(session.stage.GetPrimAtPath(
                "/World/Props/TemporaryBox/Geometry").IsA(UsdGeom.Cube))
            self.assertEqual(session.unload_props(["TemporaryBox"])["operation"],
                             "unload_props")
            loaded = session.load(["Outside"])
            self.assertEqual(loaded["sets"],["Outside"])
            self.assertTrue(session.stage.GetPrimAtPath(
                "/World/Sets/Outside/Camera").IsA(UsdGeom.Camera))
            self.assertTrue(session.stage.GetPrimAtPath(
                "/World/Sets/Outside/StageActor").IsDefined())
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Sets/Inside").IsLoaded())
            self.assertGreaterEqual(loaded["elapsed_ms"],0)
            receipt = session.receipt()
            self.assertEqual(receipt["loaded_set_names"],["Outside"])
            self.assertFalse(receipt["usd_delegates_or_pixels_rendered"])
            self.assertGreater(receipt["source_staging_bytes"],0)
            self.assertGreaterEqual(receipt["usd_stage_load_none_ms"],0)
            self.assertEqual(session.unload(["Outside"])["sets"],["Outside"])
            self.assertFalse(session.stage.GetPrimAtPath(
                "/World/Sets/Outside").IsLoaded())
        self.assertTrue(session.closed)
        with self.assertRaises(RuntimeError):
            session.load(["Outside"])

    def test_native_instance_prototype_and_director_variants(self):
        self.publish()
        with self.world.open(self.pid,"TownWorld",1) as session:
            stage = session.stage
            variants = stage.GetPrimAtPath("/World/Variants/Facade")
            look = variants.GetVariantSets().GetVariantSet("look")
            self.assertEqual(look.GetVariantSelection(),"Low")
            low = UsdGeom.Cube(stage.GetPrimAtPath(
                "/World/Variants/Facade/Geometry"))
            self.assertTrue(low)
            self.assertAlmostEqual(low.GetSizeAttr().Get(),2.)
            switched=session.switch_variant("Facade","High")
            self.assertTrue(switched["persists_only_if_new_world_revision_published"])
            high = UsdGeom.Cube(stage.GetPrimAtPath(
                "/World/Variants/Facade/Geometry"))
            self.assertAlmostEqual(high.GetSizeAttr().Get(),4.)
            inst = UsdGeom.PointInstancer(stage.GetPrimAtPath(
                "/World/Instancers/Trees"))
            self.assertEqual(len(inst.GetPositionsAttr().Get()),80)
            self.assertEqual(len(inst.GetProtoIndicesAttr().Get()),80)
            prototype=inst.GetPrototypesRel().GetTargets()[0]
            self.assertTrue(stage.GetPrimAtPath(str(prototype)+"/Geometry").
                            IsA(UsdGeom.Sphere))
        # Uncommitted local look switch must NEVER rewrite FilmIndex.
        with OpenUSDWorldComposer(FilmIndex(Studio(self.db))).open(
                self.pid,"TownWorld",1) as reopened:
            p = reopened.stage.GetPrimAtPath("/World/Variants/Facade")
            self.assertEqual(
                p.GetVariantSets().GetVariantSet("look").GetVariantSelection(),
                "Low")

    def test_world_revision_reuses_sources_without_mutating_old_take(self):
        self.publish()
        ledger=TemporalLedger(self.index)
        self.index.register_revision(
            self.pid,"A1","performance",
            {"format":"nvp.test.acting.v1","action":"stand"},expected_revision=0)
        ledger.publish(self.pid,"OriginalTimeline",[{
            "event_id":"first_action","event_kind":"action",
            "subject_id":"A1","start_tick":0,"end_tick":2*T,
            "source_id":"A1","source_revision":1,
            "payload":{"usd_prim_path":"/World/StageActor"},
        }],duration_tick=3*T)
        capture=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="DIRECTOR" and
                scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        capture.freeze(
            self.pid,"OriginalTake",scene_id="Street",scene_revision=1,
            timeline_id="OriginalTimeline",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="DIRECTOR")
        old_take=self.index.read_revision(
            self.pid,"OriginalTake",1)["document_sha256"]
        self.assets.publish(
            self.pid,"Crate",shape="cube",size_m=6,expected_revision=1)
        revised_props=deepcopy(self.props)
        revised_props[0]["asset_revision"]=2
        revised_variants=deepcopy(self.variants)
        revised_variants[0]["selected"]="High"
        revision=self.publish(
            expected_revision=1,props=revised_props,variants=revised_variants)
        self.assertEqual(revision["revision"],2)
        fresh=OpenUSDWorldComposer(FilmIndex(Studio(self.db)))
        with fresh.open(self.pid,"TownWorld",1) as original:
            self.assertAlmostEqual(
                UsdGeom.Cube(original.stage.GetPrimAtPath(
                    "/World/Props/Box/Geometry")).GetSizeAttr().Get(),2.)
            self.assertEqual(
                original.stage.GetPrimAtPath(
                    "/World/Variants/Facade").GetVariantSets().
                    GetVariantSet("look").GetVariantSelection(),"Low")
        with fresh.open(self.pid,"TownWorld",2) as newer:
            self.assertAlmostEqual(
                UsdGeom.Cube(newer.stage.GetPrimAtPath(
                    "/World/Props/Box/Geometry")).GetSizeAttr().Get(),6.)
            self.assertEqual(
                newer.stage.GetPrimAtPath(
                    "/World/Variants/Facade").GetVariantSets().
                    GetVariantSet("look").GetVariantSelection(),"High")
        self.assertEqual(
            self.index.read_revision(
                self.pid,"OriginalTake",1)["document_sha256"],old_take)
        self.assertEqual(
            capture.verify_take(
                self.pid,"OriginalTake")["status"],
            "VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(
            self.index.direct_dependents(self.pid,"Crate",1),
            [
                {"object_id":"TownWorld","revision":1},
                {"object_id":"TownWorld","revision":2},
            ])

    def test_foreign_film_untrusted_paths_ambiguous_views_and_unbounded_work_refused(self):
        outsider=self.studio.create_project("Other film","")["id"]
        with self.assertRaises(KeyError):
            OpenUSDWorldComposer(self.index).publish(
                outsider,"ForeignWorld",
                sets=deepcopy(self.sets))
        with self.assertRaises(ValueError):
            self.publish(props=[{
                **self.props[0],"file_path":"/tmp/another-film.usda"
            }])
        with self.assertRaises(ValueError):
            self.publish(props=[{
                **self.props[0],"name":"../Escape"
            }])
        with self.assertRaises(ValueError):
            self.publish(instancers=[{
                **self.instancers[0],
                "positions_m":[[0.,0.,0.] for _ in range(MAX_INSTANCES+1)]
            }])
        with self.assertRaises(ValueError):
            self.publish(sets=self.sets * (MAX_SETS//len(self.sets)+1))
        with self.assertRaises(ValueError):
            self.publish(props=[{
                **self.props[0],"position_m":[float("nan"),0,0]
            }])
        self.publish()
        with self.world.open(self.pid,"TownWorld",1) as session:
            with self.assertRaises(PermissionError):
                session.load(["NotAnOriginalFilmSet"])
            with self.assertRaises(ValueError):
                session.load(["Inside","Inside"])
            with self.assertRaises(ValueError):
                session.load_props(["Box"])
            with self.assertRaises(ValueError):
                session.switch_variant("Facade","UnsignedExternalLook")
        with self.assertRaises(KeyError):
            self.world.open(outsider,"TownWorld",1).__enter__()

    def test_asset_with_unresolved_texture_is_not_implicitly_rendered(self):
        # The future project asset resolver must handle images/MaterialX
        # separately. This gate cannot accept arbitrary user-file paths.
        self.publish()
        with self.world.open(self.pid,"TownWorld",1) as session:
            record = session.record["data"]
            self.assertFalse(record["external_source_paths_authoritative"])
            self.assertFalse(record["renderer_pixels_verified"])
            self.assertTrue(record["lazy_sets_default_unloaded"])
            self.assertEqual(record["ticks_per_second"],T)
            self.assertEqual(record["coordinate_system"],"meters_Z_up")


if __name__ == "__main__":
    unittest.main()
