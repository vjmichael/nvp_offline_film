#!/usr/bin/env bash
# NVP-owned exact Lu-source native Rust/prost acceptance. This is not an
# installer, Core implementation, credential broker, or production Health proof.
set -euo pipefail
: "${LU_REPO:?set LU_REPO to a complete independently reviewed Lu repository checkout}"
expected=9f43d078aa5e979de0ff72ca4c19e8c5829572af
expected_proto=4e01d921197fb1c58c99958479b1cede36e13c9a
relative=src-tauri/lu-core/proto/lu/workspace/v0/workspace.proto
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
crate="$root/native/nvp_lu_ipc_client"
command -v git >/dev/null || { echo 'BLOCKED: native git unavailable' >&2; exit 19; }
[ -e "$LU_REPO/.git" ] || { echo 'BLOCKED: complete pinned Lu checkout missing' >&2; exit 20; }
actual=$(git -C "$LU_REPO" rev-parse HEAD)
[ "$actual" = "$expected" ] || { echo 'DENIED: Lu checked-out commit mismatch' >&2; exit 21; }
# Prove both that the accepted Lu commit contains the expected schema and
# that the *working tree file* has not been edited after checkout.
recorded=$(git -C "$LU_REPO" rev-parse "HEAD:$relative")
[ "$recorded" = "$expected_proto" ] || { echo 'DENIED: Lu workspace.proto Git blob mismatch' >&2; exit 22; }
git -C "$LU_REPO" diff --quiet -- "$relative" || { echo 'DENIED: dirty Lu Protobuf source' >&2; exit 23; }
export LU_WORKSPACE_PROTO="$LU_REPO/$relative"
[ -f "$LU_WORKSPACE_PROTO" ] || { echo 'DENIED: Lu proto absent' >&2; exit 23; }
command -v cargo >/dev/null && command -v rustc >/dev/null || { echo 'BLOCKED: native cargo/rustc absent' >&2; exit 24; }
[ -f "$crate/Cargo.lock" ] || { echo 'BLOCKED: reviewed NVP Cargo.lock absent; do not fake --locked' >&2; exit 25; }
# Offline+locked prevents network resolution or silent dependency revisions.
(cd "$crate" && cargo test --locked --offline --all-targets)
printf 'NVP_NATIVE_RUST_PROST_PASS source=%s lu_proto=%s os=%s\n' "$actual" "$recorded" "$(uname -s)"
# A Rust/prost PASS does NOT prove trusted installed Lu Core or signed NVP.
