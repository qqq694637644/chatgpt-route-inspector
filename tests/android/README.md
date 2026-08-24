# Edge Android arm64-v8a E2E

This directory contains the Python-driven Android E2E used by `.github/workflows/edge-android-e2e.yml`.

## Test boundary

The test runs a real **arm64-v8a Microsoft Edge Canary APK** inside the Android Emulator. Desktop Edge/Chromium is not used as a browser substitute.

GitHub-hosted macOS ARM runners cannot boot a true arm64 AVD because nested Hypervisor.Framework is unavailable (`HV_UNSUPPORTED`). The hosted CI therefore uses Google's API 35 `google_apis/x86_64` Android system image, whose Android ABI list includes `arm64-v8a` and whose native translation can execute ARM64-only APKs. The test contract is ARM64 Android application execution, not the CI host CPU or the AVD's primary CPU ABI.

The workflow YAML is only environment orchestration. APK download and verification, CRX3 creation, Android UI automation, DevTools/CDP assertions, screenshots, and failure evidence collection are implemented in `run_edge_android_e2e.py`. Do not move test logic into inline Python, `python -c`, shell heredocs, or YAML-generated Python source.

## Trust pins

The test downloads a pinned Edge Canary APK through `justapk` using the APKPure source, then refuses to install it unless all of these match the constants in `run_edge_android_e2e.py`:

- package: `com.microsoft.emmx.canary`;
- version: pinned Edge Canary version;
- signer SHA-256: pinned Microsoft Edge Android signing certificate;
- native ABI: `arm64-v8a`.

The APK file SHA-256 is recorded in the job log for evidence but is not used as the trust root because mirror-side packaging can change the file digest. The Microsoft signer certificate, package name, pinned version, and `arm64-v8a` ABI are mandatory. A re-signed APK or a different package/version/ABI fails before installation.

Downloaded APKs and the ephemeral CRX signing key live under `.tmp/edge-android-e2e` and are never uploaded as CI evidence. The evidence artifact contains only test outputs such as the generated CRX, screenshots, UI dumps, and logcat.

## What is asserted

The emulator test verifies:

1. Android is running and advertises `arm64-v8a` in `ro.product.cpu.abilist`.
2. The pinned Microsoft-signed Edge Canary APK is installed.
3. Android reports the installed Edge package as `primaryCpuAbi=arm64-v8a`.
4. The current `dist/edge-android` build is packaged as CRX3 and side-loaded through Edge Android Developer Options.
5. Edge exposes the extension service worker with the CRX's expected extension ID.
6. Opening `https://chatgpt.com/` injects the Route Inspector overlay.
7. `window.fetch` and `window.WebSocket` are wrapped in the MAIN world at runtime.
8. Overlay compact/expand interaction works in the Android browser.
9. A synthetic same-origin conversation request is captured through MAIN hook → page message → ISOLATED bridge → extension runtime → service worker → `chrome.storage.local`.

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

The full command without flags expects a booted Android emulator reachable through ADB with `arm64-v8a` listed as a supported ABI.
