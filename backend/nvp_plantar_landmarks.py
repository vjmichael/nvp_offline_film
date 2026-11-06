"""PROD-06E2C3B: auditable foot surface landmark attachment, not anatomy inference.

Authoritative anatomical roles are *plantar* heel, first metatarsal head,
fifth metatarsal head and hallux pad. A mocap landmark on the foot dorsum
is NOT automatically a pressure-bearing plantar surface marker.

This module stores provenance and geometrically verifies selected vertices.
It cannot certify the expert's actual anatomical judgment. A separately
reviewed source and data-use rights remain required for production use.
"""
from __future__ import annotations
import json
import math

from backend.nvp_plantar_correction import PlantarCorrectionPlan
from backend.nvp_production_scene import compact, digest

LANDMARKS=("heel_pad","mt1_pad","mt5_pad","hallux_pad")
SIDES=("left","right")
MAX_VERTEX=250_000
FORMAT="nvp.foot.attachment.v1"


def _str(v, what, maximum=160):
    if type(v) is not str or not 1<=len(v.strip())<=maximum or "\x00" in v:
        raise ValueError(what+" must be a nonempty bounded identifier")
    return v


def _sha(v, what):
    if type(v) is not str or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError(what+" requires a real lowercase SHA256 digest")
    return v


def _vector(v,what):
    if type(v) not in (list,tuple) or len(v)!=3 or any(
        type(x) not in (int,float) or not math.isfinite(x) or abs(x)>10000 for x in v):
        raise ValueError(what+" requires a finite 3-vector")
    return tuple(float(x) for x in v)


def _distance(a,b):
    return math.dist(a,b)


def validate_landmarks(value, correction_package):
    """Strict distinct labels and external attestation; fixture cannot be approved."""
    if type(value) is not dict or set(value)!={"evidence","actors"}:
        raise ValueError("Foot annotation requires evidence and exact approved actors")
    ev=value["evidence"]
    if type(ev) is not dict or set(ev)!={
        "reference_id","reference_sha256","license_id","annotator_id",
        "reviewer_id","method","origin"}:
        raise ValueError("Required independent anatomical annotation evidence missing")
    evidence={k:_str(v,"Evidence "+k,256) for k,v in ev.items() if k!="reference_sha256"}
    evidence["reference_sha256"]=_sha(ev["reference_sha256"],"Anatomical reference")
    if evidence["origin"]!="independently_reviewed_annotation":
        raise ValueError("Automatically proposed fixture vertices are not anatomically reviewed")
    if evidence["annotator_id"]==evidence["reviewer_id"]:
        raise ValueError("An independent person must review annotated foot geometry")
    if evidence["method"] not in ("manual_mesh_landmark_review","registered_anatomical_scan"):
        raise ValueError("Unknown anatomical labeling method")
    approved={x["instance_id"] for x in correction_package["leg_identity"]["actors"]}
    actors=value["actors"]
    if type(actors) is not dict or not approved or set(actors)!=approved:
        raise ValueError("Annotation actor roster must exactly match approved real rig")
    out={"format":FORMAT,"evidence":evidence,"actors":{}}
    for rid in sorted(approved):
        item=actors[rid]
        if type(item) is not dict or set(item)!=set(SIDES):
            raise ValueError("Both sides of the foot must have reviewed labels")
        used=set();sides={}
        for side in SIDES:
            cfg=item[side]
            if type(cfg) is not dict or set(cfg)!={"mesh_name","vertex_indices"}:
                raise ValueError("Side requires exact mesh and four landmark vertices")
            name=_str(cfg["mesh_name"],"Mesh name",128)
            points=cfg["vertex_indices"]
            if type(points) is not dict or set(points)!=set(LANDMARKS):
                raise ValueError("Heel pad, MT1, MT5 and hallux pad are all required")
            if any(type(x) is not int or not 0<=x<MAX_VERTEX for x in points.values()):
                raise ValueError("Anatomical mesh vertex index invalid")
            if len(set(points.values()))!=4:
                raise ValueError("Anatomical foot roles may not share vertices")
            for idx in points.values():
                key=(name,idx)
                if key in used:raise ValueError("Bilateral feet reuse the same source mesh vertex")
                used.add(key)
            sides[side]={"mesh_name":name,"vertex_indices":dict(points)}
        out["actors"][rid]=sides
    return out


def analyze_imported_landmarks(report, approved_annotation, package):
    """Independent shape tests; does not assert biomechanical accuracy.

    The separate Blender survey must inspect *evaluated skinned mesh* points
    and exact anatomical source+review digest, not a text-only annotation.
    """
    if type(report) is not dict or report.get("format")!="nvp.foot.attachment.observation.v1":
        raise ValueError("Imported anatomy observation format mismatch")
    if report.get("annotation_sha")!=digest(approved_annotation):
        raise ValueError("Blender report belongs to a different annotation revision")
    if report.get("leg_identity_sha")!=package["leg_identity"]["approval_sha"]:
        raise ValueError("Blender report belongs to a different approved leg chain")
    if report.get("correction_sha")!=package["plantar_correction"]["approval_sha"]:
        raise ValueError("Blender report belongs to an outdated contact revision")
    actors=report.get("actors")
    if type(actors) is not dict or set(actors)!=set(approved_annotation["actors"]):
        raise ValueError("Geometry report does not cover the exact actor roster")
    summary={}
    for rid,data in actors.items():
        source=next(x for x in package["leg_identity"]["actors"] if x["instance_id"]==rid)
        if type(data) is not dict or data.get("asset_sha256")!=source["asset_sha256"]:
            raise ValueError("Anatomical mesh source SHA changed")
        sides=data.get("sides")
        if type(sides) is not dict or set(sides)!=set(SIDES):
            raise ValueError("Both feet must be independently observed")
        detail={}
        for side in SIDES:
            payload=sides[side]
            if type(payload) is not dict or set(payload)!={"ankle_world_m","toe_joint_world_m","points"}:
                raise ValueError("Anatomical geometry report incomplete")
            ankle=_vector(payload["ankle_world_m"],"ankle")
            toe=_vector(payload["toe_joint_world_m"],"toe joint")
            forward=tuple(b-a for a,b in zip(ankle,toe))
            length=math.sqrt(sum(x*x for x in forward))
            if not .02<=length<=.6:raise ValueError("Foot joint vector implausible")
            axis=tuple(x/length for x in forward)
            points=payload["points"]
            if type(points) is not dict or set(points)!=set(LANDMARKS):
                raise ValueError("Four independently observed plantar labels required")
            locations={}
            for label,marker in points.items():
                if type(marker) is not dict or set(marker)!={"position_world_m","normal_world"}:
                    raise ValueError("Anatomical world landmark requires position and surface normal")
                pos=_vector(marker["position_world_m"],label)
                normal=_vector(marker["normal_world"],label+" normal")
                norm=math.sqrt(sum(x*x for x in normal))
                if not .9<=norm<=1.1:raise ValueError("Surface normal is unnormalized")
                # This conservative condition catches obvious top-of-foot
                # landmarks in a nearly upright previsualized stance. Tilted
                # and upside-down actors require a different reviewed protocol.
                if normal[2] > .35:
                    raise ValueError(label+" faces upward; not a validated plantar underside")
                locations[label]=pos
            projected={k:sum((p-a)*v for p,a,v in zip(pos,ankle,axis))
                       for k,pos in locations.items()}
            heel=projected["heel_pad"]
            first=projected["mt1_pad"]
            fifth=projected["mt5_pad"]
            tip=projected["hallux_pad"]
            if not (heel+.02<min(first,fifth) and max(first,fifth)+.01<tip):
                raise ValueError("Heel / metatarsal / hallux longitudinal order contradicts foot anatomy")
            if not .065<=_distance(locations["heel_pad"],locations["hallux_pad"])<=.5:
                raise ValueError("Heel-to-hallux dimension anatomically implausible")
            width=_distance(locations["mt1_pad"],locations["mt5_pad"])
            if not .02<=width<=.18:
                raise ValueError("Medial/lateral metatarsal breadth anatomically implausible")
            detail[side]={"longitudinal_m":{k:round(v,8) for k,v in projected.items()},
                          "mt_head_spacing_m":round(width,8),
                          "heel_to_hallux_m":round(_distance(locations["heel_pad"],
                                                              locations["hallux_pad"]),8)}
        summary[rid]=detail
    return {"format":"nvp.foot.attachment.geometry_review.v1",
            "annotation_sha":digest(approved_annotation),
            "native_report_sha":digest(report),
            "actors":summary,
            "attached_geometry_valid":True,
            "clinical_anatomy_certified":False,
            "source_rights_cleared_for_distribution":False,
            "limitations":"Geometry and reviewer records are not independent verification of anatomical expertise, clinical truth, or rights"}


class FootAnatomyAttachment:
    """Keep reviewed anatomy separate from automatically generated fixture labels."""
    def __init__(self,studio):
        self.studio=studio
        self.correction=PlantarCorrectionPlan(studio)
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_foot_anatomy (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, upstream_sha TEXT NOT NULL,
                annotation_json TEXT NOT NULL, observation_json TEXT NOT NULL,
                receipt_sha TEXT, PRIMARY KEY(project_id,scene_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_foot_anatomy_history(
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))""")

    def _context(self,pid,sid):
        pkg=self.correction.export(pid,sid)
        return pkg,digest([pkg["plantar_correction"],pkg["leg_identity"],pkg["plantar"]])

    def _get(self,db,pid,sid):
        row=db.execute("SELECT * FROM prod_foot_anatomy WHERE project_id=? AND scene_id=?",(pid,sid)).fetchone()
        if row is None:raise KeyError("No foot anatomy attachment in this project/scene")
        return dict(row)

    def create(self,pid,sid):
        _,source=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM prod_foot_anatomy WHERE project_id=? AND scene_id=?",(pid,sid)).fetchone():
                raise RuntimeError("Cannot discard an existing anatomical annotation revision")
            db.execute("INSERT INTO prod_foot_anatomy VALUES(?,?,?,?,?,?,?,?)",
                       (pid,sid,0,"draft",source,"{}","{}",None))
            db.execute("INSERT INTO prod_foot_anatomy_history VALUES(?,?,?,?,?)",
                       (pid,sid,0,"create","{}"))
        return self.read(pid,sid)

    def read(self,pid,sid):
        _,source=self._context(pid,sid)
        with self.studio._connection() as db:row=self._get(db,pid,sid)
        return {"revision":row["revision"],"status":row["status"],
                "stale":row["upstream_sha"]!=source,"receipt_sha":row["receipt_sha"],
                "attachment":json.loads(row["annotation_json"]),
                "geometry_observed":bool(json.loads(row["observation_json"]))}

    def configure(self,pid,sid,value,expected_revision):
        pkg,source=self._context(pid,sid)
        checked=validate_landmarks(value,pkg)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._get(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=source or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Foot annotation stale, approved or revised concurrently")
            revision=row["revision"]+1
            db.execute("UPDATE prod_foot_anatomy SET revision=?,annotation_json=?,observation_json=? WHERE project_id=? AND scene_id=?",
                       (revision,compact(checked),"{}",pid,sid))
            db.execute("INSERT INTO prod_foot_anatomy_history VALUES(?,?,?,?,?)",
                       (pid,sid,revision,"configure",compact({"attachment_sha":digest(checked)})))
        return self.read(pid,sid)

    def attest_imported_geometry(self,pid,sid,report,expected_revision):
        """Developer host only: report must originate from separate native survey."""
        pkg,source=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._get(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=source or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Native geometry evidence out of revision or scope")
            annotation=json.loads(row["annotation_json"])
            if not annotation:raise RuntimeError("Anatomical points not authored")
            checked=analyze_imported_landmarks(report,annotation,pkg)
            revision=row["revision"]+1
            db.execute("UPDATE prod_foot_anatomy SET revision=?,observation_json=? WHERE project_id=? AND scene_id=?",
                       (revision,compact(checked),pid,sid))
            db.execute("INSERT INTO prod_foot_anatomy_history VALUES(?,?,?,?,?)",
                       (pid,sid,revision,"native_geometry",compact({"receipt_sha":digest(checked)})))
        return self.read(pid,sid)

    def approve_attachment(self,pid,sid,expected_revision):
        pkg,source=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._get(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=source or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Anatomical attachment approval denied: stale or conflicted")
            annotation=json.loads(row["annotation_json"])
            proof=json.loads(row["observation_json"])
            if (not proof or proof.get("attached_geometry_valid") is not True or
                proof.get("annotation_sha")!=digest(annotation)):
                raise RuntimeError("Anatomical geometry must pass actual independent Blender survey")
            receipt=digest([source,annotation,proof])
            revision=row["revision"]+1
            db.execute("UPDATE prod_foot_anatomy SET revision=?,status=?,receipt_sha=? WHERE project_id=? AND scene_id=?",
                       (revision,"geometry_attested",receipt,pid,sid))
            db.execute("INSERT INTO prod_foot_anatomy_history VALUES(?,?,?,?,?)",
                       (pid,sid,revision,"approve_geometry",compact({"receipt_sha":receipt})))
        return self.read(pid,sid)

    def export(self,pid,sid):
        pkg,source=self._context(pid,sid)
        with self.studio._connection() as db:row=self._get(db,pid,sid)
        annotation=json.loads(row["annotation_json"])
        proof=json.loads(row["observation_json"])
        if (row["upstream_sha"]!=source or row["status"]!="geometry_attested" or
            row["receipt_sha"]!=digest([source,annotation,proof])):
            raise RuntimeError("Anatomical attachment missing, stale or unverified")
        return {**pkg,"anatomy_attachment":{
            "format":FORMAT,"upstream_sha":source,"receipt_sha":row["receipt_sha"],
            "annotation":annotation,"native_geometry":proof,
            "clinical_anatomy_certified":False,"rights_cleared_for_distribution":False}}
