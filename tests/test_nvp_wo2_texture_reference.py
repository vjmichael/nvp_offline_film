"""WO2 deterministic native source-texture UV reference before GPU acceptance.

Independent tiny canonical 2x2 linear RGB fixture verifies perspective
coordinates, top-left PNG row order, bottom-origin USD st, and repeat
boundary. The actual native WebGL hardware pixel comparison is separate.
"""
import unittest
import numpy as np

from backend.nvp_native_scene_linear_raster import (
    _draw_triangle,_shade,_shade_texture_texels,WIDTH,HEIGHT)


class WO2NativeTextureReference(unittest.TestCase):
    def test_native_source_uv_corner_colors_and_repeat(self):
        # Input texel array in Pillow/PNG top-left row order:
        # green white / red blue. USD UV (0,0) must sample bottom-left red.
        tex=np.array([
            [[0.,1.,0.],[1.,1.,1.]],
            [[1.,0.,0.],[0.,0.,1.]],
        ],dtype=np.float32)
        rgba=np.zeros((HEIGHT,WIDTH,4),dtype=np.float32)
        depth=np.full((HEIGHT,WIDTH),np.inf,dtype=np.float32)
        rgba[:,:,3]=1
        screen=[(0.,0.,2.),(10.,0.,2.),(0.,10.,2.)]
        world=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
        uv=[[0.,0.],[1.,0.],[0.,1.]]
        drawn=_draw_triangle(
            rgba,depth,screen,world,
            ((1.,1.,1.),.8,0.,False),[],(0.,0.,5.),np,
            texture=tex,uv_face=uv)
        self.assertTrue(drawn)
        self.assertGreater(float(rgba[1,1,0]),0.)
        self.assertEqual(float(rgba[1,1,1]),0.)
        self.assertEqual(float(rgba[1,1,2]),0.)
        self.assertGreater(float(rgba[1,7,2]),0.)
        self.assertEqual(float(rgba[1,7,0]),0.)
        self.assertEqual(float(rgba[1,7,1]),0.)
        self.assertEqual(float(rgba[100,100,0]),0.)

    def test_source_texels_enter_reflectance_before_ggx_lighting(self):
        points=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
        material=((.8,.6,.4),.35,.2,False)
        lights=[((0.5,0.5,3.),2000.)]
        eye=(0.5,0.5,5.)
        expected=_shade(points,material,lights,eye)
        white=np.ones((2,2,3),dtype=np.float32)
        observed=_shade_texture_texels(
            points,material,lights,eye,white,np)
        self.assertTrue(np.allclose(
            observed,np.asarray(expected),rtol=1e-5,atol=1e-5))
        # Zero diffuse green/blue still reflects a dielectric specular lobe.
        dielectric=((1.,1.,1.),.3,0.,False)
        red=np.zeros((1,1,3),dtype=np.float32)
        red[:,:,0]=1.
        lit=_shade_texture_texels(points,dielectric,lights,eye,red,np)
        self.assertGreater(float(lit[0,0,1]),0.)
        self.assertGreater(float(lit[0,0,2]),0.)
        self.assertGreater(float(lit[0,0,0]),float(lit[0,0,1]))

    def test_source_texture_cannot_render_without_authoritative_uv(self):
        rgba=np.zeros((HEIGHT,WIDTH,4),dtype=np.float32)
        depth=np.full((HEIGHT,WIDTH),np.inf,dtype=np.float32)
        with self.assertRaises(RuntimeError):
            _draw_triangle(
                rgba,depth,[(0.,0.,2.),(10.,0.,2.),(0.,10.,2.)],
                [(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)],
                ((1.,1.,1.),.8,0.,False),[],(0.,0.,5.),np,
                texture=np.ones((2,2,3),dtype=np.float32),
                uv_face=None)


if __name__=="__main__":
    unittest.main()
