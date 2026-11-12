"""INT-01D source checks for the Lu-owned NVP Film Home seam.

Native Lu transport/model loading is NOT mocked into being 'installed'; these
tests use a host double exercising explicit source/scope admission, per-event
verification, proposal-only G04 storage, director approval and cancellation.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from backend.nvp_studio import Studio
from backend.nvp_g04_preproduction import G04Preproduction
from backend.nvp_int01d_lu_host import NativeLuFilmService,UNCONNECTED
from backend.nvp_lu_workspace import LuHostError


TEXT="INT. KITCHEN - NIGHT\n\nThe table is lit by one candle.\n\nSAM\nI came back."
MODEL="m-0123456789abcdef0123456789abcdef"
SESSION="s-0123456789abcdef0123456789abcdef"
GENERATION="g-0123456789abcdef0123456789abcdef"


class FakeAccess:
    def __init__(self):
        self.locked=False
        self.allowed=True

    def protected(self,pid):
        return self.locked

    def permitted(self,pid,token,*,renew=False):
        return self.allowed


class FakeLive:
    def __init__(self):
        self.sealed=False
    def exists(self,pid):
        return self.sealed


class NativeLuHostDouble:
    """A fake *host*, never a fake native OS approval or model process."""
    def __init__(self,studio,pid):
        self.scope=object()
        self.claim={"module":"nvp.film","workspace":"NvpWindow",
                    "project":pid,"epoch":"a"*32,"state":"active"}
        self.studio=studio
        self.runtime={"modelRef":MODEL,"sessionId":SESSION,
                      "generationId":None,"phase":"Ready","pid":1234}
        self.catalog=1
        self.events=None
        self.revoked=False
        self.receipts=[]
        self.saved=[]
        self.cancelled=0
        self.commit_other_script=False
        self.inference_calls=0

    def verify_scope(self,scope,operation):
        if self.revoked or scope is not self.scope:
            raise LuHostError("Workspace revoked")
        return dict(self.claim)

    def read_runtime(self,scope):
        self.verify_scope(scope,"status")
        return dict(self.runtime)

    def catalog_count(self,scope):
        self.verify_scope(scope,"status")
        return self.catalog

    def read_project(self,scope):
        self.verify_scope(scope,"read")
        return self.studio.get_project(self.claim["project"])

    def _event(self,n,kind,**additional):
        return {"v":1,"workspace":self.claim["workspace"],
                "project":self.claim["project"],
                "epoch":self.claim["epoch"],"modelRef":MODEL,
                "sessionId":SESSION,"generationId":GENERATION,
                "sequence":n,"kind":kind,**additional}

    def generate_events(self,scope,system,user,max_new_tokens):
        self.verify_scope(scope,"generate")
        self.inference_calls+=1
        assert "NVP" in system
        assert max_new_tokens==2800
        if self.commit_other_script:
            before=self.studio.get_project(self.claim["project"])
            self.studio.save_screenplay(before["id"],"INT. FIELD - DAY\n\nA tree.",
                                       before["revision"])
        events=self.events if self.events is not None else [
            self._event(1,"chunk",text=TEXT),
            self._event(2,"finished",cancelled=False)]
        for event in events:
            yield dict(event)

    def record_generation(self,scope,receipt):
        self.verify_scope(scope,"receipt")
        self.receipts.append(dict(receipt))
        return {"status":"recorded",
                "request_sha256":receipt["request_sha256"],
                "generated_sha256":receipt["generated_sha256"],
                "proposal_sha256":receipt["proposal_sha256"]}

    def save_proposal(self,scope,*,stage,content,instructions,
                      expected_revision):
        self.verify_scope(scope,"save")
        project=self.read_project(scope)
        if project["revision"]!=expected_revision:
            raise LuHostError("Lu project revision changed")
        digest=sha256(content.encode("utf8")).hexdigest()
        if not any(r["proposal_sha256"]==digest for r in self.receipts):
            raise LuHostError("Missing complete generation")
        self.saved.append({"stage":stage,"content":content})
        return {"status":"proposed","stage":stage,"content":content,
                "consumed_proposal_sha256":digest,"source_mutated":False}

    def cancel_active(self,scope):
        self.verify_scope(scope,"cancel")
        self.cancelled+=1
        return True


@pytest.fixture
def film(tmp_path):
    studio=Studio(tmp_path/"studio.sqlite3")
    movie=studio.create_project("Lantern","A family returns to the mountains")
    pid=movie["id"]
    access=FakeAccess()
    live=FakeLive()
    host=NativeLuHostDouble(studio,pid)
    service=NativeLuFilmService(studio,lambda:access,lambda:live,
        lu_host=host,issue_scope=lambda requested,operation:host.scope)
    return studio,movie,access,live,host,service


def test_no_lu_bridge_does_not_claim_a_loaded_model():
    assert UNCONNECTED["state"]=="disconnected"
    assert UNCONNECTED["nvp_owns_model"] is False
    assert UNCONNECTED["inference_authorized_by_status"] is False


def test_status_is_host_reported_only_and_tracks_ready_busy_unloaded(film):
    _,movie,_,_,host,service=film
    pid=movie["id"]
    ready=service.status(pid,None)
    assert ready["state"]=="ready"
    assert ready["host_reported_only"] is True
    assert ready["weights_verified_here"] is False
    assert ready["vram_verified_here"] is False
    assert ready["nvp_owns_model"] is False
    host.runtime.update(phase="Generating",generationId=GENERATION)
    assert service.status(pid,None)["state"]=="busy"
    host.runtime.update(phase="Idle",modelRef=None,sessionId=None,
                        generationId=None,pid=None)
    assert service.status(pid,None)["state"]=="available_unloaded"
    host.catalog=0
    assert service.status(pid,None)["state"]=="no_model"


def test_real_host_proposal_is_only_staged_pending_director_approval(film):
    studio,movie,_,_,host,service=film
    pid=movie["id"]
    result=service.propose_screenplay(pid,None,"Write an opening scene",
        expected_revision=movie["revision"])
    draft=result["screenplay_drafts"][0]
    assert draft["status"]=="proposed" and draft["stale"] is False
    assert draft["content"]==TEXT
    assert studio.get_project(pid)["screenplay"]==""
    assert studio.get_project(pid)["revision"]==movie["revision"]
    assert host.inference_calls==1
    assert host.receipts[0]["source_mutation_authorized"] is False
    assert host.receipts[0]["tool_execution_authorized"] is False
    decision=G04Preproduction(studio).decide_screenplay(
        pid,draft["id"],"accept",movie["revision"],TEXT)
    assert decision["applied"] is True
    assert studio.get_project(pid)["screenplay"]==TEXT


def test_decline_does_not_replace_original_script(film):
    studio,movie,_,_,_,service=film
    pid=movie["id"]
    result=service.propose_screenplay(pid,None,"Propose an opening")
    draft=result["screenplay_drafts"][0]
    G04Preproduction(studio).decide_screenplay(pid,draft["id"],"discard",
                                                movie["revision"])
    assert studio.get_project(pid)["screenplay"]==""


def test_revoked_or_cross_project_scope_cannot_read_or_generate(film):
    _,movie,_,_,host,service=film
    pid=movie["id"]
    host.claim["project"]="b"*32
    with pytest.raises(LuHostError,match="another film"):
        service.status(pid,None)
    host.claim["project"]=pid
    host.revoked=True
    with pytest.raises(LuHostError,match="revoked"):
        service.propose_screenplay(pid,None,"Write a scene")
    assert host.inference_calls==0


def test_stale_studio_revision_never_creates_an_approved_draft(film):
    studio,movie,_,_,host,service=film
    host.commit_other_script=True
    with pytest.raises((LuHostError,RuntimeError)):
        service.propose_screenplay(movie["id"],None,"Try a different script")
    assert studio.get_project(movie["id"])["revision"]==1
    assert G04Preproduction(studio).view(movie["id"])["screenplay_drafts"]==[]


def test_model_busy_and_partial_generation_cannot_commit(film):
    studio,movie,_,_,host,service=film
    host.runtime.update(phase="Generating",generationId=GENERATION)
    with pytest.raises(LuHostError,match="not ready"):
        service.propose_screenplay(movie["id"],None,"Write")
    host.runtime.update(phase="Ready",generationId=None)
    host.events=[host._event(1,"chunk",text=TEXT)]
    with pytest.raises(LuHostError,match="without verified"):
        service.propose_screenplay(movie["id"],None,"Write")
    assert G04Preproduction(studio).view(movie["id"])["screenplay_drafts"]==[]


def test_private_film_and_revoked_local_grant_never_reach_external_lu(film):
    _,movie,access,live,host,service=film
    live.sealed=True
    with pytest.raises(PermissionError,match="encrypted"):
        service.propose_screenplay(movie["id"],None,"Write")
    assert host.inference_calls==0
    live.sealed=False;access.locked=True;access.allowed=False
    with pytest.raises(PermissionError,match="Unlock"):
        service.status(movie["id"],None)


def test_cancel_is_a_request_not_a_falsely_finished_generation(film):
    _,movie,_,_,host,service=film
    outcome=service.cancel(movie["id"],None)
    assert outcome["state"]=="cancellation_requested"
    assert outcome["terminal_verified"] is False
    assert host.cancelled==1


def test_native_scope_issuer_is_required_and_cannot_be_installed_twice(film):
    from fastapi import FastAPI
    from backend.nvp_int01d_lu_host import install_native_lu_film_service
    studio,movie,access,live,host,service=film
    app=FastAPI()
    with pytest.raises(TypeError):
        NativeLuFilmService(studio,lambda:access,lambda:live,
            lu_host=host,issue_scope=None)
    installed=install_native_lu_film_service(
        app,studio,lambda:access,lambda:live,
        lu_host=host,issue_scope=lambda pid,operation:host.scope)
    assert installed.status(movie["id"],None)["state"]=="ready"
    with pytest.raises(RuntimeError,match="already bound"):
        install_native_lu_film_service(
            app,studio,lambda:access,lambda:live,
            lu_host=host,issue_scope=lambda pid,operation:host.scope)
