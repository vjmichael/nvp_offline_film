"""AUDIO-01K.2 DCP-readiness gate. Never mislabel MOV as a cinema DCP.

A real DCP requires independently authored and validated cinema picture/sound
assets and composition/package metadata. This module is a fail-closed
capability gate; no cinema-compliant encoder or packaging is claimed here.
"""
from __future__ import annotations

from backend.nvp_audio01k_distribution import FORMAT as MEZZANINE_FORMAT,PROFILE

FORMAT="nvp.audio01k.dcp_preflight.v1"
REQUIRED=(
    "cinema_picture_jpeg2000_xyz_mxf",
    "cinema_audio_pcm_mxf",
    "composition_playlist_cpl",
    "packing_list_pkl",
    "assetmap_and_volume_index",
    "independent_dcp_asset_hash_and_metadata_validation",
)


def assess_dcp_readiness(distribution_document):
    if (type(distribution_document) is not dict or
        distribution_document.get("format")!=MEZZANINE_FORMAT or
        distribution_document.get("profile")!=PROFILE or
        distribution_document.get("dcp_delivered") is not False):
        raise ValueError("DCP readiness requires genuine NVP mezzanine provenance")
    return {"format":FORMAT,"status":"NOT_READY",
            "distribution_profile":PROFILE,
            "distribution_movie_sha256":
                distribution_document["delivered_movie_sha256"],
            "missing_capabilities":list(REQUIRED),
            "can_claim_dcp":False,"dcp_delivered":False,
            "reason":"ProRes/PCM24 MOV mezzanine is not a DCP; no validated cinema asset package exists"}
