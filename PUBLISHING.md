# Safe GitHub publication

## Scope boundary

Publish only the reviewed source export of this application as **NeAntik-Win**.

Never publish the parent `TGNET` folder. It contains other projects and local configuration that
are outside NeAntik Win. The separate macOS repository must not be modified.

## Before the first push

1. The owner has requested public source publication. Do not silently assign MIT, GPL or another
   reuse license: no original-source license has been selected. Preserve all third-party notices.
   A public repository without an explicit license does not grant an open-source reuse license.
   Review visual-asset provenance before inclusion.
2. Run the local guard and tests:

   ```powershell
   .\tools\check-public-repo.ps1 -StagedOnly
   git diff --cached --name-only
   git diff --cached --check
   python -m unittest -v test_nevision_win.py
   python .\nevision_win.py --self-test
   ```

3. Confirm that the staged list contains only source, tests, documentation, assets, tools and
   `.github/`. It must not contain `Data/`, `release/`, `build/`, `dist/`, archives or binaries.

## Create the GitHub repository

1. On GitHub, create `NeAntik-Win` as a **Public** repository in the authenticated owner's account. Do not ask GitHub to generate a
   README, `.gitignore` or license because they are managed locally.
2. In this local folder, configure the public identity you want GitHub commits to show, create
   the first commit, add the remote and push:

   ```powershell
   git config user.name "Your public name"
   git config user.email "your-public-email@example.com"
   git commit -m "chore: prepare public repository"
   git branch -M main
   git remote add origin https://github.com/<your-account>/NeAntik-Win.git
   git push -u origin main
   ```

3. On GitHub, review the **Files** tab and **Security** tab. Enable Dependabot alerts, secret
   scanning, push protection and private vulnerability reporting where available.

Use `python tools/export-public-source.py --help` to prepare a new, out-of-tree, allowlisted
source snapshot. It excludes runtime data, engine binaries, build/release folders and transient
QA reports. Review its inventory and run the guard inside the export before any commit or push.
Never push the current workspace's existing index without reviewing its staged files.

## Publish a binary safely

1. Build from a clean checkout. Do not reuse an unpacked portable folder that has ever been run,
   because it may contain `Data/`.
2. Run `.\build.ps1 -Clean`, then test the generated EXE with `--self-test`.
3. Run `.\tools\verify-release-archive.ps1 -ArchivePath <path-to-zip>`.
4. On GitHub, create a **draft prerelease** for the matching tag, for example
   `v0.1.3-preview`.
5. Attach only the freshly generated ZIP, its matching `.sha256` file and the release
   `.manifest.json` file. Never attach an
   unpacked `release/` folder, `Data/`, an EXE by itself, a signing certificate or a screenshot
   containing user data.
6. State clearly that the preview is unsigned until code signing is introduced.
