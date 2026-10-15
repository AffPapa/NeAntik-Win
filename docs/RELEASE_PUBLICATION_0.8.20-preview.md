# NeAntik Win 0.8.20-preview — publication evidence

Date: 2026-10-15. Channel: public preview. This update adds explicit consent
before the external IP diagnostics page opens. It is not a fingerprint or
Chromium privacy patch and makes no anonymity claim.

## Identity

- Browser source commit and tag target: `4c06345c33ad09676a9b967b12d12f8964ea197e` (`v0.8.20-preview`).
- Tag note: GitHub reports this already-published ref as lightweight (`object.type=commit`), created by the release command's `--target`; it resolves to the exact source commit. It was not rewritten. Future releases use a pre-pushed annotated tag plus `gh release create --verify-tag`.
- GitHub prerelease: <https://github.com/AffPapa/NeAntik-Win/releases/tag/v0.8.20-preview>.
- ZIP: `NeAntikWin-portable-v0.8.20-preview.zip`, 262,379,286 bytes.
- ZIP SHA-256: `b3f4afe05240453e4a3cbb830a0c4004fbfa263fa1720de4ce7543063e7e566f`.
- Packaged `NeAntikWin.exe` SHA-256: `41ad4fd5f7851398ec16ee4f1c51ea06f11df6c47ae02bdfa5a24afdfd2479c5`.
- Runtime: Windows 11 Pro x64 build 26200, CPython 3.12.10, PyInstaller 6.21.0.
- Engine: stock Chromium 155.0.8059.79, source commit `a49e2e3d4addfd84e765b52afe230bedb81096db`; build-compat patch SHA-256 `2992c690bd16fd3f7196a52b018cdc0a2556f4148959fb7f3b7072803fe81a3d`; no runtime fingerprint patch (`fingerprint_modification: false`, empty privacy patch).

## PASS

- `python -m unittest discover -q` on feature source `f754c56`: 268 tests, 3 skipped. `python tools/gui_regression.py`: 20/20. Candidate commit `4c06345` changes release metadata only after that code-tested commit.
- Clean portable build from candidate commit `4c06345`: PASS. Local archive verifier: PASS (1,066 files). Packaged executable `--self-test`: exit 0. Synthetic isolated GUI startup opened the manager and displayed the new diagnostics-consent dialog; no external IP request was made.
- Windows CI run `38720021560` for exact browser source commit `4c06345`: success.
- Hosted second-host gate: PASS, [GitHub Actions run 38721393396](https://github.com/AffPapa/NeAntik-Win/actions/runs/38721393396), Windows Server 2022 runner. It fetched this exact public ZIP, checked its expected SHA/source identity, ran the packaged self-test and verified isolated portable storage using synthetic data. This does not establish external network routing, fingerprint resistance, consumer Windows compatibility or cross-account portability.
- GitHub prerelease metadata reports `v0.8.20-preview`, prerelease state, and all three assets uploaded. GitHub's ZIP asset digest matches the local ZIP. A fresh public download was 262,379,286 bytes, had the same SHA-256, and passed `tools/verify-release-archive.ps1` again (1,066 files).
- Public Site version 54 deployed successfully at <https://nevision-win.mail782861.chatgpt.site>. Site source commit: `517f7301aba0ea9e9639f7baa6cf81cca2396064`; deployment status `succeeded`.
- Site `tsc --noEmit` and production `npm run build`: PASS before its source commit. The packaged Site archive contained `dist/.openai/hosting.json` and the built Worker entrypoint.
- Live `/`, `/release.json`, and `/CHANGELOG.md`: HTTP 200. Metadata exactly names version `0.8.20-preview`, browser source commit `4c06345…`, ZIP filename, 262,379,286-byte size, expected SHA-256, and exact GitHub download URL. Public ZIP HEAD: HTTP 200, Content-Length 262,379,286. Changelog contains the new version heading.

## INCONCLUSIVE / NOT RUN

- The local packaged GUI displayed its new consent dialog using a synthetic profile. The automation's attempt to activate the cancel button failed to target a cached element; after refreshing, the dialog remained visible. No "Yes" action or external request was made. GUI cancellation interaction is **INCONCLUSIVE** (automated cancel branch is covered by regression tests).
- Physical keyboard, UI Automation, screen reader, external DNS/IPv6/UDP/TURN, independent egress observer, another Windows account/PC, and Windows 10 were not tested on this exact ZIP.
- No claim of fingerprint spoofing, passing anti-bot checks, complete anonymity, or universal privacy is made. Profiles isolate local browser storage; they are not separate network identities.

## Repeatable publication sequence

The browser publication followed the immutable order: verify clean browser source and local ZIP → create preview tag/release and upload ZIP, SHA sidecar and manifest → retrieve public ZIP and compare exact length/hash, rerun archive verifier. For this Site update, the existing checkout was confirmed clean and its Site identity read first; the explicit Sites opening-mode helper was omitted until the publish workflow, which then validated the selected checkout/project, committed and pushed the exact source, and packaged it without overwriting remote history. Version 54 was saved/deployed and live metadata, changelog, homepage and public ZIP response were verified. That ordering deviation is recorded so it is not repeated: future Site edits must run opening mode before editing and pass its returned source to the publish helper. The durable procedure and Windows-specific helper notes are in [`RELEASE_OPERATIONS.md`](RELEASE_OPERATIONS.md).
