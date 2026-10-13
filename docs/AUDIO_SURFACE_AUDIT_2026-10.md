# Audio fingerprint baseline — 13 October 2026

This is an observation, not an audio-fingerprint protection feature or an
anonymity claim. No audio patch or browser setting was changed in the public
0.8.3-preview ZIP.

## Reproducible measurement

`tools/fingerprint_surface_audit.py` renders a fixed 997 Hz triangle oscillator
through a 0.35 gain node in an `OfflineAudioContext` (one channel, 4096 frames,
44100 Hz). It hashes 2048 float samples after the first 256 frames rather than
recording a raw device fingerprint in the repository. The same operation runs
in the main frame, a same-origin iframe and a cross-origin iframe. The audit
also keeps its existing CPU, RAM, Canvas, WebGL, HTTP and worker checks.

Two complete runs against the **extracted public 0.8.3-preview Chromium** on
one Windows 11 x64 computer created four disposable profiles. All four runs
reported a valid 64-character digest, frame parity and the same digest across
profiles and runs. The private raw reports are:

- `C:\NeAntikBuild\qa\audio-fingerprint-v083-20261013-a.json`
- `C:\NeAntikBuild\qa\audio-fingerprint-v083-20261013-b.json`

The script returns a non-zero status if the observation is missing or any
frame comparison fails. Unit tests cover both cases.

The same extended audit ran once against the separately staged experimental
V3 core. Its ordinary and three persona runs had the same Audio digest and
passed cross-context consistency, but the overall V3 gate **failed** because
different Canvas seeds still produced different stable outputs. Private report:
`C:\NeAntikBuild\qa\audio-persona-v3-20261013.json`. V3 remains unreleased.

## What this does not establish

One oscillator and one machine cannot estimate entropy or establish how many
other computers share this result. It does not cover AudioWorklet, microphone
capture, speech synthesis, GPU/media codecs, different sample rates, two
hardware configurations or third-party sites. Equal values on four local
profiles do **not** imply anonymous or unlinkable profiles. A policy decision
for Audio remains open until a comparison with unmodified Chromium of the
same source revision, cross-machine measurements and compatibility testing.
