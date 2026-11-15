# 2026-11-16 VM 客户端绑定实验

## 结论摘要

**结论：无法确认“新 BrowserContext 缺失浏览器存储标识导致 `hatch_vm_auth_no_match`”，也无法确认“同一时间只允许一个客户端，关闭后等待 5 分钟会释放”。**

任务书要求先找到一个能取得工作机、使 `/api/hatch/token` 成功的账号，再做 E1–E4。实验时生产账号池共有 5 个启用且带 Cookie 的账号，没有账号处于排队或处理中；5 个账号各做 1 次只加载页面探测，均未取得成功 token。因此按任务书的停止条件结束，没有继续消耗探测预算，也没有修改运行代码。

静态分析同时表明：

- `open_id` 是一次页面打开的临时 UUID，不是 localStorage、sessionStorage、IndexedDB 或 Cookie 中的持久客户端 ID。
- `connect_attempt_id` 由当前连接/唤醒流程把内存中的 `attemptId` 传给 wake 请求；未发现它从 localStorage 或 sessionStorage 读取。
- `/api/hatch/token` 的请求体只有 `vmAddress`、可选 `vmName` 和可选 `force_refresh`；不会提交 `open_id` 或 `connect_attempt_id`。成功 token 只缓存在当前 JS 运行时的变量和 Map 中。
- 页面运行时唯一观察到的相关 Web Storage 键是 localStorage 的 `hatch:debug:device-id` 和 sessionStorage 的 `hatch_saved_account_registered`。公开 bundle 没有把这两个键接入 wake 或 token 请求；前者名称也明确属于 debug 命名空间。仅凭键名不能把它认定为 VM 匹配凭据。
- 页面存在 `hatch-cvm-credentials`、`hatch-cvm-provisioning`、`hatch-cvm-replacement` 等 IndexedDB。这些代码按 `ownerId`、`sessionBindingId`、`envId` 保存机密 VM（CVM）的恢复密钥、置换尝试和撤销状态；它们不是 E2 指定复制的 localStorage/sessionStorage 键，也没有出现在 `/api/hatch/token` 请求体中。

现有证据更直接地说明实验时上游没有给这些账号提供稳定可用的 VM：两账号返回 `/api/session` 的 `unavailable/retryable`，一账号在 wake 200 后得到 token 401 `hatch_vm_auth_no_match`，另两账号 wake 200 后在观察窗口内没有发出 token 请求。

## 静态分析

### 取证范围

只下载 muse.ai 无凭据公开资源，没有携带账号 Cookie：

- `3e-p5628-9165.js`：VM assignment 与 wake。
- `0e7r790tskdhg.js`：gateway token 获取与缓存。
- `1edy9lfamzbt5.js`、`1hp39f-4m10fz.js`：VM/session 连接状态。
- `1ekrnf5tjbh9q.js` 与其依赖：页面打开生命周期。
- 公开首页当前引用的 49 个 JS chunk，用于交叉检索存储键和标识来源。

访问 `/thread/new` 本身需要认证并返回 401，故静态文件地址来自前一日调查已识别的公开 immutable chunk 路径；下载这些 chunk 不需要凭据。

### `open_id`

页面打开生命周期先读取 `<html>` 的 `data-hatch-page-load-id`，只接受 UUID v4；不存在或格式无效时使用 `crypto.randomUUID()`。页面从后台返回前台时也会在内存中生成新的 UUID。该值保存在当前模块的 `open` 状态中，随 wake 请求作为 `open_id` 发送，并用于性能埋点。

没有发现它写入或读取 localStorage、sessionStorage、IndexedDB 或 Cookie。因此新建 BrowserContext 会得到新的 `open_id`，但这是前端明确设计的每次打开标识，不是丢失的持久客户端标识。

### `connect_attempt_id`

wake helper 将调用方的 `attemptId` 映射成 `connect_attempt_id`，同一对象还提供 `trigger`、`openId`、`awayMs`。当前连接代码在内存中维护连接代次、目标和 attempt 状态；CVM 置换流程另会把 attempt 记录在 `hatch-cvm-replacement` IndexedDB 中。

没有发现通用 VM wake 的 `connect_attempt_id` 从 Web Storage 或 Cookie 恢复。公开压缩 chunk 没有暴露普通 VM 连接 attempt 的完整创建函数，因此只能确认它来自当前连接流程的内存参数，不能进一步证明其 UUID 生成语句。不能把 CVM 置换 attempt 与普通 VM token 匹配混为一谈。

### token 请求与缓存

`POST /api/hatch/token` 的 JSON 为：

- `vmAddress`：必填，来自当前 VM 的 gateway URL。
- `vmName`：有值时提交。
- `force_refresh`：强制刷新时提交。

服务端还会自然收到当前账号 Cookie，但请求体不含 `open_id`、`connect_attempt_id` 或浏览器存储值。成功响应在页面内组合成 `{token, gatewayUrl, vmName, noiseNotaryToken}`，按 gateway URL 与 VM name 缓存在模块级变量和 Map；页面还会在目标变化、重置或注销时清空。bundle 启动时主动删除旧的 `hatch-gateway-token-v2`、`hatch:gateway-token` 和 `hatch-device-id` localStorage 键，进一步说明当前 gateway token 不依赖这些旧持久键。

`session_binding_id` 来自认证/session 响应，与 `viewer_id` 一起进入 React 认证上下文。它不是浏览器随机生成的 localStorage 客户端 ID；CVM IndexedDB 使用它给本地安全状态分区。

## 生产对照实验

### 方法与安全边界

- 脚本以 base64 传入生产容器，文件名为 `/tmp/vm_binding_probe.py`，使用 `python -I` 运行；结束后已删除。
- 每次探测使用独立 `Target.createBrowserContext`，只注入账号 Cookie 并导航到 `https://muse.ai/thread/new`，没有填写或发送提示词。
- 页面脚本只保存 token 的 HTTP 状态、`code`、`error`，session 的状态分类，以及存储键名；不读取或输出 token、Cookie、Key、完整账号 ID或存储值。
- 每次页面加载结束后，均先用 `Network.getCookies` 读取该上下文最新 Cookie，通过本机管理接口 `POST /admin/accounts/{aid}/cookies` 回写成功，再调用 `Target.disposeBrowserContext`。
- 总探测 5 次，低于上限 12；5 个账号各 1 次，低于单账号上限 6。
- 未调用 `/v1/images*`、`/v1/videos`、`/v1/chat*`，未发起生成或付费调用；未更改 Railway 配置，未部署。

### 前置账号确认结果

| # | 账号标签 | 页面结果 | 相关存储键名 | Cookie 回写 |
|---|---|---|---|---|
| 1 | 237 | 页面原生 wake HTTP 200；观察窗口内未发 token | local: `hatch:debug:device-id`；session: `hatch_saved_account_registered`；存在 CVM/cache IndexedDB | HTTP 200 |
| 2 | 238 | 页面原生 wake HTTP 200；观察窗口内未发 token | 同上 | HTTP 200 |
| 3 | 235 | wake HTTP 200；token HTTP 401，`hatch_vm_auth_no_match` | 同上 | HTTP 200 |
| 4 | 218 | session HTTP 200，`status=unavailable`、`kind=retryable`；未发 token | local/session 同上；未观察到 IndexedDB | HTTP 200 |
| 5 | 217 | session HTTP 200，`status=unavailable`、`kind=retryable`；未发 token | local/session 同上；未观察到 IndexedDB | HTTP 200 |

“存在 CVM/cache IndexedDB”只记录数据库名称是否存在，不读取 object store 内容。不同账号看到的数据库集合差异可能来自页面加载进度或功能资格，不能据此判断 VM 绑定成功与否。

### E1–E4

- **E1：未执行。** 任务书要求先确认一个当前能拿到工作机的账号。5/5 启用账号都没有成功 token，不能建立“成功 A → 新上下文 B”的基线。
- **E2：未执行。** 没有成功的 A 可作为复制存储后的对照；强行复制失败页的键不能检验“存储恢复成功”。
- **E3：未执行。** 没有单客户端成功基线，同时打开两个客户端无法区分“并发排斥”和“账号本来就拿不到 VM”。
- **E4：未执行。** 同理，没有关闭前成功基线，等待 5 分钟后的结果不具备因果解释力。

这是任务书明确规定的停止分支，不是实验遗漏。继续探测只会增加生产负担，并可能在没有有效对照的情况下产生误导结论。

## 修复决策

不修改 `engine.py` 或 `app.py`：

1. E2 没有形成“复制存储后成功”的证据，不能引入账号级 Web Storage 持久化。
2. E3/E4 没有形成“并发失败、等待后成功”的证据，不能增加上下文复用或冷却。
3. 任务书规定两类假设都不成立或无法证实时只写报告。
4. 因没有运行代码变更，本任务与 PR #6 的冷却逻辑没有合并顺序依赖。

## 后续建议

等至少一个账号在同一生产出口能稳定取得 token 200 后，再严格按本报告的方法重跑 E1–E4；优先保留 6 次单账号序列：E1 A/B、E2 A、E2 B（保持打开并兼作 E3 A）、E3 B、关闭后等待 5 分钟的 E4 B。这样正好满足单账号 6 次上限。

在有成功基线前，不建议持久化 `hatch:debug:device-id`、复制 CVM IndexedDB 或复用长期 BrowserContext。这些动作可能扩大凭据面或引入跨账号状态污染，却没有证据能解决当前 `unavailable/no-match`。

## 离线自测

使用 `/tmp` 临时虚拟环境安装现有 `requirements.txt`，没有修改依赖文件。需要真实 Chromium 的测试通过临时 `google-chrome` shell 包装器 `exec` 本机 Google Chrome，并设置 `MUSE2API_CHROMIUM`。

- `python tests/test_*.py`：38/38 通过，0 失败（逐个独立运行）。
- `node tests/test_admin_api_error_messages.mjs`：通过。
- 首轮有 4 个浏览器测试因把 macOS Chrome 应用包内二进制直接做符号链接而无法启动；改用仓库说明要求的 `exec` 包装器后，4 项逐个复跑全部通过。该问题属于本地测试启动方式，不是代码或断言失败。
