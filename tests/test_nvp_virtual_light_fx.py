"""V-LIGHT artistic cheats must be deterministic, optional and source-safe."""
import unittest
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_virtual_light_fx import (
    make_simple_virtual_fx,evaluate_virtual_light_fx,captured_light_fx,FORMAT)


class VirtualLightFXTest(unittest.TestCase):
    def test_virtual_silver_gold_bounce_requires_no_physical_board(self):
        for kind in ("silver_fill","gold_fill"):
            light=make_simple_virtual_fx(kind,"/World/Face",fx_id="face_fill")
            out=evaluate_virtual_light_fx(light,27*T,final_render=True)
            self.assertEqual(out["format"],FORMAT)
            self.assertTrue(out["cinematic_artistic_cheat"])
            self.assertFalse(out["physical_bounce_reflector_required"])
            self.assertFalse(out["usd_light_or_renderer_change_applied"])
            self.assertFalse(out["dci_render_or_photometric_accuracy_proven"])
            self.assertFalse(out["original_source_modified"])
        self.assertGreater(
            evaluate_virtual_light_fx(make_simple_virtual_fx(
                "gold_fill","/World/Face",fx_id="gold"),0)[
                    "evaluated_color_rgb"][0],
            evaluate_virtual_light_fx(make_simple_virtual_fx(
                "gold_fill","/World/Face",fx_id="gold"),0)[
                    "evaluated_color_rgb"][2])

    def test_summer_3pm_sun_never_moves_when_story_time_changes(self):
        sun=make_simple_virtual_fx(
            "locked_summer_3pm_sun","/World/Set",fx_id="fixed_sun",
            azimuth=237,elevation=48)
        a=evaluate_virtual_light_fx(sun,0,final_render=True)
        b=evaluate_virtual_light_fx(sun,30*T,final_render=True)
        for key in ("sun_azimuth_deg","sun_elevation_deg",
                    "evaluated_color_rgb","evaluated_intensity","fx_decision_sha256"):
            self.assertEqual(a[key],b[key])
        self.assertEqual(a["sun_azimuth_deg"],237)
        self.assertEqual(a["sun_elevation_deg"],48)

    def test_independent_cop_lights_capture_phase_and_replay_after_restart(self):
        fx=make_simple_virtual_fx(
            "police_red_blue","/World/PoliceRig",fx_id="flasher",
            clock_mode="independent_live",anchor_monotonic_ns=10_000_000_000,
            frequency_hz=2)
        with self.assertRaises(PermissionError):
            evaluate_virtual_light_fx(fx,0,monotonic_ns=10_250_000_000,
                                      final_render=True)
        prior=evaluate_virtual_light_fx(
            fx,0,monotonic_ns=10_250_000_000,final_render=False)
        saved=captured_light_fx(
            fx,film_tick=5*T,monotonic_ns=10_250_000_000)
        replay=evaluate_virtual_light_fx(saved,5*T,final_render=True)
        self.assertEqual(prior["evaluated_color_rgb"],replay["evaluated_color_rgb"])
        self.assertEqual(prior["evaluated_intensity"],replay["evaluated_intensity"])
        self.assertEqual(replay,evaluate_virtual_light_fx(saved,5*T,final_render=True))
        self.assertNotEqual(replay["evaluated_color_rgb"],
            evaluate_virtual_light_fx(saved,5*T+T//4,final_render=True)[
                "evaluated_color_rgb"])

    def test_fireworks_deterministic_without_wall_time_and_invalid_fx_rejected(self):
        fx=make_simple_virtual_fx(
            "firework_flash","/World/Firework",fx_id="burst",
            frequency_hz=1,intensity=500,decay_seconds=0.15,seed=42)
        first=evaluate_virtual_light_fx(fx,0,final_render=True)
        half=evaluate_virtual_light_fx(fx,T//2,final_render=True)
        self.assertGreater(first["evaluated_intensity"],half["evaluated_intensity"])
        self.assertEqual(first,evaluate_virtual_light_fx(fx,0,final_render=True))
        started_later={**fx,"anchor_film_tick":T}
        self.assertEqual(
            evaluate_virtual_light_fx(started_later,0,final_render=True)[
                "evaluated_intensity"],0.0)
        one_shot=make_simple_virtual_fx(
            "firework_flash","/World/Firework",fx_id="no_cycle",
            anchor_film_tick=T,intensity=100)
        self.assertGreater(
            evaluate_virtual_light_fx(one_shot,T,final_render=True)[
                "evaluated_intensity"],0.0)
        for change in (
            {"intensity":float("nan")},
            {"color_rgb":[1,2]},
            {"clock_mode":"not-a-clock"},
            {"frequency_hz":-2},
            {"target_path":"file:///private/key"},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                evaluate_virtual_light_fx({**fx,**change},0,final_render=True)


if __name__=="__main__":
    unittest.main()
