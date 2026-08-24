<div align="center">

# ChatGPT Route Inspector · Edge Android

面向 **Microsoft Edge for Android 151+** 的 ChatGPT 模型路由检测扩展。

Languages: [简体中文](README.md) · [English](README-en.md)

</div>

## 2.0 破坏式更新

2.0 起项目只面向 Microsoft Edge for Android，不再维护以下兼容路径：

- Google Chrome / Chrome Web Store；
- Edge 桌面版以及其他 Chromium 浏览器；
- Chromium / Edge 150 及更早版本；
- `chat.openai.com` 旧域名；
- 桌面扩展的 `options_ui` / `openOptionsPage` 入口。

代码仍使用 `chrome.*` 命名空间，因为 Microsoft Edge 的 Chromium 扩展 API 本身使用这一命名空间；这不表示继续兼容 Google Chrome。

## 功能

- **实时请求检测**：显示 ChatGPT 网页请求的模型与服务器响应报告的路由模型。
- **会话重载检测**：刷新已有会话后读取可用的路由字段和模型标签。
- **页面浮窗**：直接在 ChatGPT 页面查看请求模型、响应路由和 PoW 难度。
- **移动端 Popup**：针对窄屏和触控重新布局，不依赖桌面工具栏尺寸。
- **路由诊断台**：查看本机记录并导出 Markdown / JSON。
- **本地优先**：记录保存在 Edge 当前配置文件的 `chrome.storage.local`，不会自动上传。

扩展只展示网页请求与响应中实际存在的字段，不根据速度、回答风格、模型自述或主观质量猜测模型。

## 平台基线

- Microsoft Edge for Android **151+**
- Manifest V3
- 目标站点仅 `https://chatgpt.com/*`
- 依赖的 Edge Android 扩展 API：`action`、`runtime`、`storage`、`tabs`、`i18n`

项目不提供旧平台兜底分支。若 Edge Android 缺少上述能力或版本低于 151，扩展应直接视为不受支持。

## Android 安装与分发

### Microsoft Edge Add-ons

正式分发目标是 **Microsoft Edge Add-ons**。构建出的 ZIP 用于 Partner Center 提交；通过审核后仍需在 Android 真机确认该商店条目已对 Edge 移动端开放，不能把桌面商店审核通过等同于 Android 可安装。

本仓库不再提供 Chrome Web Store 安装方式。

### 企业托管 Android

获得 Edge Add-ons 的扩展 ID / 更新地址后，可由管理员通过 Edge Android 的 `ExtensionInstallForcelist` / `ExtensionSettings` 策略进行托管部署。

### Android arm64-v8a 模拟器 E2E 与真机验证

`dist/edge-android` 只是待部署的扩展产物，**桌面 Edge/Chromium 的 Load unpacked 或 Windows Playwright 不属于 Android E2E**。

GitHub Actions 的 `Edge Android arm64-v8a E2E` workflow 使用 GitHub 原生 `ubuntu-24.04-arm` runner 作为基础设施；Android 环境本身由 Python 测试脚本管理。脚本下载 Google 官方 Linux-aarch64 Emulator 构建和 Google APIs `arm64-v8a` system image、校验 system image 仓库摘要、创建 AVD，并用 ARM64 软件虚拟化路径启动。测试不走 Android 的 ARM-on-x86 native bridge，也不会回退到 x86_64 Android。

Python 测试会强制确认 Android 自身 `ro.product.cpu.abi=arm64-v8a`、`uname -m` 为 `aarch64/arm64`、native bridge 未启用，同时确认安装后的 Edge 包为 `primaryCpuAbi=arm64-v8a`。之后再验证 Microsoft APK 签名证书、扩展 service worker、`MAIN` / `ISOLATED` 注入、页面浮窗交互，以及 `fetch` 请求最终写入 `chrome.storage.local` 的完整链路。

未发布扩展的自动化侧载使用 Edge Canary；这不改变生产基线仍为 Edge Android 151+。真实手机/平板仍应执行手工验收，尤其是商店分发、触控尺寸和下载行为。

## 从源码构建

需要 Node.js 20 或更高版本。

```powershell
npm ci
npm run build
```

构建结果：

```text
dist/edge-android/
```

生成 Partner Center 提交包：

```powershell
npm run package
```

输出：

```text
release/chatgpt-route-inspector-edge-android-2.0.0.zip
release/SHA256SUMS.txt
```

## 使用方法

### 检测新回答

1. 在 Edge Android 中打开 `https://chatgpt.com/` 并进入目标会话。
2. 从 Edge 的扩展入口打开 Route Inspector。
3. 选择“实时请求”。
4. 在 ChatGPT 中发送消息。
5. 在 Popup 或页面浮窗查看“请求模型 → 响应路由”。

### 复查已有回答

1. 在扩展 Popup 中选择“会话重载”。
2. 刷新当前 ChatGPT 会话。
3. 查看当前会话可读取到的响应路由和模型标签。

## 隐私与权限

完整说明见 [PRIVACY.md](PRIVACY.md)。

| 权限 / 主机 | 用途 |
|---|---|
| `storage` | 在 Edge 当前配置文件保存设置与检测记录 |
| `https://chatgpt.com/*` | 注入路由检测脚本并显示页面浮窗 |

扩展不申请 `debugger`、`cookies`、`webRequest`、`history` 或 `<all_urls>` 权限，也不会保存提示词、回答正文、Cookie、Authorization、JWT、附件内容或完整网络响应。

## Android 真机验收

Android 真机的安装、交互与路由捕获验收项见 [Edge Android 手工核验指南](docs/edge-android-manual-verification.md)。

## 开发验证

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npm run verify:edge-android
npm run package
```

Android E2E 由 GitHub Actions 在 `arm64-v8a` 模拟器内执行，入口为 `tests/android/run_edge_android_e2e.py --managed-emulator`。workflow YAML 只负责 checkout、运行时/依赖安装、构建、调用 Python 和上传 evidence；Emulator/system image 获取与校验、AVD 生命周期、APK 获取与签名校验、Android UI 自动化、CRX 安装和浏览器断言全部由 Python 文件实现，不使用 `python -c`、heredoc 或 YAML 内联 Python。真实手机/平板的补充验收仍见手工核验指南。

## 免责声明

本项目是独立的非官方工具，与 OpenAI 或 Microsoft 不存在隶属、授权或背书关系。ChatGPT、OpenAI、Microsoft Edge 及相关标识属于各自权利人。扩展显示的是 ChatGPT 网页请求与响应中可读取的信息，不构成对 OpenAI 内部基础设施、计费系统或账号状态的官方证明。
