# Release operations: GitHub + public Site

This is the repeatable publication path validated on the Windows host on
2026-10-14. It supplements the per-version evidence; it does not replace the
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
   immutable annotated tag at the recorded binary source commit. Do not move an
   existing tag or overwrite a published release.

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
- Create the release against the exact tag and upload the portable ZIP, its
  `.sha256` sidecar, and the build manifest. Keep the release prerelease when
  the channel is preview.
- Query public release metadata and print only allowlisted fields (tag,
  prerelease state, asset names/sizes/states/digests). Download the ZIP again
  from the public `browser_download_url`. Require nonzero size, exact size and
  SHA-256 equality with the local candidate and the published sidecar/API
  digest; rerun the archive verifier on the downloaded bytes. A zero-byte file
  from `gh release download` is not a pass: retry once with `curl.exe -L
  --fail` to the public asset URL, then stop if it is still incomplete.

## 3. Update the existing Sites publication

1. Read the Sites skill and the selected checkout's `.openai/hosting.json`.
   Preserve the current Site audience. Call `get_site`; use its exact
   `project_id`, then obtain the short-lived source-write credential. Keep that
   credential only in session memory and send it to `site-workflow.mjs` via its
   hidden stdin protocol. Never write it to disk, command arguments, output or
   chat.
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
4. Important retry rule: `site-workflow.mjs` saves/pushes the source commit
   before it packages the deployment archive. If the helper fails during
   packaging, first inspect branch, HEAD, working tree and remote state. The
   exact source commit may already have been pushed; do not blindly repeat the
   edit or create another commit. Complete packaging for that same commit.
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
