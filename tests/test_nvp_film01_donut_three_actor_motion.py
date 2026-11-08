"""A real object-actor box passes behind donut as sphere crosses its hole.

Native depth proves which actor owns the CENTER pixel at 0s, 1s and
2s. All three actor transforms derive from one frozen OpenUSD Take.
Real hard shadows and reflection rays are explicitly NOT yet supported
by this rasterizer; never count depth or colored fill as those effects.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from tools.nvp_film01_donut_light_probe import (
    DONUT_PATH,BOX_PATH,SPHERE_PATH,build_frozen_donut_source)
from tools.nvp_film01_donut_three_actor_motion import (
    render_actual_three_actor_frames,export_three_actor_picture_probe,
    EXPECTED_CENTER_OWNER,KEY_FRAMES)


class ThreeRealUSDObjectActors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory()
        cls.root=Path(cls.tmp.name).resolve()
        cls.source=build_frozen_donut_source(cls.root/"one-original-scene")
        cls.frames,cls.rows=render_actual_three_actor_frames(
            cls.source,full_72_frames=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_all_three_are_actor_roles_and_source_geometry_authorized(self):
        idx=self.source["index"]
        pid=self.source["project_id"]
        scene=idx.read_revision(pid,"DonutLightingScene",1)
        self.assertEqual(scene["document_sha256"],self.source["scene_sha256"])
        for path in (DONUT_PATH,BOX_PATH,SPHERE_PATH):
            self.assertEqual(scene["data"]["prim_roles"][path],"actor")
        binds={r["path"]:r for r in scene["data"]["asset_bindings"]}
        self.assertEqual(set(binds),{DONUT_PATH,BOX_PATH,SPHERE_PATH})
        self.assertEqual(binds[DONUT_PATH]["asset_id"],"DonutMesh")
        self.assertEqual(binds[BOX_PATH]["asset_id"],"BoxActorMesh")
        self.assertEqual(binds[SPHERE_PATH]["asset_id"],"SphereActorMesh")
        self.assertGreater(self.source["sphere_clearance_from_hole_m"],.2)
        take=idx.read_revision(pid,"DonutLightingTake",1)
        self.assertEqual(take["document_sha256"],self.source["take_sha256"])

    def test_real_center_depth_witnesses_sphere_then_box_then_sphere(self):
        by={row["frame_zero"]:row for row in self.rows}
        self.assertEqual(set(by),set(KEY_FRAMES))
        for frame,path in EXPECTED_CENTER_OWNER.items():
            self.assertEqual(
                by[frame]["camera_depth_test_center_actor"],path)
        self.assertLess(by[0]["box_world_position"][0],-2)
        self.assertAlmostEqual(by[24]["box_world_position"][0],0,places=4)
        self.assertGreater(by[48]["box_world_position"][0],2)
        self.assertLess(by[0]["sphere_world_position"][2],-3)
        self.assertLess(by[24]["sphere_world_position"][2],-3)
        self.assertGreater(by[48]["sphere_world_position"][2],0)
        for row in self.rows:
            self.assertTrue(row["box_physically_behind_torus"])
            self.assertEqual(row["sphere_through_torus_axis_xy"],[0.,0.])
            self.assertGreater(row["sphere_clearance_from_real_mesh_hole_m"],.2)
            self.assertGreater(
                row["native_visible_source_actor_pixels"][DONUT_PATH],50)
            self.assertFalse(row["real_shadow_ray_tracing_performed"])
            self.assertFalse(row["interobject_reflection_ray_tracing_performed"])
            self.assertEqual(
                row["original_take_sha256"],self.source["take_sha256"])
        self.assertEqual(len({row["depth_tested_native_picture_sha256"]
                              for row in self.rows}),len(self.rows))

    def test_six_actual_usd_frames_render_to_artistic_contact_sheet(self):
        output=self.root/"six_real_actor_moments"
        report=export_three_actor_picture_probe(
            self.source,output,full_72_frames=False)
        self.assertEqual(report["genuine_raster_source_frames"],6)
        self.assertFalse(report["full_72_frames_and_gif"])
        self.assertTrue(report["native_depth_occlusion_computed"])
        self.assertFalse(report["real_interobject_cast_shadows_computed"])
        self.assertFalse(report["real_interobject_reflections_computed"])
        with Image.open(output/
                        "donut_box_sphere_real_NVP_6_moments.png") as img:
            img.load()
            self.assertEqual(img.format,"PNG")
            self.assertEqual(img.size,(1956,816))
        self.assertEqual(len(list(output.glob("donut_actors_key_*.png"))),6)
        with self.assertRaises(PermissionError):
            export_three_actor_picture_probe(
                self.source,output,full_72_frames=False)


if __name__=="__main__":
    unittest.main()
