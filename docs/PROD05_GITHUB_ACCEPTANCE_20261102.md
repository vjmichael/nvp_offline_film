# PROD-05 verified GitHub acceptance — 2026-11-02

[GitHub Actions run 41561034667](https://github.com/vjmichael/nvp_offline_film/actions/runs/41561034667) completed successfully at commit `78e46b24a10c823a388cbd480611b3385007b1fb`.

All five jobs succeeded: Linux Python suite, Linux React build, Linux native Blender audit and Workbench render, Windows Python/React, and Windows native Blender save/reopen/geometry audit. The generated two-camera scene included a moving proxy actor and verified timeline markers and actor positions. The general test suites completed 283 cases per OS, with three expected native-only skips, while the native Blender tests ran separately.

**Scope boundary:** The fixture scene was authored for reproducible test evidence, not extracted into a finished creative scene. This acceptance does not validate skeleton deformation, motion capture, lip-sync, voice, Windows interactive GUI or AMD R9700 rendering. The PR stays draft.
