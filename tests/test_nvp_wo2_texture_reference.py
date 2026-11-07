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

    def test_binary_cutout_does_not_write_depth_or_color_on_masked_pixels(self):
        pixels=np.zeros((HEIGHT,WIDTH,4),dtype=np.float32)
        depth=np.full((HEIGHT,WIDTH),np.inf,dtype=np.float32)
        white=np.ones((2,2,3),dtype=np.float32)
        cutout=np.array([
            [[0.,0.,0.],[1.,1.,1.]],
            [[0.,0.,0.],[1.,1.,1.]],
        ],dtype=np.float32)
        result=_draw_triangle(
            pixels,depth,
            [(0.,0.,2.),(100.,0.,2.),(0.,100.,2.)],
            [(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)],
            ((1.,1.,1.),.5,0.,False),[],(0.,0.,5.),np,
            texture=white,uv_face=[[0,0],[1,0],[0,1]],
            pbr_maps={"opacity":cutout})
        self.assertTrue(result)
        self.assertTrue(np.isinf(depth[10,10]))
        self.assertEqual(float(pixels[10,10,0]),0.)
        self.assertTrue(np.isfinite(depth[10,60]))
        self.assertGreater(float(pixels[10,60,0]),0.)

    def test_source_maps_change_reflectance_and_emission_before_output(self):
        points=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
        surface=((.8,.7,.5),.5,.0,False)
        lights=[((0.,0.,5.),1500.)]
        eye=(0.,0.,5.)
        white=np.ones((2,2,3),dtype=np.float32)
        base=_shade_texture_texels(points,surface,lights,eye,white,np)
        bright=_shade_texture_texels(
            points,surface,lights,eye,white,np,
            emission_texels=np.ones_like(white))
        self.assertTrue(np.all(bright>base))
        matte=_shade_texture_texels(
            points,surface,lights,eye,white,np,
            roughness_texels=np.ones((2,2),dtype=np.float32))
        gloss=_shade_texture_texels(
            points,surface,lights,eye,white,np,
            roughness_texels=np.full((2,2),.1,dtype=np.float32))
        self.assertFalse(np.allclose(matte,gloss))
        normal=np.full((2,2,3),.5,dtype=np.float32)
        normal[:,:,2]=1.
        raised=_shade_texture_texels(
            points,surface,lights,eye,white,np,
            normal_texels=normal,
            uv_face=[[0,0],[1,0],[0,1]])
        self.assertTrue(np.all(np.isfinite(raised)))

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
