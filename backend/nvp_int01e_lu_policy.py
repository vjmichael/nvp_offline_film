"""INT-01E: one Lu-owned creative inference authority for the NVP GUI.

This is an explicit denial for retired legacy inference routes, not a model
discovery endpoint or an implicit bridge. There is no native Lu transport
proven for these typed operations yet. Director manual creation and approval
routes remain independent and available.

Until the actual Lu host exposes an authenticated, receipt-backed typed
operation, do NOT invoke an LM Studio/OpenAI-compatible port or a second
model runtime as a silent fallback.
"""
from fastapi import HTTPException

UNPORTED = frozenset({
    "creative_draft", "scene_ideas", "scene_objects",
    "performance_notes", "editorial_ideas"
})

def refuse_unported_lu_operation(operation):
    if operation not in UNPORTED:
        raise ValueError("Unknown NVP creative operation")
    raise HTTPException(
        status_code=503,
        detail=("Lu Workspace has not enabled "+operation.replace("_"," ")+
                " for this film. Continue directing manually; "
                "no independent model backend was contacted."))
