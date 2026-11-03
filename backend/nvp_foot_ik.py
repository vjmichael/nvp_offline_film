"""NVP-PROD-06E1: bounded, deterministic world-space biped foot-plant planning.

This is a *preflight solver*, not a Blender constraint and not an approval gate.
It never modifies actor root motion, approved retarget keys, or cameras. A later
native Blender adapter must verify real bone chains and contact geometry.
"""
from __future__ import annotations

import math

MAX_FRAMES = 2400
MAX_CONTACTS = 32
LEGS = ('left', 'right')


def _number(value, name, lower=-10000.0, upper=10000.0):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be finite in [{lower}, {upper}]')
    return float(value)


def _vec(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError(f'{name} must have three coordinates')
    return tuple(_number(x, name) for x in value)


def _sub(a, b):
    return tuple(x-y for x,y in zip(a,b))


def _add(a, b):
    return tuple(x+y for x,y in zip(a,b))


def _mul(v, scalar):
    return tuple(x*scalar for x in v)


def _dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def _norm(v):
    return math.sqrt(_dot(v,v))


def solve_two_bone(hip, ankle, pole, thigh_m, shin_m):
    """Solve the knee analytically, or refuse a degenerate/unreachable pose.

    All inputs and outputs use the same world coordinate frame. ``pole`` is an
    anatomical bend hint (a point), *not* an unconstrained direction. No hidden
    clamping or stretching occurs: invalid reach must be fixed by the director.
    """
    hip=_vec(hip,'hip'); ankle=_vec(ankle,'ankle');pole=_vec(pole,'pole')
    a=_number(thigh_m,'thigh_m',0.001,10.0)
    b=_number(shin_m,'shin_m',0.001,10.0)
    target=_sub(ankle,hip);distance=_norm(target)
    epsilon=1e-7
    if distance<=epsilon or distance>=a+b-epsilon or distance<=abs(a-b)+epsilon:
        raise ValueError('Unreachable or singular two-bone target; refuse to stretch or flip knee')
    axis=_mul(target,1.0/distance)
    projection=(a*a-b*b+distance*distance)/(2*distance)
    radius_squared=a*a-projection*projection
    if radius_squared<=epsilon*epsilon:
        raise ValueError('Collinear knee solution; bend direction is undefined')
    hint=_sub(pole,hip)
    perpendicular=_sub(hint,_mul(axis,_dot(hint,axis)))
    plen=_norm(perpendicular)
    if plen<=epsilon:
        raise ValueError('Pole aligns with hip-to-ankle axis; bend direction is undefined')
    normal=_mul(perpendicular,1/plen)
    knee=_add(_add(hip,_mul(axis,projection)),_mul(normal,math.sqrt(radius_squared)))
    length_upper=_norm(_sub(knee,hip));length_lower=_norm(_sub(ankle,knee))
    if abs(length_upper-a)>1e-6 or abs(length_lower-b)>1e-6:
        raise RuntimeError('Numerical two-bone length residual exceeded tolerance')
    knee_inner_cos=_dot(_sub(hip,knee),_sub(ankle,knee))/(a*b)
    flexion=180.0-math.degrees(math.acos(max(-1.0,min(1.0,knee_inner_cos))))
    return {'hip':list(hip),'knee':list(knee),'ankle':list(ankle),
            'thigh_m':a,'shin_m':b,'knee_flexion_deg':flexion,
            'length_error_m':max(abs(length_upper-a),abs(length_lower-b))}


def _windows(value, first, last):
    if not isinstance(value, list) or len(value)>MAX_CONTACTS:
        raise ValueError('Contact windows must be a bounded list')
    result=[];previous=first-1
    for pair in value:
        if (not isinstance(pair,(list,tuple)) or len(pair)!=2 or
            any(type(f) is not int for f in pair)):
            raise ValueError('Contact window must contain two integer frame indices')
        start,end=pair
        if start<first or end>last or start>end or start<=previous:
            raise ValueError('Contact windows must be in range, ordered and nonoverlapping')
        result.append((start,end));previous=end
    return result


def solve_biped_foot_plants(frames, leg_settings, *, ground_z=0.0,
                            max_correction_m=0.25, approval_sha=None):
    """Calculate left/right independently while preserving every supplied hip.

    ``frames`` is a dense sequence of per-frame world-space measurements:
    {frame: int, left/right: {hip, ankle, pole}}. The first ankle in each
    director-authored contact window sets the fixed XY anchor; ground_z sets Z.
    Non-contact ankles remain unmodified. Contact correction has a hard ceiling.
    This plan is useful only after real geometry/chain binding is independently
    verified in Blender; SHA here is a *binding reference*, not authorization.
    """
    if (not isinstance(frames,list) or not 1<=len(frames)<=MAX_FRAMES or
        not isinstance(leg_settings,dict) or set(leg_settings)!=set(LEGS)):
        raise ValueError('Supply bounded frames and explicit settings for both legs')
    ground_z=_number(ground_z,'ground_z')
    correction_cap=_number(max_correction_m,'max_correction_m',0,2)
    if approval_sha is not None and (not isinstance(approval_sha,str) or len(approval_sha)!=64 or
                                     any(ch not in '0123456789abcdef' for ch in approval_sha)):
        raise ValueError('Retarget binding SHA must be lowercase 64-character hex')
    ordered=[];previous=None
    for item in frames:
        if not isinstance(item,dict) or type(item.get('frame')) is not int:
            raise ValueError('Each sample needs a positive integer frame')
        number=item['frame']
        if number<1 or (previous is not None and number!=previous+1):
            raise ValueError('Samples must be consecutive positive frames')
        if any(leg not in item for leg in LEGS):
            raise ValueError('Every frame must include both legs')
        ordered.append(number);previous=number
    first,last=ordered[0],ordered[-1]
    settings={}
    for leg in LEGS:
        cfg=leg_settings[leg]
        if not isinstance(cfg,dict) or set(cfg)!={'thigh_m','shin_m','contact_windows'}:
            raise ValueError(f'{leg} requires explicit chain lengths and contact windows')
        settings[leg]={
            'thigh_m':_number(cfg['thigh_m'],leg+' thigh',.001,10),
            'shin_m':_number(cfg['shin_m'],leg+' shin',.001,10),
            'windows':_windows(cfg['contact_windows'],first,last)}
    output={'format':'nvp.foot_ik.preflight.v1','retarget_approval_sha':approval_sha,
            'ground_z':ground_z,'max_correction_m':correction_cap,
            'frames':[{'frame':n} for n in ordered],'legs':{},'contacts':{},
            'limitations':'Preflight world-space knee targets; no Blender rig application or native geometry proof'}
    for leg in LEGS:
        cfg=settings[leg];windows=cfg['windows']
        anchors=[];contact_lookup={}
        for start,end in windows:
            source=frames[start-first][leg]
            if not isinstance(source,dict):raise ValueError('Invalid leg sample')
            ankle=_vec(source.get('ankle'),leg+' ankle')
            anchor=(ankle[0],ankle[1],ground_z)
            anchors.append({'start_frame':start,'end_frame':end,'ankle_world_m':list(anchor)})
            for n in range(start,end+1):contact_lookup[n]=anchor
        max_seen=0.0
        for i,item in enumerate(frames):
            sample=item[leg]
            if not isinstance(sample,dict) or set(sample)!={'hip','ankle','pole'}:
                raise ValueError('Leg sample requires hip, ankle, pole')
            hip=_vec(sample['hip'],leg+' hip')
            original=_vec(sample['ankle'],leg+' ankle')
            pole=_vec(sample['pole'],leg+' pole')
            n=ordered[i];contact=n in contact_lookup
            target=contact_lookup[n] if contact else original
            correction=_norm(_sub(target,original))
            if correction>correction_cap+1e-9:
                raise ValueError(f'{leg} foot correction exceeded authorized bound at frame {n}')
            result=solve_two_bone(hip,target,pole,cfg['thigh_m'],cfg['shin_m'])
            result.update({'contact':contact,'correction_m':correction})
            output['frames'][i][leg]=result
            max_seen=max(max_seen,correction)
        output['legs'][leg]={'thigh_m':cfg['thigh_m'],'shin_m':cfg['shin_m'],
                             'max_correction_m':max_seen}
        output['contacts'][leg]=anchors
    return output
