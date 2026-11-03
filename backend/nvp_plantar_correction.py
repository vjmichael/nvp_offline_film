"""NVP PROD-06E2C3: revisioned, bounded real-mesh contact corrections.

Does not infer anatomical identity, and will not turn an engineering fixture
vertex into a medically certified heel or metatarsal. Authoritative source:
approved imported character, 06E2A leg mapping, 06E2B ankle IK, 06E2C2
creator-chosen original mesh vertices and exact floor.
"""
from __future__ import annotations

import json
import math

from backend.nvp_plantar import PlantarContactPlan, ROLES, SIDES, _num
from backend.nvp_production_scene import compact, digest

MAX_ITERS = 8
MAX_ADJUST_M = 0.03
FORMAT = "nvp.plantar.correction.approved.v1"


def solve_vertical_contact(gaps_m, penetration_m, max_gap_m, max_adjust_m,
                           target_gap_m=0.001):
    """Find bounded normal displacement satisfying ALL selected contact roles.

    Gaps are current signed distances to the floor; positive means hovering.
    A single leg displacement cannot resolve widely separated heel/ball/toe
    gaps. Refuse in that case; do not inflate the acceptance tolerances.
    """
    if type(gaps_m) is not dict or not gaps_m or not set(gaps_m).issubset(ROLES):
        raise ValueError("Explicit nonempty subset of measured plantar markers required")
    p = _num(penetration_m, "penetration limit", 0, .03)
    q = _num(max_gap_m, "gap limit", 0, .05)
    a = _num(max_adjust_m, "correction budget", 0, MAX_ADJUST_M)
    target = _num(target_gap_m, "contact target", 0, q)
    checked = {role: _num(g, role + " floor gap", -5, 5) for role, g in gaps_m.items()}
    low = max([-a] + [-p - gap for gap in checked.values()])
    high = min([a] + [q - gap for gap in checked.values()])
    if low > high + 1e-9:
        raise RuntimeError("Author-selected plantar contacts cannot share a bounded vertical correction")
    if low > high:
        low = high = (low + high)/2
    desired = target - sum(checked.values())/len(checked)
    return max(low, min(high, desired))


def validate_correction_config(config, plantar_package):
    if type(config) is not dict or set(config) != {"actors"}:
        raise ValueError("Correction plan needs an explicit actor roster")
    approved = plantar_package["plantar"]["plan"]["actors"]
    actors = config["actors"]
    if type(actors) is not dict or set(actors) != set(approved):
        raise ValueError("Correction actor roster does not match current approved plantar geometry")
    checked = {}
    for rid, item in actors.items():
        if type(item) is not dict or set(item) != {
            "max_ankle_delta_m", "max_iterations", "target_clearance_m", "max_joint_delta_deg"}:
            raise ValueError("Require correction ceiling, iteration count and desired clearance")
        bound = _num(item["max_ankle_delta_m"], "ankle correction", 0.0001, MAX_ADJUST_M)
        n = item["max_iterations"]
        if type(n) is not int or not 1 <= n <= MAX_ITERS:
            raise ValueError("Contact iteration budget must be an explicit integer 1..8")
        gap = _num(item["target_clearance_m"], "desired floor clearance",
                   0, min(approved[rid]["max_gap_m"], .02))
        angle = _num(item["max_joint_delta_deg"],"maximum pose joint angle change",1,60)
        checked[rid] = {"max_ankle_delta_m": bound,
                        "max_iterations": n, "target_clearance_m": gap,
                        "max_joint_delta_deg": angle}
    return {"actors": checked}


class PlantarCorrectionPlan:
    """Approvals for measured marker-driven leg IK, distinct from anatomy."""
    def __init__(self, studio):
        self.studio = studio
        self.plantar = PlantarContactPlan(studio)
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_plantar_correction (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, upstream_sha TEXT NOT NULL,
                plan_json TEXT NOT NULL, approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_plantar_correction_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))""")

    def _context(self, pid, sid):
        pkg = self.plantar.export(pid, sid)
        return pkg, digest([pkg["plantar"], pkg["foot_lock"],pkg["leg_identity"],pkg["take"]])

    def _row(self, db, pid, sid):
        row = db.execute("SELECT * FROM prod_plantar_correction WHERE project_id=? AND scene_id=?",
                         (pid, sid)).fetchone()
        if row is None:
            raise KeyError("No correction plan for this project and scene")
        return dict(row)

    def create(self, pid, sid):
        _, source = self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM prod_plantar_correction WHERE project_id=? AND scene_id=?",
                          (pid,sid)).fetchone():
                raise RuntimeError("Existing correction must not be overwritten")
            db.execute("INSERT INTO prod_plantar_correction VALUES (?,?,?,?,?,?,?)",
                       (pid,sid,0,"draft",source,compact({}),None))
            db.execute("INSERT INTO prod_plantar_correction_history VALUES (?,?,?,?,?)",
                       (pid,sid,0,"create",compact({})))
        return self.read(pid,sid)

    def read(self, pid, sid):
        _, source = self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._row(db,pid,sid)
        return {"revision":row["revision"],"status":row["status"],
                "stale":row["upstream_sha"]!=source,
                "approval_sha":row["approval_sha"],"plan":json.loads(row["plan_json"])}

    def configure(self, pid, sid, config, expected_revision):
        pkg,source=self._context(pid,sid)
        plan=validate_correction_config(config,pkg)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=source or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Correction draft is stale, approved or revision-conflicted")
            revision=row["revision"]+1
            db.execute("UPDATE prod_plantar_correction SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?",
                       (revision,compact(plan),pid,sid))
            db.execute("INSERT INTO prod_plantar_correction_history VALUES (?,?,?,?,?)",
                       (pid,sid,revision,"configure",compact(plan)))
        return self.read(pid,sid)

    def approve(self, pid, sid, expected_revision):
        pkg,source=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,pid,sid)
            if (row["status"]!="draft" or row["upstream_sha"]!=source or
                type(expected_revision) is not int or row["revision"]!=expected_revision):
                raise RuntimeError("Correction requires an unmodified current draft")
            current=json.loads(row["plan_json"])
            if not current:raise RuntimeError("Cannot approve an empty correction plan")
            plan=validate_correction_config(current,pkg)
            receipt=digest([source,plan])
            revision=row["revision"]+1
            db.execute("UPDATE prod_plantar_correction SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?",
                       (revision,"approved",receipt,pid,sid))
            db.execute("INSERT INTO prod_plantar_correction_history VALUES (?,?,?,?,?)",
                       (pid,sid,revision,"approve",compact({"approval_sha":receipt})))
        return self.read(pid,sid)

    def export(self, pid, sid):
        pkg,source=self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._row(db,pid,sid)
        plan=json.loads(row["plan_json"])
        if (row["status"]!="approved" or row["upstream_sha"]!=source or
            row["approval_sha"]!=digest([source,plan])):
            raise RuntimeError("Stale, absent or altered correction authorization")
        return {**pkg, "plantar_correction":{
            "format":FORMAT,"upstream_sha":source,"approval_sha":row["approval_sha"],
            "plan":plan,"anatomical_sole_certified":False,
            "scope":"Exact artist-selected skinned vertices against approved flat NVP_FLOOR, ankle IK only"}}
