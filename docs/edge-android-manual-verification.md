# 使用 Edge Android 手工核验 ChatGPT 路由

这套步骤用于在 Android 真机上与扩展结果交叉核验。Android 端不依赖本机 DevTools；通过 USB 把 Microsoft Edge for Android 的 ChatGPT 标签页连接到桌面 Edge DevTools。

不要用“回答很快”“答案较短”或让模型自报型号作为路由证据。

## 连接 Android 真机

1. 在 Android 的开发者选项中开启 USB 调试。
2. 用 USB 将手机连接到电脑，并在手机上确认调试授权。
3. 在 Android 的 Microsoft Edge 中打开 `https://chatgpt.com/`。
4. 在电脑端 Microsoft Edge 打开 `edge://inspect`。
5. 找到手机上的 ChatGPT 标签页并选择 **inspect**，打开远程 DevTools。
6. 后续的 Network、Elements 和 Console 操作都在电脑上的这个远程 DevTools 窗口完成。

如果设备或标签页没有出现，先确认 USB 调试授权和数据线连接；这属于 Android/Edge 远程调试链路，不是扩展的兼容兜底路径。

## 抓本轮请求

1. 在远程 DevTools 打开 **Network**。
2. 开启 **Preserve log** 并清空当前记录。
3. 在过滤框输入 `conversation`。
4. 回到手机上的 ChatGPT，选择目标模型并发送一条普通消息。
5. 找到 `POST /backend-api/f/conversation`。若同名请求很多，按开始时间和 Method 对齐本轮。

在 **Payload** 中搜索：

```text
"model"
"thinking_effort"
"conversation_id"
"conversation_mode"
```

`model` 是 requested model。记录原值，不要拿响应中的 `default_model_slug` 反推请求模型。

## 查本轮响应路由（实时请求）

打开同一请求的 **Response** 或 **EventStream**，搜索：

```text
resolved_model_slug
default_model_slug
server_ste_metadata
model_slug
request_id
plan_type
fast_convo
```

重点对照：

```text
请求：model = gpt-…-pro
响应：resolved_model_slug = gpt-…-mini
响应：server_ste_metadata.model_slug = gpt-…-mini
```

`resolved_model_slug` 与 `server_ste_metadata.model_slug` 属于实际路由证据；assistant 消息自己的 `metadata.model_slug` 是模型标签。出现“标签 Pro、resolved Instant”时，扩展应把实际响应路由显示为 Instant，而不是把标签当成实际路由。

### 如果 POST 响应只有 handoff

ChatGPT 可能让 POST EventStream 只返回控制事件，例如：

```text
resume_conversation_token
stream_handoff
resume_sse_endpoint
subscribe_ws_topic
```

这种情况下真实回答可能已转到 WebSocket：

1. 保持 **Preserve log** 开启，在 Network 中切到 **Socket / WS**。
2. 选择发送消息前后持续连接、并在回答期间持续收到 frame 的 WebSocket。
3. 打开该连接的 **Messages**，找到与本轮时间对应的文本 frame。
4. frame 外层通常是 JSON 数组；检查：

```text
[0].payload.payload.encoded_item
```

5. `encoded_item` 是 SSE 文本，在其中搜索：

```text
resolved_model_slug
server_ste_metadata
model_slug
request_id
conversation_id
```

手工判断时必须确认 frame 属于本轮会话/消息。扩展会用 POST 的 `conversation_id`、`messages[0].id` 和 `parent_message_id` 与 WebSocket 消息 ID 配对；无法可靠匹配的 frame 不应按“最近一条请求”猜测归属。

## 重新加载会话复查（会话重载）

1. 在扩展 Popup 中切换到“会话重载”。
2. 刷新手机上的目标 ChatGPT 会话。
3. 在远程 DevTools 的 **Elements** 中搜索：

```text
data-message-model-slug
```

4. 找到同时具有以下属性的已完成 assistant 回答节点：

```text
data-message-author-role="assistant"
data-message-model-slug="gpt-…"
```

也可以在远程 **Console** 中运行下面的只读查询：

```js
[...document.querySelectorAll('[data-message-author-role="assistant"][data-message-model-slug]')]
  .map((element, index) => ({
    index: index + 1,
    messageId: element.getAttribute('data-message-id'),
    model: element.getAttribute('data-message-model-slug')
  }))
```

`data-message-model-slug` 与 assistant `metadata.model_slug` 都只是模型标签，不能单独证明实际路由。若刷新时出现 `GET /backend-api/conversation/{conversation_id}`，应在其 Response 中另找 `resolved_model_slug` 或 `server_ste_metadata.model_slug`。

重载复查通常没有原始 POST 请求体中的 requested `model`。若只取得 DOM 标签，则 requested model 与实际 route 都仍未知；不要补造缺失字段。

## 查看 PoW difficulty

1. 在远程 Network 过滤框输入 `chat-requirements`。
2. 发送消息前后检查以下请求，优先 `/prepare` 链路，不选 `/finalize`：

```text
POST /backend-api/sentinel/chat-requirements/prepare
POST /backend-anon/sentinel/chat-requirements/prepare
POST /backend-api/sentinel/chat-requirements
POST /backend-anon/sentinel/chat-requirements
```

3. 在 Response 中搜索：

```text
proofofwork
difficulty
```

前端也可能使用 `proof_of_work` 或 `pow`，或将结果放在 `chat_requirements` / `requirements` 对象中。扩展显示的是 PoW 对象中的 `difficulty` 原始十六进制字符串，并用任意精度整数转换为十进制。

可在远程 Console 用只读表达式核对换算：

```js
BigInt(`0x${'063556'.replace(/^0x/i, '')}`).toString(10)
// "406870"
```

扩展不会读取或保存 seed、设备指纹、nonce、proof token、requirements token 或 Turnstile 数据，也不会自行求解 PoW。

## 核验移动端扩展 UI

在 Android 真机上至少检查以下内容：

- 从 Edge 的扩展入口能打开 Route Inspector Popup；
- Popup 在竖屏窄宽度下没有水平滚动，主要按钮触控高度足够；
- “实时请求 / 会话重载”和“显示 / 隐藏浮窗”按钮可以修改状态；
- “打开诊断台”和“设置与隐私”会通过新标签页打开扩展页面；
- 页面浮窗在 ChatGPT 竖屏布局下不超出视口；
- 发送消息、WebSocket handoff、刷新会话后都能继续收到状态更新；
- JSON / Markdown 导出在当前 Edge Android 版本中能触发下载。

## 判断规则

- 实际路由字段存在且值一致：显示精确值，不附加概率。
- requested 与实际路由都有：相同为正常，不同为错配。
- 只有 DOM / assistant 模型标签：显示标签级信息，不把标签当实际路由。
- 模型标签与实际路由不同：同时展示，以实际路由字段作为 route。
- `resolved_model_slug` 与 `server_ste_metadata.model_slug` 互相矛盾：显示实际路由字段冲突。
- 实际路由字段缺失：route 显示未取得。
- `default_model_slug`、回答速度、风格、模型自述和单独 UI 截图不参与路由判定。

## HAR 安全提醒

HAR 可能包含聊天正文、请求体、Cookie、Authorization、会话 ID 和其他个人数据。不要把原始 HAR 发到公开论坛或 GitHub。优先使用扩展导出的脱敏 JSON / Markdown；若支持人员明确要求 HAR，只通过私有渠道提交，并在提交前检查敏感字段。
