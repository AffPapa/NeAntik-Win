# Release operations: GitHub + public Site

This is the repeatable publication path validated on the Windows host through
2026-10-15 (including browser v0.8.25-preview and public Site version 62). It supplements the per-version evidence; it does not replace the
release test matrix or authorize publishing a candidate that failed a gate.

## 1. Prepare the immutable browser release

1. Read the root `PROJECT_INDEX.md`, this repository's current status, branch,
   HEAD, `docs/MASTER_IMPLEMENTATION_PLAN.md`, `SECURITY_AND_SCOPE.md`, and the
   relevant release checklist. Do not treat a previous chat summary or old
   release record as current state.
2. Build from the exact clean, committed public source state. Record the source
   commit, archive size and SHA-256, executable SHA-256, runtime/core identity,
   and test results. Keep user `Data/` out of the archive.
3. Run tests selected by `docs/QA_TEST_SELECTION.md`, then
   `tools/verify-release-archive.ps1` and the packaged executable self-test.
   Distinguish PASS, FAIL, NOT RUN and INCONCLUSIVE. Never promote a local
   candidate test into evidence for a different ZIP or machine.
4. Check that the version tag does not already exist. Create and push an
   annotated tag at the recorded binary source commit (`git tag -a <tag>
   <commit> -m <message>`, then push that exact tag). Confirm the remote tag
   resolves to the binary source commit. Create the release with `gh release
   create <tag> ... --verify-tag` and omit `--target`; allowing the release
   command to invent the tag can produce a lightweight ref instead. Treat the
   published tag as immutable: do not move an existing tag or overwrite a
   published release.

## 2. Publish and independently verify GitHub assets

- Prefer the already-authenticated GitHub CLI and its protected Windows
  credential store. On this host `gh.exe` was installed by WinGet but not on
  `PATH`; locate the registered `GitHub.cli` package and invoke its executable
  directly. Do not launch GitHub Desktop or copy credentials into a command,
  file, clipboard, chat, or log.
- A new full-account PAT is not the default fix. Release creation/upload needs
  repository write access; use the existing scoped login if it is active. If
  auth is genuinely absent, stop and use GitHub's supported secure sign-in
  outside chat. Never request or print a token, use `--show-token`, or put a
  token in a remote URL.
- Run `gh.exe` from the canonical source checkout or pass `--repo
  AffPapa/NeAntik-Win` explicitly. The Sites source checkout may have no Git
  remote, so implicit repository detection can fail even while GitHub auth is
  valid; do not respond by changing credentials.
- Create the release against the exact tag and upload the portable ZIP, its
  `.sha256` sidecar, and the build manifest. Keep the release prerelease when
  the channel is preview.
- Query public release metadata and print only allowlisted fields (tag,
  prerelease state, asset names/sizes/states/digests). For this preview channel,
  do not use GitHub's `/releases/latest` endpoint as the existence check: it
  excludes prereleases and can return 404 while valid preview releases exist.
  Enumerate `/releases?per_page=...` or request the exact
  `/releases/tags/<tag>` and compare the returned tag to the intended immutable
  version. Download the ZIP again from the public `browser_download_url`.
  Require nonzero size, exact size and
  SHA-256 equality with the local candidate and the published sidecar/API
  digest; rerun the archive verifier on the downloaded bytes. A zero-byte file
  from `gh release download` is not a pass: retry once with `curl.exe -L
  --fail` to the public asset URL, then stop if it is still incomplete.

## 2.1 Attest a reviewed existing ZIP (not a build)

The manual workflow `.github/workflows/attest-existing-release.yml` is a
separate trust layer for an already-published artifact. Run it only from
`main`, with the exact existing release tag. On a Windows runner it resolves
the annotated tag through GitHub's API, downloads the ZIP and its two public
sidecars, checks the GitHub asset digests and source commit, and runs the full
portable archive verifier before creating a short-lived OIDC/Sigstore
attestation with the custom predicate
`https://affpapa.org/attestations/neantik-release-review/v1`.
This is a publisher/repository trust statement, not an independent approval:
the GitHub API reported no classic branch protection on `main` and no visible
repository rulesets when checked on 2026-10-15. Recheck that state before
relying on the attestation; anyone able to change repository workflows is
inside the publisher trust boundary. Enabling required review/status checks
and restricting workflow changes is a separate repository-administration task.

After the workflow succeeds, download that same ZIP and verify it with a recent
GitHub CLI:

```powershell
gh attestation verify .\NeAntikWin-portable-vX.Y.Z.zip `
  --repo AffPapa/NeAntik-Win `
  --predicate-type https://affpapa.org/attestations/neantik-release-review/v1 `
  --signer-workflow AffPapa/NeAntik-Win/.github/workflows/attest-existing-release.yml `
  --source-ref refs/heads/main
```

This claim means only that the identified workflow reviewed the existing
release bytes and their embedded release metadata. It does **not** claim that
CI built the ZIP, prove the build reproducible, cryptographically verify a
release-tag signature, replace Authenticode, or guarantee that the program is
safe or anonymous. A failed attestation or verifier is a release gate failure;
do not replace or move an existing tag to work around it.

## 3. Update the existing Sites publication

1. Read the Sites skill and the selected checkout's `.openai/hosting.json`.
   Preserve the current Site audience. Call `get_site`; use its exact
   `project_id`, then obtain the short-lived source-write credential. Before
   editing any Site file, run `site-workflow.mjs` in opening mode and use the
   returned `checkout_path` and full opening result as `source` for the publish
   run. Keep the credential only in session memory and send it to the helper
   through its hidden stdin protocol. Never write it to disk, command
   arguments, output or chat.
2. Run typecheck and production build before committing. On this Windows host,
   the direct Site helper command `node .../build-site.mjs` failed while
   resolving the npm shim, but `cmd.exe /d /c npm.cmd run build` succeeded.
   TypeScript can be run directly with the installed `node.exe` and the
   checkout's `node_modules/typescript/bin/tsc --noEmit`.
3. The Sites `package-site.mjs` wrapper passed a Windows absolute script path
   through Bash incorrectly on this host. Package with the same Site plugin's
   `skills/sites/scripts/package-site.sh` from WSL using POSIX paths (`/mnt/c/...`).
   Confirm the archive contains `dist/.openai/hosting.json` and the built
   release metadata. Preserve the package bytes until `save_site_version`
   succeeds.
   On this Windows host, first resolve Node inside the selected WSL distro with
   `wsl.exe -d Ubuntu --exec bash -lc 'command -v node'`. The Site workflow's
   nested non-login Bash inherits the caller's environment; invoking the
   workflow with Node by absolute path alone can therefore fail later with
   `node: command not found`. Start it with a PATH that includes the resolved
   Node directory so both the workflow and nested `package-site.sh` can run.
   Use only POSIX checkout/archive paths inside WSL.
   When the workflow runs under WSL, convert only the returned opening
   result's Windows `checkout_path` to its equivalent POSIX path
   (for example `C:\\Users\\...` to `/mnt/c/Users/...`); preserve the other
   opening-result fields unchanged. Give the workflow a POSIX absolute
   `archivePath`; convert that resulting file path back to its Windows host
   path only for the native Sites save call. This is a path representation
   conversion, not a second opening or a new source state.
4. Important retry rule: `site-workflow.mjs` saves/pushes the source commit
   before it packages the deployment archive. If the helper fails during
   packaging, first inspect branch, HEAD, working tree and remote state. The
   exact source commit may already have been pushed; do not blindly repeat the
   edit or create another commit. Complete packaging for that same commit.
   If packaging fails on nested `node` resolution, inspect local HEAD/status
   and reconcile the remote with the open-source workflow first; then reuse
   that same pushed commit and package it again with the corrected PATH. Do not
   repeat source edits, issue a second commit, or generate a new version solely
   to recover the package step.
5. Save the Site version with the helper's exact pushed `commit_sha` and
   matching deployment archive. For the existing public Site use
   `deploy_site_version` with the exact saved `version_id`; do not use the
   owner-private deploy operation or change access.

## 4. Production acceptance

After deployment succeeds, check the live homepage, `/release.json`, and
`/CHANGELOG.md` over HTTP. Require the page and metadata to name the new version;
read the current `neantik-release-v1` JSON schema rather than assuming artifact
fields are top-level. Compare `version` and `source_commit` at the root, then
`archive.filename`, `archive.download_url`, `archive.size_bytes`, and
`archive.sha256` with the verified GitHub asset. A missing top-level alias is
not a mismatch if the nested canonical field is present; an absent or unequal
canonical field is a failed gate. Check a public ZIP HEAD response and content
length, and retain the fresh download/hash evidence. Record the browser binary
source commit separately from the Site source commit and the Sites version
number.

Never describe successful deployment or a checksum as proof of complete
anonymity, fingerprint resistance, or independent network-route behavior.
Publish only claims that the exact build and tests support.
