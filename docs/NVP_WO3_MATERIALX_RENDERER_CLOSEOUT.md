# WO3 — MaterialX source-graph verification and independent renderer integrity

**Status:** Implementation submitted; **native acceptance OPEN**.
**Stack:** WO3 on WO2 draft PR #95 on WO1 draft PR #94.
**Branch:** `nvp/wo3-materialx-renderer-integrity-20261107`.

## The original real failure

Native DATA-AV `test_nvp_wo2_pbr_channels` and the real 60-second
`test_nvp_wo2_mixed_60s` previously failed when
`backend/nvp_wo2_openpbr.py` raised `RuntimeError: MaterialX source scalar changed`.
Those tests were authoring valid native roughness/metallic texture maps that
connected the OpenPBR scalar inputs; the prior blanket rejection of all
connected scalar sources was incorrect. A narrowly path-restricted allowance
was added on the WO1 branch, but had no real exact-head native passing evidence.

## WO3 integrity changes

1. Added `backend/nvp_wo3_materialx_integrity.py`, an immutable shader
   connection authority that validates exact trusted source **prim path,
   output socket name, output/Input shading attribute kind and USD type**.
   A source on a valid named shader with a substituted output socket is no
   longer admitted.
2. `verify_pbr_map_graph` checks the preview USD graph and MaterialX
   roughness, metallic, emission, normal, and opacity graph sockets. The
   literal filter mode, UV primvar, UV index, address modes, source color-space
   policy, output types, emission luminance, binary cutout threshold and
   normalmap bridge are guarded against tampering.
3. `verify_openpbr_texture` and `verify_openpbr_scalar` retain valid
   source-bound scalar maps, while rejecting crosswired and incorrectly typed
   image/scalar/texcoord outputs. The primary `mtlx` material terminal
   requires its exact OpenPBR source output.
4. Independent `resolved_materialx_probe` now writes the approved,
   original FilmIndex PNG into a temporary read-only path, and **after**
   the renderer context checks each source's SHA-256 and non-symlink,
   regular-file identity. A modified/swap/deleted source copy raises
   before a successful renderer result can escape the context. FilmIndex
   original USD/PNG bytes are never modified by the resolver.
5. Tests in `tests/test_nvp_wo3_materialx_integrity.py` use genuine USD
   and actual SHA-addressed project PNGs to test positive five-channel
   inputs, malicious alternate sockets on existing shaders, UV/channel
   mutations, unapproved file paths, successful temporary source cleanup,
   and native source tampering after material resolution.

## Native verification

Dedicated CI workflow:
`.github/workflows/nvp-wo3-materialx-renderer-integrity.yml`.
Required four real Windows 2025/Ubuntu 24.04 Python 3.11/3.13 cells
with official `usd-core==26.11`, positive existing PBR source regression,
new adversarial source tests, independent Hydra probe's refusal/claims,
numeric comparison claims, and the no-FFmpeg policy check.

Separate Ubuntu Python 3.11 job reruns actual 60-second mixed source,
including skinned character, five-channel materials, and native CPU
raster across 60 source-time samples. Store its measured receipt.
This is **not** 24 fps feature-film acceptance and not GPU or calibrated
Hydra shader parity.

Physical renderer parity is deliberately NOT certified by a successful
source-graph verification or renderer existence. A true independent
Hydra/MaterialX backend and shader output matching across color pipelines
and target machines remain separate production acceptance gates.

## WO3 closure conditions

- Obtain native **completed success**, not queued/cancelled/skipped, on all
  required OS/Python cells at final exact head and the real 60-second job.
- Repair *actual* compiler/runtime/unit failures rather than dropping tests.
- Both valid original PBR graph and hostile output-socket rewires must pass.
- Renderer temp PNG mutation/replacement must fail closed; approved original
  FilmIndex layer and texture identities remain stable.
- Compare real independent renderer images where the binary is genuinely
  present. If `usdrecord` is unavailable, record a **separate remaining
  native Hydra image parity gate**, never infer it from success of other tests.
- Update this document and project ledger with job IDs, SHA, and actual
  passing or failed results. Only then close WO3 implementation acceptance.
