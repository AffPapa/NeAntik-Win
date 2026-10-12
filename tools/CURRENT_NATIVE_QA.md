# Own Chromium 155 native-core QA

This harness targets NeAntik's own Chromium **155.0.8059.40**, source commit
`cfaadc5a132d78e1828635aa8405a499f3e14864`. It does not accept a different
browser, the previous Chromium 150 experiment, or JavaScript getter replacements
as substitutes for a native-core test.

## Prerequisites and invocation

Use Windows, Python 3, and a complete portable build with
`Engine/NeAntikChromium/core-manifest.json`. Obtain the manifest's SHA-256 from a
separately trusted build/release record; copying a digest from an untrusted
download is not authentication.

```powershell
python tools/test_current_native_fingerprint.py `
  --portable-root C:\QA\NeAntikWin `
  --execution-root C:\QA\NeAntikWin-DisposableCopy `
  --trusted-manifest-sha256 <trusted-64-character-sha256> `
  --output docs\qa\current-native-runtime.json
```

`--portable-root` is the immutable release candidate; `--execution-root` is a
separate disposable copy used for browser runs. Windows Chromium can create an
early-startup `debug.log` beside its executable during malformed-input tests.
The source bundle is reverified after visits; the disposable copy may contain
that test side effect. The executable and every manifest member in both roots
are checked before visits.
The manifest must exactly cover the engine tree; path traversal, alternate data
streams, symlinks/junctions, case collisions, unknown engine identity, and missing
files fail closed. The actual `--neantik-core-info` probe must report the pinned
version and all required capabilities, including the deliberately narrow
`canvas_opaque_srgb_uint8` capability rather than a general Canvas guarantee.
Capability declarations alone do not
count as runtime proof: page observations must also satisfy the assertions.

The tool uses fresh disposable profiles, except the explicit A/A restart test.
Every launched process belongs to an unnamed Windows Job created for this run;
closing that job terminates only those owned descendants. Existing user browser
processes are not targeted. Loopback servers do not forward external requests.
Disposable profiles are retained in the system temporary directory for failure
investigation. Generated QA JSON can contain environment observations and is not
part of the public-source export.

## Coverage

- Missing/malformed native flags must fail with exit 78.
- Main document, same/cross-origin iframe, dedicated/shared/service workers:
  hardware concurrency, device memory, Date/Intl timezone and DST observations.
- HTTP Client Hints are checked only for document/iframe fetch contexts. The
  tested Chromium WorkerFetchContext does not add Device-Memory hints because
  worker contexts lack Permissions Policy; worker JavaScript values are checked
  independently and this transport limitation is reported, not marked as a
  fingerprint match.
- Seed A, same-profile A restart, seed B, another hardware/timezone persona,
  and no-persona baseline.
- Canvas exact native pixel reference, absolute-coordinate subrects, repeated
  reads, `putImageData`, clearing, PNG exports, HTML and Offscreen paths.
- 2048 x 2048 readback and PNG timings, plus owned-process peak committed memory.
- WebRTC five-scenario network checks: ordinary and native unproxied positive
  controls must show an OS-accepted `UDP_BYTES_SENT` event to the exact owned
  STUN IP:port in NetLog. Native with an owned HTTP proxy must load the fixture
  through that proxy and show no send event to that endpoint. A broken HTTP proxy must receive the test
  document request without any DIRECT request reaching the owned origin.
  An additional unavailable TCP proxy test holds an exclusively bound, non-listening
  IPv4 TCP socket alive throughout the browser visit. Chrome must show the exact
  `ERR_PROXY_CONNECTION_FAILED` neterror, exit normally, and make no origin hit.
  Since headless Chrome may emit an empty dumpDOM for failed navigation, exact
  source-bound NetLog evidence is also accepted: the owned URL's unique
  `URL_REQUEST_START_JOB` BEGIN/END pair, same URL_REQUEST source ID, with numeric
  `net_error=-130`. Empty output, arbitrary log text or a different request's
  error cannot satisfy this check. WebRTC NetLog uses `Everything` capture but
  contains only fresh test profiles and is retained privately, never packaged
  or published. On the current host custom Chromium logged OS-accepted STUN
  sends but the local listener received zero datagrams; no raw-NIC capture was
  performed, so this does not prove external delivery.

The network fixture uses an owned UDP server on the active local IPv4 address;
the documentation-only route probe sends no packet. It removes Chrome's implicit loopback HTTP bypass with
`--proxy-bypass-list=<-loopback>`. Without that, visiting `127.0.0.1` would not
prove HTTP proxy use. These observations do not cover remote network interfaces,
external IP leaks, HTTPS CONNECT tunnelling, SOCKS, extensions, other UDP APIs or
a global network kill-switch. CONNECT is deliberately rejected, not claimed
tested. In the broken-proxy case JavaScript never loads, so its zero STUN count
does not by itself demonstrate WebRTC protection; the successful-proxy visit and
positive unproxied native control are both mandatory.
Both HTTP 502 and TCP unavailability are covered; the latter fixture may refuse
or drop a Windows SYN until timeout, but Chrome's precise neterror is separately
mandatory. DNS failure, proxy authentication and
failover lists remain separate uncovered cases.

Canvas protection is intentionally scoped to opaque sRGB uint8 pixels. P3,
float16, and translucent observations are recorded as **unprotected**. RGB high
bits remain intact, so this does not establish undetectability or resistance to
an adversarial normalization attack. Timings use one baseline visit and three
readbacks per case; they are not cold-start, p95, or controlled-laboratory claims.
GUI, extensions, proxy routing, real account workflows, other IANA zones and
transitions still require separate release QA.

## Harness self-tests are not native-browser evidence

```powershell
python -m unittest discover -s tools -p test_current_native_harness_unit.py -v
node --check tools/fixtures/current-native-surfaces.js
node --check tools/fixtures/current-native-driver.js
```

These use clearly labelled synthetic validator inputs or syntax checks. They
cannot certify native behavior. A real run returns exit 0 and report status
`passed` only after all required runtime assertions and final bundle checks pass.
A missing or incomplete compiled core returns a failure, not a placeholder PASS.
