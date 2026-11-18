#!/usr/bin/env bash
# NVP-E2E-01E: local Linux NSIS build using an ACTUAL Windows PyInstaller bundle.
# Does not try to cross-compile Python Windows runtime. Requires a real Windows
# NVP.exe and the matching full dist/NVP/_internal contents.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle="${NVP_WINDOWS_BUNDLE:-$repo/dist/NVP}"
compiler="${MAKENSIS:-makensis}"
if ! command -v "$compiler" >/dev/null 2>&1 && [ ! -x "$compiler" ]; then
  echo "NSIS compiler missing. Restore nsis + nsis-common from Lu Library." >&2
  exit 2
fi

if [ ! -d "$bundle" ]; then
  echo "Genuine Windows NVP PyInstaller bundle missing: $bundle" >&2
  echo "Never build a release from a stub EXE or empty directory." >&2
  exit 3
fi

# NSIS script uses ../dist/NVP relative to packaging/. Do not silently
# substitute an arbitrary unrelated bundle.
if [ "$(realpath "$bundle")" != "$(realpath "$repo/dist/NVP")" ]; then
  echo "Copy vetted original bundle to repo/dist/NVP first; no symlink input." >&2
  exit 4
fi
if [ -L "$bundle" ] || [ -L "$bundle/NVP.exe" ]; then
  echo "Windows bundle or executable is a symlink, refusing package." >&2
  exit 4
fi

# W1-G: trusted build inputs only. A missing reviewed binary roster never
# acquires fictional worker acceptance; partial configuration fails closed.
if [ -n "${NVP_W1G_WORKER_ROSTER:-}" ] || [ -n "${NVP_W1G_WORKER_BINARIES:-}" ]; then
  if [ -z "${NVP_W1G_WORKER_ROSTER:-}" ] || [ -z "${NVP_W1G_WORKER_BINARIES:-}" ]; then
    echo "Both the reviewed worker roster and genuine binary directory are required" >&2
    exit 6
  fi
  python3 "$repo/tools/nvp_w1g_worker_package.py" provision \
    --platform windows-amd64 --bundle "$bundle" \
    --roster "$NVP_W1G_WORKER_ROSTER" \
    --trusted-binaries "$NVP_W1G_WORKER_BINARIES"
fi

if [ -n "${NVP_W1G_WHEEL_LOCK:-}" ] || [ -n "${NVP_W1G_WHEELHOUSE:-}" ]; then
  if [ -z "${NVP_W1G_WHEEL_LOCK:-}" ] || [ -z "${NVP_W1G_WHEELHOUSE:-}" ]; then
    echo "Incomplete offline wheel dependency lock configuration" >&2
    exit 7
  fi
  python3 "$repo/tools/nvp_w1g_native_dependencies.py" verify \
    --platform windows-amd64 --lock "$NVP_W1G_WHEEL_LOCK" \
    --wheelhouse "$NVP_W1G_WHEELHOUSE" \
    > "$repo/dist/NVP-W1G-native-wheels-audit.json"
fi

python3 "$repo/tools/nvp_e2e01e_validate_installer_payload.py" \
  --bundle "$bundle" --report "$repo/dist/NVP-package-audit.json"
# W1-G: seal every packaged Python, OpenUSD, React and native-worker byte.
# Keep the external receipt OUTSIDE NSIS payload for post-install comparison.
python3 "$repo/tools/nvp_w1g_native_package.py" build \
  --bundle "$bundle" --output "$repo/dist/NVP-W1G-native-build.json"

version="${NVP_RELEASE_VERSION:-0.1.0}"
if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Release version must be a reviewed X.Y.Z value" >&2
  exit 8
fi

# WO5: independently approved offline codecs are deployed in a distinct
# machine transaction. The one per-user installer never copies or elevates them.
codec_pin="${NVP_WO5_RELEASE_PIN:-disabled}"
codec_args=()
if [ "$codec_pin" != disabled ]; then
  if ! [[ "$codec_pin" =~ ^[0-9a-f]{64}$ ]] || [ -z "${NVP_WO5_MACHINE_PAYLOAD:-}" ]; then
    echo "Codec release requires independent manifest SHA and reviewed offline payload" >&2
    exit 9
  fi
  codec_args+=(--codec-payload "$NVP_WO5_MACHINE_PAYLOAD")
elif [ -n "${NVP_WO5_MACHINE_PAYLOAD:-}" ]; then
  echo "Codec-disabled release must not carry a machine payload" >&2
  exit 9
fi
mkdir -p "$repo/dist"
(
  cd "$repo"
  python3 -m backend.nvp_wo5_install_contract --expected "$codec_pin" \
    --pin-module backend/_nvp_wo5_release_pin.py --app-bundle "$bundle" \
    "${codec_args[@]}" > dist/NVP-WO5-installer-contract.json
  "$compiler" "-DAPP_VERSION=$version" "-DWO5_CODEC_PIN=$codec_pin" -V3 "packaging/nvp-alpha.nsi"
)
exe="$repo/dist/NVP-Alpha-Setup.exe"
test -s "$exe" || { echo "NSIS did not produce an installer" >&2; exit 5; }
file "$exe"
sha256sum "$exe"
echo "NSIS packaging succeeded, not Windows application execution acceptance."
