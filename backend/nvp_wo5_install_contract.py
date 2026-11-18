"""One canonical per-user installer, independently provisioned machine codecs.

This module never elevates the user application, initializes a project, or
runs a codec. A codec-enabled build must declare the same independently
approved manifest digest at source-build and actual frozen installer admission.
"""
import ast
import json
from pathlib import Path
import sys

from backend.nvp_wo5_codec_provision import MANIFEST, ROSTER, require_pin, verify_payload

DISABLED = "disabled"


def compiled_source_pin(path):
    """Read the generated pin as data, without importing executable code."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise PermissionError("Exact build pin module required")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and type(body[0].value.value) is str:
        body = body[1:]
    if (len(body) != 1 or not isinstance(body[0], ast.Assign) or len(body[0].targets) != 1
            or not isinstance(body[0].targets[0], ast.Name)
            or body[0].targets[0].id != "RELEASE_CODEC_MANIFEST_SHA256"
            or not isinstance(body[0].value, ast.Constant) or type(body[0].value.value) is not str):
        raise PermissionError("Build pin module is not a literal release binding")
    value = body[0].value.value
    return require_pin(value) if value else DISABLED


def verify_install_request(expected, *, compiled, frozen, check_machine):
    """Before promoting NVP.pending: check the actual frozen pin and machine files."""
    if frozen is not True or type(compiled) is not str:
        raise PermissionError("Installer requires the genuine frozen app")
    if expected == DISABLED:
        if compiled != "":
            raise PermissionError("Codec-enabled app cannot enter an unpinned installer")
        return DISABLED
    require_pin(expected)
    if expected != compiled:
        raise PermissionError("Installer and frozen application codec pins differ")
    target = check_machine(expected)
    if not isinstance(target, Path) or target.name != expected:
        raise PermissionError("Machine codec admission did not confirm exact release")
    return expected


def build_contract(*, expected, pin_module, app_bundle, codec_payload=None):
    """Validate source binding and separate machine payload; no binary execution."""
    if compiled_source_pin(pin_module) != expected:
        raise PermissionError("Build source pin differs from requested installer pin")
    app = Path(app_bundle)
    if app.is_symlink() or not app.is_dir():
        raise PermissionError("Actual Windows app bundle directory required")
    forbidden = {MANIFEST.casefold(), 'native-codecs', 'codec-payloads'}
    for entry in ROSTER.values():
        forbidden.update((entry[2].casefold(), entry[3].casefold()))
    for path in app.rglob('*'):
        if path.name.casefold() in forbidden:
            raise PermissionError("Machine codecs must not enter user-writable app payload")
    if expected == DISABLED:
        if codec_payload is not None:
            raise PermissionError("Disabled installer must not carry a machine codec payload")
        count = 0
    else:
        require_pin(expected)
        if codec_payload is None:
            raise PermissionError("Codec-enabled release requires its approved offline machine payload")
        count = len(verify_payload(Path(codec_payload), expected))
    return {"format": "nvp.wo5.canonical_installer_contract.v1", "codec_release_pin": expected,
            "machine_payload_files_verified": count, "source_pin_verified": True,
            "frozen_pin_and_machine_admission_verified": False,
            "native_playback_accepted": False}


def installer_entry(argv):
    """Installer-only, read-only exit code; closed on all errors, no GUI/server."""
    from backend._nvp_wo5_release_pin import RELEASE_CODEC_MANIFEST_SHA256
    from backend.nvp_wo5_codec_provision import check_installed
    try:
        if len(argv) != 1:
            return 2
        verify_install_request(argv[0], compiled=RELEASE_CODEC_MANIFEST_SHA256,
                               frozen=getattr(sys, 'frozen', False), check_machine=check_installed)
        return 0
    except Exception:
        return 2


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--pin-module', required=True, type=Path)
    parser.add_argument('--app-bundle', required=True, type=Path)
    parser.add_argument('--codec-payload', type=Path)
    args = parser.parse_args()
    print(json.dumps(build_contract(expected=args.expected, pin_module=args.pin_module,
                                    app_bundle=args.app_bundle, codec_payload=args.codec_payload),
                     sort_keys=True))


if __name__ == '__main__':
    main()
