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

### Device development and validation

`dist/edge-android` is a deployable extension artifact. **Desktop Edge/Chromium Load unpacked and Windows Playwright are not Android E2E.** Android acceptance is based on the extension actually running in Microsoft Edge for Android, deployed through Edge Add-ons or managed Android extension policy.

When the automation environment has no Android device, it can verify the build artifact contract only and must not claim Android E2E passed.

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

The repository no longer treats Windows / desktop Chromium Playwright as Edge Android E2E. Real E2E must run in Microsoft Edge on a physical Android device. The repository provides automated type, lint, unit/integration, build, and artifact-contract checks plus a device acceptance checklist.

## Disclaimer

This is an independent, unofficial project and is not affiliated with, authorized by, or endorsed by OpenAI or Microsoft. ChatGPT, OpenAI, Microsoft Edge, and related marks belong to their respective owners. The extension reports information available in ChatGPT web requests and responses; it is not an official attestation of OpenAI infrastructure, billing systems, or account status.
