"""G03-M5: independent isolated reconstruction of an original film.

Runs in a fresh Windows process using DPAPI/AES-GCM candidate input. Restores
original reviewed SQLite schema and project rows, exact FilmIndex PCM/source
blobs and project sidecars in a TEMPORARY scratch directory; reopens the actual
Studio/FilmIndex APIs and verifies FK/integrity. No source cutover or deletion.
Any unclassified file/global table/native worker custody blocks reconstruction.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile

from backend.nvp_g03_candidate_recovery import _verified_inventory
from backend.nvp_g03_legacy_migration import MigrationRefused
from backend.nvp_g03_live_store import LiveFilmStore

_IDENT=re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SHA=re.compile(r"[a-f0-9]{64}\Z")

def _decode(value):
    if isinstance(value,dict) and set(value)=={"bytes_b64"}:
        return base64.b64decode(value["bytes_b64"],validate=True)
    if value is None or type(value) in (str,int,float):
        return value
    raise MigrationRefused("Unknown original SQLite cell type")

def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def _rebuild_sqlite(path,source,pid):
    if source.get("format")!="nvp.g03.legacy.sql_snapshot.v2":
        raise MigrationRefused("Original SQLite schema v2 required")
    schema=source.get("schema");tables=source.get("tables")
    if not isinstance(schema,list) or not isinstance(tables,dict) or not schema:
        raise MigrationRefused("Relational source schema not preserved")
    if len(schema)>2048 or len(tables)>512:
        raise MigrationRefused("Original SQL reconstruction exceeds budget")
    db=sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("BEGIN IMMEDIATE")
        for item in schema:
            if not isinstance(item,dict) or set(item)!={"type","name","table","sql"}:
                raise MigrationRefused("Unreviewed SQLite DDL metadata")
            kind,name,owner,sql=(item[k] for k in ("type","name","table","sql"))
            if (kind not in ("table","index","view","trigger") or
                    not isinstance(name,str) or not _IDENT.fullmatch(name) or
                    not isinstance(owner,str) or not _IDENT.fullmatch(owner) or
                    not isinstance(sql,str) or not 1<=len(sql)<=1024*1024):
                raise MigrationRefused("Unsafe original relational DDL")
            if kind=="table":
                if not re.match(r"CREATE\s+TABLE\b",sql,re.I):
                    raise MigrationRefused("Legacy virtual table requires a converter")
                db.execute(sql)
        for name,rows in tables.items():
            if not isinstance(name,str) or not _IDENT.fullmatch(name) or not isinstance(rows,list):
                raise MigrationRefused("Bad original table/row identity")
            columns=[r[1] for r in db.execute('PRAGMA table_info("'+name+'")')]
            if not columns or len(rows)>250000:
                raise MigrationRefused("Original table structure or budget invalid")
            names=",".join('"'+c+'"' for c in columns)
            marks=",".join("?" for _ in columns)
            for row in rows:
                if not isinstance(row,dict) or set(row)!=set(columns):
                    raise MigrationRefused("Original relational row shape changed")
                db.execute('INSERT INTO "'+name+'" ('+names+') VALUES ('+marks+')',
                           [_decode(row[c]) for c in columns])
        for kind in ("index","view","trigger"):
            for item in schema:
                if item["type"]==kind: db.execute(item["sql"])
        for pragma in ("user_version","application_id"):
            value=source.get(pragma,0)
            if type(value) is not int or not 0<=value<=2147483647:
                raise MigrationRefused("Unsafe original SQLite pragma")
            db.execute("PRAGMA "+pragma+"="+str(value))
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()!=("ok",):
            raise MigrationRefused("Rebuilt original relational SQLite is corrupt")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise MigrationRefused("Original film has missing relational references")
        db.row_factory=sqlite3.Row
        for name,expected in tables.items():
            columns=[x[1] for x in db.execute('PRAGMA table_info("'+name+'")')]
            key="id" if name=="projects" else "project_id"
            if key not in columns:
                raise MigrationRefused("Original project owner key missing")
            found=db.execute('SELECT * FROM "'+name+'" WHERE "'+key+'"=?',
                             (pid,)).fetchall()
            def enc(x):
                if isinstance(x,bytes):
                    return {"bytes_b64":base64.b64encode(x).decode("ascii")}
                return x
            actual=[{c:enc(r[c]) for c in columns} for r in found]
            if sorted(map(_json,actual))!=sorted(map(_json,expected)):
                raise MigrationRefused("Source SQLite row-by-row reconstruction failed")
        return len(schema),sum(len(x) for x in tables.values())
    finally:
        db.close()

def reconstruct_and_reopen(candidate_root,pid,passphrase,inventory):
    """No access to original Studio filesystem; no persistent plaintext restore."""
    if sys.platform!="win32":
        raise MigrationRefused("Authentic Windows DPAPI required")
    review=_verified_inventory(inventory,pid)
    if any(inventory.get(x) for x in
            ("unknown_nonproject_tables","unclassified_worker_journals",
             "unattributed_original_files","global_worker_journal_provenance")):
        raise MigrationRefused("Unclassified original file/global table/worker custody")
    if not isinstance(passphrase,str) or not passphrase:
        raise MigrationRefused("Owner recovery secret required")
    store=LiveFilmStore(Path(candidate_root))
    token="g03-full-recovery-"+secrets.token_urlsafe(32)
    store.authorize(pid,passphrase,token)
    try:
        raw=store.get_original(pid,token,"migration/legacy-project-tables.json")
        if (hashlib.sha256(raw).hexdigest()!=inventory["legacy_sql_sha256"] or
                len(raw)!=inventory["legacy_sql_bytes"]):
            raise MigrationRefused("Original SQL source digest invalid")
        source=json.loads(raw)
        if source.get("project_id")!=pid:
            raise MigrationRefused("Reopened SQL source belongs to another film")
        with tempfile.TemporaryDirectory(prefix="nvp-g03-reconstruct-original-") as tmp:
            root=Path(tmp)
            sqlite_path=root/"studio.sqlite3"
            schema_count,row_count=_rebuild_sqlite(sqlite_path,source,pid)
            restored_count=0;pcm_count=0
            for item in inventory.get("filmindex_blobs",[]):
                sha=item["sha256"]
                if not _SHA.fullmatch(sha):
                    raise MigrationRefused("Invalid original asset hash")
                payload=store.get_original(pid,token,"migration/filmindex/"+sha)
                if (len(payload)!=item["size_bytes"] or
                        hashlib.sha256(payload).hexdigest()!=sha):
                    raise MigrationRefused("Original FilmIndex payload changed")
                target=root/"studio_film_blobs"/pid/sha[:2]/sha
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open("xb") as output:
                    output.write(payload);output.flush();os.fsync(output.fileno())
                restored_count+=1
                if str(item.get("media_type","")).startswith("audio/"):pcm_count+=1
            for item in inventory.get("project_sidecars",[]):
                relative=item["relative"]
                parts=relative.split("/")
                if (not parts or any(x in ("",".","..") for x in parts) or
                        "\\" in relative or relative.startswith("/")):
                    raise MigrationRefused("Original sidecar path unsafe")
                payload=store.get_original(pid,token,"migration/sidecars/"+relative)
                if (len(payload)!=item["size_bytes"] or
                        hashlib.sha256(payload).hexdigest()!=item["sha256"]):
                    raise MigrationRefused("Original USD/media sidecar changed")
                dest=root.joinpath(*parts)
                if not dest.resolve().is_relative_to(root.resolve()):
                    raise MigrationRefused("Sidecar escapes scratch recovery")
                dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open("xb") as output:
                    output.write(payload);output.flush();os.fsync(output.fileno())
                restored_count+=1
            from backend.nvp_studio import Studio
            from backend.nvp_film_index import FilmIndex
            studio=Studio(sqlite_path)
            movie=studio.get_project(pid)
            original=source["tables"]["projects"][0]
            for key in ("id","title","idea","screenplay","revision",
                        "created_at","updated_at"):
                if movie[key]!=original[key]:
                    raise MigrationRefused("Real Studio movie reopening changed original")
            index=FilmIndex(studio)
            for item in inventory.get("filmindex_blobs",[]):
                data=index.get_blob(pid,item["sha256"])
                if hashlib.sha256(data).hexdigest()!=item["sha256"]:
                    raise MigrationRefused("Real FilmIndex source relationship changed")
            with sqlite3.connect(sqlite_path) as db:
                if (db.execute("PRAGMA integrity_check").fetchone()!=("ok",) or
                        db.execute("PRAGMA foreign_key_check").fetchone() is not None):
                    raise MigrationRefused("Reopened restored SQLite/FK matrix failed")
            return {
                "format":"nvp.g03.isolated_original_reconstruction.v1",
                "project_id":pid,"reviewed_inventory_sha256":review,
                "reconstructed_sql_schema_objects":schema_count,
                "reconstructed_project_rows":row_count,
                "authenticated_original_assets":restored_count,
                "reopened_pcm_blobs":pcm_count,
                "reopened_studio_and_filmindex":True,
                "actual_sqlite_schema_and_fk_verified":True,
                "plaintext_restored_to_original_location":False,
                "isolated_scratch_removed_on_return":True,
                "original_film_modified":False,
                "source_cutover_authorized":False,
                "owner_physical_restore_accepted":False}
    finally:
        store.revoke(pid)
