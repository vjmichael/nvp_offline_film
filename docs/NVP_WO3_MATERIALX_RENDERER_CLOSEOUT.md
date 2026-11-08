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

## Additional source integrity closeout requirements

- USD shading ports must have **exactly one authored connection path**, not merely a valid first source from `GetConnectedSource()` with a secondary, invalid or hostile edge. The new gate compares the raw `UsdAttribute.GetConnections()` against the exact expected output path.
- Native `usdrecord` is resolved to an exact executable path and SHA-256 hashed before/after rendering. Failed, symbolic-link or oversized image outputs cannot produce `HYDRA_FRAME_RENDERED` receipt. Raw stderr containing private directories is not returned through the renderer receipt.
- Negative tests include executable change during a mock native run (must throw), failure stderr redaction (must not certify a rendered frame), and an extra USD connection on an otherwise valid OpenPBR input (must fail).
- No evidence exists yet that an independent real Hydra/MaterialX renderer achieved visual parity, even if the four matrix cells complete successfully: `usdrecord` may not be installed. Renderer output custody and source graph acceptance are separate from cinematic parity.

## WO3 follow-up hardening — exact authored edge custody

Native results from initial PR #96 run 42435076173 were still **queued** when
reviewed. The follow-up commits below are **not** a passing native test claim.

- Exact authored USD connection lists are checked even when referenced
  sources are unresolved. `HasConnectedSource()` alone can miss dangling
  paths which later become live under scene composition. This extends to
  literal shader settings, source file paths, and permitted scalar maps.
- PreviewSurface and OpenPBR PBR input USD types are checked alongside the
  already pinned shader output types. The normal-map scale and bias must
  remain typed literal `float4` values with no authored upstream edges.
- The disposable MaterialX image resolver denies connected `file` inputs
  even if the visible `nvp-blob://` source URI has not changed.
- Independent `usdrecord` stdout/stderr now go to `DEVNULL`, rather than
  unbounded `capture_output` host RAM; private renderer diagnostics remain
  absent from acceptance receipts.
- Additional real OpenUSD native tests cover hidden normal scale/bias edges,
  unresolved texture and literal edges, and refusing a shadowed file during
  source resolution. Hydra mock verifies bounded diagnostic handling.

**New acceptance requirement:** At the final PR #96 exact commit, all five
WO3 native jobs must complete successfully: Windows 2025/Python 3.11 and 3.13,
Ubuntu 24.04/Python 3.11 and 3.13, and the Ubuntu real 60-second USD/skin/PBR
CPU continuity job. Inspect failing job logs and repair without dropping
regressions. CI is currently queued; native OpenUSD 26.11 is absent from the
assistant's local environment, so local direct USD execution is **not**
evidence. Real independent Hydra picture parity, shader colors under reference
renderers, installed Windows GPU and calibrated cinema tests remain **OPEN**.

Further renderer custody fix: post-render source verification no longer calls
`Path.read_bytes()` on an untrusted worker-mutated file. It opens the source
with no-follow/nonblocking flags where available, validates the opened
regular file's exact originally approved byte length via `fstat`, and hashes
in at most 64 KiB chunks. An inflated or replaced source fails closed
without consuming worker-controlled RAM. The native regression deliberately
inflates a temporary source file. This remains **unverified by native CI**.

## WO3 mandatory actual Hydra image and color-response acceptance

**Gate OPEN until observed real native jobs succeed.** Prior optional
`usdrecord` test skipping was insufficient evidence of a working renderer.
New required workflow: `.github/workflows/nvp-wo3-real-hydra-color.yml`.
It provisions independent conda-forge OpenUSD **26.08** native executable and
Mesa/GLX/Xvfb software-OpenGL context, with PySide6 for `usdrecord`.
The main source-authoring matrix remains **OpenUSD 26.11**, so no cross-version
bitwise parity or certified renderer compatibility is inferred from this audit.

The real `tests/test_nvp_wo3_real_hydra_color.py` test must **NOT SKIP** when
`usdrecord` is absent or fails. It publishes two different immutable
FilmIndex-owned scenes with identical USD mesh, UVs, source-light/camera,
normal/roughness/metallic/emission/opacity maps and different red/blue base
textures. Both must genuinely render under **Hydra Storm**, not Embree.
OpenUSD's HdEmbree example does not use materials and therefore **cannot
prove texture color fidelity**. Storm supports USD PreviewSurface/MaterialX
shading in a real graphics context. Passing requires genuine decoded image
pixels, independent scene and pixel SHA-256s, same pinned native Storm executable,
center-swatch red/blue dominance, and CIE ΔE76 separation at least 25 *between
the two output swatches*. The ΔE is diagnostic and assumes unprofiled RGB8 is
sRGB; it is **NOT** an allowable error versus a reference color and cannot
certify photographic/colorimetric accuracy.

The audit uploads `wo3-hydra-color-evidence.json` with raw measured center
RGB8 means, hash-bound native renderer identity, per-scene SHA and measured
color separation. A missing renderer, failed draw, black/gray/identical output,
wrong shader sampling, missing source file or reused fake pixels fails the
required job rather than creating acceptance.

**Still separate and OPEN even after this gate passes:** independent proof that
Storm selected/evaluated the actual `mtlx` OpenPBR terminal rather than the
UsdPreviewSurface fallback; absolute reference ΔE76/ΔE2000 versus known
color-managed expected pixels; ACES/OCIO transform, target gamut transfer
function, HDR/film mastering, physical GPU and calibrated projection. A successful
Mesa software-OpenGL Storm run does not count as physical GPU acceptance.
