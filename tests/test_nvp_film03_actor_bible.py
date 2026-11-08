"""FILM03-02: real canonical ActorID + original asset/wardrobe/voice/script histories.

All records use the actual Studio, StoryBible, FilmIndex, immutable
OpenUSD source fixture and original PNG bytes, never fake source hashes.
Imported GLB catalog tests are separately exercised by their native suite.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_production_bible_actors import ProductionBibleActors, FORMAT
from backend.nvp_native_usd_texture import publish_texture
from tools.nvp_film01_original_30s import write_original_30s_source


SCRIPT_ONE = """INT. RELAY - NIGHT

DONUT
I hear something.

BOX
The systems are coming online.
"""
SCRIPT_TWO = SCRIPT_ONE.replace(
    "I hear something.", "The new script changes the line.")


class ActorIDSourceProductionBible(unittest.TestCase):
    def test_actorid_survives_rename_script_recast_asset_revisions_restart(self):
        with TemporaryDirectory() as d:
            src = Path(d).resolve() / "original"
            report = write_original_30s_source(src, approve_test_only=True)
            pid = report["project_id"]
            studio = Studio(src / "short.sqlite3")
            index = FilmIndex(studio)
            bible = StoryBible(studio)
            registry = ProductionBibleActors(studio)
            project = studio.save_screenplay(pid, SCRIPT_ONE, expected_revision=0)
            scene = project["scenes"][0]
            donut = bible.create_entity(pid, "character", "DONUT")
            box = bible.create_entity(pid, "character", "BOX")
            sphere = bible.create_entity(pid, "character", "SPHERE")
            costume = bible.create_entity(pid, "prop", "Copper Metallic Costume")
            costume_2 = bible.create_entity(pid, "prop", "Matte Gold Costume")
            self.assertEqual(donut["actor_id"], donut["id"])
            self.assertEqual(box["actor_id"], box["id"])
            self.assertEqual(sphere["actor_id"], sphere["id"])
            self.assertIsNone(costume["actor_id"])
            actor_id = donut["actor_id"]
            ro = registry.actor(pid, actor_id)
            self.assertEqual(ro["actor_id"], actor_id)
            self.assertEqual(ro["active_links"], [])
            self.assertTrue(ro["all_relations_versioned_not_destroyed"])

            # Existing scene and native USD mesh source links are real:
            # no fictional asset or unrelated project is accepted.
            ro = registry.link(
                pid, actor_id, role="scene", source_family="screenplay_scene",
                target_id=scene["id"], target_revision=project["revision"],
                expected_actor_revision=ro["bible_revision"],
                director_note="Original StoryBible screenplay scene")
            scene_link = ro["active_links"][0]
            self.assertEqual(scene_link["source_snapshot"]["scene_id"], scene["id"])
            self.assertEqual(scene_link["source_snapshot"]["screenplay_revision"], 1)
            ro = registry.link(
                pid, actor_id, role="model", source_family="filmindex",
                target_id="EngineerDonut", target_revision=1,
                expected_actor_revision=ro["bible_revision"],
                director_note="Original 504-vertex OpenUSD donut model")
            ro = registry.link(
                pid, actor_id, role="actor_prim", source_family="filmindex",
                target_id="RelayRekindleTake", target_revision=1,
                actor_prim_path="/World/Engineer",
                expected_actor_revision=ro["bible_revision"])
            ro = registry.link(
                pid, actor_id, role="wardrobe", source_family="bible_prop",
                target_id=costume["id"], target_revision=costume["revision"],
                expected_actor_revision=ro["bible_revision"],
                production_scope="scene:relay_first_costume")
            self.assertEqual(len(ro["active_links"]), 4)
            incomplete = registry.casting_coverage(pid, "RelayRekindleTake")
            self.assertFalse(incomplete["complete"])
            self.assertIn("/World/CrossingBox", incomplete["uncast_prim_paths"])
            self.assertEqual(incomplete["actor_id_by_prim"]["/World/Engineer"], actor_id)
            with self.assertRaises(RuntimeError):
                registry.require_complete_cast(pid, "RelayRekindleTake")
            wardrobe = next(l for l in ro["active_links"] if l["role"] == "wardrobe")
            self.assertEqual(wardrobe["source_snapshot"]["entity_id"], costume["id"])
            self.assertEqual(wardrobe["source_snapshot"]["kind"], "prop")
            self.assertEqual(wardrobe["link_revision"], 1)
            # Two wardrobe choices are distinct scene/costume states. Revising
            # one version never mutates the original wearable object source.
            ro = registry.link(
                pid, actor_id, role="wardrobe", source_family="bible_prop",
                target_id=costume_2["id"], target_revision=costume_2["revision"],
                expected_actor_revision=ro["bible_revision"],
                production_scope="scene:relay_rekindle")
            ro = registry.link(
                pid, actor_id, role="voice", source_family="filmindex",
                target_id="RelayRekindleRoomTone", target_revision=1,
                expected_actor_revision=ro["bible_revision"],
                director_note="Verified original PCM association; room tone is not spoken dialogue")
            self.assertEqual(len(ro["active_links"]), 6)
            self.assertEqual(len({x["link_id"] for x in ro["active_links"]}), 6)

            png = BytesIO()
            Image.new("RGB", (2, 2), (185, 118, 66)).save(png, "PNG")
            texture = publish_texture(index, pid, png.getvalue())
            ro = registry.link(
                pid, actor_id, role="texture", source_family="texture_blob",
                target_id=texture["sha256"], target_revision=1,
                expected_actor_revision=ro["bible_revision"])
            linked_texture = next(x for x in ro["active_links"] if x["role"] == "texture")
            self.assertEqual(linked_texture["source_sha256"], texture["sha256"])
            self.assertEqual(linked_texture["source_snapshot"]["pixel_width"], 2)

            # Actor ID remains the same when the character is renamed.
            current = bible.get_entity(pid, actor_id)
            renamed = bible.rename_entity(
                pid, actor_id, "ENGINEER DONUT", current["revision"])
            self.assertEqual(renamed["actor_id"], actor_id)
            self.assertIn("DONUT", renamed["aliases"])
            self.assertEqual(registry.actor(pid, actor_id)["actor_id"], actor_id)
            # Source screenplay changed. The old source link stays in history;
            # an old revision must NEVER be mistaken for a current scene.
            changed = studio.save_screenplay(pid, SCRIPT_TWO, expected_revision=1)
            self.assertEqual(changed["revision"], 2)
            before = registry.actor(pid, actor_id)
            original_scene = next(x for x in before["active_links"]
                                  if x["role"] == "scene")
            self.assertEqual(original_scene["target_revision"], 1)
            with self.assertRaises(RuntimeError):
                registry.link(
                    pid, actor_id, role="scene", source_family="screenplay_scene",
                    target_id=scene["id"], target_revision=1,
                    expected_actor_revision=before["bible_revision"])

            # Link revisions are append-only; director can point one old
            # wardrobe relationship at a new exact source and preserve both.
            prior = next(x for x in before["active_links"]
                         if x["link_id"] == wardrobe["link_id"])
            after = registry.link(
                pid, actor_id, role="wardrobe", source_family="bible_prop",
                target_id=costume_2["id"], target_revision=costume_2["revision"],
                expected_actor_revision=before["bible_revision"],
                production_scope="scene:updated_costume",
                director_note="Director chose the revised costume",
                link_id=wardrobe["link_id"],
                expected_link_revision=prior["link_revision"])
            current_wardrobe = next(
                x for x in after["active_links"]
                if x["link_id"] == wardrobe["link_id"])
            self.assertEqual(current_wardrobe["link_revision"], 2)
            old_wardrobe = [x for x in after["history"]
                            if x["link_id"] == wardrobe["link_id"] and
                            x["link_revision"] == 1][0]
            self.assertEqual(old_wardrobe["target_id"], costume["id"])
            self.assertEqual(current_wardrobe["target_id"], costume_2["id"])
            with self.assertRaises(RuntimeError):
                registry.link(
                    pid, actor_id, role="wardrobe", source_family="bible_prop",
                    target_id=costume["id"], target_revision=costume["revision"],
                    expected_actor_revision=before["bible_revision"])
            after_retire = registry.retire(
                pid, actor_id, wardrobe["link_id"],
                expected_actor_revision=after["bible_revision"],
                expected_link_revision=2,
                reason="Actor changed outfits; preserve old source for retakes")
            self.assertFalse(any(x["link_id"] == wardrobe["link_id"]
                                 for x in after_retire["active_links"]))
            self.assertEqual(len([x for x in after_retire["history"]
                                  if x["link_id"] == wardrobe["link_id"]]), 3)
            self.assertEqual([x for x in after_retire["history"]
                              if x["link_id"] == wardrobe["link_id"]][-1]["status"],
                             "retired")

            # Restart and read identical canonical ActorID and immutable
            # source revisions using fresh Studio, FilmIndex and registry.
            reopened = ProductionBibleActors(Studio(src/"short.sqlite3"))
            final = reopened.actor(pid, actor_id)
            self.assertEqual(final["actor_id"], actor_id)
            self.assertEqual(len(final["history"]), len(after_retire["history"]))
            self.assertEqual(final["actor_name"], "ENGINEER DONUT")
            self.assertIn(texture["sha256"], {x["source_sha256"]
                                             for x in final["active_links"]})
            self.assertEqual(reopened.catalog(pid)["format"], FORMAT)
            self.assertEqual(index.read_revision(pid, "RelayRekindleTake", 1)[
                "kind"], "take")
            # Cast the two other original nonhuman actors and the source
            # ServiceCraft actor. Scene acceptance is still blocked until
            # EVERY OpenUSD actor prim belongs to a canonical StoryBible ID.
            for eid, prim in ((box["id"], "/World/CrossingBox"),
                              (sphere["id"], "/World/PassingSphere")):
                data = reopened.actor(pid, eid)
                reopened.link(
                    pid, eid, role="actor_prim", source_family="filmindex",
                    target_id="RelayRekindleTake", target_revision=1,
                    actor_prim_path=prim, expected_actor_revision=data["bible_revision"])
            craft = bible.create_entity(pid, "character", "SERVICE CRAFT")
            craft_data = reopened.actor(pid, craft["actor_id"])
            reopened.link(
                pid, craft["actor_id"], role="actor_prim", source_family="filmindex",
                target_id="RelayRekindleTake", target_revision=1,
                actor_prim_path="/World/ServiceCraft",
                expected_actor_revision=craft_data["bible_revision"])
            accepted = reopened.require_complete_cast(pid, "RelayRekindleTake")
            self.assertTrue(accepted["complete"])
            self.assertEqual(len(accepted["actor_id_by_prim"]), 4)
            self.assertEqual(accepted["actor_id_by_prim"]["/World/PassingSphere"],
                             sphere["actor_id"])

    def test_cross_project_invented_and_nonactor_links_are_refused(self):
        with TemporaryDirectory() as d:
            studio = Studio(Path(d)/"nvp.sqlite3")
            p1 = studio.create_project("One", "Actual source")
            p2 = studio.create_project("Two", "Other film")
            bible = StoryBible(studio)
            registry = ProductionBibleActors(studio)
            actor = bible.create_entity(p1["id"], "character", "DONUT")
            other = bible.create_entity(p2["id"], "prop", "Hat")
            with self.assertRaises((KeyError, PermissionError)):
                registry.actor(p1["id"], other["id"])
            with self.assertRaises(PermissionError):
                registry.actor(p2["id"], actor["id"])
            with self.assertRaises(KeyError):
                registry.link(p1["id"], actor["actor_id"],
                    role="wardrobe", source_family="bible_prop",
                    target_id=other["id"], target_revision=other["revision"],
                    expected_actor_revision=actor["revision"])
            with self.assertRaises((KeyError, ValueError)):
                registry.link(p1["id"], actor["actor_id"],
                    role="texture", source_family="texture_blob",
                    target_id="0"*64, target_revision=1,
                    expected_actor_revision=actor["revision"])
            with self.assertRaises((KeyError, ValueError)):
                registry.link(p1["id"], actor["actor_id"],
                    role="mesh", source_family="filmindex",
                    target_id="NoSuchOriginalModel", target_revision=1,
                    expected_actor_revision=actor["revision"])
            with self.assertRaises(ValueError):
                registry.link(p1["id"], actor["actor_id"],
                    role="wardrobe", source_family="texture_blob",
                    target_id="0"*64, target_revision=1,
                    expected_actor_revision=actor["revision"])
            with self.assertRaises(ValueError):
                registry.link(p1["id"], actor["actor_id"],
                    role="actor_prim", source_family="filmindex",
                    target_id="ImpossibleTake", target_revision=1,
                    actor_prim_path="../../outside", 
                    expected_actor_revision=actor["revision"])
            self.assertEqual(registry.actor(p1["id"], actor["id"])["history"], [])

if __name__ == "__main__":
    unittest.main()
