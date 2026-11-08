"""FILM03-04: persistent VoiceID tied to canonical StoryBible ActorID.

A correct actor saying a correct line in the WRONG VOICE ruins continuity.
NVP therefore treats voice casting as its own APPROVED PRODUCTION-BIBLE
AUTHORITY, independent of individual PCM clips, AI guesses and USD prims.

Contract:
  ActorID -> one current VoiceID -> immutable reference PCM revision/SHA
  -> individually director-reviewed exact spoken performance/PCM revision.
Each decision APPENDS history. Recasting requires a NEW VoiceID, specific
reason and trusted host approval. Ordinary AI/tool output cannot enroll
itself, transfer a VoiceID or auto-accept arbitrary recorded samples.

Important limit: bytes/metadata can PROVE what was submitted and approved,
not independently establish that a person's timbre is acoustically identical.
Different voice clips require a real director's explicit comparison to the
reference audio; there is NO claim of automatic speaker recognition.
"""
from __future__ import annotations

import hashlib
import re
from backend.nvp_data_av_source import (
    RecordedSoundSources, SAMPLE_RATE, MAX_READ_SAMPLES)
from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_story_bible import StoryBible
from backend.nvp_film03_object_dialogue import PERFORMANCE_FORMAT


VOICE_FORMAT = "nvp.film03.production_bible_voice_identity.v1"
DELIVERY_FORMAT = "nvp.film03.voice_performance_review.v1"
MAX_REVIEW_NOTE = 1200
MIN_REVIEW_NOTE = 12
HEX_ACTOR = re.compile(r"[a-f0-9]{32}\Z")


def _note(value):
    if type(value) is not str or not MIN_REVIEW_NOTE <= len(value.strip()) <= MAX_REVIEW_NOTE:
        raise ValueError("A bounded, explicit director voice-audition note is required")
    return value.strip()


def _rev(value, label):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid exact " + label + " revision")
    return value


class ProductionBibleVoiceIdentity:
    """First-party voice-casting decisions, not an automatic voice recognizer."""

    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index, FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Real FilmIndex plus trusted director authority required")
        self.index = index
        self.studio = index.studio
        self.bible = StoryBible(self.studio)
        self._approve = verify_creator_action
        with self.studio._connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS nvp_bible_voice_casts (
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              actor_id TEXT NOT NULL REFERENCES bible_entities(id),
              cast_revision INTEGER NOT NULL CHECK(cast_revision > 0),
              voice_id TEXT NOT NULL,
              reference_audio_id TEXT NOT NULL,
              reference_audio_revision INTEGER NOT NULL,
              reference_audio_sha256 TEXT NOT NULL,
              reference_excerpt_sha256 TEXT NOT NULL,
              reference_sample_count INTEGER NOT NULL,
              director_review_note TEXT NOT NULL,
              voice_recast_reason TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(project_id,actor_id,cast_revision)
            );
            CREATE INDEX IF NOT EXISTS nvp_bible_voice_cast_lookup
              ON nvp_bible_voice_casts(project_id,voice_id,actor_id);
            CREATE TABLE IF NOT EXISTS nvp_bible_voice_take_approvals (
              project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
              actor_id TEXT NOT NULL REFERENCES bible_entities(id),
              performance_id TEXT NOT NULL,
              approval_revision INTEGER NOT NULL CHECK(approval_revision > 0),
              voice_id TEXT NOT NULL,
              voice_cast_revision INTEGER NOT NULL,
              reference_audio_sha256 TEXT NOT NULL,
              performance_document_sha256 TEXT NOT NULL,
              original_audio_id TEXT NOT NULL,
              original_audio_revision INTEGER NOT NULL,
              original_audio_sha256 TEXT NOT NULL,
              director_comparison_note TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(project_id,actor_id,performance_id,approval_revision)
            );
            CREATE INDEX IF NOT EXISTS nvp_bible_voice_audio_owner
              ON nvp_bible_voice_take_approvals(
                project_id,original_audio_id,original_audio_revision);
            """)

    def _actor(self, pid, actor_id):
        _require_pid(pid)
        if type(actor_id) is not str or not HEX_ACTOR.fullmatch(actor_id):
            raise ValueError("Voice-cast actor must have a canonical StoryBible ActorID")
        entity = self.bible.get_entity(pid, actor_id)
        if entity["kind"] != "character" or entity["id"] != actor_id:
            raise PermissionError("A source voice cannot belong to a prop or different actor")
        return entity

    def _auth(self, event, operation, scope):
        exact = {"operation": operation, **scope}
        if not self._approve(event, exact):
            raise PermissionError("No director authorization for precise ActorID voice operation")

    def current(self, pid, actor_id):
        """Read authoritative ActorID voice, including full immutable recast history."""
        actor = self._actor(pid, actor_id)
        with self.studio._connection() as db:
            rows = [dict(r) for r in db.execute(
                """SELECT * FROM nvp_bible_voice_casts
                   WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision""", (pid,actor_id))]
        return {
            "format": VOICE_FORMAT,
            "project_id": pid, "actor_id": actor_id,
            "actor_name": actor["name"],
            "current": rows[-1] if rows else None,
            "cast_history": rows,
            "approved_spoken_audio_not_assumed_from_cast": True,
            "acoustic_same_speaker_automatically_verified": False,
            "effect": "read",
        }

    def performance_candidates(self, pid, actor_id):
        """Read-only list: original actor performances needing voice review."""
        self._actor(pid,actor_id)
        entries=[]
        for item in self.index.list_objects(pid,kind="performance")[:512]:
            original=self.index.read_revision(
                pid,item["object_id"],item["head_revision"])
            doc=original["data"]
            if (original["kind"]!="performance" or
                    doc.get("format")!=PERFORMANCE_FORMAT or
                    doc.get("production_bible",{}).get("actor_id")!=actor_id or
                    not doc.get("recorded_voice_source")):
                continue
            sound=doc["recorded_voice_source"]
            source=self.index.read_revision(
                pid,sound["audio_id"],sound["audio_revision"])
            if source["kind"]!="audio" or source["document_sha256"]!=sound["audio_sha256"]:
                raise PermissionError("Original candidate voice source no longer resolves")
            with self.studio._connection() as db:
                latest=db.execute(
                    """SELECT approval_revision,voice_id,voice_cast_revision
                       FROM nvp_bible_voice_take_approvals
                       WHERE project_id=? AND actor_id=? AND performance_id=?
                       ORDER BY approval_revision DESC LIMIT 1""",
                    (pid,actor_id,item["object_id"])).fetchone()
            source_samples=RecordedSoundSources(self.index).describe(
                pid,sound["audio_id"],sound["audio_revision"])["data"]["sample_count"]
            entries.append({
                "source_sample_count":source_samples,
                "approved_voice_id":(latest["voice_id"] if latest else None),
                "voice_cast_revision":(latest["voice_cast_revision"] if latest else None),
                "latest_approval_revision":(latest["approval_revision"] if latest else 0),
                "performance_id":item["object_id"],
                "performance_document_sha256":original["document_sha256"],
                "source_audio_id":sound["audio_id"],
                "source_audio_revision":sound["audio_revision"],
                "source_audio_sha256":sound["audio_sha256"],
                "script_line_id":doc["script_line_id"],
                "script_line_text":doc["script_line_text"],
                "source_take_id":doc["source_take_id"],
                "source_take_sha256":doc["source_take_sha256"],
                "recorded_source_not_approved_voice":True,
            })
        return {
            "format":"nvp.film03.voice_candidate_audition_catalog.v1",
            "project_id":pid,"actor_id":actor_id,"candidates":entries,
            "unlisted_sources_may_exist_beyond_first_512":len(entries)>=512,
            "no_automatic_voice_approval":True,
        }

    def _original_audio(self, pid, source_id, revision):
        _id(source_id, "original reference/recorded audio identity")
        if _rev(revision, "audio source") < 1:
            raise ValueError("Original audio revision must be positive")
        audio = RecordedSoundSources(self.index)
        source = audio.describe(pid,source_id,revision)
        count=source["data"]["sample_count"]
        if count < 1:
            raise RuntimeError("Original PCM must contain real audio samples")
        first=audio.read(pid,source_id,revision,0,min(1024,count))
        end_first=max(0,count-1024)
        last=audio.read(pid,source_id,revision,end_first,
                        min(1024,count-end_first))
        return source,hashlib.sha256(first+last).hexdigest()

    def cast_voice(self, pid, actor_id, *, voice_id,
                   reference_audio_id, reference_audio_revision,
                   expected_cast_revision, director_review_note,
                   voice_recast_reason="", creator_event):
        """Director enrolls ONE stable VoiceID + anchor for a character.

        For a genuine change of voice, choose a NEW VoiceID, do not silently
        mutate what the old VoiceID means. Merely linking a source blob,
        naming a voice, or a model claiming similarity is NOT approval.
        """
        self._actor(pid,actor_id)
        _id(voice_id,"approved VoiceID")
        if not voice_id.startswith("Voice_"):
            raise ValueError("VoiceID must be an explicit Voice_ production identity")
        _rev(expected_cast_revision,"voice casting")
        note=_note(director_review_note)
        if type(voice_recast_reason) is not str or len(voice_recast_reason)>MAX_REVIEW_NOTE:
            raise ValueError("Invalid director voice-recast reason")
        reference,excerpt=self._original_audio(
            pid,reference_audio_id,reference_audio_revision)
        source_sha=reference["document_sha256"]
        scope={
            "project_id":pid,"actor_id":actor_id,"voice_id":voice_id,
            "reference_audio_id":reference_audio_id,
            "reference_audio_revision":reference_audio_revision,
            "reference_audio_sha256":source_sha,
            "reference_excerpt_sha256":excerpt,
            "expected_cast_revision":expected_cast_revision,
            "director_review_note":note,
            "voice_recast_reason":voice_recast_reason.strip(),
        }
        self._auth(creator_event,"film03_cast_actor_voice_identity",scope)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            actor=db.execute(
                "SELECT kind FROM bible_entities WHERE project_id=? AND id=?",
                (pid,actor_id)).fetchone()
            if actor is None or actor["kind"]!="character":
                raise PermissionError("ActorID was removed or is not a castable character")
            previous=db.execute(
                """SELECT * FROM nvp_bible_voice_casts
                   WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            head=previous["cast_revision"] if previous else 0
            if head != expected_cast_revision:
                raise RuntimeError("Voice cast changed; reload before director decision")
            owned=db.execute(
                """SELECT DISTINCT actor_id FROM nvp_bible_voice_casts
                   WHERE project_id=? AND voice_id=?""",(pid,voice_id)).fetchall()
            if any(x["actor_id"]!=actor_id for x in owned):
                raise PermissionError("VoiceID already assigned to another ActorID")
            if previous:
                if previous["voice_id"]==voice_id:
                    if (previous["reference_audio_sha256"]!=source_sha or
                            previous["reference_audio_id"]!=reference_audio_id or
                            previous["reference_audio_revision"]!=reference_audio_revision):
                        raise PermissionError(
                            "An existing VoiceID's acoustic reference is immutable; recast with NEW VoiceID")
                else:
                    if not _review_reason(voice_recast_reason):
                        raise PermissionError("Voice recast needs an explicit director reason")
                    if previous["reference_audio_sha256"]==source_sha:
                        raise PermissionError(
                            "New VoiceID must use a different immutable original voice reference")
            elif voice_recast_reason:
                raise ValueError("First voice cast is not a recast")
            # Reference source bytes are immutable and SHA-addressed.
            confirmed=db.execute(
                """SELECT document_sha FROM film_object_revisions
                   WHERE project_id=? AND object_id=? AND revision=?""",
                (pid,reference_audio_id,reference_audio_revision)).fetchone()
            if confirmed is None or confirmed["document_sha"]!=source_sha:
                raise RuntimeError("Voice identity reference changed during commit")
            # Avoid silently authorizing the same reference clip for a
            # different voice/person. A real alternate character needs a
            # separately approved recording and identity.
            reused=db.execute(
                """SELECT DISTINCT actor_id FROM nvp_bible_voice_casts
                   WHERE project_id=? AND reference_audio_sha256=?""",
                (pid,source_sha)).fetchall()
            if any(x["actor_id"]!=actor_id for x in reused):
                raise PermissionError("Reference PCM already belongs to another ActorID")
            db.execute(
                """INSERT INTO nvp_bible_voice_casts
                   (project_id,actor_id,cast_revision,voice_id,
                    reference_audio_id,reference_audio_revision,
                    reference_audio_sha256,reference_excerpt_sha256,
                    reference_sample_count,director_review_note,voice_recast_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,actor_id,head+1,voice_id,
                 reference_audio_id,reference_audio_revision,source_sha,
                 excerpt,reference["data"]["sample_count"],note,
                 voice_recast_reason.strip()))
        return self.current(pid,actor_id)

    def approve_delivery(self, pid, actor_id, performance_id, *,
                         voice_id, expected_cast_revision,
                         expected_approval_revision=0, reference_audio_sha256,
                         director_comparison_note, creator_event):
        """Human-review the EXACT performance source against VoiceID's anchor.

        A new PCM clip is never assumed to have the right timbre merely
        because the AI labeled it with a VoiceID. It must have an explicit
        director comparison decision tied to BOTH exact source SHAs.
        """
        self._actor(pid,actor_id)
        _id(performance_id,"approved recorded voice performance")
        _id(voice_id,"cast voice identity")
        _sha(reference_audio_sha256)
        _rev(expected_cast_revision,"voice cast")
        _rev(expected_approval_revision,"approved delivery")
        note=_note(director_comparison_note)
        cast=self.current(pid,actor_id)["current"]
        if (cast is None or cast["cast_revision"]!=expected_cast_revision or
                cast["voice_id"]!=voice_id or
                cast["reference_audio_sha256"]!=reference_audio_sha256):
            raise PermissionError("Actor voice assignment/anchor differs from director request")
        performance=self.index.read_revision(pid,performance_id,1)
        pd=performance["data"]
        if (performance["kind"]!="performance" or
                pd.get("format")!=PERFORMANCE_FORMAT or
                pd["production_bible"]["actor_id"]!=actor_id or
                pd["recorded_voice_source"] is None):
            raise PermissionError("Wrong actor or unrecorded performance")
        audio_ref=pd["recorded_voice_source"]
        recording,_=self._original_audio(
            pid,audio_ref["audio_id"],audio_ref["audio_revision"])
        if recording["document_sha256"]!=audio_ref["audio_sha256"]:
            raise PermissionError("Performance references changed original voice bytes")
        scope={
            "project_id":pid, "actor_id":actor_id,"voice_id":voice_id,
            "voice_cast_revision":expected_cast_revision,
            "reference_audio_sha256":reference_audio_sha256,
            "performance_id":performance_id,
            "performance_document_sha256":performance["document_sha256"],
            "original_audio_id":audio_ref["audio_id"],
            "original_audio_revision":audio_ref["audio_revision"],
            "original_audio_sha256":recording["document_sha256"],
            "expected_approval_revision":expected_approval_revision,
            "director_comparison_note":note,
        }
        self._auth(creator_event,"film03_approve_actor_voice_performance",scope)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            latest_cast=db.execute(
                """SELECT voice_id,cast_revision,reference_audio_sha256
                   FROM nvp_bible_voice_casts
                   WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            if (latest_cast is None or
                    latest_cast["voice_id"]!=voice_id or
                    latest_cast["cast_revision"]!=expected_cast_revision or
                    latest_cast["reference_audio_sha256"]!=reference_audio_sha256):
                raise RuntimeError("Voice identity recast during approval; retry")
            prior=db.execute(
                """SELECT MAX(approval_revision) AS r
                   FROM nvp_bible_voice_take_approvals
                   WHERE project_id=? AND actor_id=? AND performance_id=?""",
                (pid,actor_id,performance_id)).fetchone()
            old_revision=prior["r"] or 0
            if old_revision!=expected_approval_revision:
                raise RuntimeError("Voice performance approval changed; explicit revision required")
            for oid,rev,sha in (
                    (performance_id,1,performance["document_sha256"]),
                    (audio_ref["audio_id"],audio_ref["audio_revision"],
                     recording["document_sha256"])):
                saved=db.execute(
                    """SELECT document_sha FROM film_object_revisions
                       WHERE project_id=? AND object_id=? AND revision=?""",
                    (pid,oid,rev)).fetchone()
                if saved is None or saved["document_sha"]!=sha:
                    raise RuntimeError("Original performance/audio source changed during approval")
            owners=db.execute(
                """SELECT DISTINCT actor_id,voice_id FROM nvp_bible_voice_take_approvals
                   WHERE project_id=? AND original_audio_id=?
                     AND original_audio_revision=?""",
                (pid,audio_ref["audio_id"],audio_ref["audio_revision"])).fetchall()
            if any(row["actor_id"]!=actor_id for row in owners):
                raise PermissionError("One recorded voice clip cannot serve two different actors")
            if any(row["voice_id"]!=voice_id for row in owners):
                raise PermissionError(
                    "A recording already approved for another VoiceID cannot be relabeled; record new voice source")
            db.execute(
                """INSERT INTO nvp_bible_voice_take_approvals
                   (project_id,actor_id,performance_id,approval_revision,
                    voice_id,voice_cast_revision,reference_audio_sha256,
                    performance_document_sha256,original_audio_id,
                    original_audio_revision,original_audio_sha256,
                    director_comparison_note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,actor_id,performance_id,old_revision+1,voice_id,
                 expected_cast_revision,reference_audio_sha256,
                 performance["document_sha256"],audio_ref["audio_id"],
                 audio_ref["audio_revision"],recording["document_sha256"],note))
        return self.verify_delivery(pid,actor_id,performance_id,require_current_cast=True)

    def verify_delivery(self, pid, actor_id, performance_id, *,
                        require_current_cast=True):
        """Fail closed if any clip is attached to the wrong current VoiceID."""
        self._actor(pid,actor_id)
        _id(performance_id,"selected original voice performance")
        with self.studio._connection() as db:
            cast=db.execute(
                """SELECT * FROM nvp_bible_voice_casts
                   WHERE project_id=? AND actor_id=?
                   ORDER BY cast_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            approved=db.execute(
                """SELECT * FROM nvp_bible_voice_take_approvals
                   WHERE project_id=? AND actor_id=? AND performance_id=?
                   ORDER BY approval_revision DESC LIMIT 1""",
                (pid,actor_id,performance_id)).fetchone()
        if cast is None or approved is None:
            raise PermissionError("No explicitly approved ActorID VoiceID/recorded performance")
        if (require_current_cast and
                (cast["voice_id"]!=approved["voice_id"] or
                 cast["cast_revision"]!=approved["voice_cast_revision"] or
                 cast["reference_audio_sha256"]!=approved["reference_audio_sha256"])):
            raise PermissionError("Recorded voice is from prior VoiceID, not current actor's voice")
        p=self.index.read_revision(pid,performance_id,1)
        if (p["kind"]!="performance" or
                p["data"].get("format")!=PERFORMANCE_FORMAT or
                p["document_sha256"]!=approved["performance_document_sha256"] or
                p["data"]["production_bible"]["actor_id"]!=actor_id):
            raise PermissionError("Voice approval no longer matches original actor/performance")
        sound=p["data"]["recorded_voice_source"]
        if (sound is None or sound["audio_id"]!=approved["original_audio_id"] or
                sound["audio_revision"]!=approved["original_audio_revision"] or
                sound["audio_sha256"]!=approved["original_audio_sha256"]):
            raise PermissionError("Recorded actor voice does not match selected PCM source")
        audio,excerpt=self._original_audio(
            pid,sound["audio_id"],sound["audio_revision"])
        if audio["document_sha256"]!=approved["original_audio_sha256"]:
            raise PermissionError("Original voiced performance audio SHA changed")
        reference,_=self._original_audio(
            pid,cast["reference_audio_id"],cast["reference_audio_revision"])
        if reference["document_sha256"]!=cast["reference_audio_sha256"]:
            raise PermissionError("Canonical VoiceID reference recording changed")
        return {
            "format": DELIVERY_FORMAT,
            "project_id":pid,"actor_id":actor_id,
            "voice_id":approved["voice_id"],
            "cast_revision":approved["voice_cast_revision"],
            "approved_performance_id":performance_id,
            "approval_revision":approved["approval_revision"],
            "reference_audio_sha256":approved["reference_audio_sha256"],
            "original_audio_id":sound["audio_id"],
            "original_audio_revision":sound["audio_revision"],
            "original_audio_sha256":sound["audio_sha256"],
            "performance_document_sha256":p["document_sha256"],
            "director_reviewed_against_reference":True,
            "same_voice_acoustically_measured":False,
            "automatic_voice_identity_guess":False,
            "source_original_preserved":True,
            "effect":"read",
        }


def _review_reason(text):
    return type(text) is str and MIN_REVIEW_NOTE <= len(text.strip()) <= MAX_REVIEW_NOTE
