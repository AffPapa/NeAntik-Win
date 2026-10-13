# Chromium lifecycle checkpoint — 13 October 2026

This is a dated **P5.1 decision record**, not a standing claim that the
portable browser is current or secure. Check the live release channel again
before each new release and after a security advisory.

## 14 October checkpoint for 0.8.13-preview

The exact 0.8.13 portable ZIP still bundles Chromium `155.0.8059.40`, with
`chrome.exe` SHA-256
`751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
Its source/binary tag is `4543ce34b92a6428f3540ed511b888ca64c19b12`;
the public ZIP SHA-256 is
`41cb553778d476e2dc175c9b57bd24d0b316af99d46e614e6043ad6eb05fac62`.
On 14 October, the official desktop [general Stable post of 6 October](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_086471744.html)
still listed Windows `155.0.8059.39/.40`; the [7 October Early Stable post](https://chromereleases.googleblog.com/2026/10/early-stable-update-for-desktop.html)
listed `156.0.8078.12/.13` for a small percentage of users. Do not treat
Early Stable alone as proof that the shipped general-Stable core is obsolete.
This is a point-in-time channel observation, not a security certificate or a
waiver of an urgent advisory.

## Exact shipped core

- Public portable release: `v0.8.7-preview`; downloaded ZIP SHA-256
  `9bf12392f8c8057763024cb88666679e8d9938e73cc050f976e7057b5c5234d1`.
- Extracted `chrome.exe` Windows ProductVersion: `155.0.8059.40`; SHA-256
  `751c706c20bba0583fdfbf7c239a3bc42b29cf67b9e0c7820e8c01139a0ef2eb`.
- Bundled `ENGINE_PROVENANCE.json` names upstream Chromium commit
  `cfaadc5a132d78e1828635aa8405a499f3e14864` and version
  `155.0.8059.40`. This records source provenance; it does not prove a
  byte-for-byte reproducible build.
- The public v0.8.7 release tag resolves to application source commit
  `d2e6eac9a50f5edfa474ec72aff9ace64c2e8801`; later documentation-only commits
  do not change the binary provenance. The public ZIP checksum was independently
  matched against the downloaded release archive and Site metadata during this
  checkpoint.
- The live [Site release metadata](https://nevision-win.mail782861.chatgpt.site/release.json)
  reported the same version, engine version and public ZIP SHA-256 during this
  checkpoint.

## Upstream channel observation

The official [Chrome Releases desktop Stable update of 6 October](https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_086471744.html)
lists Windows `155.0.8059.39/.40`. The official
[Early Stable update of 7 October](https://chromereleases.googleblog.com/2026/10/early-stable-update-for-desktop.html)
lists `156.0.8078.12/.13` for a limited percentage of users. The
[Chromium Dash Windows Stable feed](https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform=Windows&num=5)
also listed `155.0.8059.40` and `156.0.8078.12` when queried on 13 October.
The feed includes Early Stable; do not treat its highest milestone alone as a
general Stable security-upgrade instruction.

**Decision:** no source or portable rebuild solely for this checkpoint. The
shipped 155.0.8059.40 matches the published general Windows Stable version
observed here. This does not establish that every Chrome security fix applies
identically to the unbranded patched Chromium build or that no later advisory
exists. The portable core has no automatic updater.

## Next update gate

When a newer general Stable or relevant security fix is published, compare
the exact upstream commit and advisories, rebase and review the public patch,
build the pinned source, then repeat fingerprint, route, profile-migration,
packaged-GUI and public-download gates on the **new** binary SHA-256. Update
the changelog and Site only after the new immutable ZIP, checksum and source
tag agree. Preserve old `Data/` and a rollback snapshot; never silently
replace the user's portable folder.
