"""Real OpenUSD donut object-actor source, curved shading and lighting tests."""
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_film01_donut_actor import original_donut_mesh
from backend.nvp_virtual_light_fx import make_simple_virtual_fx
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from tools.nvp_film01_donut_light_probe import (
    DONUT_PATH,LOOKS,build_frozen_donut_source,
    render_donut_four_looks,export_donut_lighting_contact)


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


class DonutSourceMesh(unittest.TestCase):
    def test_closed_torus_hole_real_curved_topology_normals_and_uv(self):
        geom=original_donut_mesh()
        n=geom["major_segments"]*geom["minor_segments"]
        self.assertEqual(len(geom["mesh_points"]),n)
        self.assertEqual(len(geom["mesh_triangles"]),n*2)
        self.assertEqual(len(geom["mesh_face_uvs"]),n*2)
        self.assertGreater(geom["hole_radius"],.2)
        self.assertGreater(geom["outer_radius"],geom["hole_radius"])
        self.assertEqual(geom,original_donut_mesh())
        pts=geom["mesh_points"]
        for triangle in geom["mesh_triangles"]:
            a,b,c=[pts[i] for i in triangle]
            u=[b[i]-a[i] for i in range(3)]
            v=[c[i]-a[i] for i in range(3)]
            normal=_cross(u,v)
            radius=math.hypot(a[0],a[1])
            outward=(a[0]/radius*(radius-geom["major_radius"]),
                     a[1]/radius*(radius-geom["major_radius"]),a[2])
            self.assertGreater(sum(x*y for x,y in zip(normal,outward)),-1e-8)
            self.assertGreater(math.sqrt(sum(x*x for x in normal)),1e-7)
        self.assertEqual(geom["format"],"nvp.film01.original_donut_torus_mesh.v1")

    def test_malformed_donuts_are_rejected_before_original_usd(self):
        for kwargs in (
            {"major_radius":0.2,"minor_radius":0.3},
            {"major_radius":float("nan")},
            {"major_segments":8},
            {"minor_segments":40},
            {"major_segments":64,"minor_segments":24},
        ):
            # 64x24 is within the authoring vertex budget and is valid,
            # unlike an unbounded 100x40 mesh. Keep large but valid
            # native source meshes legal for later actor detail.
            if kwargs.get("major_segments")==64:
                self.assertEqual(len(original_donut_mesh(**kwargs)[
                    "mesh_points"]),64*24)
            else:
                with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                    original_donut_mesh(**kwargs)


class NativeDonutPixelLighting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.root=Path(cls.temp.name).resolve()
        cls.source=build_frozen_donut_source(cls.root/"source")
        cls.results,cls.comparisons=render_donut_four_looks(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_actor_is_bound_real_openusd_mesh_and_three_time_samples(self):
        i=self.source["index"]
        scene=i.read_revision(
            self.source["project_id"],"DonutLightingScene",1)
        self.assertEqual(scene["data"]["prim_roles"][DONUT_PATH],"actor")
        self.assertEqual(scene["document_sha256"],self.source["scene_sha256"])
        self.assertTrue(any(
            b["asset_id"]=="DonutMesh" and b["asset_revision"]==1
            for b in scene["data"]["asset_bindings"]))
        take=i.read_revision(
            self.source["project_id"],"DonutLightingTake",1)
        self.assertEqual(take["document_sha256"],self.source["take_sha256"])
        self.assertEqual(take["data"]["sample_ticks"],[
            0,7056000000,14112000000,17640000000])
        self.assertEqual(scene["data"]["prim_roles"][
            "/World/BoxActor"],"actor")
        self.assertEqual(scene["data"]["prim_roles"][
            "/World/SphereActor"],"actor")

    def test_real_native_3d_donut_hole_visible_and_all_four_looks_affect_pixels(self):
        self.assertEqual([r["look"] for r in self.results],list(LOOKS))
        self.assertEqual(
            len({r["original_take_sha256"] for r in self.results}),1)
        self.assertEqual(
            len({r["torus_mesh_sha256"] for r in self.results}),1)
        for row in self.results:
            self.assertGreater(row["rendered_triangle_count"],0)
            self.assertEqual(
                row["authored_torus_triangle_count"],
                len(self.source["geometry"]["mesh_triangles"]))
            # The center is now occupied by the box crossing *behind*
            # the real donut opening: a dark hole would be a false pass.
            self.assertGreater(row["central_hole_mean_brightness_8bit"],2)
            self.assertEqual(row["center_visible_original_actor"],
                             "/World/BoxActor")
            self.assertGreater(row["annular_ring_mean_brightness_8bit"],1)
            self.assertGreater(row["lit_ring_highlight_range_8bit"],0)
            self.assertFalse(row["real_interobject_shadow_rays_computed"])
            self.assertFalse(row["real_interobject_reflection_rays_computed"])
            self.assertEqual(row["original_acting_object_role"],"actor")
        self.assertFalse(self.results[0][
            "virtual_effects_applied_to_real_pixels"])
        self.assertTrue(all(r["virtual_effects_applied_to_real_pixels"]
                            for r in self.results[1:]))
        self.assertEqual(len(self.comparisons),3)
        self.assertTrue(all(c["real_changed_pixel_count"]>20
                            for c in self.comparisons))
        gold=self.comparisons[1]["real_RGB_mean_delta_8bit"]
        self.assertGreater(gold[0],gold[2])

    def test_wrong_target_and_uncaptured_independent_light_cannot_render(self):
        raster=NativeSceneLinearRaster(self.source["index"])
        for fx in (
            make_simple_virtual_fx(
                "gold_fill","/World/NotAnActor",fx_id="Forged"),
            make_simple_virtual_fx(
                "police_red_blue",DONUT_PATH,fx_id="LivePolice",
                clock_mode="independent_live",anchor_monotonic_ns=10,
                frequency_hz=2),
        ):
            with self.subTest(kind=fx["kind"]),self.assertRaises(
                    (PermissionError,ValueError)):
                raster.render(
                    self.source["project_id"],"DonutLightingTake",
                    self.source["take_sha256"],tick=7056000000,
                    camera_path="/World/Camera",virtual_fx=[fx])

    def test_actual_four_png_contact_and_per_look_receipts(self):
        output=self.root/"real-original-actor-lighting"
        data=export_donut_lighting_contact(self.source,output)
        self.assertTrue(data["real_usd_torus_ring_with_hole"])
        self.assertEqual(len(data["genuine_per_light_render_receipts"]),4)
        self.assertTrue((output/
            "donut_actor_real_NVP_4_lighting_looks.png").is_file())
        self.assertEqual(len(list(output.glob("donut_actor_*_real_NVP.png"))),4)
        self.assertTrue((output/
            "donut_actor_actual_source_lighting_receipt.json").is_file())
        self.assertFalse(data["no_authorized_film_release_or_DCI_master"] is False)
        with self.assertRaises(PermissionError):
            export_donut_lighting_contact(self.source,output)


if __name__=="__main__":
    unittest.main()
