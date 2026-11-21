"""NVP-owned conservative Lu capability registration gate.

This is a local catalog review / deny policy, not a Lu Core registry or an
authorization grant. NativeToolRegistry and original-user-turn authority remain
Lu-owned. NVP's creator authorization remains separately mandatory.
"""
from __future__ import annotations
from pathlib import Path
import json

READ_ONLY_IDS=frozenset({
    'nvp.film.project.read','nvp.film.scene.read',
    'nvp.film.picture.review.read',
})
HIGH_RISK_IDS=frozenset({'nvp.film.render.shot','nvp.film.edit.export'})


def review_catalog(catalog:Path,alignment:Path)->dict:
    """Assert strict correspondence; return NO registration authority."""
    caps=json.loads(Path(catalog).read_text('utf8'))
    native=json.loads(Path(alignment).read_text('utf8'))
    if caps.get('schema_status')!='draft_unregistered_no_permissions' or \
       native.get('status')!='DRAFT_UNREGISTERED_NOT_EFFECT_AUTHORIZED':
        raise PermissionError('Unreviewed Lu catalog status')
    records=caps.get('capabilities',[])
    mapping=native.get('mappings',[])
    if (len(records)!=8 or len(mapping)!=8 or
        len({c.get('id') for c in records})!=8 or
        {c.get('id') for c in records}!={c.get('id') for c in mapping}):
        raise PermissionError('Lu film capability map changed')
    by_id={m['id']:m for m in mapping}
    for cap in records:
        ident=cap['id'];policy=by_id[ident]
        if cap.get('version')!=1:
            raise PermissionError('Unknown Lu tool version')
        if ident in READ_ONLY_IDS:
            if cap.get('effect_classes')!=['READ_WORKSPACE'] or \
               policy['core_tool_effect']!='ReadWorkspace':
                raise PermissionError('Invalid read-only effect')
        elif ident in HIGH_RISK_IDS:
            if cap.get('effect_classes')!=['EXECUTE','WRITE_WORKSPACE'] or \
               policy.get('core_registration_status')!='BLOCKED_EFFECT_BRIDGE_APPROVAL':
                raise PermissionError('Unsafe render/export effect downgrade')
        if policy.get('core_registration_status') not in ('PENDING','BLOCKED_EFFECT_BRIDGE_APPROVAL'):
            raise PermissionError('Source-only catalog claims native admission')
    return {'registration_enabled':False,'effect_authorized':False,
            'read_only_candidates':sorted(READ_ONLY_IDS),
            'blocked_composite_effects':sorted(HIGH_RISK_IDS),
            'input_object_refs_supported_by_lu_host':False}


def authorize_readonly_request(capability_id:str,*,input_refs=(),
                               installed_enrollment_proven:bool=False):
    """Do NOT synthesize installed identity or grant from a source catalog.

    This function always denies in R3: the Core native host must first
    authenticate a real signed NVP package and bind the original user task.
    """
    if type(capability_id) is not str or capability_id not in READ_ONLY_IDS:
        raise PermissionError('Only exact reviewed read-only capability may be considered')
    if input_refs:
        raise PermissionError('Lu Core host currently lacks input ObjectRef resolver')
    # The caller's Boolean is never a trusted installed proof.
    raise PermissionError('Lu Core registry and enrolled original-user grant unavailable')
