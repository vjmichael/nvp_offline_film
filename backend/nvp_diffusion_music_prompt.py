"""Reusable NVP diffusion prompt audio policy; no media or authorization effects.

A creator-owned switch adds a negative background-music instruction before a
bounded prompt is sent to LTX or another diffuser. Original dialogue/PCM is
managed separately by NVP; the instruction is not an audio mute or receipt.
"""
from __future__ import annotations
import json
import re
from hashlib import sha256

NO_BACKGROUND_MUSIC_LINE = "No background music."
MAX_PROMPT_CHARS = 500
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CAMERA = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


def compose_diffusion_prompt(prompt: str, *, no_background_music: bool) -> str:
    """Return exact user prompt, followed by a separate negative music line.

    Only explicit bool values accepted; no quiet coercion of model/UI claims.
    Retains original visual directions and enforces the installed LTX bound.
    """
    if type(prompt) is not str or type(no_background_music) is not bool:
        raise ValueError("Explicit creator text and background-music switch required")
    if (not prompt.strip() or '\x00' in prompt or '\r' in prompt or
            any(ord(ch) < 32 and ch not in ('\n', '\t') for ch in prompt)):
        raise ValueError("Unsafe or empty diffusion prompt")
    result = prompt
    if no_background_music and NO_BACKGROUND_MUSIC_LINE not in [
            line.strip() for line in prompt.split('\n')]:
        result = prompt.rstrip() + '\n' + NO_BACKGROUND_MUSIC_LINE
    if not 8 <= len(result) <= MAX_PROMPT_CHARS:
        raise ValueError("Diffusion prompt exceeds reviewed LTX bounds")
    return result


def freeze_diffusion_conditioning(*, positive_prompt: str, take_sha256: str,
                                  camera_id: str, no_background_music: bool) -> tuple[bytes, str]:
    """Seal a creator's chosen switch in the existing immutable Take digest.

    Existing LTX v1 without the optional flag retains its old, unchecked
    behavior. New creator-originated requests include the explicit boolean.
    """
    compose_diffusion_prompt(positive_prompt, no_background_music=no_background_music)
    if (type(take_sha256) is not str or not _SHA.fullmatch(take_sha256) or
            type(camera_id) is not str or not _CAMERA.fullmatch(camera_id)):
        raise ValueError("Source-bound frozen Take and camera required")
    payload = {'positive_prompt': positive_prompt, 'take_sha256': take_sha256,
               'camera_id': camera_id, 'no_background_music': no_background_music}
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True, allow_nan=False).encode('ascii')
    if len(encoded) > 16 * 1024:
        raise ValueError('Unbounded LTX conditioning')
    return encoded, sha256(encoded).hexdigest()
