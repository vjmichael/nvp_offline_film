#!/usr/bin/env bash
# CI-only acquisition of the exact reviewed Blender release. Never called by NVP.
set -euo pipefail
version=${1:?exact Blender release required}
case "$version" in 5.2.3|5.2.4) ;; *) echo 'Unreviewed Blender version' >&2; exit 2;; esac
archive="blender-${version}-linux-x64.tar.xz"
manifest="blender-${version}.sha256"
# Blender Foundation's enabled mirrors: https://projects.blender.org/infrastructure/mirror/wiki
# Keep the original version, not an arbitrary newest or distribution package.
roots=(https://download.blender.org/release/Blender5.2
       https://mirror.blender.org/release/Blender5.2
       https://mirrors.ocf.berkeley.edu/blender/release/Blender5.2
       https://mirror.clarkson.edu/blender/release/Blender5.2
       https://mirror.fcix.net/blender/release/Blender5.2)
tmp=$(mktemp -d .nvp-blender-download.XXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT
fetch() {
    curl --fail --location --retry 1 --retry-delay 2 --connect-timeout 15 --max-time "$3" \
        --proto '=https' --proto-redir '=https' "$1" -o "$2"
}
# Obtain the exact manifest entry before fetching a large executable archive.
expected=''
for root in "${roots[@]}"; do
    rm -f -- "$tmp/manifest"
    if fetch "$root/$manifest" "$tmp/manifest" 45; then
        candidate=$(awk -v file="$archive" '$2==file || $2=="*"file {print $1}' "$tmp/manifest")
        if [[ "$candidate" =~ ^[a-fA-F0-9]{64}$ ]]; then
            expected=${candidate,,}
            echo "Verified manifest entry from $root: $expected  $archive"
            break
        fi
    fi
done
[[ -n "$expected" ]] || { echo 'No valid official checksum entry' >&2; exit 1; }
for root in "${roots[@]}"; do
    rm -f -- "$tmp/archive"
    if fetch "$root/$archive" "$tmp/archive" 180; then
        actual=$(sha256sum "$tmp/archive" | cut -d ' ' -f1)
        if [[ "$actual" == "$expected" ]]; then
            mv -f -- "$tmp/archive" "$archive"
            printf '%s  %s\n' "$expected" "$archive" > blender.sha256
            sha256sum --check --status blender.sha256
            echo "Exact Blender $version archive verified from $root"
            exit 0
        fi
        echo "Checksum mismatch from $root; refusing those bytes" >&2
    fi
done
echo "Exact Blender $version unavailable from reviewed mirrors" >&2
exit 1
