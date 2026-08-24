from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import websocket
from androguard.core.apk import APK
from crx3 import creator, verifier
from justapk import APKDownloader

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "edge-android-e2e"
TEMP = ROOT / ".tmp" / "edge-android-e2e"
EDGE_PACKAGE = "com.microsoft.emmx.canary"
EDGE_REQUEST_VERSION = "153.0.4201.0"
EDGE_MIN_MAJOR = 151
MICROSOFT_CERT_SHA256 = "01e1999710a82c2749b4d50c445dc85d670b6136089d0a766a73827c82a1eac9"
STATE_KEY = "chatgptRouteInspectorStateV2"
TEST_MODEL = "gpt-edge-android-ci"
DEVTOOLS_PORT = 9222
ANDROID_API = 31
ANDROID_AVD_NAME = "edge-arm64"
ANDROID_SERIAL = "emulator-5554"
ANDROID_SYSIMG_PACKAGE = f"system-images;android-{ANDROID_API};google_apis;arm64-v8a"
ANDROID_SYSIMG_REPOSITORY = "https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-5.xml"
ANDROID_SYSIMG_BASE = "https://dl.google.com/android/repository/sys-img/google_apis/"
ANDROID_EMULATOR_BUILD_ID = "8632828"
ANDROID_EMULATOR_URL = (
    "https://ci.android.com/builds/submitted/8632828/emulator-linux_aarch64/latest/"
    "sdk-repo-linux_aarch64-emulator-8632828.zip"
)


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
    return run("adb", "-s", os.environ.get("ANDROID_SERIAL", ANDROID_SERIAL), *args, check=check, text=text, timeout=timeout)


def download_file(url: str, destination: Path, timeout: int = 900) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        log(f"reusing cached download {destination.name} ({destination.stat().st_size / 1024 / 1024:.1f} MiB)")
        return destination
    request = urllib.request.Request(url, headers={"User-Agent": "chatgpt-route-inspector-edge-android-e2e/2.0"})
    started = time.time()
    transferred = 0
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0") or "0")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            transferred += len(chunk)
            if transferred % (128 * 1024 * 1024) < len(chunk):
                suffix = f"/{total / 1024 / 1024:.0f} MiB" if total else " MiB"
                log(f"downloaded {transferred / 1024 / 1024:.0f}{suffix}: {destination.name}")
    log(f"downloaded {destination.name}: {transferred / 1024 / 1024:.1f} MiB in {time.time() - started:.1f}s")
    return destination


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def system_image_archive() -> tuple[str, str, str]:
    request = urllib.request.Request(ANDROID_SYSIMG_REPOSITORY, headers={"User-Agent": "edge-android-e2e/2.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        root = ET.fromstring(response.read())
    package: ET.Element | None = None
    for element in root.iter():
        if local_name(element.tag) == "remotePackage" and element.attrib.get("path") == ANDROID_SYSIMG_PACKAGE:
            package = element
            break
    if package is None:
        raise RuntimeError(f"Google repository does not contain {ANDROID_SYSIMG_PACKAGE}")

    for archive in package.iter():
        if local_name(archive.tag) != "archive":
            continue
        complete = next((node for node in archive if local_name(node.tag) == "complete"), None)
        if complete is None:
            continue
        url_node = next((node for node in complete if local_name(node.tag) == "url"), None)
        checksum_node = next((node for node in complete if local_name(node.tag) == "checksum"), None)
        if url_node is None or not url_node.text or checksum_node is None or not checksum_node.text:
            continue
        algorithm = checksum_node.attrib.get("type", "sha1").lower().replace("-", "")
        return urllib.parse.urljoin(ANDROID_SYSIMG_BASE, url_node.text.strip()), algorithm, checksum_node.text.strip().lower()
    raise RuntimeError(f"Google repository has no complete archive for {ANDROID_SYSIMG_PACKAGE}")


def verify_digest(path: Path, algorithm: str, expected: str) -> None:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest().lower()
    if actual != expected.lower():
        raise AssertionError(f"{path.name} {algorithm} mismatch: {actual} != {expected}")


def install_host_android_tools() -> None:
    if shutil.which("adb") and shutil.which("apksigner"):
        return
    log("installing native ARM64 adb and Java apksigner from Ubuntu packages")
    run("sudo", "apt-get", "update", timeout=600)
    run("sudo", "apt-get", "install", "-y", "adb", "apksigner", timeout=600)
    if not shutil.which("adb") or not shutil.which("apksigner"):
        raise RuntimeError("adb/apksigner unavailable after package installation")


def prepare_arm64_emulator() -> tuple[Path, Path]:
    machine = platform.machine().lower()
    if machine not in {"aarch64", "arm64"}:
        raise RuntimeError(f"managed ARM64 emulator requires a native ARM64 runner, got host {machine}")
    install_host_android_tools()
    sdk_root = TEMP / "android-sdk"
    emulator_zip = TEMP / f"sdk-repo-linux_aarch64-emulator-{ANDROID_EMULATOR_BUILD_ID}.zip"
    download_file(ANDROID_EMULATOR_URL, emulator_zip, timeout=1800)
    emulator_dir = sdk_root / "emulator"
    if not (emulator_dir / "emulator").exists():
        sdk_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(emulator_zip) as archive:
            archive.extractall(sdk_root)
    emulator = emulator_dir / "emulator"
    if not emulator.exists():
        raise RuntimeError(f"Google ARM64 emulator archive did not produce {emulator}")
    emulator.chmod(emulator.stat().st_mode | 0o111)

    image_url, image_algorithm, image_checksum = system_image_archive()
    image_zip = TEMP / f"google-apis-api-{ANDROID_API}-arm64-v8a.zip"
    download_file(image_url, image_zip, timeout=1800)
    verify_digest(image_zip, image_algorithm, image_checksum)
    image_parent = sdk_root / "system-images" / f"android-{ANDROID_API}" / "google_apis"
    image_dir = image_parent / "arm64-v8a"
    if not (image_dir / "system.img").exists():
        image_parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(image_zip) as archive:
            archive.extractall(image_parent)
    if not (image_dir / "system.img").exists():
        raise RuntimeError(f"Google ARM64 system image did not produce {image_dir / 'system.img'}")

    avd_home = TEMP / "avd"
    avd_dir = avd_home / f"{ANDROID_AVD_NAME}.avd"
    avd_home.mkdir(parents=True, exist_ok=True)
    avd_dir.mkdir(parents=True, exist_ok=True)
    (avd_home / f"{ANDROID_AVD_NAME}.ini").write_text(
        f"avd.ini.encoding=UTF-8\npath={avd_dir}\ntarget=android-{ANDROID_API}\n",
        encoding="utf-8",
    )
    (avd_dir / "config.ini").write_text(
        "\n".join(
            [
                "AvdId=edge-arm64",
                "abi.type=arm64-v8a",
                "avd.ini.displayname=Edge Android ARM64 CI",
                "avd.ini.encoding=UTF-8",
                "disk.dataPartition.size=6G",
                "fastboot.forceColdBoot=yes",
                "fastboot.forceFastBoot=no",
                "hw.cpu.arch=arm64",
                "hw.cpu.ncore=2",
                "hw.gpu.enabled=yes",
                "hw.gpu.mode=swiftshader_indirect",
                "hw.keyboard=yes",
                "hw.lcd.density=420",
                "hw.lcd.height=1920",
                "hw.lcd.width=1080",
                "hw.ramSize=3072",
                f"image.sysdir.1={image_dir}/",
                "skin.dynamic=yes",
                "tag.display=Google APIs",
                "tag.id=google_apis",
                "vm.heapSize=512",
                "",
            ]
        ),
        encoding="utf-8",
    )
    log(f"prepared Google ARM64 emulator build {ANDROID_EMULATOR_BUILD_ID} and API {ANDROID_API} arm64-v8a image")
    return emulator, avd_home


@contextmanager
def managed_arm64_emulator():
    emulator, avd_home = prepare_arm64_emulator()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    emulator_log = ARTIFACTS / "emulator.log"
    env = os.environ.copy()
    env["ANDROID_AVD_HOME"] = str(avd_home)
    env["ANDROID_HOME"] = str(TEMP / "android-sdk")
    env["ANDROID_SDK_ROOT"] = str(TEMP / "android-sdk")
    env["ANDROID_SERIAL"] = ANDROID_SERIAL
    command = [
        str(emulator),
        f"@{ANDROID_AVD_NAME}",
        "-port",
        "5554",
        "-no-window",
        "-noaudio",
        "-no-boot-anim",
        "-no-snapshot",
        "-wipe-data",
        "-skip-adb-auth",
        "-gpu",
        "swiftshader_indirect",
        "-accel",
        "off",
        "-qemu",
        "-accel",
        "tcg",
    ]
    log("starting official Linux-aarch64 Android Emulator with TCG")
    with emulator_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=env, text=True)
    os.environ.update({"ANDROID_AVD_HOME": str(avd_home), "ANDROID_HOME": env["ANDROID_HOME"], "ANDROID_SDK_ROOT": env["ANDROID_SDK_ROOT"], "ANDROID_SERIAL": ANDROID_SERIAL})
    deadline = time.time() + 1800
    try:
        while time.time() < deadline:
            if process.poll() is not None:
                tail = emulator_log.read_text(encoding="utf-8", errors="replace")[-12000:]
                raise RuntimeError(f"ARM64 Android Emulator exited before boot ({process.returncode})\n{tail}")
            result = adb("shell", "getprop", "sys.boot_completed", check=False, timeout=15)
            if result.returncode == 0 and result.stdout.strip() == "1":
                adb("shell", "input", "keyevent", "82", check=False)
                log("ARM64 Android Emulator boot completed")
                yield
                return
            time.sleep(5)
        tail = emulator_log.read_text(encoding="utf-8", errors="replace")[-12000:]
        raise TimeoutError(f"ARM64 Android Emulator did not boot within 1800 seconds\n{tail}")
    finally:
        adb("emu", "kill", check=False, timeout=30)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()


def ensure_arm64_android() -> None:
    api = adb("shell", "getprop", "ro.build.version.sdk").stdout.strip()
    release = adb("shell", "getprop", "ro.build.version.release").stdout.strip()
    abi = adb("shell", "getprop", "ro.product.cpu.abi").stdout.strip()
    abi_list = adb("shell", "getprop", "ro.product.cpu.abilist").stdout.strip()
    native_bridge = adb("shell", "getprop", "ro.dalvik.vm.native.bridge").stdout.strip()
    machine = adb("shell", "uname", "-m").stdout.strip()
    log(
        f"device Android {release}, API {api}, primary ABI {abi}, ABI list {abi_list}, "
        f"kernel machine {machine}, native bridge {native_bridge or '<none>'}"
    )
    if abi != "arm64-v8a":
        raise AssertionError(f"expected a real arm64-v8a Android system image, got primary ABI {abi}")
    if machine not in {"aarch64", "arm64"}:
        raise AssertionError(f"expected an ARM64 Android kernel/userspace, got uname -m {machine}")
    if native_bridge not in {"", "0", "none"}:
        raise AssertionError(f"ARM native bridge must not be active in the arm64-v8a AVD: {native_bridge}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_certificate_sha256(cert_output: str) -> str:
    match = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]+)", cert_output)
    if not match:
        raise AssertionError(f"could not read Edge signing certificate\n{cert_output}")
    return match.group(1).lower()


def download_and_verify_edge() -> tuple[Path, str]:
    apk_dir = TEMP / "apk"
    apk_dir.mkdir(parents=True, exist_ok=True)
    cached_apk = apk_dir / f"{EDGE_PACKAGE}-{EDGE_REQUEST_VERSION}.apk"
    if cached_apk.exists():
        log(f"reusing cached Edge Canary APK {cached_apk.name}")
        apk = cached_apk
    else:
        downloader = APKDownloader()
        log(f"requesting Edge Canary {EDGE_REQUEST_VERSION} from APKPure")
        result = downloader.download(EDGE_PACKAGE, output_dir=apk_dir, source="apkpure", version=EDGE_REQUEST_VERSION)
        apk = Path(result.path)
    if apk.suffix.lower() != ".apk":
        raise AssertionError(f"expected a single APK, got {apk.name}")

    actual_hash = sha256_file(apk)

    apksigner = shutil.which("apksigner")
    if not apksigner:
        raise RuntimeError("apksigner is required to cryptographically verify the Edge APK")
    cert_output = run(apksigner, "verify", "--print-certs", str(apk)).stdout
    cert_sha256 = extract_certificate_sha256(cert_output)
    if cert_sha256 != MICROSOFT_CERT_SHA256:
        raise AssertionError(f"unexpected Edge signing certificate: {cert_sha256}")

    apk_info = APK(str(apk))
    package_name = apk_info.get_package()
    if package_name != EDGE_PACKAGE:
        raise AssertionError("downloaded APK package is not Microsoft Edge Canary")
    actual_version = apk_info.get_androidversion_name()
    if not actual_version:
        raise AssertionError("downloaded Edge APK has no Android manifest versionName")
    major_match = re.match(r"(\d+)", actual_version)
    if not major_match or int(major_match.group(1)) < EDGE_MIN_MAJOR:
        raise AssertionError(f"downloaded Edge version {actual_version} is below supported major {EDGE_MIN_MAJOR}")
    min_sdk = int(apk_info.get_min_sdk_version() or "1")
    if min_sdk > ANDROID_API:
        raise AssertionError(f"Edge APK minSdk {min_sdk} exceeds emulator API {ANDROID_API}")
    with zipfile.ZipFile(apk) as archive:
        native_abis = {
            name.split("/", 2)[1]
            for name in archive.namelist()
            if name.startswith("lib/") and len(name.split("/", 2)) >= 3
        }
    if "arm64-v8a" not in native_abis:
        raise AssertionError(f"downloaded Edge APK has no arm64-v8a native libraries: {sorted(native_abis)}")
    forbidden_abis = native_abis.intersection({"x86", "x86_64", "armeabi-v7a", "armeabi"})
    if forbidden_abis:
        raise AssertionError(f"Edge APK must be the ARM64 variant, found extra native ABIs: {sorted(forbidden_abis)}")

    log(
        f"verified Edge Canary {actual_version}, arm64-v8a APK {actual_hash[:16]}… "
        f"and Microsoft certificate {cert_sha256[:16]}…"
    )
    return apk, actual_version


def build_crx() -> tuple[Path, str]:
    extension_dir = ROOT / "dist" / "edge-android"
    if not (extension_dir / "manifest.json").exists():
        raise RuntimeError("dist/edge-android is missing; run npm run build first")
    package_dir = ARTIFACTS / "extension"
    package_dir.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    key = TEMP / "edge-android-e2e.pem"
    crx = package_dir / "chatgpt-route-inspector-edge-android.crx"
    creator.create_private_key_file(str(key))
    creator.create_crx_file(str(extension_dir), str(key), str(crx))
    verify_result, header = verifier.verify(str(crx))
    if verify_result != verifier.VerifierResult.OK_FULL:
        raise AssertionError(f"generated CRX3 failed verification: {verify_result}")
    log(f"built CRX3 extension id {header.crx_id}")
    return crx, header.crx_id


def install_edge(apk: Path, expected_version: str) -> None:
    log("installing arm64-v8a Edge Canary into Android emulator")
    adb("install", "-r", str(apk), timeout=240)
    package_dump = adb("shell", "dumpsys", "package", EDGE_PACKAGE).stdout
    if f"versionName={expected_version}" not in package_dump:
        raise AssertionError(f"installed Edge version does not match APK manifest version {expected_version}")
    if "primaryCpuAbi=arm64-v8a" not in package_dump:
        raise AssertionError("installed Edge Canary is not using arm64-v8a as its primary package ABI")
    log("verified installed Edge primaryCpuAbi=arm64-v8a")


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


def find_ui_in_tree(root: ET.Element, patterns: tuple[str, ...]) -> ET.Element | None:
    lowered = tuple(pattern.lower() for pattern in patterns)
    for node in root.iter("node"):
        label = node_label(node).lower()
        if label and any(pattern in label for pattern in lowered):
            return node
    return None


def find_ui(patterns: tuple[str, ...]) -> ET.Element | None:
    return find_ui_in_tree(dump_ui(), patterns)


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
    log("launching Edge directly without the Android launcher")
    adb(
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
        "-p",
        EDGE_PACKAGE,
        timeout=60,
    )
    time.sleep(3)
    ready_patterns = (
        "search or enter web address",
        "search or type web address",
        "search or type url",
        "address and search bar",
        "address bar",
        "new tab",
    )
    first_run_patterns = (
        "accept and continue",
        "accept & continue",
        "get started",
        "continue without signing in",
        "continue without an account",
        "not now",
        "maybe later",
        "no thanks",
        "skip",
        "confirm",
        "continue",
    )
    for _ in range(20):
        root = dump_ui()
        if find_ui_in_tree(root, ready_patterns) is not None:
            return

        anr_title = find_ui_in_tree(root, ("isn't responding", "is not responding"))
        if anr_title is not None:
            title = node_label(anr_title)
            if "edge" in title.lower():
                screenshot("edge-anr")
                raise AssertionError(f"Edge ANR during first run: {title}")
            close_app = find_ui_in_tree(root, ("close app",))
            if close_app is not None:
                log(f"dismissing unrelated system ANR: {title}")
                tap_node(close_app)
                time.sleep(1)
                adb(
                    "shell",
                    "am",
                    "start",
                    "-W",
                    "-a",
                    "android.intent.action.MAIN",
                    "-c",
                    "android.intent.category.LAUNCHER",
                    "-p",
                    EDGE_PACKAGE,
                    timeout=60,
                )
                time.sleep(2)
                continue

        first_run = find_ui_in_tree(root, first_run_patterns)
        if first_run is not None:
            log(f"first-run action: {node_label(first_run)}")
            tap_node(first_run)
            time.sleep(1)
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
            if re.search(r"\b(?:15[1-9]|1[6-9]\d|[2-9]\d\d)\.\d+\.\d+\.\d+\b", label):
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


def main(manage_emulator: bool = False) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if manage_emulator:
        with managed_arm64_emulator():
            main(False)
        return
    ensure_arm64_android()
    apk, edge_version = download_and_verify_edge()
    crx, crx_id = build_crx()
    install_edge(apk, edge_version)
    finish_first_run()
    enable_edge_developer_options()
    sideload_extension(crx)
    run_browser_assertions(crx_id)
    log("PASS: Edge Android arm64-v8a emulator E2E")


def self_check() -> None:
    APKDownloader()
    sample_cert_output = "V2 Signer: certificate SHA-256 digest: 01E1999710A82C2749B4D50C445DC85D670B6136089D0A766A73827C82A1EAC9"
    if extract_certificate_sha256(sample_cert_output) != MICROSOFT_CERT_SHA256:
        raise AssertionError("apksigner certificate parser self-check failed")
    crx, crx_id = build_crx()
    if not crx.is_file() or crx.stat().st_size == 0:
        raise AssertionError("CRX3 self-check produced no package")
    if not re.fullmatch(r"[a-p]{32}", crx_id):
        raise AssertionError(f"invalid CRX extension id: {crx_id}")
    log(f"PASS: Python E2E dependencies and CRX3 packaging ({crx_id})")


def verify_edge_apk() -> None:
    apk, edge_version = download_and_verify_edge()
    log(f"PASS: Edge Android APK verified ({edge_version}, {apk.name})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--verify-edge-apk", action="store_true")
    parser.add_argument("--managed-emulator", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_check:
            self_check()
        elif args.verify_edge_apk:
            verify_edge_apk()
        else:
            main(args.managed_emulator)
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
