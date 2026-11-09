"""Contract-only source-object camera-ray masking tests, no Blender pixels."""
import unittest
from tools.nvp_usd_film01m_camera_ray_mask import (
    per_camera_primary_ray_exclusions, source_geometry_roots)

class Object:
    def __init__(self,name,obj_type="EMPTY",parent=None):
        self.name=name
        self.type=obj_type
        self.parent=parent
        self.children=[]
        self.visible_camera=True
        self.visible_shadow=True
        self.visible_glossy=True
        self.visible_diffuse=True
        if parent is not None:
            parent.children.append(self)

    @property
    def children_recursive(self):
        out=[]
        for child in self.children:
            out.append(child)
            out.extend(child.children_recursive)
        return out

class DirectorCameraMaskContract(unittest.TestCase):
    def setUp(self):
        world=Object("World")
        sets=Object("Sets",parent=world)
        self.set=Object("Stage",parent=sets)
        self.wall=Object("Wall",parent=self.set)
        self.wallmesh=Object("Geometry","MESH",parent=self.wall)
        self.donut=Object("Donut",parent=self.set)
        self.actormesh=Object("Geometry","MESH",parent=self.donut)
        self.cameras=Object("NVPDirectorCameraRig",parent=world)
        self.cam=Object("ReverseCamera","CAMERA",parent=self.cameras)
        self.objects=[
            world,sets,self.set,self.wall,self.wallmesh,
            self.donut,self.actormesh,self.cameras,self.cam]

    def test_wall_primary_ray_only_and_restored_before_second_camera(self):
        self.assertIs(source_geometry_roots(
            self.objects,["/World/Sets/Stage/Wall"])[0],self.wall)
        with per_camera_primary_ray_exclusions(
                self.objects,["/World/Sets/Stage/Wall"]) as report:
            self.assertEqual(report["masked_mesh_object_count"],1)
            self.assertFalse(self.wallmesh.visible_camera)
            self.assertTrue(self.wallmesh.visible_shadow)
            self.assertTrue(self.wallmesh.visible_glossy)
            self.assertTrue(self.wallmesh.visible_diffuse)
            self.assertTrue(self.actormesh.visible_camera)
            self.assertTrue(self.cam.visible_camera)
        self.assertTrue(self.wallmesh.visible_camera)
        with per_camera_primary_ray_exclusions(self.objects,[]):
            self.assertTrue(self.wallmesh.visible_camera)

    def test_ray_mask_reverts_on_native_render_failure(self):
        with self.assertRaises(RuntimeError):
            with per_camera_primary_ray_exclusions(
                    self.objects,["/World/Sets/Stage/Wall"]):
                self.assertFalse(self.wallmesh.visible_camera)
                raise RuntimeError("Actual native render crashed")
        self.assertTrue(self.wallmesh.visible_camera)

    def test_non_source_and_ambiguous_wall_refused(self):
        with self.assertRaises(RuntimeError):
            source_geometry_roots(self.objects,["/World/Sets/Stage/FakeWall"])
        duplicate=Object("Wall",parent=self.set)
        self.objects.append(duplicate)
        with self.assertRaises(RuntimeError):
            source_geometry_roots(self.objects,["/World/Sets/Stage/Wall"])

    def test_does_not_guess_ambiguous_blender_leaf_only(self):
        orphan=Object("Wall")
        with self.assertRaises(RuntimeError):
            source_geometry_roots([orphan],["/World/Sets/Stage/Wall"])

if __name__=="__main__":
    unittest.main()
