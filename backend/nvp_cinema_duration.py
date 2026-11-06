"""NVP-CINEMA-01C: explicit, frame-quantized cinema duration policy.

The default never changes the director-approved frozen performance duration.
For the observed DCP-o-matic minimum-one-second behavior, an *opt-in*
technical-only profile may append independently proved black frames.
Do not generalize this short-take contract to arbitrary long-form reel edits.
"""
from __future__ import annotations

DURATION_EXACT = "exact_source_frames"
DURATION_PAD = "explicit_one_second_black_tail"
DURATION_POLICIES = frozenset((DURATION_EXACT, DURATION_PAD))
DURATION_FORMAT = "nvp.cinema.duration.contract.v1"


def plan_cinema_duration(source_frames, fps, policy=DURATION_EXACT):
    if type(source_frames) is not int or not 1 <= source_frames <= 240:
        raise ValueError("Invalid approved source frame count")
    if type(fps) is not int or fps != 24:
        raise ValueError("This cinema duration adapter requires exactly 24fps")
    if policy not in DURATION_POLICIES:
        raise ValueError("Unknown cinema duration policy")
    if source_frames < fps:
        if policy == DURATION_EXACT:
            raise RuntimeError(
                "Short film is under one second; the installed cinema packager "
                "may append black frames. Exact-mode export is blocked; "
                "request a 24+ frame frozen take or explicitly approve "
                "one-second technical-only black-tail padding."
            )
        output = fps
    else:
        if policy != DURATION_EXACT:
            raise ValueError(
                "One-second black-tail exception is only valid for a "
                "shorter-than-one-second frozen source"
            )
        output = source_frames

    pad = output - source_frames
    return {
        "format": DURATION_FORMAT,
        "policy": policy,
        "source_frames": source_frames,
        "dcp_frames": output,
        "black_tail_frames": pad,
        "fps": fps,
        "source_samples_48000": source_frames * 48000 // fps,
        "dcp_samples_48000": output * 48000 // fps,
        "status": "explicit_padded_technical_only" if pad else "source_exact",
    }


def validate_duration_contract(contract, source_frames, fps):
    if type(contract) is not dict or contract.get("format") != DURATION_FORMAT:
        raise RuntimeError("Missing or invalid source-to-DCP duration receipt")
    try:
        expected = plan_cinema_duration(source_frames, fps, contract["policy"])
    except (KeyError, ValueError, RuntimeError) as exc:
        raise RuntimeError("Invalid stored source-to-DCP duration policy") from exc
    if contract != expected:
        raise RuntimeError("DCP duration receipt was altered or is internally inconsistent")
    return expected
