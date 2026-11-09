"""USD-FILM-02M: real native OpenUSD source building module/revision tests.

This suite creates actual 3D closed source triangle meshes in FilmIndex,
assembles four independently authored street buildings using shared
modules, and reopens genuine USD references at front/rear/oblique shots.
No synthetic Blender pixels or actual completed films are claimed.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import unittest

from pxr import Usd,UsdGeom,UsdShade

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_usd_film02m_modular_buildings import (
    OriginalBuildingKit,MODULE_FORMAT,
    BUILD_FORMAT,_bbox,_rotate)


def cube_mesh(width,depth,height):
    x,y,z=width/2,depth/2,height/2
    points=[
        [-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],
        [-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]]
    triangles=[
        [0,2,1],[0,3,2],[4,5,6],[4,6,7],
        [0,1,5],[0,5,4],[3,7,6],[3,6,2],
        [0,4,7],[0,7,3],[1,2,6],[1,6,5]]
    return points,triangles


def sock(name,at,normal,span,type_name):
    return {"name":name,"connector_type":type_name,
            "gender":"universal","at_m":at,
            "normal":normal,"span_m":span,"tolerance_m":0.01}


def node(node_id,module,*,parent=None,attached=None,own=None,
         yaw=0,position=None,options=None):
    return {
        "node_id":node_id,"options":options or [
            {"module_id":module,"revision":1}],
        "parent_id":parent,"parent_socket":attached,
        "own_socket":own,"yaw_deg":yaw,"root_position_m":position}


def building_recipe(root,facade_options):
    return [
        node("Floor","ModuleFloor",position=[root,0,0]),
        node("Front","ModuleFacadeRed",parent="Floor",
            attached="Front",own="Back",options=[
                {"module_id":name,"revision":1}
                for name in facade_options]),
        node("Rear","ModuleRear",parent="Floor",
            attached="Rear",own="Front"),
        node("SideLeft","ModuleSideLeft",parent="Floor",
            attached="Left",own="Inner"),
        node("SideRight","ModuleSideRight",parent="Floor",
            attached="Right",own="Inner"),
        node("CornerFL","ModuleCornerLeft",parent="Front",
            attached="LeftEdge",own="Inner"),
        node("CornerFR","ModuleCornerRight",parent="Front",
            attached="RightEdge",own="Inner"),
        node("CornerRL","ModuleCornerLeft",parent="Rear",
            attached="LeftEdge",own="Inner"),
        node("CornerRR","ModuleCornerRight",parent="Rear",
            attached="RightEdge",own="Inner"),
        node("Roof","ModuleRoof",parent="Front",
            attached="Top",own="FrontBottom")]


class OriginalModularBuildingSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-02m-source-modules-")
        cls.root=Path(cls.tmp.name)
        cls.studio=Studio(cls.root/"film.sqlite3")
        cls.pid=cls.studio.create_project(
            "02M source modular film building",
            "Four actual camera-visible 3D original buildings")["id"]
        cls.index=FilmIndex(cls.studio)
        cls.approval="TEST_NATIVE_DIRECTOR_02M"
        cls.kit=OriginalBuildingKit(
            cls.index,verify_director_action=lambda event,scope:
                event==cls.approval and
                scope.get("operation") in (
                    "nvp.film02m.publish_original_building_module.v1",
                    "nvp.film02m.publish_original_architecture.v1") and
                len(scope.get("proposed_module_sha256",
                              scope.get("proposed_assembly_sha256","")))==64)
        cls.catalog={}
        pieces=[
            ("ModuleFloor","floor",[12,10,.4],[
                sock("Front",[0,-5,0],[0,-1,0],12,"wall_base"),
                sock("Rear",[0,5,0],[0,1,0],12,"wall_base"),
                sock("Left",[-6,0,0],[-1,0,0],10,"side_base"),
                sock("Right",[6,0,0],[1,0,0],10,"side_base")],
                [.45,.45,.43]),
            ("ModuleRear","rear",[12,.4,6],[
                sock("Front",[0,-.2,-3],[0,-1,0],12,"wall_base"),
                sock("LeftEdge",[-6,0,0],[-1,0,0],6,"corner_edge"),
                sock("RightEdge",[6,0,0],[1,0,0],6,"corner_edge")],
                [.42,.44,.46]),
            ("ModuleSideLeft","side",[.4,10,6],[
                sock("Inner",[.2,0,-3],[1,0,0],10,"side_base")],
                [.48,.5,.52]),
            ("ModuleSideRight","side",[.4,10,6],[
                sock("Inner",[-.2,0,-3],[-1,0,0],10,"side_base")],
                [.48,.5,.52]),
            ("ModuleCornerLeft","corner",[.4,.4,6],[
                sock("Inner",[.2,0,0],[1,0,0],6,"corner_edge")],
                [.36,.39,.42]),
            ("ModuleCornerRight","corner",[.4,.4,6],[
                sock("Inner",[-.2,0,0],[-1,0,0],6,"corner_edge")],
                [.36,.39,.42]),
            ("ModuleRoof","roof",[12.8,10.8,.4],[
                sock("FrontBottom",[0,-5.2,-.2],[0,0,-1],12,"roof_edge")],
                [.26,.3,.36]),
        ]
        colors=[
            ("ModuleFacadeRed",[.7,.24,.2]),
            ("ModuleFacadeBlue",[.2,.4,.76]),
            ("ModuleFacadeGreen",[.24,.64,.35]),
            ("ModuleFacadeGold",[.78,.63,.22])]
        cls.facades=[name for name,color in colors]
        for name,color in colors:
            pieces.append((name,"facade",[12,.4,6],[
                sock("Back",[0,.2,-3],[0,1,0],12,"wall_base"),
                sock("Top",[0,0,3],[0,0,1],12,"roof_edge"),
                sock("LeftEdge",[-6,0,0],[-1,0,0],6,"corner_edge"),
                sock("RightEdge",[6,0,0],[1,0,0],6,"corner_edge")],color))
        assets=OpenUSDAssetRegistry(cls.index)
        for name,role,dims,sockets,color in pieces:
            vertices,faces=cube_mesh(*dims)
            asset="Asset"+name
            published=assets.publish(
                cls.pid,asset,shape="mesh",size_m=max(dims),
                points=vertices,triangles=faces,
                preview_material={
                    "base_color_rgb":color,"roughness":.6,
                    "metallic":0.04})
            metadata=cls.kit.publish_module(
                cls.pid,name,asset_id=asset,asset_revision=1,
                role=role,style_family="UrbanFilm",
                size_m=dims,sockets=sockets,director_event=cls.approval)
            cls.catalog[name]={
                "asset":published,"module":metadata,
                "role":role,"size_m":dims,"sockets":sockets}
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_02m_a_real_native_mesh_dimensions_and_socket_source(self):
        floor=self.kit.module(self.pid,"ModuleFloor",1)
        self.assertEqual(floor["size_m"],[12.0,10.0,.4])
        self.assertEqual(floor["coordinate_system"],"meters_Z_up")
        self.assertEqual(len(floor["sockets"]),4)
        self.assertTrue(floor["source_mesh_real"])
        self.assertFalse(floor["cycles_pixels_reviewed"])
        self.assertEqual(floor["asset_document_sha256"],
                         self.catalog["ModuleFloor"]["asset"][
                             "document_sha256"])
        self.assertEqual(_rotate([1,0,5],90),[0,1,5])
        self.assertEqual(_bbox([12,10,.4],[0,0,0],0),
                         [[-6.,-5.,-.2],[6.,5.,.2]])

    def test_02m_b_four_deterministic_buildings_reopen_3d_source(self):
        mapping={}
        for seed in range(150):
            recipe=building_recipe(0,self.facades)
            choices,_=self.kit._resolve(self.pid,seed,recipe)
            identity=choices[1]["module_id"]
            mapping.setdefault(identity,seed)
            if len(mapping)==4:
                break
        self.assertEqual(len(mapping),4,"Seeds must select four genuinely distinct facades")
        common_rear=None
        building_records=[]
        for i,(facade,seed) in enumerate(mapping.items()):
            blueprint=building_recipe(i*30,self.facades)
            bid="Building_"+str(i+1)
            saved=self.kit.publish_building(
                self.pid,bid,seed=seed,
                blueprint=blueprint,director_event=self.approval)
            building_records.append(saved)
            with self.kit.open_building(self.pid,bid,1) as result:
                doc=result["building"]
                self.assertEqual(doc["format"],BUILD_FORMAT)
                self.assertEqual(doc["module_count"],10)
                self.assertEqual(result["mesh_count"],10)
                self.assertEqual(len(result["referenced_modules"]),10)
                self.assertEqual(doc["placements"][1]["module_id"],facade)
                self.assertFalse(doc["renderer_pixels_verified"])
                self.assertFalse(doc["source_geometry_quality_accepted"])
                self.assertTrue(result["original_source_meshes_reopened"])
                rear=next(p for p in doc["placements"]
                          if p["node_id"]=="Rear")["module_document_sha256"]
                if common_rear is None:common_rear=rear
                else:self.assertEqual(rear,common_rear)
                stage=result["stage"]
                self.assertEqual(UsdGeom.GetStageUpAxis(stage),"Z")
                self.assertAlmostEqual(
                    UsdGeom.GetStageMetersPerUnit(stage),1.0)
                for piece in ("Front","Rear","SideLeft","SideRight","Roof"):
                    path="/World/Buildings/"+piece+"/Geometry"
                    self.assertTrue(stage.GetPrimAtPath(path).IsA(
                        UsdGeom.Mesh))
                front=doc["placements"][1]
                roof=doc["placements"][-1]
                self.assertGreater(front["world_bounds_m"][0][1],
                    doc["placements"][0]["world_bounds_m"][0][1]-1)
                self.assertAlmostEqual(
                    roof["world_bounds_m"][0][2],6.,places=4)
                self.assertEqual(
                    result["root_layer_sha256"],
                    doc["original_usd_root_sha256"])
        self.assertEqual(len({x["document_sha256"] for x in
                              building_records}),4)

    def test_02m_b_source_revisions_do_not_rewrite_previous_buildings(self):
        seed=12
        first=self.kit.publish_building(
            self.pid,"RevisionedFilmBuilding",seed=seed,
            blueprint=building_recipe(0,self.facades),
            director_event=self.approval)
        second=self.kit.publish_building(
            self.pid,"RevisionedFilmBuilding",seed=seed+1,
            blueprint=building_recipe(35,self.facades),
            expected_revision=1,director_event=self.approval)
        self.assertEqual(first["revision"],1)
        self.assertEqual(second["revision"],2)
        with self.kit.open_building(self.pid,"RevisionedFilmBuilding",1) as old:
            self.assertEqual(old["building"]["blueprint"][0][
                "root_position_m"],[0,0,0])
            self.assertEqual(old["record"]["document_sha256"],
                             first["document_sha256"])
        with self.kit.open_building(self.pid,"RevisionedFilmBuilding",2) as new:
            self.assertEqual(new["building"]["blueprint"][0][
                "root_position_m"],[35,0,0])
            self.assertEqual(new["record"]["document_sha256"],
                             second["document_sha256"])

    def test_02m_invalid_geometry_orientation_span_auth_denied(self):
        recipe=building_recipe(0,self.facades)
        invalid=deepcopy(recipe)
        invalid[1]["yaw_deg"]=90
        with self.assertRaises(ValueError):
            self.kit._resolve(self.pid,3,invalid)
        invalid=deepcopy(recipe)
        invalid[-1]["own_socket"]="NotARoofConnector"
        with self.assertRaises(PermissionError):
            self.kit._resolve(self.pid,3,invalid)
        invalid=deepcopy(recipe)
        invalid[1]["options"]=[
            {"module_id":"ModuleRoof","revision":1},
            {"module_id":"ModuleFacadeRed","revision":1}]
        with self.assertRaises(ValueError):
            self.kit._resolve(self.pid,3,invalid)
        invalid=deepcopy(recipe)
        invalid[1]["node_id"]="../InvalidUSDPrim"
        with self.assertRaises(ValueError):
            self.kit._resolve(self.pid,3,invalid)
        denied=OriginalBuildingKit(self.index,
            verify_director_action=lambda *_:False)
        with self.assertRaises(PermissionError):
            denied.publish_building(self.pid,"DeniedArchitecture",
                seed=0,blueprint=recipe,director_event="fake-permission")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DeniedArchitecture",1)

    def test_02m_real_native_blender_three_view_reverse_oblique_smoke(self):
        import os
        import sys
        import shutil
        import subprocess
        import json
        from PIL import Image
        from backend.nvp_blender_worker import (
            BlenderOperation,BlenderWorkerSupervisor,sha_file)
        executable=os.environ.get("NVP_FILM02M_BLENDER_BIN")
        if not executable:
            self.skipTest("Actual Blender 5.2 native front/rear/oblique pixels required")
        binary=Path(executable).resolve(strict=True)
        version=subprocess.run(
            [str(binary),"-b","--version"],
            check=True,capture_output=True,text=True,timeout=30
        ).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        building="NativeReviewBuilding"
        saved=self.kit.publish_building(
            self.pid,building,
            seed=0,blueprint=building_recipe(0,self.facades),
            director_event=self.approval)
        workspace=self.root/"02m_protected_native_jobs"
        runner=BlenderWorkerSupervisor(
            workspace,blender_executable=binary,
            blender_sha256=sha_file(binary),blender_version=version)
        script=Path(__file__).resolve().parents[1]/"tools"/(
            "nvp_usd_film02m_blender_three_views.py")
        job=workspace/"Film02MThreeViews"
        job.mkdir(mode=0o700,parents=True)
        shutil.copyfile(script,job/script.name)
        with self.kit.open_building(self.pid,building,1) as opened:
            stage=Path(opened["stage"].GetRootLayer().realPath)
            self.assertEqual(sha_file(stage),
                             opened["building"]["original_usd_root_sha256"])
            shutil.copyfile(stage,job/"building.usda")
            shutil.copytree(stage.parent/"assets",job/"assets")
            references={}
            for item in opened["building"]["placements"]:
                sha=item["source_layer_sha256"]
                references[sha]=sha
            self.assertEqual(len(references),
                             len(list((job/"assets").glob("*.usda"))))
            manifest={
                "format":"nvp.usd_film02m.cycles_three_angle_request.v1",
                "building_source_format":BUILD_FORMAT,
                "source_building_sha256":saved["document_sha256"],
                "usd_root_sha256":sha_file(job/"building.usda"),
                "assets":references,"expected_modules":10,
                "camera_views":["front","rear","oblique"]}
        (job/"manifest.json").write_text(json.dumps(
            manifest,sort_keys=True,separators=(",",":")),"utf8")
        inputs={"building.usda":sha_file(job/"building.usda"),
                "manifest.json":sha_file(job/"manifest.json")}
        for path in (job/"assets").glob("*.usda"):
            inputs["assets/"+path.name]=sha_file(path)
        inputs[script.name]=sha_file(job/script.name)
        op=BlenderOperation(
            job_id="Film02MThreeViews",
            script=script.name,script_sha256=sha_file(job/script.name),
            inputs=inputs,
            outputs={
                "film02m_front.png":"png",
                "film02m_rear.png":"png",
                "film02m_oblique.png":"png",
                "audit.json":"json_audit"},
            arguments={"--manifest":"manifest.json","--audit":"audit.json"},
            timeout_seconds=600,memory_limit_mb=6144,
            require_linux_cgroup_v2=False)
        result=runner.run(op)
        self.assertEqual(result["state"],"SUCCEEDED")
        self.assertEqual(runner.verify_completed(
            "Film02MThreeViews")["state"],"SUCCEEDED")
        audit=json.loads((job/"audit.json").read_text("utf8"))
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["source_building_sha256"],
                         saved["document_sha256"])
        self.assertEqual(audit["actual_original_native_meshes"],10)
        self.assertGreaterEqual(audit["actual_original_native_faces"],120)
        self.assertEqual(
            [x["view"] for x in audit["rendered_views"]],
            ["front","rear","oblique"])
        self.assertFalse(audit["director_visual_quality_reviewed"])
        hashes=set()
        for view in ("front","rear","oblique"):
            image=job/("film02m_"+view+".png")
            with Image.open(image) as png:
                self.assertEqual(png.format,"PNG")
                self.assertEqual(png.size,(320,180))
                png.verify()
            hashes.add(sha_file(image))
        self.assertEqual(len(hashes),3)
        destination=Path(os.environ.get(
            "NVP_FILM02M_ARTIFACT_DIR",
            str(self.root/"02m_native_three_view_evidence"))).resolve()
        destination.mkdir(parents=True,exist_ok=True)
        for name in ("film02m_front.png","film02m_rear.png",
                     "film02m_oblique.png","audit.json","manifest.json",
                     "building.usda"):
            shutil.copyfile(job/name,destination/name)
        (destination/"native_view_status.json").write_text(json.dumps({
            "real_original_building_meshes":10,
            "authentic_blender_cycles_views":3,
            "different_front_rear_oblique_images":True,
            "camera_visible_rear_and_roof_meshes_preserved":True,
            "original_building_source_unchanged":True,
            "director_visual_quality_reviewed":False},
            sort_keys=True,indent=2),"utf8")

    def _02m_d_original_building(self,tag,origin,seed,treatment):
        from backend.nvp_usd_film02m_d_openings import (
            facade_layout,publish_facade_with_detail,
            publish_room_with_detail)
        layout=facade_layout(
            width_m=12,height_m=6,stories=2,bays=3,
            treatment=treatment,seed=seed)
        facade=publish_facade_with_detail(
            self.index,self.pid,"AssetFacadeD"+tag,
            "DetailFacadeD"+tag,layout=layout,
            thickness_m=.4,color_rgb=[.65,.38,.22])
        published_facade=self.kit.publish_module(
            self.pid,"ModuleFacadeD"+tag,
            asset_id="AssetFacadeD"+tag,asset_revision=1,
            role="facade",style_family="UrbanFilm",
            size_m=[12,.4,6],
            sockets=self.catalog["ModuleFacadeRed"]["sockets"],
            geometry_detail_id="DetailFacadeD"+tag,
            geometry_detail_revision=1,
            director_event=self.approval)
        # Reuse the EXACT original floor mesh revision and only extend
        # its director-authored floor socket metadata for the 3D room.
        floor_sockets=list(self.catalog["ModuleFloor"]["sockets"])
        floor_sockets.append(
            sock("RoomMount",[0,0,.2],[0,0,1],4,"room_floor"))
        floor=self.kit.publish_module(
            self.pid,"ModuleFloorD"+tag,
            asset_id="AssetModuleFloor",asset_revision=1,
            role="floor",style_family="UrbanFilm",
            size_m=[12,10,.4],sockets=floor_sockets,
            director_event=self.approval)
        room=publish_room_with_detail(
            self.index,self.pid,"AssetInteriorD"+tag,
            "DetailInteriorD"+tag,
            width_m=11,depth_m=9,height_m=5.2,
            wall_thickness_m=.08,
            color_rgb=[.82,.78,.69])
        interior=self.kit.publish_module(
            self.pid,"ModuleInteriorD"+tag,
            asset_id="AssetInteriorD"+tag,asset_revision=1,
            role="interior",style_family="UrbanFilm",
            size_m=[11,9,5.2],
            sockets=[sock("Base",[0,0,-2.6],
                          [0,0,-1],4,"room_floor")],
            geometry_detail_id="DetailInteriorD"+tag,
            geometry_detail_revision=1,
            director_event=self.approval)
        recipe=building_recipe(origin,["ModuleFacadeD"+tag])
        recipe[0]["options"]=[{
            "module_id":"ModuleFloorD"+tag,"revision":1}]
        recipe.append(node(
            "Interior","ModuleInteriorD"+tag,
            parent="Floor",attached="RoomMount",own="Base"))
        building_id="BuildingSourceD"+tag
        building=self.kit.publish_building(
            self.pid,building_id,seed=seed,
            blueprint=recipe,director_event=self.approval)
        return {
            "id":building_id,"revision":1,
            "building":building,"layout":layout,
            "facade":facade,"room":room,
            "facade_module":published_facade,
            "room_module":interior,"floor_module":floor}

    def test_02m_d_actual_opening_surface_geometry_and_story_variants(self):
        from backend.nvp_usd_film02m_d_openings import (
            facade_layout,apertured_wall_mesh,
            prove_facade_geometry,original_through_opening,
            room_shell_mesh)
        for treatment in ("residential","shopfront","industrial"):
            layout=facade_layout(
                width_m=12,height_m=6,stories=2,bays=3,
                treatment=treatment,seed=125)
            self.assertEqual(len(layout["openings"]),6)
            self.assertEqual(
                len([x for x in layout["openings"]
                     if x["kind"]=="door"]),1)
            mesh=apertured_wall_mesh(
                12,.4,6,layout["openings"])
            proof=prove_facade_geometry(mesh)
            self.assertTrue(proof["all_source_openings_ray_verified"])
            self.assertTrue(mesh["real_jambs_and_wall_thickness"])
            self.assertGreater(len(mesh["triangles"]),60)
            self.assertFalse(original_through_opening(
                mesh["points"],mesh["triangles"],
                -5.94,0,.4))
            for opening in mesh["openings"]:
                x=opening["x_center_m"]
                z=opening["bottom_m"]+opening["height_m"]/2
                self.assertTrue(original_through_opening(
                    mesh["points"],mesh["triangles"],x,z,.4))
            if treatment=="shopfront":
                self.assertGreater(
                    len([x for x in layout["openings"]
                         if x["kind"]=="storefront"]),0)
        height=9.
        tall=facade_layout(
            width_m=12,height_m=height,stories=3,bays=4,
            treatment="residential",seed=71)
        self.assertEqual(len(tall["openings"]),12)
        mesh=apertured_wall_mesh(12,.4,height,tall["openings"])
        self.assertTrue(prove_facade_geometry(mesh)[
            "all_source_openings_ray_verified"])
        room=room_shell_mesh(11,9,5.2,.08)
        self.assertTrue(room["front_portal_open"])
        self.assertTrue(room["rear_wall_is_real_geometry"])
        self.assertFalse(original_through_opening(
            room["points"],room["triangles"],0,0,9))
        # No source PBR opacity map can create this aperture; the
        # actual source indexed triangle faces leave a real void.

    def test_02m_d_source_asset_module_and_interior_continuity(self):
        from backend.nvp_usd_film02m_d_openings import (
            original_through_opening,verify_detail)
        result=self._02m_d_original_building(
            "Continuity",0,18,"shopfront")
        source=verify_detail(
            self.index,self.pid,"DetailFacadeDContinuity",1,
            asset_id="AssetFacadeDContinuity",asset_revision=1,
            required_kind="wall_with_real_apertures")
        self.assertTrue(source["data"][
            "through_wall_rays_independently_verified"])
        self.assertFalse(source["data"]["native_cycles_pixels_verified"])
        with self.kit.open_building(
                self.pid,result["id"],1) as world:
            self.assertEqual(world["mesh_count"],11)
            self.assertEqual(world["building"]["module_count"],11)
            stage=world["stage"]
            facade=UsdGeom.Mesh(stage.GetPrimAtPath(
                "/World/Buildings/Front/Geometry"))
            room=UsdGeom.Mesh(stage.GetPrimAtPath(
                "/World/Buildings/Interior/Geometry"))
            self.assertTrue(facade)
            self.assertTrue(room)
            points=[[float(v[i]) for i in range(3)]
                    for v in facade.GetPointsAttr().Get()]
            counts=list(facade.GetFaceVertexCountsAttr().Get())
            inds=list(facade.GetFaceVertexIndicesAttr().Get())
            self.assertTrue(all(n==3 for n in counts))
            triangles=[inds[i:i+3] for i in range(0,len(inds),3)]
            entrance=next(x for x in result["layout"]["openings"]
                          if x["kind"]=="door")
            sight_x=entrance["x_center_m"]
            sight_z=entrance["bottom_m"]+entrance["height_m"]*.5
            self.assertTrue(original_through_opening(
                points,triangles,sight_x,sight_z,.4))
            room_verts=[[float(v[i]) for i in range(3)]
                        for v in room.GetPointsAttr().Get()]
            room_ids=list(room.GetFaceVertexIndicesAttr().Get())
            room_faces=[room_ids[i:i+3]
                        for i in range(0,len(room_ids),3)]
            # Convert from original facade-local Z to original
            # interior-local Z: 3.0m facade centre versus 2.8m room
            # centre (actual attached authored floor/socket transforms).
            self.assertFalse(original_through_opening(
                room_verts,room_faces,sight_x,
                sight_z+3.-2.8,9.))
            placements=world["building"]["placements"]
            floor=next(p for p in placements if p["node_id"]=="Floor")
            inside=next(p for p in placements if p["node_id"]=="Interior")
            self.assertTrue(inside["connector_fit"])
            self.assertEqual(inside["parent_id"],"Floor")
            self.assertGreater(
                inside["world_bounds_m"][1][2],
                floor["world_bounds_m"][1][2]+4)
            self.assertEqual(world["building"][
                "original_actors_untouched"],True)

    def test_02m_d_published_cells_hysteresis_required_interiors(self):
        from backend.nvp_usd_film02m_d_cells import (
            OriginalBuildingCells,FORMAT)
        kit=OriginalBuildingCells(
            self.index,verify_director_action=lambda event,scope:
                event==self.approval and
                scope.get("operation")==
                    "nvp.film02m.publish_original_building_cells.v1" and
                len(scope.get("source_cell_manifest_sha256",""))==64)
        choices=[]
        for i,(tag,design) in enumerate(
                (("West","residential"),
                 ("Middle","shopfront"),
                 ("East","industrial"))):
            building=self._02m_d_original_building(
                tag,origin=i*30,seed=8+i,treatment=design)
            choices.append({
                "cell_id":"Cell"+tag,
                "building_id":building["id"],
                "building_revision":1})
        receipt=kit.publish(
            self.pid,"OriginalCitySourceCellsD",
            cells=choices,director_event=self.approval)
        self.assertEqual(receipt["revision"],1)
        with kit.open(self.pid,"OriginalCitySourceCellsD",1) as session:
            stage=session.stage
            self.assertEqual(UsdGeom.GetStageUpAxis(stage),"Z")
            self.assertEqual(sorted(session.original),
                             ["CellEast","CellMiddle","CellWest"])
            self.assertFalse(stage.GetPrimAtPath(
                "/World/Cells/CellMiddle").IsLoaded())
            near=session.transition(
                camera_positions_m=[[0,-12,2]],
                required_cell_ids=["CellWest"],
                next_shot_required_cell_ids=["CellMiddle"],
                load_distance_m=10,unload_distance_m=25,
                max_loaded_cells=2)
            self.assertEqual(near["loaded_cell_ids"],
                             ["CellMiddle","CellWest"])
            self.assertTrue(near["native_usd_payload_load_verified"])
            self.assertEqual(
                {row["native_meshes_reopened"] for row in near[
                    "source_original_building_mesh_receipts"]},{11})
            self.assertFalse(stage.GetPrimAtPath(
                "/World/Cells/CellEast").IsLoaded())
            # Director-required cells stay loaded even when the
            # camera crosses the unload threshold to the far set.
            far=session.transition(
                camera_positions_m=[[90,-12,2]],
                required_cell_ids=["CellWest"],
                next_shot_required_cell_ids=["CellEast"],
                load_distance_m=10,unload_distance_m=25,
                max_loaded_cells=2)
            self.assertEqual(far["loaded_cell_ids"],
                             ["CellEast","CellWest"])
            self.assertIn("CellMiddle",far["newly_unloaded"])
            self.assertTrue(far["director_required_geometry_retained"])
            with self.assertRaises(MemoryError):
                session.transition(
                    camera_positions_m=[[30,0,2]],
                    required_cell_ids=["CellWest","CellMiddle"],
                    next_shot_required_cell_ids=["CellEast"],
                    load_distance_m=10,unload_distance_m=25,
                    max_loaded_cells=2)
            self.assertEqual(sorted(session.loaded),
                             ["CellEast","CellWest"])
            # The on-disk original source manifest is unchanged by
            # all temporary streaming/prefetch choices.
            self.assertEqual(self.index.read_revision(
                self.pid,"OriginalCitySourceCellsD",1)[
                "document_sha256"],receipt["document_sha256"])
        with self.assertRaises(PermissionError):
            denied=OriginalBuildingCells(
                self.index,verify_director_action=lambda *_:False)
            denied.publish(
                self.pid,"DeniedCellsD",cells=choices,
                director_event="fake")

    def test_02m_original_geometry_collision_rejected(self):
        original=building_recipe(0,self.facades)
        overlapping=deepcopy(original)
        overlapping[2]["parent_socket"]="Front"
        overlapping[2]["own_socket"]="Front"
        # Wrong connector attachment is never silently moved or blended.
        with self.assertRaises((ValueError,PermissionError)):
            self.kit._resolve(self.pid,0,overlapping)


if __name__=="__main__":
    unittest.main()
