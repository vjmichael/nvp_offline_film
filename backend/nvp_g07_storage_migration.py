"""Authenticated, bounded migration of historic sealed-film section records.

Migration changes representation, never the canonical section digest, edit
revision, or HEAD authority. This is not a migration of the G03 database or
original media yet. Never remove an indexed/damaged encrypted object.
"""
import json
from backend.nvp_g06_filming import _json,_sha
from backend.nvp_g07_edit import _project
from backend.nvp_g07_sections import _check_sha,_number,HEX
from backend import nvp_g07_section_pages as pages
from backend.nvp_g03_windows_vault import VaultError

LIMIT=32


def _rows(db,pid,after):
    if after is not None and (type(after) is not str or not HEX.fullmatch(after)):
        raise ValueError('Invalid storage page')
    return list(db.execute('SELECT section_id,document_json,document_sha256 FROM g07_sections WHERE project_id=? AND section_id>? ORDER BY section_id LIMIT ?', (pid,after or '',LIMIT+1)))


def storage_status(service,pid,after=None):
    if not service._page_context(pid):raise PermissionError('Unlock the protected film first')
    def read(db,movie):
        revision,_=_project(db,pid,allow_paged=True);rows=_rows(db,pid,after);items=[]
        for row in rows[:LIMIT]:
            if service.access_guard:service.access_guard()
            ident,raw,digest=row
            status='needs_review'
            try:
                info=json.loads(raw)
                if info=={'format':pages.FORMAT,'sha256':digest}:
                    context=service._page_context(pid)
                    # Existing corruption and missing data are distinct; do
                    # not turn an unreadable/reparse path into a repair grant.
                    try:
                        target=pages._location(context['folder'],context['key'],digest,missing_directory=True)
                    except (VaultError,OSError):target=None
                    if target is not None and not target.exists() and not target.is_symlink():status='missing'
                    else:
                        service._section(db,pid,ident,digest);status='available'
                else:
                    service._section(db,pid,ident,digest);status='legacy_available'
            except (VaultError,ValueError,RuntimeError,KeyError,OSError):pass
            items.append({'section_id':ident,'status':status})
        return {'format':'nvp.g07.storage_status.v1','project_id':pid,'revision':revision,'items':items,'next_after':rows[LIMIT-1]['section_id'] if len(rows)>LIMIT else None,'media_verified':False,'render_approved':False}
    return service._run(pid,read)


def _review(service,db,pid,revision,after):
    current,_=_project(db,pid,allow_paged=True)
    if current!=_number(revision,1,15000):raise RuntimeError('Active edit changed')
    rows=_rows(db,pid,after);entries=[]
    for row in rows[:LIMIT]:
        if service.access_guard:service.access_guard()
        ident,raw,digest=row
        document,sha=service._verified(db,pid,ident,digest)
        if json.loads(raw).get('format')!=pages.FORMAT:
            if len(raw.encode('utf8'))>pages.MAX_BYTES or raw!=_json(document):raise VaultError('Legacy section is not canonical')
            entries.append({'section_id':ident,'sha256':sha})
    return {'format':'nvp.g07.section_migration.v1','project_id':pid,'revision':revision,'after':after,'entries':entries,'next_after':rows[LIMIT-1]['section_id'] if len(rows)>LIMIT else None}


def migration_review(service,pid,revision,after=None):
    if not service._page_context(pid):raise PermissionError('Unlock the protected film first')
    def read(db,movie):
        report=_review(service,db,pid,revision,after)
        return {**report,'approval_digest':_sha(_json(report).encode('utf8'))}
    return service._run(pid,read)


def migrate(service,pid,revision,after,approval_digest,*,human_approved=False):
    """Trusted host only. Exact reviewed batch; no browser-supplied authority."""
    if human_approved is not True or not service._page_context(pid):raise PermissionError('Director-approved protected migration required')
    _check_sha(approval_digest)
    def write(db,movie):
        report=_review(service,db,pid,revision,after)
        if _sha(_json(report).encode('utf8'))!=approval_digest:raise PermissionError('Review the current storage batch again')
        for entry in report['entries']:
            ident,sha=entry['section_id'],entry['sha256']
            doc,_=service._verified(db,pid,ident,sha)
            if service.access_guard:service.access_guard()
            pointer=pages.seal_page(raw=_json(doc),sha=sha,**service._page_context(pid))
            n=db.execute('UPDATE g07_sections SET document_json=? WHERE project_id=? AND section_id=? AND document_sha256=? AND document_json=?',(pointer,pid,ident,sha,_json(doc))).rowcount
            if n!=1:raise RuntimeError('Indexed original changed during migration')
            service._verified(db,pid,ident,sha)
        return {'project_id':pid,'revision':revision,'migrated':len(report['entries']),'next_after':report['next_after'],'render_approved':False}
    return service._run(pid,write,write=True)
