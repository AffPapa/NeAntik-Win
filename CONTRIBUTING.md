# Contributing to NeAntik Win

NeAntik Win is an open, local-first portable browser project. The current
download is a preview, not a guarantee of anonymity. Read the
[implementation plan](docs/MASTER_IMPLEMENTATION_PLAN.md) and the
[native-prototype audit](docs/NATIVE_PERSONA_PROTOTYPE_AUDIT.md) before changing
privacy behavior.

## Local setup

Use Windows, PowerShell and Python 3.12.

```powershell
python -m pip install -r requirements-build.txt
python -m pip install -r requirements-dev.txt
python -m unittest -v test_nevision_win.py test_proxy_diagnostics.py
python .\nevision_win.py --self-test
```

`requirements-dev.txt` is only needed to regenerate the application icon.

## Pull-request rules

- Keep the product local-first; do not add cloud sync, telemetry or credentials to source.
- Do not add `Data/`, browser profiles, backups, databases, logs, screenshots with private
  data, tokens or certificates.
- Add a regression test for a behaviour change in storage, recovery or profile launch logic.
- Run `.\tools\check-public-repo.ps1 -StagedOnly` and the test commands before opening a PR.
- Run `.\tools\test-release-tools.ps1` when changing packaging or release gates.
- Update [CHANGELOG.md](CHANGELOG.md) only for a user-visible release change.

## UI and security boundary

The downloadable browser bundles Chromium and separates local profile data.
Experimental native privacy changes are welcome only as reviewable patches
against the pinned Chromium source, with an explicit threat model, cross-context
tests, compatibility and performance measurements, and truthful release notes.
Do not present distinct per-profile values as proof of anonymity: they may make
people easier to recognize. Keep experimental switches disabled in public
builds until the documented release gates pass.

Do not add account automation, credential collection, telemetry, hidden network
fallbacks, or claims of anti-fraud bypass. Do not disable Chromium's sandbox or
security updates to make a privacy feature work. Report suspected vulnerabilities
privately before publishing exploit details.
