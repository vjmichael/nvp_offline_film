"""CONV-06: recovered original USD-FILM-02M-D geometry/cell source contracts.

The original historic full 02M native/Blender suite remains separately OPEN.
These source checks never claim protected storage, camera-cell OS memory
admission, completed Cycles pictures, licensed assets or director film signoff.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_usd_film02m_d_openings import (
    _box_shell_mesh, facade_layout, apertured_wall_mesh,
    original_through_opening, prove_facade_geometry, room_shell_mesh,
)
from backend.nvp_usd_film02m_d_cells import (
    OriginalBuildingCells, _bounds, _dist_to_aabb,
)


class OriginalApertureAndCellSource(unittest.TestCase):
    def test_original_three_treatments_have_real_topological_doorways(self):
        # Keep the historical 02M-D original geometry assertions, including
        # independent through-triangle tests, not opacity masks or fake doors.
        for treatment in ("residential","shopfront","industrial"):
            layout=facade_layout(
                width_m=12,height_m=6,stories=2,bays=3,
                treatment=treatment,seed=125)
            self.assertEqual(len(layout["openings"]),6)
            self.assertEqual(sum(x["kind"]=="door"
                                 for x in layout["openings"]),1)
            mesh=apertured_wall_mesh(12,.4,6,layout["openings"])
            self.assertTrue(prove_facade_geometry(mesh)[
                "all_source_openings_ray_verified"])
            self.assertTrue(mesh["real_jambs_and_wall_thickness"])
            self.assertGreater(len(mesh["triangles"]),60)
            self.assertFalse(original_through_opening(
                mesh["points"],mesh["triangles"],-5.94,0,.4))
            for opening in mesh["openings"]:
                self.assertTrue(original_through_opening(
                    mesh["points"],mesh["triangles"],
                    opening["x_center_m"],
                    opening["bottom_m"]+opening["height_m"]/2,.4))
            if treatment=="shopfront":
                self.assertGreater(sum(
                    x["kind"]=="storefront" for x in layout["openings"]),0)
        for stories in (1,3,4):
            height=3.*stories
            layout=facade_layout(
                width_m=12,height_m=height,stories=stories,
                bays=3,treatment="industrial",seed=73)
            source=apertured_wall_mesh(12,.4,height,layout["openings"])
            self.assertTrue(prove_facade_geometry(source)[
                "all_source_openings_ray_verified"])
        room=room_shell_mesh(11,9,5.2,.08)
        self.assertTrue(room["front_portal_open"])
        self.assertTrue(room["rear_wall_is_real_geometry"])
        self.assertFalse(original_through_opening(
            room["points"],room["triangles"],0,0,9))

    def test_source_refuses_fake_transparent_apertures_and_oversize_holes(self):
        layout=facade_layout(
            width_m=12,height_m=6,stories=2,bays=3,
            treatment="residential",seed=93)
        mesh=apertured_wall_mesh(12,.4,6,layout["openings"])
        solid_points,solid_faces=_box_shell_mesh([(-6,6,-.2,.2,-3,3)])
        fake={**mesh,"points":solid_points,"triangles":solid_faces}
        with self.assertRaises(RuntimeError):
            prove_facade_geometry(fake)
        invalid=list(layout["openings"])
        invalid[1]={**invalid[1],"width_m":11.95}
        with self.assertRaises(ValueError):
            apertured_wall_mesh(12,.4,6,invalid)
        self.assertTrue(prove_facade_geometry(mesh)[
            "all_source_openings_ray_verified"])

    def test_cells_require_real_frozen_building_sources_and_director_action(self):
        with TemporaryDirectory(prefix="nvp-conv06-02md-source-") as temp:
            studio=Studio(Path(temp)/"source.sqlite3")
            pid=studio.create_project("Original architecture cells","")["id"]
            index=FilmIndex(studio)
            with self.assertRaises(TypeError):
                OriginalBuildingCells(index,verify_director_action=None)
            host=OriginalBuildingCells(
                index,verify_director_action=lambda *_:False)
            with self.assertRaises(ValueError):
                host.publish(pid,"CityCells",cells=[],director_event=object())
            with self.assertRaises(ValueError):
                host.publish(pid,"CityCells",cells=[
                    {"cell_id":"CellWest","building_id":"SourceBuilding",
                     "building_revision":0}],director_event=object())
            with self.assertRaises(KeyError):
                host.publish(pid,"CityCells",cells=[
                    {"cell_id":"CellWest","building_id":"SourceBuilding",
                     "building_revision":1}],director_event=object())
            self.assertEqual(index.list_objects(pid,kind="presentation"),[])

    def test_cell_bounds_only_prefetch_and_never_revise_original_geometry(self):
        placements=[
            {"world_bounds_m":[[-5.,-3.,0.],[5.,3.,7.]]},
            {"world_bounds_m":[[10.,-2.,0.],[12.,2.,8.]]}]
        original=[dict(x) for x in placements]
        bounds=_bounds(placements)
        self.assertEqual(bounds,[[-5.,-3.,0.],[12.,3.,8.]])
        self.assertEqual(_dist_to_aabb([0.,0.,2.],bounds),0.)
        self.assertGreater(_dist_to_aabb([90.,0.,2.],bounds),70.)
        self.assertEqual(placements,original)


if __name__=="__main__":
    unittest.main()
