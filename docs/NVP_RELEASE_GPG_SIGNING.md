# NVP-GPG-01 — owner ECC GPG detached signing for approved Windows installer

**Status:** workflow and negative tests implemented and locally qualified; **NO NVP installer was signed**. This is a gated signing capability, not a production-release or physical LTX acceptance. NVP-STAB-01A is complete. Stabilization 01B–01F, independent W1-G redistribution license review, security, physical Windows/R9700 authorization, and release package acceptance must still finish.

## Scope and custody

The manual-only `.github/workflows/nvp-release-gpg-sign.yml` **never** starts from a PR/push, builds an installer, mutates application code, approves model inference, or creates/publishes a GitHub Release. It accepts one immutable installer artifact from the existing approved `NVP DATA-AV-01` Windows installed/NSIS workflow, checks a first-party successful **main** branch run on the *exact same Git commit as the signing workflow*, checks the installed-build workflow ID `409862454`, a unique nonexpired named artifact, one regular Windows PE installer, and the independently entered SHA-256. Any missing/mismatched input refuses signing before private-key import. The historical successful PR artifact `14729274368` from `581ce161` **is not eligible for this main-only release signer**.

When separately enabled, an approved GitHub Actions `release-signing` environment job imports the existing owner private ECC GPG key only into a newly created temporary 0700 GnuPG home on an ephemeral hosted runner. The required **full 40-hex primary fingerprint** must match the imported key and the public-only verification key. The job makes two detached `.sig` files, verifies each from an isolated public-only keyring and checks that the verified signature's primary fingerprint matches the reviewed fingerprint. Signing stage prints only hashes, non-secret fingerprints and status markers. Its keyring is deleted at job exit and never uploaded; the GitHub runner is ephemeral. GitHub Actions secrets are not readable back via the GitHub app.

Signed candidate artifact includes exactly:

- `NVP-Alpha-Setup.exe` (the unchanged source installer)
- `NVP-Alpha-Setup.exe.sig` (detached GPG signature)
- `NVP-Release-Manifest.json` (source SHA, original run and artifact, SHA-256, candidate version, owner key fingerprint and honest non-admission fields)
- `NVP-Release-Manifest.json.sig` (detached manifest signature)
- `NVP-ECC-GPG-public.asc` (public verification key)

This is **not Authenticode** (Windows SmartScreen may still warn). It does **not** independently verify that every redistributed binary's license was reviewed; the separate W1-G externally pinned Ed25519 redistribution review remains mandatory. Key ownership verified by an entered fingerprint is not third-party certification. Signing by itself is not a promise that the installer is complete, safe, or approved for release.

## One-time GitHub setup (do not enable until formal release authorization)

1. Repo `Settings` → `Environments` → create **`release-signing`**. Restrict deployment branches to `main` and configure **required reviewers** (and prevent self-review if feasible with a different trusted reviewer). GitHub environments without protection can be automatically created by workflows: *do not enable signing until the environment actually has the intended protections*. NVP is a public repo, so GitHub's public-repo environment protections are available depending on account permissions.
2. Existing repo Actions secrets are expected: `NVP_GPG_PRIVATE_KEY` (ASCII-armored private key export) and `NVP_GPG_PASSPHRASE`. Prefer migrating them to environment-scoped secrets inside `release-signing` and removing broad repo-level copies once you have verified that move. Never upload key material to chat, source, logs, repository artifacts or plain GitHub variables.
3. **Only after environment protection and approved release readiness**, create the repository **Actions variable** `NVP_GPG_RELEASE_SIGNING_ENABLED` with the literal value `true`. While absent/false the manual signing job is skipped even if someone invokes the workflow.
4. A future accepted main-branch `NVP DATA-AV-01` Windows installed NSIS workflow run must be explicitly triggered and must complete successfully with its artifact still available (current retention seven days). Record its run ID, exact `main` source SHA, and the actual installer file SHA-256; review those values independently before proceeding. This is not authority to start that native workflow early.
5. In GitHub Actions run `NVP approved Windows installer - ECC GPG detached signatures` on **`main`**, supplying the exact build run ID, matching 40-hex source SHA, installer SHA-256, candidate X.Y.Z version, 40-hex PRIMARY GPG fingerprint, and literal approval phrase `SIGN_NVP_REVIEWED_INSTALLER`. Approve the protected environment job separately. The workflow will fail closed on mismatches.

To see your full **public** key fingerprint on Windows, run `gpg --fingerprint --list-secret-keys`. The fingerprint is safe to discuss; the private key and passphrase are not.

## Independent verification after a qualified signing run

Download the candidate artifact from GitHub Actions. In a fresh temporary GPG keyring, import the included public key and verify the two signatures explicitly:

```powershell
# In the folder containing all five downloaded files:
gpg --import .\NVP-ECC-GPG-public.asc
gpg --verify .\NVP-Alpha-Setup.exe.sig .\NVP-Alpha-Setup.exe
gpg --verify .\NVP-Release-Manifest.json.sig .\NVP-Release-Manifest.json
Get-FileHash .\NVP-Alpha-Setup.exe -Algorithm SHA256
```

Compare the GPG verified primary fingerprint to your known owner fingerprint and the installer digest to the manifest and independently reviewed build. Successful verification confirms those bytes were signed by the corresponding private key, **not** independent code safety, installer qualification, original-film conformance or owner-released production.

## Local qualification record

- `python3 -m unittest discover -s tests -p 'test_nvp_release_gpg.py' -v`: **11 passed**, including refusal of PR/foreign/failed runs, mismatched source, wrong/expired artifacts, wrong hash, wrong PE, symlink, nonapproved version and false release assertions.
- Workflow YAML parsed and all four shell-run scripts passed `bash -n` syntax qualification.
- Detached signature exercise passed using a locally generated **disposable Ed25519 test key**, never the owner's actual ECC key. Both signatures verified in a fresh keyring. The test used a clearly fake fixture instead of a real NVP installer.
- **Not performed:** production secret retrieval, genuine ECC key import, real NSIS signing, owner protected environment approval, GitHub Actions execution of this workflow, Windows Authenticode or release publication.

**No additional CI batch should be started for this signer during NVP stabilization.** The workflow is disabled by default and does not change the 01B→01F engineering sequence.
