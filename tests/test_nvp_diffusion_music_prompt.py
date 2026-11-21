import json
import unittest
from backend.nvp_diffusion_music_prompt import (
    compose_diffusion_prompt, freeze_diffusion_conditioning, NO_BACKGROUND_MUSIC_LINE)


class MusicPrompt(unittest.TestCase):
    def setUp(self):
        self.prompt = 'A rainy city at dusk with cinematic lighting.'

    def test_selected_adds_exact_new_line(self):
        self.assertEqual(compose_diffusion_prompt(self.prompt, no_background_music=True),
                         self.prompt + '\n' + NO_BACKGROUND_MUSIC_LINE)

    def test_disabled_preserves_existing_prompt(self):
        self.assertEqual(compose_diffusion_prompt(self.prompt, no_background_music=False),self.prompt)

    def test_idempotent_and_honors_existing_directive(self):
        text=self.prompt+'\nNo background music.'
        self.assertEqual(compose_diffusion_prompt(text, no_background_music=True), text)

    def test_invalid_bool_and_unbounded_prompt_refused(self):
        for switch in (None, 1, 'true', 0):
            with self.subTest(switch=switch), self.assertRaises(ValueError):
                compose_diffusion_prompt(self.prompt, no_background_music=switch)
        with self.assertRaises(ValueError):
            compose_diffusion_prompt('a'*497, no_background_music=True)
        with self.assertRaises(ValueError):
            compose_diffusion_prompt('rain\r\nnoise', no_background_music=True)
        with self.assertRaises(ValueError):
            compose_diffusion_prompt('a\x00bxxxxxx', no_background_music=False)

    def test_freeze_stores_flag_under_reviewed_source_hash(self):
        data,digest=freeze_diffusion_conditioning(positive_prompt=self.prompt,
            take_sha256='a'*64,camera_id='cam01',no_background_music=True)
        self.assertTrue(json.loads(data)['no_background_music'])
        self.assertEqual(len(digest),64)
        off,other=freeze_diffusion_conditioning(positive_prompt=self.prompt,
            take_sha256='a'*64,camera_id='cam01',no_background_music=False)
        self.assertNotEqual(other,digest)
        self.assertFalse(json.loads(off)['no_background_music'])

    def test_invalid_take_or_camera_refused(self):
        for take,cam in [('bad','cam01'),('a'*64,'../bad')]:
            with self.assertRaises(ValueError):
                freeze_diffusion_conditioning(positive_prompt=self.prompt,
                    take_sha256=take,camera_id=cam,no_background_music=True)


if __name__=='__main__': unittest.main()
