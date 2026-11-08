"""FILM03-06: real offline spoken-audio worker with ActorID ownership.

First reviewed speech adapter: local eSpeak NG (rule-based offline speech
synthesis, NOT a neural voice clone). Uses the SAME NVP OS-contained native
process launcher as the established Blender supervisor; no untrusted shell,
network, arbitrary executable/script, voice override or download.

Only the canonical ActorIdentityCore + source-audited unrecorded selected
dialogue creates input. An OS-host-confirmed run produces a verifiable WAV,
durable journal and a FilmIndex content-addressed UNAPPROVED voice CANDIDATE.
It never becomes an approved actor dialogue Take just because TTS completed.

A real neural/TTS provider can follow this same exact input/output contract,
but must obtain its own reviewed binary/model/voice-pack provenance first.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import io
import json
import os
import re
import sqlite3
import struct
import subprocess
import time
import wave

from backend.nvp_film03_actor_identity_core import ActorIdentityCore, digest, canonical
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_host_lease import WorkerHostLease

FORMAT = "nvp.film03.native_actor_voice_worker.v1"
CANDIDATE_FORMAT = "nvp.film03.unapproved_generated_actor_voice.v1"
ENGINE = "NvpEspeakNG"
MODEL = "EspeakNG"
VOICE = re.compile(r"en(?:-us|-gb)?(?:\+[mMfF][1-5])?\Z")
JOB = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
MAX_WAV = 16 * 1024 * 1024


def file_sha(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def exclusive(path,data):
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:Path(path).unlink(missing_ok=True)
        except OSError: pass
        raise


def wav_info(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 48<path.stat().st_size<=MAX_WAV:
        raise PermissionError("No bounded real generated WAV output")
    with wave.open(str(path),"rb") as wav:
        channels=wav.getnchannels()
        width=wav.getsampwidth()
        rate=wav.getframerate()
        frames=wav.getnframes()
        if channels!=1 or width!=2 or not 8000<=rate<=48000 or not 128<=frames<=rate*45:
            raise PermissionError("Actual generated speech is not bounded PCM16 mono")
        raw=wav.readframes(frames)
    if len(raw)!=frames*2 or all(b==0 for b in raw):
        raise RuntimeError("Generated WAV has no actual PCM16 signal")
    if not any(x!=0 for x in struct.unpack("<"+"h"*frames,raw)):
        raise RuntimeError("Generated WAV signal contains only silence")
    return {"sample_rate":rate,"channels":channels,
            "sample_width":width,"sample_count":frames,
            "pcm_sha256":sha256(raw).hexdigest(),
            "wav_sha256":file_sha(path),"wav_bytes":path.stat().st_size}


class ReviewedActorVoiceWorker:
    """Trusted NVP host owns binary path, exact SHA, consent, budget and output."""

    def __init__(self,index:FilmIndex,workspace,*,executable,executable_sha256,
                 engine_revision,verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Actual FilmIndex and trusted director approval required")
        self.index=index
        self.root=Path(workspace).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():
            raise PermissionError("Untrusted TTS workspace symlink")
        self.binary=Path(executable).resolve(strict=True)
        if not self.binary.is_file() or self.binary.is_relative_to(self.root):
            raise ValueError("Real host-owned eSpeak engine executable required")
        if file_sha(self.binary)!=executable_sha256:
            raise PermissionError("Reviewed eSpeak engine executable SHA mismatch")
        if type(engine_revision) is not str or not re.fullmatch(r"EspeakNG_[0-9_]{3,20}",engine_revision):
            raise ValueError("Reviewed engine revision is required")
        self.revision=engine_revision
        self.sha=executable_sha256
        self._auth=verify_creator_action
        self.db=self.root/"actor_voice_jobs.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS actor_voice_jobs(
                job_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,contract_sha256 TEXT NOT NULL,
                binary_sha256 TEXT NOT NULL,state TEXT NOT NULL,
                generated_wav_sha256 TEXT,filmindex_candidate_id TEXT,
                error TEXT,created_at REAL NOT NULL)""")

    def _invoke(self,args,jobdir,*,timeout):
        # Only vetted fixed eSpeak command construction. No shell/PATH.
        with (jobdir/"worker_stdout.log").open("ab") as out, \
             (jobdir/"worker_stderr.log").open("ab") as err:
            child=launch_contained([str(self.binary),*args],cwd=str(jobdir),
                stdout=out,stderr=err,memory_mb=1024,
                linux_cgroup_tree_required=False)
            try:
                try:
                    code=child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    child.terminate_tree()
                    raise TimeoutError("Contained original actor voice synthesis timed out")
                if code!=0:
                    raise RuntimeError("Contained eSpeak voice worker exited "+str(code))
            finally:
                if child.poll() is None:
                    child.terminate_tree()
                child.close()

    def _runtime_version(self,jobdir):
        self._invoke(["--version"],jobdir,timeout=15)
        lines=(jobdir/"worker_stdout.log").read_text("utf8",errors="replace")
        if not lines.startswith("eSpeak NG text-to-speech:"):
            # Ubuntu's Debian wrapper formats prefix somewhat differently.
            if not lines.lower().startswith("espeak ng") and "eSpeak NG" not in lines:
                raise RuntimeError("Actual executable is not reviewed eSpeak NG")
        expected=self.revision.replace("EspeakNG_","").replace("_",".")
        if expected not in lines:
            raise RuntimeError("Native TTS version disagrees with approved actor profile")
        return lines.splitlines()[0][:240]

    def _row(self,job_id):
        with sqlite3.connect(self.db) as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM actor_voice_jobs WHERE job_id=?",
                           (job_id,)).fetchone()
        return dict(row) if row else None

    def _state(self,job_id,state,*,wav=None,candidate=None,error=None):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE actor_voice_jobs SET state=?,generated_wav_sha256=?,"
                       "filmindex_candidate_id=?,error=? WHERE job_id=?",
                       (state,wav,candidate,error,job_id))

    def run(self,pid,source_route,*,profile_revision,job_id,creator_event):
        _require_pid(pid)
        if type(job_id) is not str or not JOB.fullmatch(job_id):
            raise ValueError("Invalid bounded native ActorID TTS job")
        core=ActorIdentityCore(self.index,verify_creator_action=lambda *_:False)
        plan=core.prepare_generated_voice(pid,source_route,
                                          profile_revision=profile_revision)
        settings=plan["generation_settings"]
        if (settings["engine_id"]!=ENGINE or settings["model_id"]!=MODEL or
                settings["model_revision"]!=self.revision):
            raise PermissionError("Actor profile does not select reviewed installed engine/version")
        selector=settings["engine_voice_id"]
        if type(selector) is not str or not VOICE.fullmatch(selector):
            raise PermissionError("Actor voice engine selector not in reviewed offline voice set")
        if settings["seed"]!=0 or settings["stability"]!=1.0:
            raise PermissionError("eSpeak cannot fulfill stochastic seed/stability settings; refuse pretending")
        if settings["pitch_shift"]!=0.0:
            raise PermissionError("eSpeak v1 adapter does not implement profile semitone shift")
        scope={
            "operation":"film03_generate_actor_voice_candidate",
            "project_id":pid,"actor_id":plan["actor_id"],
            "voice_id":plan["voice_id"],
            "voice_type_id":plan["voice_type"]["voice_type_id"],
            "profile_sha256":plan["actor_identity_profile_sha256"],
            "source_take_sha256":plan["source_take_sha256"],
            "script_line_id":plan["script_line_id"],
            "contract_sha256":plan["contract_sha256"],
            "engine_binary_sha256":self.sha,
            "engine_revision":self.revision,"engine_voice_selector":selector,
            "job_id":job_id,
        }
        if not self._auth(creator_event,scope):
            raise PermissionError("Native director did not approve this exact ActorID voice job")
        with WorkerHostLease(self.root):
            if self._row(job_id) or (self.root/job_id).exists():
                raise RuntimeError("Native actor voice job cannot replay or overwrite prior source")
            jobdir=self.root/job_id
            jobdir.mkdir(mode=0o700)
            exclusive(jobdir/"contract.json",canonical(plan))
            exclusive(jobdir/"source.txt",plan["exact_script_text"].encode("utf8"))
            with sqlite3.connect(self.db) as db:
                db.execute("""INSERT INTO actor_voice_jobs
                    (job_id,project_id,actor_id,contract_sha256,binary_sha256,state,created_at)
                    VALUES(?,?,?,?,?,'PREPARED',?)""",
                    (job_id,pid,plan["actor_id"],plan["contract_sha256"],self.sha,time.time()))
            try:
                if file_sha(self.binary)!=self.sha:
                    raise PermissionError("TTS binary changed between approval and execution")
                version=self._runtime_version(jobdir)
                self._state(job_id,"RUNNING")
                # Never pass model-/browser-supplied commands, flags or a
                # user-controlled output path. Exact words are read from a
                # freshly staged source file, not interpolated into argv.
                self._invoke(["-v",selector,"-s",str(round(175*settings["rate"])),
                              "-f",str(jobdir/"source.txt"),
                              "-w",str(jobdir/"voice.wav")],jobdir,timeout=60)
                if (file_sha(jobdir/"contract.json")!=sha256(canonical(plan)).hexdigest()
                        or file_sha(jobdir/"source.txt")!=
                            sha256(plan["exact_script_text"].encode("utf8")).hexdigest()
                        or file_sha(self.binary)!=self.sha):
                    raise PermissionError("Source text, model executable or ActorID contract changed")
                info=wav_info(jobdir/"voice.wav")
                # Re-query current casting/lineage AFTER native execution. A
                # recast or screenplay change DURING TTS invalidates this job.
                after=core.prepare_generated_voice(pid,source_route,
                                                    profile_revision=profile_revision)
                if after!=plan:
                    raise PermissionError("Voice/ActorID/script profile changed during native speech")
                # Publish as a content-addressed FilmIndex candidate only.
                # There is NO approved performance/audio source and no
                # automatic binding to the finished film.
                wav_data=(jobdir/"voice.wav").read_bytes()
                stored_sha=self.index.put_blob(pid,wav_data,media_type="audio/wav")
                if stored_sha!=info["wav_sha256"]:
                    raise RuntimeError("Filmlndex source WAV SHA mismatch")
                candidate_id="ActorVoiceCandidate_"+job_id
                record={
                    "format":CANDIDATE_FORMAT,"actor_id":plan["actor_id"],
                    "voice_id":plan["voice_id"],
                    "voice_type":plan["voice_type"],
                    "engine_selector":selector,"engine_revision":self.revision,
                    "engine_executable_sha256":self.sha,
                    "runtime_version_observed":version,
                    "script_line_id":plan["script_line_id"],
                    "original_script_document_sha256":plan["script_document_sha256"],
                    "original_take_sha256":plan["source_take_sha256"],
                    "profile_sha256":plan["actor_identity_profile_sha256"],
                    "generation_contract_sha256":plan["contract_sha256"],
                    "source_pcm_wav_blob_sha256":stored_sha,
                    "wav_info":info,
                    "director_audition_approved":False,
                    "same_voice_acoustically_verified":False,
                    "voice_is_neural_model":False,
                    "voice_is_offline_rule_based_tts":True,
                    "film_dialogue_take_published":False,
                    "release_approved":False,
                }
                def guard(db):
                    row=db.execute(
                        """SELECT document_sha256 FROM nvp_bible_actor_identity_profiles
                           WHERE project_id=? AND actor_id=?
                           ORDER BY profile_revision DESC LIMIT 1""",
                        (pid,plan["actor_id"])).fetchone()
                    # The source profile itself is still bound even if an
                    # unrelated asset/wardrobe update occurred.
                    if not row or row[0]!=plan["actor_identity_profile_sha256"]:
                        raise RuntimeError("ActorID current profile changed before candidate commit")
                self.index.register_revision(pid,candidate_id,"asset",record,
                                             expected_revision=0,precommit_guard=guard)
                receipt={
                    "format":FORMAT,"job_id":job_id,"project_id":pid,
                    "actor_id":plan["actor_id"],"voice_id":plan["voice_id"],
                    "voice_type_id":plan["voice_type"]["voice_type_id"],
                    "profile_sha256":plan["actor_identity_profile_sha256"],
                    "contract_sha256":plan["contract_sha256"],
                    "binary_sha256":self.sha,"engine_revision":self.revision,
                    "runtime_version":version,
                    "source_text_sha256":sha256(
                        plan["exact_script_text"].encode("utf8")).hexdigest(),
                    "engine_voice_selector":selector,
                    "source_take_sha256":plan["source_take_sha256"],
                    "wav_info":info,
                    "candidate_id":candidate_id,
                    "voice_output_generated_in_contained_real_process":True,
                    "speech_audition_required":True,
                    "voice_approved_for_film":False,
                    "acoustic_identity_independently_verified":False,
                    "worker_exited_and_closed":True,
                    "passed":True,
                }
                exclusive(jobdir/"receipt.json",canonical(receipt))
                self._state(job_id,"SUCCEEDED",wav=info["wav_sha256"],
                            candidate=candidate_id)
                return receipt
            except BaseException as error:
                self._state(job_id,"FAILED",error=(type(error).__name__+": "+str(error))[:600])
                raise

    def verify(self,pid,job_id):
        row=self._row(job_id)
        if not row or row["project_id"]!=pid or row["state"]!="SUCCEEDED":
            raise PermissionError("Only completed exact native voice jobs are verifiable")
        jobdir=self.root/job_id
        if jobdir.is_symlink() or (jobdir/"receipt.json").is_symlink():
            raise PermissionError("Native voice receipt cannot be symlinked")
        receipt=json.loads((jobdir/"receipt.json").read_text("utf8"))
        plan=json.loads((jobdir/"contract.json").read_text("utf8"))
        if (receipt.get("format")!=FORMAT or receipt.get("passed") is not True or
                receipt.get("job_id")!=job_id or receipt.get("actor_id")!=row["actor_id"]
                or receipt.get("contract_sha256")!=row["contract_sha256"] or
                receipt.get("binary_sha256")!=row["binary_sha256"] or
                receipt.get("voice_approved_for_film") is not False or
                digest({k:v for k,v in plan.items() if k!="contract_sha256"})!=
                  plan.get("contract_sha256") or
                receipt["wav_info"]!=wav_info(jobdir/"voice.wav") or
                receipt["wav_info"]["wav_sha256"]!=row["generated_wav_sha256"] or
                receipt["source_text_sha256"]!=file_sha(jobdir/"source.txt")):
            raise PermissionError("Independently verified ActorID source/voice WAV receipt differs")
        candidate=self.index.read_revision(pid,receipt["candidate_id"],1)
        if (candidate["kind"]!="asset" or
                candidate["data"]["format"]!=CANDIDATE_FORMAT or
                candidate["data"]["actor_id"]!=row["actor_id"] or
                candidate["data"]["source_pcm_wav_blob_sha256"]!=
                   receipt["wav_info"]["wav_sha256"] or
                self.index.get_blob(pid,receipt["wav_info"]["wav_sha256"]) !=
                   (jobdir/"voice.wav").read_bytes()):
            raise PermissionError("Immutable FilmIndex generated actor voice blob differs")
        return receipt
