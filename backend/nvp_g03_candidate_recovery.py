"""G03-M4: independently reopen known encrypted legacy source bytes.

Run in a FRESH process after staging, never in the staging transaction.
This readback authenticates known project SQLite row snapshots and each known
FilmIndex/sidecar source in memory. It makes no plaintext restoration or
modification to the creator's original film. It is NOT a full SQLite/schema
reconstruction or a migration cutover permission; unattributed sources and
native worker custody remain unresolved until verified independently.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

from backend.nvp_g03_legacy_migration import MigrationRefused
from backend.nvp_g03_live_store import LiveFilmStore

_ID = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _verified_inventory(doc, pid):
    if type(pid) is not str or not _ID.fullmatch(pid):
        raise MigrationRefused("Invalid project for independent recovery")
    if not isinstance(doc, dict) or doc.get("project_id") != pid:
        raise MigrationRefused("Independent recovery inventory is for another film")
    supplied = doc.get("inventory_sha256")
    if type(supplied) is not str or not _SHA.fullmatch(supplied):
        raise MigrationRefused("Reviewed recovery inventory digest absent")
    body = dict(doc)
    del body["inventory_sha256"]
    encoded = json.dumps(body, sort_keys=True, separators=(",",":")).encode()
    if hashlib.sha256(encoded).hexdigest() != supplied:
        raise MigrationRefused("Reviewed recovery inventory changed")
    if doc.get("format") != "nvp.g03.migration_inventory.v1":
        raise MigrationRefused("Unknown original-film inventory format")
    if not _SHA.fullmatch(str(doc.get("legacy_sql_sha256", ""))):
        raise MigrationRefused("Legacy SQL source digest missing")
    return supplied


def reopen_known_originals(candidate_root, pid, passphrase, inventory):
    """Independent fresh-store readback, no original DB or plaintext file writes.

    The caller MUST be outside the original staging process, ideally on the
    original owner's Windows account after an application restart.
    """
    if sys.platform != "win32":
        raise MigrationRefused("Real Windows DPAPI required for original recovery")
    inventory_sha = _verified_inventory(inventory, pid)
    if type(passphrase) is not str or not passphrase:
        raise MigrationRefused("Original-film recovery requires owner passphrase")
    expected = {"migration/legacy-project-tables.json":
                (inventory["legacy_sql_sha256"], inventory["legacy_sql_bytes"])}
    for row in inventory.get("filmindex_blobs", []):
        if not isinstance(row, dict) or not _SHA.fullmatch(str(row.get("sha256",""))):
            raise MigrationRefused("Bad FilmIndex recovery identity")
        name = "migration/filmindex/" + row["sha256"]
        if name in expected:
            raise MigrationRefused("Duplicate FilmIndex recovery identity")
        expected[name] = (row["sha256"], row["size_bytes"])
    for row in inventory.get("project_sidecars", []):
        if not isinstance(row, dict) or not isinstance(row.get("relative"),str):
            raise MigrationRefused("Bad legacy sidecar identity")
        relative = row["relative"]
        parts = relative.split("/")
        if (not parts or any(x in ("", ".", "..") for x in parts)
                or "\\" in relative or relative.startswith("/")):
            raise MigrationRefused("Unsafe source path in reviewed recovery inventory")
        if not _SHA.fullmatch(str(row.get("sha256",""))):
            raise MigrationRefused("Bad legacy sidecar digest")
        name = "migration/sidecars/" + relative
        if name in expected:
            raise MigrationRefused("Duplicate legacy sidecar identity")
        expected[name] = (row["sha256"], row["size_bytes"])
    if len(expected) > 250001:
        raise MigrationRefused("Recovery inventory exceeds verified bound")
    verifier = LiveFilmStore(Path(candidate_root))
    token = "g03-independent-reopen-" + secrets.token_urlsafe(32)
    verifier.authorize(pid, passphrase, token)
    total = 0
    digest = hashlib.sha256()
    try:
        recovered = verifier.read(pid, token)
        actual = {row["name"]: (row["sha256"], row["size_bytes"])
                  for row in recovered["source_assets"]}
        if actual != expected:
            raise MigrationRefused("Encrypted candidate is incomplete or has extra assets")
        raw_sql = verifier.get_original(
            pid, token, "migration/legacy-project-tables.json")
        if len(raw_sql) != inventory["legacy_sql_bytes"]:
            raise MigrationRefused("Recovered source SQL length changed")
        try:
            sql = json.loads(raw_sql)
        except (ValueError, UnicodeError) as exc:
            raise MigrationRefused("Recovered SQLite row snapshot malformed") from exc
        if (sql.get("format") != "nvp.g03.legacy.sql_snapshot.v1"
                or sql.get("project_id") != pid):
            raise MigrationRefused("Recovered SQLite row source identity invalid")
        projects = sql.get("tables",{}).get("projects",[])
        if len(projects)!=1 or projects[0].get("id")!=pid:
            raise MigrationRefused("Original film project row cannot be recovered")
        for key in ("title","idea","screenplay"):
            if projects[0].get(key)!=recovered[key]:
                raise MigrationRefused("Candidate active metadata mismatches original SQL")
        for name in sorted(expected):
            raw = raw_sql if name=="migration/legacy-project-tables.json" else (
                verifier.get_original(pid,token,name))
            sha, size = expected[name]
            if (type(size) is not int or not 0 <= size <= 1024*1024*1024
                    or len(raw)!=size or hashlib.sha256(raw).hexdigest()!=sha):
                raise MigrationRefused("Independent original-film byte recovery mismatch")
            total += len(raw)
            if total > 2*1024*1024*1024:
                raise MigrationRefused("Recovery exceeds source archive budget")
            digest.update(name.encode("utf8"))
            digest.update(b"\0")
            digest.update(bytes.fromhex(sha))
        return {
            "format":"nvp.g03.known_source_recovery.v1",
            "project_id":pid,
            "reviewed_inventory_sha256":inventory_sha,
            "known_source_count":len(expected),
            "known_original_bytes_reopened":total,
            "readback_receipt_sha256":digest.hexdigest(),
            "known_payloads_authenticated":True,
            "original_film_modified":False,
            "plaintext_restoration_performed":False,
            "sql_schema_reconstruction_verified":False,
            "live_worker_custody_verified":False,
            "full_film_cutover_authorized":False,
            "unresolved_unattributed_files":len(
                inventory.get("unattributed_original_files",[])),
            "unresolved_global_workers":len(
                inventory.get("unclassified_worker_journals",[])),
        }
    finally:
        verifier.revoke(pid)
