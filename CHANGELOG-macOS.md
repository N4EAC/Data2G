# macOS changelog

## 0.5.3 macOS beta 1 — 2026-11-24

- Package the upstream HF modem and Qt GUI through `95c94b1` as Data2G.app.
- Include HF carrier/noise and receive-preview fixes after upstream v0.5.3.
- Bundle Hamlib, miniaudio, TCI, command/KISS interfaces and diagnostic tools.
- Isolate preferences from the official build and Ragtime apps.
- Include source revisions, licenses and a reproducible macOS build recipe.
- Verify 33 native/GUI tests and interoperability with Ragtime macOS.

Apple Silicon, macOS 27 or later. Physical radio TX/ALC requires station testing.
