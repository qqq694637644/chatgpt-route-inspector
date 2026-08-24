from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import websocket
from crx3 import creator, verifier
from justapk import APKDownloader

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "edge-android-e2e"
EDGE_PACKAGE = "com.microsoft.emmx.canary"
EDGE_VERSION = "153.0.4201.0"
MICROSOFT_CERT_SHA256 = "01e1999710a82c2749b4d50c445dc85d670b6136089d0a766a73827c82a1eac9"
STATE_KEY = "chatgptRouteInspectorStateV2"
TEST_MODEL = "gpt-edge-android-ci"
DEVTOOLS_PORT = 9222


def log(message: str) -> None:
    print(f"[edge-android-e2e] {message}", flush=True)


def run(*args: str, check: bool = True, text: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(args, check=False, text=text, capture_output=True, timeout=timeout)
    if check and result.returncode != 0:
        stdout = result.stdout if text else "<binary>"
        stderr = result.stderr if text else "<binary>"
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\nstdout:\n{stdout}\nstderr:\n{stderr}")
    return result


def adb(*args: str, check: bool = True, text: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[Any]:
    return run("adb", *args, check=check, text=text, timeout=timeout)


def ensure_arm64_android() -> None:
    api = adb("shell", "getprop", "ro.build.version.sdk").stdout.strip()
    release = adb("shell", "getprop", "ro.build.version.release").stdout.strip()
    abi = adb("shell", "getprop", "ro.product.cpu.abi").stdout.strip()
    log(f"device Android {release}, API {api}, ABI {abi}")
    if abi != "arm64-v8a":
        raise AssertionError(f"expected arm64-v8a emulator, got {abi}")


def locate_android_tool(name: str) -> str:
    direct = shutil.which(name)
    if direct:
        return direct
    sdk = Path(os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") or "")
    candidates = sorted((sdk / "build-tools").glob(f"*/{name}"), reverse=True)
    if not candidates:
        raise RuntimeError(f"Android SDK tool not found: {name}")
    return str(candidates[0])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_and_verify_edge() -> Path:
    apk_dir = ARTIFACTS / "apk"
    apk_dir.mkdir(parents=True, exist_ok=True)
    cached_apk = apk_dir / f"{EDGE_PACKAGE}-{EDGE_VERSION}.apk"
    if cached_apk.exists():
        log(f"reusing cached Edge Canary APK {cached_apk.name}")
        apk = cached_apk
    else:
        downloader = APKDownloader()
        log(f"downloading Edge Canary {EDGE_VERSION} from APKPure")
        result = downloader.download(EDGE_PACKAGE, output_dir=apk_dir, source="apkpure", version=EDGE_VERSION)
        apk = Path(result.path)
    if apk.suffix.lower() != ".apk":
        raise AssertionError(f"expected a single APK, got {apk.name}")

    actual_hash = sha256_file(apk)

    apksigner = locate_android_tool("apksigner")
    cert_output = run(apksigner, "verify", "--print-certs", str(apk)).stdout
    match = re.search(r"Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]+)", cert_output)
    if not match:
        raise AssertionError(f"could not read Edge signing certificate\n{cert_output}")
    cert_sha256 = match.group(1).lower()
    if cert_sha256 != MICROSOFT_CERT_SHA256:
        raise AssertionError(f"unexpected Edge signing certificate: {cert_sha256}")

    aapt = locate_android_tool("aapt")
    badging = run(aapt, "dump", "badging", str(apk)).stdout
    if f"name='{EDGE_PACKAGE}'" not in badging:
        raise AssertionError("downloaded APK package is not Microsoft Edge Canary")
    if f"versionName='{EDGE_VERSION}'" not in badging:
        raise AssertionError("downloaded Edge version does not match the pinned test version")
    if "arm64-v8a" not in badging:
        raise AssertionError("downloaded Edge APK is not arm64-v8a")

    log(f"verified Edge APK {actual_hash[:16]}… and Microsoft certificate {cert_sha256[:16]}…")
    return apk


def build_crx() -> tuple[Path, str]:
    extension_dir = ROOT / "dist" / "edge-android"
    if not (extension_dir / "manifest.json").exists():
        raise RuntimeError("dist/edge-android is missing; run npm run build first")
    package_dir = ARTIFACTS / "extension"
    package_dir.mkdir(parents=True, exist_ok=True)
    key = package_dir / "edge-android-e2e.pem"
    crx = package_dir / "chatgpt-route-inspector-edge-android.crx"
    creator.create_private_key_file(str(key))
    creator.create_crx_file(str(extension_dir), str(key), str(crx))
    verify_result, header = verifier.verify(str(crx))
    if verify_result != verifier.VerifierResult.OK_FULL:
        raise AssertionError(f"generated CRX3 failed verification: {verify_result}")
    log(f"built CRX3 extension id {header.crx_id}")
    return crx, header.crx_id


def install_edge(apk: Path) -> None:
    log("installing Edge Canary into arm64-v8a Android emulator")
    adb("install", "-r", str(apk), timeout=240)
    package_dump = adb("shell", "dumpsys", "package", EDGE_PACKAGE).stdout
    if f"versionName={EDGE_VERSION}" not in package_dump:
        raise AssertionError("Edge Canary did not install at the pinned version")


def screenshot(name: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    result = adb("exec-out", "screencap", "-p", text=False)
    (ARTIFACTS / f"{name}.png").write_bytes(result.stdout)


def dump_ui() -> ET.Element:
    device_path = "/sdcard/edge-e2e-window.xml"
    adb("shell", "uiautomator", "dump", device_path, timeout=30)
    xml = adb("exec-out", "cat", device_path).stdout
    return ET.fromstring(xml)


def node_label(node: ET.Element) -> str:
    return " | ".join(filter(None, (node.attrib.get("text"), node.attrib.get("content-desc"), node.attrib.get("resource-id"))))


def bounds_center(bounds: str) -> tuple[int, int]:
    numbers = [int(value) for value in re.findall(r"\d+", bounds)]
    if len(numbers) != 4:
        raise ValueError(f"invalid bounds: {bounds}")
    left, top, right, bottom = numbers
    return (left + right) // 2, (top + bottom) // 2


def find_ui(patterns: tuple[str, ...]) -> ET.Element | None:
    root = dump_ui()
    lowered = tuple(pattern.lower() for pattern in patterns)
    for node in root.iter("node"):
        label = node_label(node).lower()
        if label and any(pattern in label for pattern in lowered):
            return node
    return None


def tap_node(node: ET.Element, repeat: int = 1) -> None:
    x, y = bounds_center(node.attrib["bounds"])
    for _ in range(repeat):
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(0.35)


def tap_ui(patterns: tuple[str, ...], timeout: int = 20, required: bool = True) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        node = find_ui(patterns)
        if node is not None:
            tap_node(node)
            return True
        time.sleep(0.6)
    if required:
        labels = [node_label(node) for node in dump_ui().iter("node") if node_label(node)]
        raise AssertionError(f"UI element not found: {patterns}\nvisible nodes:\n" + "\n".join(labels[:120]))
    return False


def scroll_down() -> None:
    adb("shell", "input", "swipe", "540", "1780", "540", "520", "320")
    time.sleep(0.7)


def finish_first_run() -> None:
    adb("shell", "monkey", "-p", EDGE_PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(3)
    for _ in range(12):
        if find_ui(("search or enter web address", "address and search bar", "new tab")) is not None:
            return
        if tap_ui(("accept and continue", "accept & continue", "get started"), timeout=1, required=False):
            continue
        if tap_ui(("continue without signing in", "continue without an account", "skip"), timeout=1, required=False):
            continue
        if tap_ui(("not now", "maybe later", "no thanks"), timeout=1, required=False):
            continue
        if tap_ui(("confirm", "continue"), timeout=1, required=False):
            continue
        time.sleep(1)
    screenshot("first-run-stuck")
    raise AssertionError("Edge first-run UI could not be completed")


def enable_edge_developer_options() -> None:
    log("enabling Edge Canary developer options through the Android UI")
    tap_ui(("settings and more", "more options", "menu"))
    tap_ui(("settings",))
    for _ in range(6):
        about = find_ui(("about microsoft edge", "about edge"))
        if about is not None:
            tap_node(about)
            break
        scroll_down()
    else:
        screenshot("settings-no-about")
        raise AssertionError("About Microsoft Edge was not found")

    version_node: ET.Element | None = None
    for _ in range(5):
        root = dump_ui()
        for node in root.iter("node"):
            label = node_label(node)
            if EDGE_VERSION in label or re.search(r"\b15[1-9]\.\d+\.\d+\.\d+\b", label):
                version_node = node
                break
        if version_node is not None:
            break
        scroll_down()
    if version_node is None:
        screenshot("about-no-version")
        raise AssertionError("Edge build number was not found on About Microsoft Edge")
    tap_node(version_node, repeat=8)
    time.sleep(1)
    adb("shell", "input", "keyevent", "4")
    time.sleep(1)

    for _ in range(8):
        developer = find_ui(("developer options",))
        if developer is not None:
            tap_node(developer)
            return
        scroll_down()
    screenshot("settings-no-developer-options")
    raise AssertionError("Developer options did not appear after tapping the Edge build number")


def sideload_extension(crx: Path) -> None:
    log("sideloading CRX3 through Edge Android Developer Options")
    remote_crx = "/sdcard/Download/chatgpt-route-inspector-edge-android.crx"
    adb("push", str(crx), remote_crx, timeout=120)
    tap_ui(("extension install by crx",))
    tap_ui(("choose .crx file", "choose crx file", "choose file"))
    tap_ui(("downloads",), timeout=10, required=False)
    tap_ui(("chatgpt-route-inspector-edge-android.crx", "chatgpt-route-inspector"), timeout=20)
    tap_ui(("ok",), timeout=15)
    tap_ui(("add extension", "add"), timeout=20)
    time.sleep(3)
    screenshot("extension-installed")


def find_devtools_socket() -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        sockets = adb("shell", "cat", "/proc/net/unix").stdout
        candidates: list[str] = []
        for line in sockets.splitlines():
            if "devtools_remote" not in line:
                continue
            endpoint = line.split()[-1].lstrip("@")
            if "edge" in endpoint.lower() or EDGE_PACKAGE.replace(".", "_") in endpoint:
                return endpoint
            candidates.append(endpoint)
        if len(candidates) == 1:
            return candidates[0]
        time.sleep(1)
    raise AssertionError("Edge DevTools remote socket was not exposed")


def json_url(path: str) -> Any:
    with urllib.request.urlopen(f"http://127.0.0.1:{DEVTOOLS_PORT}{path}", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class Cdp:
    def __init__(self, websocket_url: str):
        self.ws = websocket.create_connection(websocket_url, timeout=15, suppress_origin=True)
        self.next_id = 0

    def close(self) -> None:
        self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.next_id += 1
        request_id = self.next_id
        self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise AssertionError(f"CDP {method} failed: {message['error']}")
            return message.get("result", {})

    def eval(self, expression: str, await_promise: bool = False) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        remote = result.get("result", {})
        if "exceptionDetails" in result:
            raise AssertionError(f"JavaScript evaluation failed: {result['exceptionDetails']}")
        return remote.get("value")


def wait_for_target(predicate, timeout: int = 35) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_targets: list[dict[str, Any]] = []
    while time.time() < deadline:
        last_targets = json_url("/json/list")
        for target in last_targets:
            if predicate(target):
                return target
        time.sleep(1)
    compact = [{"type": t.get("type"), "url": t.get("url"), "title": t.get("title")} for t in last_targets]
    raise AssertionError(f"DevTools target not found; last targets: {json.dumps(compact, indent=2)}")


def run_browser_assertions(expected_crx_id: str) -> None:
    log("opening chatgpt.com in Edge Android")
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "https://chatgpt.com/", EDGE_PACKAGE)
    time.sleep(5)
    socket = find_devtools_socket()
    adb("forward", "--remove", f"tcp:{DEVTOOLS_PORT}", check=False)
    adb("forward", f"tcp:{DEVTOOLS_PORT}", f"localabstract:{socket}")
    log(f"forwarded Edge DevTools socket {socket}")

    page_target = wait_for_target(lambda target: target.get("type") == "page" and str(target.get("url", "")).startswith("https://chatgpt.com"))
    page = Cdp(page_target["webSocketDebuggerUrl"])
    try:
        page.call("Runtime.enable")
        deadline = time.time() + 30
        overlay_ready = False
        while time.time() < deadline:
            overlay_ready = bool(page.eval("Boolean(document.getElementById('chatgpt-route-inspector-root')?.shadowRoot?.querySelector('.probe'))"))
            if overlay_ready:
                break
            time.sleep(1)
        if not overlay_ready:
            screenshot("chatgpt-no-overlay")
            raise AssertionError("Route Inspector overlay was not injected into chatgpt.com")

        hooks = page.eval("(() => { const f = Object.getOwnPropertyDescriptor(window, 'fetch'); const w = Object.getOwnPropertyDescriptor(window, 'WebSocket'); return { fetch: Boolean(f?.get && f?.set), websocket: Boolean(w?.get && w?.set) }; })()")
        if hooks != {"fetch": True, "websocket": True}:
            raise AssertionError(f"MAIN-world hooks are not installed: {hooks}")

        page.eval("document.getElementById('chatgpt-route-inspector-root').shadowRoot.getElementById('compact').click()")
        time.sleep(1)
        if not page.eval("Boolean(document.getElementById('chatgpt-route-inspector-root')?.shadowRoot?.querySelector('.probe.compact'))"):
            raise AssertionError("overlay compact interaction did not update state")
        page.eval("document.getElementById('chatgpt-route-inspector-root').shadowRoot.getElementById('expand').click()")

        request_expression = f"fetch('/backend-api/f/conversation', {{ method: 'POST', headers: {{'content-type': 'application/json'}}, body: JSON.stringify({{model: '{TEST_MODEL}', messages: [{{id: 'edge-android-ci-message'}}], parent_message_id: 'edge-android-ci-parent'}}) }}).catch(() => undefined)"
        page.eval(request_expression, await_promise=True)
    finally:
        page.close()

    worker_target = wait_for_target(lambda target: target.get("type") == "service_worker" and "background/service-worker.js" in str(target.get("url", "")))
    worker_url = str(worker_target["url"])
    extension_match = re.match(r"chrome-extension://([a-p]{32})/", worker_url)
    if not extension_match:
        raise AssertionError(f"unexpected extension service worker URL: {worker_url}")
    installed_id = extension_match.group(1)
    if installed_id != expected_crx_id:
        raise AssertionError(f"installed extension id {installed_id} != packaged id {expected_crx_id}")

    worker = Cdp(worker_target["webSocketDebuggerUrl"])
    try:
        deadline = time.time() + 20
        captured = False
        state: Any = None
        while time.time() < deadline:
            state = worker.eval(f"chrome.storage.local.get('{STATE_KEY}').then(v => v['{STATE_KEY}'])", await_promise=True)
            turns = state.get("turns", []) if isinstance(state, dict) else []
            if any(turn.get("requestedModel") == TEST_MODEL for turn in turns if isinstance(turn, dict)):
                captured = True
                break
            time.sleep(1)
        if not captured:
            raise AssertionError(f"request hook did not reach chrome.storage.local: {json.dumps(state, indent=2)[:4000]}")
    finally:
        worker.close()

    log(f"verified installed extension {installed_id}, MAIN/ISOLATED injection, overlay interaction, and request-to-storage pipeline")
    screenshot("chatgpt-e2e-passed")


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    ensure_arm64_android()
    apk = download_and_verify_edge()
    crx, crx_id = build_crx()
    install_edge(apk)
    finish_first_run()
    enable_edge_developer_options()
    sideload_extension(crx)
    run_browser_assertions(crx_id)
    log("PASS: Edge Android 14 emulator E2E")


def self_check() -> None:
    APKDownloader()
    crx, crx_id = build_crx()
    if not crx.is_file() or crx.stat().st_size == 0:
        raise AssertionError("CRX3 self-check produced no package")
    if not re.fullmatch(r"[a-p]{32}", crx_id):
        raise AssertionError(f"invalid CRX extension id: {crx_id}")
    log(f"PASS: Python E2E dependencies and CRX3 packaging ({crx_id})")


def verify_edge_apk() -> None:
    apk = download_and_verify_edge()
    log(f"PASS: pinned Edge Android APK verified ({apk.name})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--verify-edge-apk", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_check:
            self_check()
        elif args.verify_edge_apk:
            verify_edge_apk()
        else:
            main()
    except Exception as error:
        log(f"FAIL: {error}")
        if not args.self_check and not args.verify_edge_apk:
            try:
                screenshot("failure")
                (ARTIFACTS / "logcat.txt").write_text(adb("logcat", "-d", check=False).stdout, encoding="utf-8")
                (ARTIFACTS / "ui.xml").write_text(ET.tostring(dump_ui(), encoding="unicode"), encoding="utf-8")
            except Exception as artifact_error:
                log(f"could not collect failure artifacts: {artifact_error}")
        raise
