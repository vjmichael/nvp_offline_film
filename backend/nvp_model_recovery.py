"""STACK-02C3B3: observational restart reconciliation for owned LM Studio models.

Read-only /api/v1/models on the explicit numeric local loopback endpoint.
An apparently missing model is NOT proof an in-flight request cannot still
complete. Therefore NO orphan cleanup, automatic memory release or unload.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener

from backend.nvp_resource_ledger import TaskLedger

_MAX_JSON=524288
_ID=re.compile(r"^nvp-[0-9a-f]{32}$")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


class LocalModelObserver:
    def __init__(self,ledger:TaskLedger,*,port:int=1234,reader=None):
        if not isinstance(ledger,TaskLedger):
            raise TypeError("TaskLedger needed for model recovery")
        if type(port) is not int or not 1024<=port<=65535:
            raise ValueError("Only numeric local LM Studio port is supported")
        self.ledger=ledger
        self.url=f"http://127.0.0.1:{port}/api/v1/models"
        self.reader=reader or self._request
        with ledger._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS owned_model_observations (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL, instance_id TEXT NOT NULL,
                state TEXT NOT NULL, observed_at REAL NOT NULL,
                note TEXT NOT NULL
            )""")

    def _request(self,url):
        # No proxy, redirect, or remote hostname; a read-only endpoint.
        request=Request(url,headers={"Accept":"application/json"},method="GET")
        opener=build_opener(ProxyHandler({}),_NoRedirect())
        try:
            with opener.open(request,timeout=4) as response:
                if response.status!=200:
                    raise RuntimeError("Local provider model listing was not HTTP 200")
                raw=response.read(_MAX_JSON+1)
        except (OSError,HTTPError,URLError) as exc:
            raise RuntimeError("Local provider listing unavailable") from exc
        if len(raw)>_MAX_JSON:
            raise RuntimeError("Provider listing exceeds bounded maximum")
        return raw

    @staticmethod
    def _instances(data):
        if isinstance(data,(bytes,bytearray)):
            if len(data)>_MAX_JSON:raise ValueError("Oversized provider response")
            data=json.loads(data.decode("utf8"))
        if not isinstance(data,dict) or not isinstance(data.get("models"),list):
            raise ValueError("Local provider did not return a models array")
        result={}
        for model in data["models"]:
            if not isinstance(model,dict):
                raise ValueError("Malformed local model entry")
            key=model.get("key")
            instances=model.get("loaded_instances")
            if not isinstance(key,str) or not isinstance(instances,list):
                raise ValueError("Incomplete loaded-instance evidence")
            for instance in instances:
                if not isinstance(instance,dict) or not isinstance(instance.get("id"),str):
                    raise ValueError("Malformed loaded-instance identifier")
                ident=instance["id"]
                if ident in result:
                    raise ValueError("Ambiguous duplicated local provider instance identity")
                result[ident]=key
        return result

    def observe(self):
        """Return/store advisory status, never perform lifecycle commands."""
        with self.ledger._db() as db:
            attempts=db.execute("""SELECT task_id,instance_id,state FROM owned_model_attempts
                WHERE state IN ('LOAD_REQUESTED','LOADED','UNVERIFIED') ORDER BY attempted_at""").fetchall()
        if not attempts:
            return []
        # Refuse to label a provider offline as 'model absent'.
        try:
            discovered=self._instances(self.reader(self.url))
        except Exception:
            discovered=None
        report=[]
        for task_id,ident,attempt_state in attempts:
            if not _ID.fullmatch(ident):
                state="UNKNOWN"
                note="Durable instance ID is malformed; manual investigation required"
            elif discovered is None:
                state="PROVIDER_UNAVAILABLE"
                note="Cannot verify model presence; reserve memory and do not unload"
            elif ident not in discovered:
                state="NOT_OBSERVED"
                note="Not in current provider listing; late in-flight completion remains possible"
            else:
                with self.ledger._db() as db:
                    spec=db.execute("""SELECT spec_json FROM authorized_task_specs
                        WHERE task_id=?""",(task_id,)).fetchone()
                expected=None
                if spec:
                    try:expected=json.loads(spec[0]).get("model_key")
                    except (ValueError,TypeError,AttributeError):pass
                state="PRESENT_UNVERIFIED" if expected==discovered[ident] else "IDENTITY_CONFLICT"
                note=("Named instance exists; no live owner handle after restart" if
                      state=="PRESENT_UNVERIFIED" else
                      "Instance ID points to a different or unverified model; never unload")
            with self.ledger._db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO owned_model_observations
                    (task_id,instance_id,state,observed_at,note)
                    VALUES(?,?,?,?,?)""",(task_id,ident,state,time.time(),note))
                db.commit()
            report.append({"task_id":task_id,"instance_id":ident,
                "attempt_state":attempt_state,"observation":state,
                "detail":note,"cleanup_proven":False,
                "reservation_released":False,"auto_unload":False})
        return report

    def history(self,task_id):
        with self.ledger._db() as db:
            return [{"at":when,"state":state,"detail":note} for when,state,note in
                db.execute("""SELECT observed_at,state,note FROM owned_model_observations
                    WHERE task_id=? ORDER BY sequence""",(task_id,))]
