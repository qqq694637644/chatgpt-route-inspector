# Privacy Policy

Effective date: August 24, 2026

ChatGPT Route Inspector (the “Extension”) is a local model-route inspection extension for Microsoft Edge for Android 151 and later. This policy explains how the Extension handles data.

## Data handled

The Extension processes only information needed for model-route inspection on `https://chatgpt.com/`, including:

- model identifiers requested by the web client;
- route models reported by server responses and related model labels;
- capture mode, evidence sources, inspection status, timestamps, and duration;
- routing-related metadata such as reasoning effort, conversation mode, and tool-use status;
- PoW difficulty values;
- tab IDs, ChatGPT page URLs, and conversation, request, and network-request identifiers;
- user settings such as language, capture mode, overlay state, and record limit.

The Extension temporarily parses requests and responses already sent or received by the ChatGPT page to extract these allowlisted fields. Unfiltered requests and responses are not written to extension storage.

## Data not handled or stored

The Extension does not store or upload:

- prompt or answer text;
- cookies, Authorization headers, JWTs, passwords, or other login credentials;
- attachment contents or filenames;
- PoW seeds, proof tokens, or device fingerprints;
- complete network requests, responses, or HAR files.

The Extension contains no advertising, analytics SDK, or user-tracking code.

## How data is used

Data is handled only to:

- display the requested model and the response route reported by the server;
- identify changes in model routing;
- display PoW difficulty and diagnostic information;
- retain local inspection history and generate diagnostic reports requested by the user.

The Extension does not sell data, use data for advertising, or provide data to data brokers or other third parties.

## Local storage and retention

Settings and inspection records are stored in `chrome.storage.local` inside the current Microsoft Edge profile. `chrome.storage.local` is the Chromium extension API namespace exposed by Microsoft Edge; using that namespace does not imply Google Chrome support.

The configured record limit controls retention. When the limit is reached, the oldest records are removed automatically. Users can clear local records from the Extension's Settings & Privacy page. Removing the Extension also removes its extension-local data according to Microsoft Edge platform behavior.

## Data transmission and exports

The Extension does not automatically transmit inspection data to the developer or any third-party server. If a user opens an author, GitHub, or other external link, Microsoft Edge navigates to that website normally.

Copying a summary, exporting JSON, or exporting a report requires an explicit user action. Exports contain routing-diagnostic fields only. Request identifiers are redacted by default and are included in full only when the user explicitly enables that setting.

## Browser permissions

- `storage`: stores settings and inspection records in the current Microsoft Edge profile.
- `https://chatgpt.com/*`: reads allowlisted routing fields on supported ChatGPT pages and displays the page overlay.

The Extension does not request `debugger`, `cookies`, `webRequest`, `history`, or access to all websites.

## Microsoft Edge Add-ons distribution

The production distribution target is Microsoft Edge Add-ons. Information received through Microsoft Edge extension APIs is used only for the user-facing inspection features described in this policy. The project does not maintain a Google Chrome or Chrome Web Store compatibility/distribution path starting with version 2.0.

## Changes to this policy

If the Extension’s data-handling practices change, this policy will be updated and the effective date above will be revised.

## Contact

For privacy questions, contact the project maintainer through [GitHub Issues](https://github.com/qqq694637644/chatgpt-route-inspector/issues).
