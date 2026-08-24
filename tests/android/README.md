# Edge Android arm64-v8a translation E2E

This directory contains the Python-driven Android E2E used by `.github/workflows/edge-android-e2e.yml`.

## Test boundary

The test runs a real **arm64-v8a Microsoft Edge Canary APK** inside the standard GitHub Android CI shape: **Ubuntu 24.04 + KVM + Android API 35 x86_64 emulator** with Android's advertised `arm64-v8a` translation support. Desktop Edge/Chromium is not used as a browser substitute.

The workflow has one `ubuntu-24.04` job. `reactivecircus/android-emulator-runner` provisions the API 35 `google_apis/x86_64` AVD and KVM acceleration. Python then rejects the environment unless Android reports API 35, primary ABI `x86_64`, kernel machine `x86_64`, and `arm64-v8a` in `ro.product.cpu.abilist`. The Edge APK itself must still be the ARM64 variant and the installed package must report `primaryCpuAbi=arm64-v8a`.

This is intentionally the standard GitHub Android CI approach. A previous real run showed Edge Canary can still crash with `SIGSEGV` under Android's ARM translation; that is a known product/runtime risk, not hidden by a custom emulator fallback. If it happens again, the job must fail and upload logcat/UI evidence.

The workflow YAML is only environment orchestration. APK download and verification, CRX3 creation, Android UI automation, DevTools/CDP assertions, screenshots, and failure evidence collection are implemented in `run_edge_android_e2e.py`. Do not move test logic into inline Python, `python -c`, shell heredocs, or YAML-generated Python source.

## Trust pins

The test downloads a pinned Edge Canary APK through `justapk` using the APKPure source, then refuses to install it unless all of these match the constants in `run_edge_android_e2e.py`:

- package: `com.microsoft.emmx.canary`;
- version: APK manifest major version must be 151 or newer;
- signer SHA-256: pinned Microsoft Edge Android signing certificate;
- native ABI: `arm64-v8a`.

The requested mirror version is only a download hint. The test does not trust the mirror filename or metadata: it reads the actual `versionName` from the downloaded APK manifest, requires Edge major 151 or newer, and then requires the installed package to report that exact same version. The APK file SHA-256 is recorded in the job log for evidence but is not used as the trust root because mirror-side packaging can change the file digest. The Microsoft signer certificate, package name, manifest version, and `arm64-v8a` ABI are mandatory. A re-signed APK or a different package/unsupported version/ABI fails before or during installation.

Downloaded APKs and the ephemeral CRX signing key live under `.tmp/edge-android-e2e` and are never uploaded as CI evidence. The evidence artifact contains only test outputs such as the generated CRX, screenshots, UI dumps, and logcat.

## What is asserted

The emulator test verifies:

1. Android reports API 35 on an x86_64 KVM AVD and advertises `arm64-v8a` translation support.
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

Running `python tests/android/run_edge_android_e2e.py` expects the workflow-provisioned API 35 x86_64 emulator to be booted and reachable through ADB.
