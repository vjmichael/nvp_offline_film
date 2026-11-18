# WO5 distribution handoff (source contract, not a release)

Group B Windows native MXF/PCM roundtrip was accepted at `ff0170ec`. The Group C GUI and build staging code are not installed acceptance.

## Host and package layout

- Application: current W1-G per-user NSIS bundle, with its existing recovery and project preservation.
- Native decoder tools: fixed, distinct HKLM Program Files directory `NVP/native-codecs`, containing exactly five reviewed static codec executables, their complete upstream license notices and canonical manifest. The ordinary application cannot elevate or replace them. No project, PATH, user-local executable or runtime-generated pin may authorize them.
- Production journal: existing host-provisioned EFS `.native-production-runtime` and exact project FilmIndex. No second production owner, arbitrary directory or fallback. The protected-project lock remains in force.
- Build-time: use `tools/nvp_wo5_release_codecs.py stage` with the exact source-reviewed Windows static binaries and complete license notices, then independently freeze resulting manifest hash into `backend/_nvp_wo5_release_pin.py` before building. Audit the complete payload again with `verify --bundle ... --pin ...`. Fixture tests verify hashing and denial, not upstream identity, real license compliance or actual executable behavior. The release owner must separately verify reviewed source revisions, binary hashes and legal notices.
- Installation: the current per-user NSIS script cannot write Program Files. The final canonical release must supply a machine-authorized, separately reviewed codec installation transaction with no overwriting of active workers, no symlink/reparse traversal, exact pinned payload verification, rollback and uninstall policy. A codec bundle copied to the per-user NVP directory must not activate the viewer. Do not generate an independent interim installer or weaken the Program Files gate.

## Acceptance still required

Actual protected project and installed native production service/SCM admission; active session origin and project revocation; real UI controls and audio-device clock across seeks/reels; source/final read-only identities; abort and recovery; reviewed native payload placement and installed immutable pin; actual creator viewing on Windows. Test fixture or clock scheduling alone is not a sustained 24fps, physical screening, artistic approval, or formal DCI certification.

The compiled pin intentionally remains blank until the final approved build. Do not build a new NSIS installer until consolidated engineering tasks are complete.
