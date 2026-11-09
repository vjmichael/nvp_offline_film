"""USD-FILM-02M-F — only the installed NVP director bridge can save USD.

AI proposals and director drafts are data, never a user/AI OS grant.
The existing WO5→WO6 exact-origin bridge is the sole writer. No HTTP
source mutation and no alternate PyWebView/Blender instance is created.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.nvp_usd_film02m_f_authoring import OriginalDistrictDrafts

SHA=re.compile(r"[0-9a-f]{64}\Z")


class OriginalDistrictDesktopMixin:
    def _film02mf_confirm(self,scope):
        window=self._native_window()
        if (type(scope) is not dict or
            scope.get("operation")!=
                "nvp.film02m_f.commit_exact_original_district.v1" or
            type(scope.get("project_id")) is not str or
            type(scope.get("district_id")) is not str or
            not all(type(scope.get(k)) is str and SHA.fullmatch(scope[k])
                for k in ("original_source_plan_sha256",
                          "native_original_layer_source_sha256")) or
            type(scope.get("version")) is not int or
            type(scope.get("base_revision")) is not int or
            type(scope.get("generated_instances")) is not int or
            type(scope.get("manual_opinion_count")) is not int or
            type(scope.get("source_triangles_estimated")) is not int):
            return False
        message=(
            "NVP — Publish this original 3D film world revision?\n\n"
            "Project: "+scope["project_id"]+"\n"
            "Original district: "+scope["district_id"]+"\n"
            "Proposal ID: "+str(scope.get("draft_id"))+"\n"
            "Proposal version: "+str(scope["version"])+"\n"
            "Current approved base revision: "+str(scope["base_revision"])+"\n"
            "Existing source SHA: "+str(scope.get("base_source_sha256"))+"\n"
            "Exact proposed plan SHA: "+
                scope["original_source_plan_sha256"]+"\n"
            "Exact proposed native USD SHA: "+
                scope["native_original_layer_source_sha256"]+"\n"
            "Generated source buildings: "+
                str(scope["generated_instances"])+"\n"
            "Director edit opinions: "+
                str(scope["manual_opinion_count"])+"\n"
            "Budgeted source triangles: "+
                str(scope["source_triangles_estimated"])+"\n\n"
            "An AI draft is NOT an approval. This operation publishes ONE "
            "immutable original FilmIndex revision, preserves prior world "
            "revisions, and does NOT render or change actor Takes.\n\n"
            "Approve this exact current source and its director changes?")
        return window.create_confirmation_dialog(
            "NVP — Approve Original Building World",message) is True

    def _film02mf_service(self,pid):
        self._wo5_project(pid)
        workspace=self._wo5_state/"original-film02m-director-proposals"
        if workspace.is_symlink():
            raise PermissionError("Installed NVP original proposal store is not symlinkable")
        return OriginalDistrictDrafts(
            self.index,workspace,confirm=self._film02mf_confirm)

    def film02mf_catalog(self,project_id):
        return self._film02mf_service(project_id).catalog(project_id)

    def film02mf_propose(self,request):
        if (type(request) is not dict or set(request)!={
                "project_id","district_id","expected_revision",
                "params","proposed_by"}):
            raise PermissionError("Original 02M AI/director draft must be typed")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).create(
            pid,request["district_id"],
            expected_revision=request["expected_revision"],
            params=request["params"],proposed_by=request["proposed_by"])

    def film02mf_reopen(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Exact NVP original source draft reopen request")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).reopen(pid,request["draft_id"])

    def film02mf_preview(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id"}:
            raise PermissionError("Only original source scene draft preview")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).preview(pid,request["draft_id"])

    def film02mf_edit(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version","action"}:
            raise PermissionError("Source director layer accepts only one typed proposed action")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).edit(
            pid,request["draft_id"],request["version"],request["action"])

    def film02mf_undo(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Only exact proposal-version undo")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).undo(
            pid,request["draft_id"],request["version"])

    def film02mf_discard(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version"}:
            raise PermissionError("Only exact proposal-version discard")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).discard(
            pid,request["draft_id"],request["version"])

    def film02mf_commit(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","draft_id","version",
                "source_plan_sha256","usd_layer_root_sha256"}:
            raise PermissionError("Only exact verified source-locked native approval")
        pid=self._wo5_project(request["project_id"])
        return self._film02mf_service(pid).approve_and_commit(
            pid,request["draft_id"],request["version"],
            request["source_plan_sha256"],
            request["usd_layer_root_sha256"])
