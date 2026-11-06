"""SCALE-02C: bind verified external camera media into authoritative FilmIndex.

Source files remain external; the FilmIndex asset revision pins their hash,
size and normalized FFprobe metadata, NOT a drive letter or mutable path.
This is trusted native-host code, never an approval or model-callable interface.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_source_media_inventory import SourceMediaInventory

FORMAT = "nvp.asset.external_source.v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class SourceFilmBridge:
    """Keep external media locators separate from immutable film provenance."""

    def __init__(self, index: FilmIndex, inventory: SourceMediaInventory):
        if not isinstance(index, FilmIndex) or not isinstance(inventory, SourceMediaInventory):
            raise TypeError("FilmIndex and source inventory are required")
        if index.studio.db_path.resolve() != inventory.studio.db_path.resolve():
            raise ValueError("FilmIndex and media inventory must use the same Studio database")
        self.index, self.inventory = index, inventory

    def _source_snapshot(self, project_id, asset_id):
        _require_pid(project_id)
        _id(asset_id, "source asset")
        with self.index.studio._connection() as db:
            row = db.execute("""SELECT m.sha256,m.size_bytes,m.media_type,
                    d.source_sha256,d.probe_json
                FROM scale_source_media m
                JOIN scale_source_details d
                    ON m.project_id=d.project_id AND m.asset_id=d.asset_id
                WHERE m.project_id=? AND m.asset_id=?""",
                (project_id, asset_id)).fetchone()
        if row is None:
            raise KeyError("Source must be registered and natively probed")
        if row["sha256"] != row["source_sha256"]:
            raise RuntimeError("Native source identity does not match inventory")
        probe = json.loads(row["probe_json"])
        if (type(probe) is not dict or probe.get("format") != "nvp.source.probe.v1"
            or probe.get("decoded_and_verified") is not False):
            raise RuntimeError("Missing normalized native source metadata")
        return {"format": FORMAT, "source_asset_id": asset_id,
                "content_sha256": row["sha256"], "size_bytes": row["size_bytes"],
                "media_type": row["media_type"], "probe": probe,
                "custody": "external_reference_not_immutable_copy",
                "original_file_present_in_filmindex": False}

    def register_source_revision(self, project_id, asset_id):
        """Publish one immutable FilmIndex asset revision, following full rehash.

        Reopening/relinking the external media later changes only its locator,
        not the FilmIndex source identity or SHA. No implicit source revision.
        """
        snapshot = self._source_snapshot(project_id, asset_id)
        checked = self.inventory.catalog.probe(project_id, asset_id, verify_bytes=True)
        if checked["status"] != "VERIFIED":
            raise RuntimeError("External source requires full SHA verification before publication")
        try:
            self.index.read_revision(project_id, asset_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("External source already published; original revisions are immutable")

        # FilmIndex invokes the guard inside its own BEGIN IMMEDIATE. The guard
        # checks DB identity only; point-in-time byte checks cannot make an
        # uncontrolled external disk immutable. Consumption MUST hash again.
        expected = hashlib.sha256(_canonical(snapshot)).hexdigest()

        def guard(db):
            row = db.execute("""SELECT m.sha256,m.size_bytes,m.media_type,
                     d.source_sha256,d.probe_json
                FROM scale_source_media m JOIN scale_source_details d
                  ON m.project_id=d.project_id AND m.asset_id=d.asset_id
                WHERE m.project_id=? AND m.asset_id=?""",
                (project_id, asset_id)).fetchone()
            if row is None or row["sha256"] != snapshot["content_sha256"] or (
                    row["source_sha256"] != snapshot["content_sha256"]
                    or row["size_bytes"] != snapshot["size_bytes"]
                    or row["media_type"] != snapshot["media_type"]
                    or hashlib.sha256(_canonical(json.loads(row["probe_json"]))).hexdigest()
                    != hashlib.sha256(_canonical(snapshot["probe"])).hexdigest()):
                raise RuntimeError("Source media metadata changed during FilmIndex publication")
            if hashlib.sha256(_canonical(snapshot)).hexdigest() != expected:
                raise RuntimeError("FilmIndex source manifest was modified")
        return self.index.register_revision(
            project_id, asset_id, "asset", snapshot,
            expected_revision=0, precommit_guard=guard)

    def resolve_source(self, project_id, asset_id, revision=1, *, verify_bytes=False):
        """Read immutable metadata even while media is offline.

        verified_bytes is True only after a fresh full rehash of the current
        external locator. No path is handed to an untrusted consumer.
        """
        record = self.index.read_revision(project_id, asset_id, revision)
        data = record["data"]
        if record["kind"] != "asset" or data.get("format") != FORMAT:
            raise RuntimeError("Requested FilmIndex object is not an external original")
        details = self.inventory.describe(project_id, asset_id)
        if details["sha256"] != data["content_sha256"]:
            raise RuntimeError("Inventory and FilmIndex immutable source disagree")
        observed = self.inventory.catalog.probe(
            project_id, asset_id, verify_bytes=verify_bytes)
        if not verify_bytes:
            status = observed["status"]
        else:
            status = observed["status"]
            if status == "VERIFIED":
                with self.index.studio._connection() as db:
                    dbrow = db.execute("""SELECT size_bytes,media_type FROM scale_source_media
                        WHERE project_id=? AND asset_id=?""", (project_id, asset_id)).fetchone()
                if (dbrow is None or dbrow["size_bytes"] != data["size_bytes"]
                    or dbrow["media_type"] != data["media_type"]):
                    raise RuntimeError("FilmIndex source metadata changed")
        return {"asset_id": asset_id, "film_revision": revision,
                "film_document_sha256": record["document_sha256"],
                "source_sha256": data["content_sha256"],
                "size_bytes": data["size_bytes"],
                "probe": data["probe"], "volume_id": details["volume_id"],
                "availability": status,
                "verified_bytes": bool(verify_bytes and status == "VERIFIED")}
