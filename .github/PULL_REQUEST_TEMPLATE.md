## Summary

Describe the user-visible change.

## Verification

- [ ] `python -m unittest -v test_nevision_win.py`
- [ ] `python .\nevision_win.py --self-test`
- [ ] `.\tools\check-public-repo.ps1 -StagedOnly`
- [ ] No `Data/`, browser profile, backup, credential, certificate or generated release file is included.

## Scope

- [ ] This does not add fingerprint spoofing, anti-fraud bypass, account automation, cloud sync or telemetry.
