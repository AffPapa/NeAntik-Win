# Contributing to NeVision Win

## Local setup

Use Windows, PowerShell and Python 3.12.

```powershell
python -m pip install -r requirements-build.txt
python -m pip install -r requirements-dev.txt
python -m unittest -v test_nevision_win.py
python .\nevision_win.py --self-test
```

`requirements-dev.txt` is only needed to regenerate the application icon.

## Pull-request rules

- Keep the product local-first; do not add cloud sync, telemetry or credentials to source.
- Do not add `Data/`, browser profiles, backups, databases, logs, screenshots with private
  data, tokens or certificates.
- Add a regression test for a behaviour change in storage, recovery or profile launch logic.
- Run `.\tools\check-public-repo.ps1 -StagedOnly` and the test commands before opening a PR.
- Update [CHANGELOG.md](CHANGELOG.md) only for a user-visible release change.

## UI and security boundary

NeVision Win uses ordinary Chrome/Edge profile isolation. Contributions must not add fingerprint
spoofing, anti-fraud bypass, account automation or credential collection.
