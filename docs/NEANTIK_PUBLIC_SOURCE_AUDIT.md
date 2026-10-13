# NeAntik Win: source publication audit

> Historical pre-publication snapshot from 2026-10-11. Its findings about a
> missing remote, license and commits described the old working tree, not the
> current public repository. Before any new publication, inspect the exact
> staged diff and run the current source/release gates; do not reuse this
> report as a security clearance.

Audit date: 2026-10-11. Read-only inspection of the existing NeVision Win source tree before the requested rename and first GitHub publication. Only this report was added by this audit; no staging, commits, remote changes or application changes were performed.

## Result and required preparation

The existing public-source guard passed for 56 candidate files. That is a useful check against common token formats and forbidden runtime files, not proof that every possible secret or personal detail is absent. The source repository has no commits and no remote. Its index already contains user-staged files, some older than the working copies; preserve that state or publish from a separately prepared source checkout rather than accidentally committing the stale index.

Publication needs these concrete changes before the first public push:

1. Decide and record the project's source license. No project `LICENSE` file exists; third-party licenses do not license this application's own code or graphics. Public GitHub hosting without a source license is technically possible, but recipients would not receive general reuse rights. The new user's explicit source-publication instruction supersedes the old private-only planning text; do not infer a preferred permissive/copyleft license from that instruction.
2. Rename the product, executable, build metadata, documentation and GitHub configuration consistently to NeAntik Win. Update the existing old publication instructions and Windows CI paths. Keep old backup-format/schema identifiers compatible when renaming so users can import existing data.
3. Sanitize local author paths in `PUBLISHING.md` and three integration reports, or omit those generated reports from the public source export. Findings: `docs/qa/browser-integration-0.2.0.json:237`, `docs/qa/browser-integration-0.2.1.json:249`, `docs/qa/proxy-integration-0.2.1.json:315`. Replace disposable root strings with `<temporary-qa-root>`; preserve measured values, source hashes and limitations. Standard `C:\Program Files\...` browser paths are installation evidence rather than credentials.
4. Stage an explicit curated source list, inspect the resulting index, then run `tools/check-public-repo.ps1 -StagedOnly` and `git diff --cached --check`. Repeat after implementing any new fingerprint subsystem, including its dependencies, generated scripts and engine artifacts.
5. Validate a fresh checkout build and tests. Preserve every actual third-party notice needed by a future bundled browser engine. The current notice inventory covers the launcher/runtime, not a new browser engine.

## Curated source contents

The first source export should include these existing files, plus any new reviewed NeAntik implementation files and a selected project license:

```text
.gitattributes
.gitignore
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/dependabot.yml
.github/workflows/ci.yml
nevision_win.py                    # rename/update references as agreed
test_nevision_win.py               # same
release-version.json
requirements-build.txt
requirements-dev.txt
build.ps1
ARCHITECTURE.md
CHANGELOG.md
CONTRIBUTING.md
PUBLISHING.md                      # sanitize local userpath/update instructions
README.md
RELEASE_CHECKLIST.md
RELEASE_NOTES.md
SECURITY.md
SECURITY_AND_SCOPE.md
SUPPORT.md
THIRD_PARTY_NOTICES.md
assets/README.md
assets/app-icon-source.svg
assets/logo-mark.svg
assets/nevision-icon-preview.png   # rename/update assets as agreed
assets/nevision.ico
tools/check-public-repo.ps1
tools/render_brand_icon.py
tools/prepare-build-metadata.py
tools/release-helpers.ps1
tools/verify-release-archive.ps1
tools/test-release-tools.ps1
tools/licenses/Tcl-license.terms
tools/licenses/OpenSSL-LICENSE.txt
tools/benchmark_runtime.py
tools/browser_integration.py
tools/proxy_integration.py
tools/gui_regression.py
tools/measure-process.ps1
docs/MARKET_RESEARCH.md
docs/PLATFORM_AND_EXTENSIONS.md
docs/RESEARCH_BACKLOG.csv
docs/CYCLE_PLAN.md
docs/QA_REPORT.md
docs/NEANTIK_PUBLIC_SOURCE_AUDIT.md
```

`docs/qa/*.json` are optional historical evidence, not build inputs. Include only the reviewed/sanitized reports. They contain test-generated profile identifiers, local loopback endpoints, timestamps, machine specs, process IDs and browser diagnostic excerpts. No browser database, cookie contents, proxy password or live session file is needed to reproduce the build. The independent GUI backup/restore report already uses a redacted temporary-root placeholder and publishes counts/hashes rather than profile contents.

## Explicit exclusions

Exclude `.git/` from source export (initialize the destination repository independently), and exclude `Data/`, `data/`, `build/`, `dist/`, `release/`, `logs/`, `outputs/`, `storage/`, virtual environments, caches, database/session files, archives, signatures/private certificates, `.env*`, runtime downloads and generated executable/DLL/PDB files. The current `.gitignore` and guard cover these principal cases. They intentionally permit the project's ICO/PNG visual assets.

At least one old unpacked release folder contains a populated Chromium `Data/` tree. Never recursively upload the whole working directory, the parent project collection or an unpacked release directory. Publish a clean source export and separately attach a verified, newly built ZIP as a GitHub Release asset.

## Build reproducibility and notices

The current build requires Windows x64, Python 3.12, and pinned build dependencies from `requirements-build.txt`. Python's exact patch release is not pinned: a fresh environment can produce different runtime files and archive hashes. `build-provenance.json` records the source tree; `runtime-components.json` records actual runtime versions. This is reproducible functionality/provenance, not guaranteed byte-identical output.

`build.ps1` additionally requires assets, `release-version.json`, the listed release documentation, `tools/release-helpers.ps1`, `tools/prepare-build-metadata.py`, and both `tools/licenses/` files. These latter helpers and metadata are currently untracked and must be included; committing only the pre-existing index would omit them and break CI/builds. PyInstaller generates its spec in an isolated build workspace, so the `*.spec` ignore rule does not omit an essential source file in this architecture.

The metadata helper copies installed Python/Tk and package license texts and includes versioned Tcl/OpenSSL notices. Current dependencies are PyInstaller, pywin32, pywin32-ctypes and development-only Pillow. Chrome/Edge are currently installed prerequisites and are not bundled. A fingerprint implementation using a bundled browser must review its license inventory, distribution terms and source obligations before packaging it; the existing runtime inventory cannot substitute for that review.

## Guard coverage limits

The existing guard rejects runtime directories, credential/key file extensions, archives/binaries, large files and several common token patterns. It scans recognized text extensions, including Python, PowerShell, Markdown, JSON and YAML. It does not scan arbitrary CSV/HTML/JavaScript/TOML text, Git history, compressed assets or binary contents. It also does not flag ordinary local usernames or every secret format. Extend coverage to any new fingerprint source file types and run a second review of the exact staged diff before publication. Report matches by location/type, never print token values.

## Auth and external state

This audit did not inspect stored GitHub credentials and did not test account authentication. Account connection and repository creation belong to the parent task. A GitHub identity and repository URL must be verified before the first push; do not overwrite the neighboring macOS repository or reuse its remote by inference.
