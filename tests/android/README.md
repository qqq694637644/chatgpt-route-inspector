# Edge Android arm64-v8a emulator E2E

This directory contains the Python-driven Android E2E used by `.github/workflows/edge-android-e2e.yml`.

## Test boundary

The test runs Microsoft Edge Canary **inside an Android `arm64-v8a` emulator**. Desktop Edge/Chromium is not used as a browser substitute. The current CI image uses API 35 only as the selected system image; the test contract is the Android `arm64-v8a` ABI, not the CI host architecture or a specific Android release.

The workflow YAML is only environment orchestration. APK download and verification, CRX3 creation, Android UI automation, DevTools/CDP assertions, screenshots, and failure evidence collection are implemented in `run_edge_android_e2e.py`. Do not move test logic into inline Python, `python -c`, shell heredocs, or YAML-generated Python source.

## Trust pins

The test downloads a pinned Edge Canary APK through `justapk` using the APKPure source, then refuses to install it unless all of these match the constants in `run_edge_android_e2e.py`:

- package: `com.microsoft.emmx.canary`;
- version: pinned Edge Canary version;
- signer SHA-256: pinned Microsoft Edge Android signing certificate;
- native ABI: `arm64-v8a`.

The APK file SHA-256 is recorded in the job log for evidence but is not used as the trust root because mirror-side packaging can change the file digest. The Microsoft signer certificate, package name, pinned version, and `arm64-v8a` ABI are mandatory. A re-signed APK or a different package/version/ABI fails before installation.

## What is asserted

The emulator test verifies:

1. Android is actually running with the `arm64-v8a` ABI.
2. The pinned Microsoft-signed Edge Canary APK is installed.
3. The current `dist/edge-android` build is packaged as CRX3 and side-loaded through Edge Android Developer Options.
4. Edge exposes the extension service worker with the CRX's expected extension ID.
5. Opening `https://chatgpt.com/` injects the Route Inspector overlay.
6. `window.fetch` and `window.WebSocket` are wrapped in the MAIN world at runtime.
7. Overlay compact/expand interaction works in the Android browser.
8. A synthetic same-origin conversation request is captured through MAIN hook → page message → ISOLATED bridge → extension runtime → service worker → `chrome.storage.local`.

The synthetic request can receive a network error or unauthorized response; the assertion concerns interception of the outgoing request before the server result and does not require a ChatGPT account or secret.

## Local self-check

After building the extension and installing `requirements.txt`, the Python dependency/CRX packaging path can be checked without an emulator:

```text
python tests/android/run_edge_android_e2e.py --self-check
```

The pinned Edge APK trust inputs can be checked independently with:

```text
python tests/android/run_edge_android_e2e.py --verify-edge-apk
```

The full command without `--self-check` expects a booted `arm64-v8a` Android emulator reachable through ADB.
