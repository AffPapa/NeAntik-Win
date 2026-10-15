# Encrypted portable backup: review gate (2026-10)

Status: design review only. No encryption implementation is enabled, no backup
format changed, and no new portable artifact was built or published.

## Current behavior (source `457debee7dd84fb595649cbc9983b8ae7a5bbab8`)

- Profile backup is ZIP `nevision-profile-backup-v1` (native preview profiles
  use the corresponding native format) with `encrypted: false`.
- Browser session state can include cookies and active logins. Proxy credentials
  are intentionally omitted.
- Restore bounds ZIP metadata, validates paths/types/duplicates and size, then
  extracts into a staging directory and uses the existing recovery journal and
  atomic profile publication path.
- Legacy ZIP restore compatibility is covered by source tests and must remain
  unchanged if an encrypted export is later added.
- The existing frozen application does not contain or verify an encryption
  implementation. Installed Python packages are not a reproducible dependency.
- Backup creation removes its `.partial` on caught exceptions, but no startup
  reconciliation for a process/power-crash leftover was found. Cleanup behavior
  is **NOT RUN** and must not be added without proving it cannot remove another
  manager instance's active partial archive.

## Review outcome

Do not invent a password-encryption envelope or add an unreviewed cipher/KDF to
the release. A multi-gigabyte archive requires authenticated streaming semantics,
not merely encrypting a whole in-memory byte string. An accepted design must
authenticate format/version/algorithm parameters, bound attacker-controlled
KDF costs before work/allocation, detect truncation/reordering/corruption and
wrong passphrases, and verify the complete encrypted input before restoring any
profile. If plaintext staging is necessary, its ACL, lifetime, crash cleanup,
disk-space failure behavior and residual-data limitations need explicit review.

The format and primitive selection remain open: one packaging review found
Python `hashlib.scrypt` available and AES-GCM packaging feasible through
PyInstaller hooks; the independent threat-model review recommends a maintained
streaming-AEAD design and Argon2id, with independent format/implementation
review. These are not yet reconciled into a reviewed, reproducible Windows
implementation. No dependency choice should be inferred from these notes.

## Required gates before implementation/public release

1. Select a maintained, versioned streaming container and implementation; record
   threat model, license, exact dependency versions and hashes, supported
   Windows/Python ABI, and portable packaging hook behavior.
2. Independent crypto review and known-answer/interoperability vectors before
   product integration. Reject unknown algorithms and excessive KDF parameters
   before invoking the KDF.
3. Preserve old plaintext ZIP import and label it honestly; never silently
   downgrade an encrypted export. Never persist or log the passphrase.
4. Source tests: wrong passphrase, header/tag tamper, truncation, appended data,
   chunk boundary/final-record verification, reordered/duplicated chunks,
   invalid/extreme KDF parameters rejected before KDF, cancellation/write failure,
   legacy ZIP restore, hostile ZIP limits, and crash/restart at each staging and
   publication boundary. Synthetic data only.
5. Portable-artifact tests on the exact extracted ZIP: packaged crypto
   self-test, successful round trip, wrong passphrase and tamper rejection,
   no profile/database mutation on failure, bounded-memory large-file test,
   dependency/license audit, and scan for residual plaintext staging. Separately
   test crash-leftover `.partial` handling under concurrent manager instances.
6. Only after all gates pass may UI and public copy describe encrypted export.
   It must state that a forgotten passphrase is unrecoverable and that backup
   encryption does not encrypt the live profile or protect against malware under
   the same Windows account.

## Findings not promoted to product claims

- No encrypted backup source test or package self-test exists: **NOT RUN**.
- No independent cryptographic implementation review/vector validation exists:
  **NOT RUN**.
- No exact portable artifact containing an encryption primitive exists: **NOT
  RUN**.
- This review does not change the product's network, fingerprint, or anonymity
  claims.

## Follow-up review (2026-10-16)

Two separate read-only reviews of the current source confirmed the existing
backup/restore boundaries and examined the Windows packaging path. No files
were changed by those reviewers and no tests were run as part of their review.

- Existing regression coverage exercises ZIP validation, legacy ZIP restore,
  tampering/corruption, size limits, and backup/restore transaction handling;
  it does not prove encryption behavior.
- `build.ps1` creates a PyInstaller `--onedir --windowed` bundle. That layout
  can carry native Python wheels in principle, but no cryptography dependency,
  frozen-app smoke test, or exact-artifact self-test exists. Feasibility is
  **NOT RUN**, not PASS.
- A dependency addition must also update the pinned build requirements,
  `tools/prepare-build-metadata.py`'s dependency/license allowlist,
  `THIRD_PARTY_NOTICES.md`, CI installation, public-source export checks, and
  release-tool tests. A successful source import alone is not packaging proof.
- The current design gate remains open: choose a maintained, independently
  specified streaming container/implementation before product code. A primitive
  API such as AES-GCM is not by itself a reviewed multi-gigabyte file format.
  Do not invent framing, use a whole-file in-memory API, or silently apply
  DPAPI (which would break cross-account/PC portability).
- NIST SP 800-132 is the relevant published password-derived-storage guidance,
  but NIST's publication page says revision is planned. Its status does not
  select a KDF or validate this product's parameters. Likewise, the
  Cryptography project's AEAD page documents primitives, not a backup container.

Result: encrypted export remains **NOT IMPLEMENTED** and is not a release
claim. Legacy ZIP import/restore remains supported as-is. No new dependency,
format, UI, binary, or site copy is authorized by this review.

## References

- [RFC 9106: Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work
  Applications](https://www.rfc-editor.org/rfc/rfc9106.html)
- [age file format specification](https://github.com/C2SP/C2SP/blob/main/age.md)
- [PyCryptodome KDF documentation](https://pycryptodome.readthedocs.io/en/latest/src/protocol/kdf.html)
- [PyInstaller Hooks Contrib](https://github.com/pyinstaller/pyinstaller-hooks-contrib)
- [Cryptography: authenticated encryption API](https://cryptography.io/en/stable/hazmat/primitives/aead/)
- [NIST SP 800-132 publication and revision note](https://csrc.nist.gov/pubs/sp/800/132/final)
