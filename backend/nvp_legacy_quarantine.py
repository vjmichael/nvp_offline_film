"""DA-06: HTTP-boundary quarantine for retired frame/codec authoring.

Old source objects and historical records are not deleted. All old
mutating frame-based handlers, proxy exports, external Blender script
endpoints and frame-bound color routes fail BEFORE the route handler
can import a decoder, spawn a process or change any source record.
"""
from __future__ import annotations

import json

FORMAT="nvp.legacy_media.quarantined.v1"


def quarantined(path,method):
    if type(path) is not str or type(method) is not str:
        return False
    parts=path.split("/")
    if len(parts)<5 or parts[:3]!=["","api","projects"] or not parts[3]:
        return False
    # All old EXR/frames/codec color endpoints are replaced by
    # /film/native-color and do not have runnable legacy exports.
    if parts[4]=="color-grading":
        return True
    if len(parts)<8 or parts[4]!="production" or parts[5]!="scenes" or not parts[6]:
        return False
    tail=parts[7:]
    if tail[-1]=="blender-script":
        return True
    if tail[0] in ("sequence","rig-motion"):
        # Immutable legacy metadata may still be read for migration.
        # Old "package" is never safe: it renders output on GET.
        safe_metadata=(len(tail)==1 or
                       (len(tail)==2 and tail[1]=="history"))
        return not (method.upper() in ("GET","HEAD") and safe_metadata)
    return False


class LegacyMediaQuarantine:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if (scope["type"]=="http" and
                quarantined(scope.get("path",""),scope.get("method",""))):
            body=json.dumps({
                "format":FORMAT,"status":"RETIRED",
                "detail":"Legacy frame/FFmpeg authoring and exports are retired. "
                         "Use exact Film Time OpenUSD Digital Takes and "
                         "creator-approved data-first delivery.",
                "historical_source_deleted":False,
                "legacy_executor_started":False,
                "ffmpeg_used":False,
            },separators=(",",":")).encode("utf8")
            await send({"type":"http.response.start","status":410,
                "headers":[(b"content-type",b"application/json"),
                           (b"cache-control",b"no-store"),
                           (b"content-length",str(len(body)).encode())]})
            await send({"type":"http.response.body","body":body})
            return
        await self.app(scope,receive,send)
