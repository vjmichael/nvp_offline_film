#!/usr/bin/env bash
# Native Linux only; invoked with restored/examined Python venv and system
# GTK development dependencies. Frontend must have been built from npm lock.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
python="${NVP_BUILD_PYTHON:?Supply path to reviewed isolated build Python}"
out="${NVP_BUILD_OUTPUT:?Supply fresh external output directory}"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]
[[ "$python" = /* && "$out" = /* && ! -e "$out" && ! -L "$out" ]]
[[ -s "$repo/frontend/dist/index.html" ]]
mkdir -p "$out"
cd "$repo"
export PYTHONPATH= PYTHONHASHSEED=0
# Fail before analysis if the build Python cannot discover the pinned GI
# namespaces or execute the real GLib callback overrides.
"$python" tools/nvp_linux_gi_packaging.py inventory "$out/gi-inventory.json"
"$python" tools/nvp_linux_gi_packaging.py flags "$out/gi-inventory.json" > "$out/gi-flags.txt"
mapfile -t gi_flags < "$out/gi-flags.txt"
"$python" -m PyInstaller --noconfirm --clean --onedir --name NVP \
  --paths "$repo" --distpath "$out/raw" --workpath "$out/work" --specpath "$out" \
  --add-data "$repo/frontend/dist:frontend/dist" \
  --add-data "$repo/backend/nvp_worker_linux_landlock.py:backend" \
  --add-data "$repo/tools/nvp_int02_cycles_frame_worker.py:tools" \
  --collect-all webview --collect-all pxr --collect-all miniaudio \
  --collect-all sounddevice --collect-all opentimelineio --collect-submodules backend \
  "${gi_flags[@]}" --hidden-import gi --hidden-import gi.repository.GLib \
  --hidden-import gi.repository.GObject --hidden-import gi.repository.Gio \
  --hidden-import gi.repository.Gtk --hidden-import gi.repository.Gdk \
  --hidden-import tools.nvp_native_device_producer_worker --hidden-import tools.nvp_audio_native_worker \
  --hidden-import tools.nvp_p1b_physical_device_acceptance \
  --hidden-import tools.nvp_data_av_installed_acceptance --hidden-import tools.nvp_perf03g_gui_smoke \
  --exclude-module torch --exclude-module torchvision --exclude-module tensorflow \
  --exclude-module cv2 --exclude-module av --exclude-module imageio_ffmpeg \
  --exclude-module moviepy --exclude-module ffmpeg --exclude-module pytest --exclude-module IPython \
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 \
  "$repo/tools/nvp_desktop_alpha.py"
"$python" packaging/linux/normalize-frozen-bundle.py "$out/raw/NVP" "$out/NVP" --receipt "$out/aliases.json"
# Verify the actual archived overrides and byte-identical typelib closure.
"$python" tools/nvp_linux_gi_packaging.py verify "$out/gi-inventory.json" "$out/NVP/NVP" > "$out/gi-bundle-audit.json"
"$out/NVP/NVP" --smoke-linux-gi
# Verify bundle graph before packaging; the existing package script independently
# checks native ELF and refuses any unreviewed symlinks.
"$python" - "$out/NVP" "$out/bundle-audit.json" <<'PY'
from pathlib import Path
from tools.nvp_w1g_linux_deb import check_real_linux_bundle
import sys, json
Path(sys.argv[2]).write_text(json.dumps(check_real_linux_bundle(Path(sys.argv[1])), indent=2))
PY
NVP_LINUX_BUNDLE="$out/NVP" NVP_DEBIAN_DEPENDS='libgtk-3-0t64, libwebkit2gtk-4.1-0, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, gir1.2-soup-3.0, python3-gi, python3-gi-cairo, libportaudio2, bubblewrap' bash packaging/build-nvp-deb.sh
