# 构建、Release 与 Edge Android 手机安装

本文说明如何从源码产出 Edge Android 2.0 扩展包、如何发布到 GitHub Release / Microsoft Edge Add-ons，以及如何在 Android 手机上正常跑起来。

## 1. 本地构建

需要 Node.js 20 或更高版本。

```powershell
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm run verify:edge-android
```

构建产物在：

```text
dist/edge-android/
```

`dist/edge-android/` 是未压缩的 MV3 扩展目录，用于检查构建结果。它不是最终上传包。

## 2. 生成发布 ZIP

```powershell
npm run package
```

该命令会重新构建并生成：

```text
release/chatgpt-route-inspector-edge-android-2.0.0.zip
release/SHA256SUMS.txt
```

ZIP 内根目录就是扩展文件，例如 `manifest.json`、`background/`、`content/`、`ui/`。不要把外层 `release/` 目录打进去。

提交或发布前至少确认：

```powershell
npm run verify:edge-android
npm run package
```

`verify:edge-android` 会检查 Edge Android 2.0 的关键契约，例如：

- Manifest V3；
- `version = 2.0.0`；
- `minimum_chrome_version = 151`；
- host 仅 `https://chatgpt.com/*`；
- 没有 `options_ui`；
- 只使用 Android 支持的扩展入口；
- `MAIN` / `ISOLATED` content scripts 都在 `document_start` 注入。

## 3. 发布到 GitHub Release

GitHub Release 用来保存可审计的构建产物和校验值，方便 reviewer 或用户下载。它本身不等于 Edge Android 可直接安装。

推荐步骤：

1. 确认 `package.json` 和 `manifest/manifest.json` 中的版本一致。
2. 本地执行完整检查：

   ```powershell
   npm ci
   npm run typecheck
   npm run lint
   npm test
   npm run package
   ```

3. 在 GitHub 仓库页面打开 **Releases**。
4. 选择 **Draft a new release**。
5. 新建 tag，例如：

   ```text
   v2.0.0
   ```

6. Release title 建议使用：

   ```text
   ChatGPT Route Inspector Edge Android 2.0.0
   ```

7. 上传以下文件：

   ```text
   release/chatgpt-route-inspector-edge-android-2.0.0.zip
   release/SHA256SUMS.txt
   ```

8. Release notes 至少写明：

   - 仅支持 Microsoft Edge for Android 151+；
   - 仅支持 `https://chatgpt.com/*`；
   - 这是 Edge Android 破坏式 2.0；
   - Chrome / desktop Edge / `chat.openai.com` 不再支持；
   - Android 真机仍需通过 Edge Add-ons 或可用的企业策略安装。

也可以用 GitHub CLI 发布，但不要把它作为唯一流程要求：

```powershell
gh release create v2.0.0 `
  release/chatgpt-route-inspector-edge-android-2.0.0.zip `
  release/SHA256SUMS.txt `
  --title "ChatGPT Route Inspector Edge Android 2.0.0" `
  --notes-file CHANGELOG.md
```

## 4. 发布到 Microsoft Edge Add-ons

手机正常安装的主路径是 Microsoft Edge Add-ons。

1. 打开 Microsoft Partner Center / Edge Add-ons 提交入口。
2. 新建或更新扩展提交。
3. 上传 `release/chatgpt-route-inspector-edge-android-2.0.0.zip`。
4. 填写说明、隐私、权限用途和截图。
5. 提交审核。
6. 审核通过后记录扩展 ID 和商店链接。
7. 在 Android 真机 Edge 中确认该商店条目对移动端可见并可安装。

注意：桌面 Edge Add-ons 审核通过并不自动证明 Android Edge 可安装。必须用真实 Android Edge 检查。

## 5. 在手机上正常跑起来

### 正常用户路径

1. 手机安装或更新 Microsoft Edge for Android，版本需要 151+。
2. 在手机 Edge 打开扩展入口或 Edge Add-ons 移动端页面。
3. 找到已经发布的 ChatGPT Route Inspector。
4. 安装扩展。
5. 打开 `https://chatgpt.com/` 并登录。
6. 打开 Edge 的扩展入口，启动 Route Inspector。
7. 选择“实时请求”。
8. 在 ChatGPT 页面发送一条消息。
9. 在 Popup 或页面浮窗确认显示 requested model、response route、PoW difficulty 等信息。

### 未上架版本

GitHub Release 下载到的 ZIP 不能假定能被普通 Edge Android 直接安装。ZIP 主要用于：

- Microsoft Edge Add-ons 提交；
- reviewer 审查构建产物；
- 企业或开发流程中的可审计归档。

如果当前 Edge Android 版本提供开发者 CRX 侧载入口，可以用开发者入口测试未上架版本；若没有该入口，则不要把 GitHub Release ZIP 当作手机安装方式。未上架扩展的可靠手机验证路径是：

- Edge Add-ons 的测试/隐藏发布流程；或
- 企业托管策略；或
- 有明确扩展侧载能力的 Edge Android 测试版本。

## 6. 真机验收

安装后至少执行：

```powershell
npm run package
```

然后在 Android 真机按 `docs/edge-android-manual-verification.md` 做手工验收，重点检查：

- 扩展能从 Edge Android 扩展入口打开；
- Popup 在竖屏下没有横向滚动；
- 页面浮窗不遮挡 ChatGPT 主操作；
- 发送新消息能捕获 `/backend-api/f/conversation`；
- WebSocket handoff 场景能继续关联路由字段；
- 刷新已有会话时不会把 DOM 模型标签误判为实际路由；
- JSON / Markdown 导出能触发手机下载。

## 7. 不再做 GitHub Android workflow E2E

公开 Microsoft Edge Android APK 当前没有可用的 x86_64 变体；在 GitHub 标准 x86_64 AVD 中安装 ARM64-only Edge 会走 ARM translation，并已观察到 Edge 进程 `SIGSEGV`。

因此本仓库不再保留 GitHub Android E2E workflow。CI/本地自动化保留在：

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npm run verify:edge-android
npm run package
```

Android 运行验收改为真实 Android Edge 设备上的手工验收或受控发布验收。
