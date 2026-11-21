"""P1-A read-only native Windows microphone and dual-ADC endpoint preflight.

Enumerates real PortAudio host descriptors on the operator's local Windows
machine. Does NOT open, record, approve, calibrate, or prove physical inputs.
Real Take, drift, unclipped PCM, device disconnect, EFS and OS process-tree
custody acceptance must be exercised in an approved original NVP session.
"""
from __future__ import annotations

import argparse
import json
import os

from backend.nvp_device_producer_custody import scope_sha256


def classify_native_adc_catalog(catalog, *, selected_ids=()):
    """Validate bounded genuine-shaped descriptors but never certify hardware.

    A PortAudio device index is not a persistent physical serial number. Two
    endpoints may share one ADC (virtual alias, host-API duplication); actual
    independent timing must be proven from separately running recording
    processes and their real per-buffer ADC timestamps.
    """
    if (type(catalog) is not list or len(catalog) > 128 or
        type(selected_ids) not in (list, tuple) or len(selected_ids) not in (0, 2)):
        raise ValueError("Bounded two-endpoint PortAudio catalog required")
    known = {}
    for item in catalog:
        if (type(item) is not dict or set(item) !=
            {"device_id", "name", "host_api", "max_input_channels"} or
            type(item["device_id"]) is not int or item["device_id"] < 0 or
            type(item["name"]) is not str or not 1 <= len(item["name"]) <= 160 or
            type(item["host_api"]) is not str or not 1 <= len(item["host_api"]) <= 80 or
            type(item["max_input_channels"]) is not int or
            not 1 <= item["max_input_channels"] <= 256 or
            item["device_id"] in known):
            raise ValueError("Invalid or duplicate native input endpoint descriptor")
        known[item["device_id"]] = dict(item)
    if selected_ids:
        if (any(type(device_id) is not int for device_id in selected_ids) or
            selected_ids[0] == selected_ids[1] or
            any(device_id not in known for device_id in selected_ids)):
            raise ValueError("Two distinct currently enumerated native ADC endpoints required")
    selected = [known[index] for index in selected_ids]
    collisions = bool(len(selected) == 2 and
        (selected[0]["name"], selected[0]["host_api"]) ==
        (selected[1]["name"], selected[1]["host_api"]))
    return {
        "format": "nvp.p1a.physical_device_enumeration_candidate.v1",
        "status": ("TWO_PORTAUDIO_ENDPOINTS_ENUMERATED_ONLY" if selected else
                   "PORTAUDIO_CATALOG_ONLY_NO_DEVICE_SELECTED"),
        "enumerated_input_count": len(known),
        "descriptors": [known[k] for k in sorted(known)],
        "selected_input_descriptor_sha256": [
            scope_sha256(item) for item in selected],
        "selected_input_ids": list(selected_ids),
        "possible_same_physical_adc_alias": collisions,
        "stream_opened": False,
        "physical_sound_samples_recorded": False,
        "independent_hardware_adcs_verified": False,
        "per_buffer_adc_clock_and_drift_verified": False,
        "creator_one_use_approval_obtained": False,
        "native_os_custody_verified_by_this_probe": False,
        "efs_protected_original_take_verified": False,
        "production_microphone_gate_accepted": False,
    }


def local_windows_device_preflight(*, selected_ids=()):
    if os.name != "nt":
        raise RuntimeError("Physical microphone preflight requires a real Windows host")
    from backend.nvp_native_independent_take import native_input_devices
    # This function only queries real OS/PortAudio descriptors. It cannot be
    # called through browser-provided device strings or fake CI authorization.
    return classify_native_adc_catalog(
        native_input_devices(), selected_ids=selected_ids)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only owner Windows ADC inventory, NOT physical acceptance")
    parser.add_argument("--device-id", type=int, action="append", default=[],
        help="Repeat exactly twice to inspect two actual independent candidate endpoints")
    args = parser.parse_args(argv)
    result = local_windows_device_preflight(selected_ids=args.device_id)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
