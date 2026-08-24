<div align="center">

# ChatGPT Route Inspector · Edge Android

A ChatGPT model-route inspection extension for **Microsoft Edge for Android 151+**.

Languages: [简体中文](README.md) · [English](README-en.md)

</div>

## 2.0 breaking update

Starting with 2.0, this project targets Microsoft Edge for Android only. The following compatibility paths are intentionally removed:

- Google Chrome / Chrome Web Store;
- desktop Edge and other Chromium browsers;
- Chromium / Edge 150 and older;
- the legacy `chat.openai.com` origin;
- desktop extension `options_ui` / `openOptionsPage` entry points.

The code still uses the `chrome.*` namespace because Microsoft Edge's Chromium extension APIs use that namespace. This does not mean Google Chrome remains a supported target.

## Features

- **Live request inspection**: shows the model requested by the ChatGPT web client and the route model reported by the server response.
- **Conversation reload inspection**: reloads an existing conversation and reads available route fields and model labels.
- **Page overlay**: shows the requested model, response route, and PoW difficulty directly on ChatGPT.
- **Mobile popup**: narrow-screen, touch-oriented layout instead of desktop-toolbar sizing.
- **Route diagnostics**: reviews locally stored records and exports Markdown / JSON.
- **Local-first storage**: records stay in the current Edge profile through `chrome.storage.local` and are not automatically uploaded.

The extension only reports fields that are present in requests or responses. It does not infer a model from speed, writing style, self-identification, or subjective quality.

## Platform baseline

- Microsoft Edge for Android **151+**
- Manifest V3
- Target origin: `https://chatgpt.com/*` only
- Required Edge Android extension APIs: `action`, `runtime`, `storage`, `tabs`, and `i18n`

There is no legacy-platform fallback path. If the required APIs are unavailable or Edge is older than 151, that environment is unsupported.

## Android installation and distribution

### Microsoft Edge Add-ons

The production distribution target is **Microsoft Edge Add-ons**. The generated ZIP is intended for Partner Center submission. After certification, the listing still has to be verified on a physical Android device as available to Edge mobile; desktop store certification alone is not treated as proof that Android installation is available.

This repository no longer provides a Chrome Web Store installation path.

### Managed Android devices

After the extension has an Edge Add-ons ID / update URL, administrators can deploy it to managed Android devices through Edge's `ExtensionInstallForcelist` / `ExtensionSettings` policies.

### Android arm64-v8a emulator E2E and device validation

`dist/edge-android` is a deployable extension artifact. **Desktop Edge/Chromium Load unpacked and Windows Playwright are not Android E2E.**

The GitHub Actions `Edge Android arm64-v8a E2E` workflow uses two infrastructure jobs. An x86_64 Ubuntu builder only shallow-syncs `emu-master-dev` and cross-builds the ARM64 Emulator bundle with Google's supported `--target linux_aarch64` path. The actual browser E2E runs only on GitHub's native `ubuntu-24.04-arm` runner. The ARM job verifies that the downloaded Emulator host executable is ARM64, then downloads the Google APIs API 35 `arm64-v8a` system image, verifies the repository-provided digest, creates the AVD, and boots it. It does not use Android's ARM-on-x86 native bridge and never falls back to x86_64 Android.

The Python test requires Android itself to report `ro.product.cpu.abi=arm64-v8a`, `uname -m` as `aarch64`/`arm64`, no active native bridge, and the installed Edge package as `primaryCpuAbi=arm64-v8a`. It then verifies the Microsoft APK signing certificate, extension service worker, `MAIN` / `ISOLATED` injection, overlay interaction, and the complete `fetch` request-to-`chrome.storage.local` pipeline.

Automated sideloading of an unpublished extension uses Edge Canary; the production baseline remains Edge Android 151+. A physical phone/tablet should still be used for store distribution, touch sizing, and download acceptance.

## Build from source

Node.js 20 or newer is required.

```powershell
npm ci
npm run build
```

Build output:

```text
dist/edge-android/
```

Create the Partner Center submission package:

```powershell
npm run package
```

Output:

```text
release/chatgpt-route-inspector-edge-android-2.0.0.zip
release/SHA256SUMS.txt
```

## Usage

### Inspect a new answer

1. Open `https://chatgpt.com/` in Edge Android and enter the target conversation.
2. Open Route Inspector from Edge's extension surface.
3. Select **Live request**.
4. Send a message in ChatGPT.
5. Read **Requested model → Response route** in the popup or page overlay.

### Review an existing answer

1. Select **Reload session** in the extension popup.
2. Reload the current ChatGPT conversation.
3. Review the response-route fields and model labels available for the active conversation.

## Privacy and permissions

See [PRIVACY.md](PRIVACY.md) for the complete disclosure.

| Permission / host | Purpose |
|---|---|
| `storage` | Stores settings and inspection records in the current Edge profile |
| `https://chatgpt.com/*` | Injects the route-inspection scripts and displays the page overlay |

The extension does not request `debugger`, `cookies`, `webRequest`, `history`, or `<all_urls>`, and it does not store prompt text, answer text, cookies, Authorization headers, JWTs, attachment contents, or complete network responses.

## Android device acceptance

See the [Edge Android manual verification guide](docs/edge-android-manual-verification.md) for installation, interaction, and route-capture acceptance on a physical Android device.

## Development validation

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npm run verify:edge-android
npm run package
```

Android E2E runs in an `arm64-v8a` emulator through `tests/android/run_edge_android_e2e.py --managed-emulator`. The workflow YAML is limited to checkout, runtime/dependency installation, build, invoking the Python file, and uploading evidence. Emulator/system-image acquisition and verification, AVD lifecycle, APK acquisition/signature checks, Android UI automation, CRX installation, and browser assertions all live in Python files, with no `python -c`, heredoc, or YAML-inline Python. Physical-device acceptance remains documented in the manual verification guide.

## Disclaimer

This is an independent, unofficial project and is not affiliated with, authorized by, or endorsed by OpenAI or Microsoft. ChatGPT, OpenAI, Microsoft Edge, and related marks belong to their respective owners. The extension reports information available in ChatGPT web requests and responses; it is not an official attestation of OpenAI infrastructure, billing systems, or account status.
