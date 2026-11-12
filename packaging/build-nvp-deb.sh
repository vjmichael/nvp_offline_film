#!/usr/bin/env bash
# G09-F: native Debian package from a genuine native Linux PyInstaller
# bundle. No Docker, simulated binaries or cross-compiled stub acceptance.
set -eo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$repo/dist/NVP-linux"
if [ -n "$NVP_LINUX_BUNDLE" ]; then bundle="$NVP_LINUX_BUNDLE"; fi
output="$repo/dist/nvp-alpha_0.1.0_amd64.deb"
arch="amd64"
if [ -n "$NVP_DEBIAN_ARCH" ]; then arch="$NVP_DEBIAN_ARCH"; fi
if [ "$arch" != "amd64" ]; then
  echo "Only genuinely built native amd64 NVP is supported." >&2;exit 2
fi
command -v dpkg-deb >/dev/null 2>&1 ||
  { echo "Native Debian package tools missing." >&2;exit 2; }
command -v readelf >/dev/null 2>&1 ||
  { echo "Native ELF inspection missing." >&2;exit 2; }
if [ ! -d "$bundle" ] || [ -L "$bundle" ] || \
   [ ! -f "$bundle/NVP" ] || [ -L "$bundle/NVP" ] || \
   [ ! -s "$bundle/_internal/base_library.zip" ] || \
   [ ! -s "$bundle/_internal/frontend/dist/index.html" ]; then
  echo "Genuine Linux PyInstaller onedir binary/React bundle missing." >&2
  exit 3
fi
if [ -n "$(find "$bundle" -type l -print -quit)" ]; then
  echo "Refusing unreviewed symbolic links in the installer payload." >&2;exit 3
fi
if [ "$(stat -c%s "$bundle/NVP")" -lt 100000 ]; then
  echo "NVP executable is only a placeholder." >&2;exit 3
fi
readelf -h "$bundle/NVP" | grep -Eq 'Class:[[:space:]]+ELF64' ||
  { echo "Native ELF64 required." >&2;exit 3; }
readelf -h "$bundle/NVP" | grep -Eq 'Machine:[[:space:]]+Advanced Micro Devices X86-64' ||
  { echo "Genuinely built x86_64 required." >&2;exit 3; }
# Check the actual installed worker dispatcher and accelerated PCM runtime.
# A selfcheck is NOT a successful movie render or physical acceptance.
"$bundle/NVP" --g09e-worker --selfcheck || {
  echo "Frozen Linux long-film worker/runtime unavailable." >&2
  exit 4
}
depends="$NVP_DEBIAN_DEPENDS"
if [ -z "$depends" ]; then
  echo "Supply vetted NVP_DEBIAN_DEPENDS from actual platform runtime." >&2
  exit 4
fi
if ! [[ "$depends" =~ ^[a-zA-Z0-9,.\ \(\)\>\<\=\+\:\-]+$ ]]; then
  echo "Runtime dependency declaration is invalid." >&2;exit 4
fi
temp_root="/tmp"
if [ -n "$TMPDIR" ]; then temp_root="$TMPDIR"; fi
stage="$(mktemp -d "$temp_root/nvp-deb-owned-XXXXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
mkdir -p "$stage/DEBIAN" "$stage/opt/nvp" "$stage/usr/share/applications"
cp -a "$bundle/." "$stage/opt/nvp/"
chmod 755 "$stage/opt/nvp/NVP"
cat > "$stage/DEBIAN/control" <<EOF
Package: nvp-alpha
Version: 0.1.0
Section: video
Priority: optional
Architecture: amd64
Maintainer: NVP Local Build
Depends: $depends
Description: NVP local data-first filmmaking desktop alpha
 OpenUSD source films and imported portable movie packages stay in
 user-owned storage outside /opt/nvp.
 This package does not certify cinema or feature-length device acceptance.
EOF
cat > "$stage/usr/share/applications/nvp-alpha.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=NVP Film Studio
Comment=Offline data-first filmmaking
Exec=/opt/nvp/NVP
Terminal=false
Categories=AudioVideo;Video;
EOF
# No maintainer scripts. dpkg remove/purge cannot erase HOME/NVP_Projects,
# user-selected NVP_HOME, original films or G09-F imported film library.
mkdir -p "$repo/dist"
dpkg-deb --build --root-owner-group "$stage" "$output"
test -s "$output" || { echo "Native Debian package failed." >&2;exit 6; }
sha256sum "$output"
echo "Native platform package candidate; real installed acceptance still required."
