# 2026-11-15 `hatch_vm_auth_no_match` 调查

## 结论摘要

线上持续失败的直接原因是 muse.ai 没有为当前会话返回可用 assignment，或 wake 后无法把页面的 token 请求匹配到该 VM。账号 235 的页面原生流程自行发送两次 wake（HTTP 200）后，`/api/hatch/token` 仍连续返回 401 `hatch_vm_auth_no_match`；账号 238 在不做外部 wake 时也直接得到 `status=unavailable`。因此，问题不能归因于 cookie 已过期，也不能仅归因于我们自己的 HTTP wake。

代码中发现两个加重因素并已修复：

1. 服务在页面前和保活时另发带随机 `connect_attempt_id` 的 wake。这不属于页面自己的连接尝试，可能抢占页面随后申请 token 的匹配关系；正常链路现已停止外部 wake，由页面独占 wake/token 流程。
2. 原实现只在生成成功后同步浏览器 cookie。失败上下文关闭时可能丢掉 muse.ai 已轮换的 httpOnly cookie；现已在任何页面关闭前统一读回并合并写入账号存储。

修复降低我们代码造成的干扰，但不能保证消除当前故障。页面原生 wake 已成功受理而 token 仍 no-match，剩余主因在 muse.ai 分配/匹配、服务器出口策略或账号在外部浏览器被占用之间，本次安全探测无法进一步区分。

## 安全边界与探测清单

- 未调用 `/v1/images*`、`/v1/videos`、`/v1/chat*`，未发送提示词，未产生生成或付费调用。
- 共 6 次探测，低于总上限 20 次；账号 235、238 各 3 次，未超过单账号上限。
- 页面探测均使用独立 `Target.createBrowserContext`，结束后立即 `Target.disposeBrowserContext`。
- 每次探测都在结束前把最新 cookie 通过本机管理接口 `POST /admin/accounts/{aid}/cookies` 写回；输出只保留账号标签、时间和 HTTP 状态。
- 未输出或记录 key、cookie、token、完整账号 ID；未更改 Railway 配置，未部署。

| # | 账号 | 时间（Asia/Shanghai） | 方法 | cookie 写回 |
|---|---|---|---|---|
| 1 | 235 | 2026-11-15 23:54:15 | A：页面前不做 HTTP wake | HTTP 200 |
| 2 | 235 | 2026-11-15 23:54:46 | B：先请求 session/尝试 wake，再加载页面 | HTTP 200 |
| 3 | 238 | 2026-11-15 23:55:59 | A：页面前不做 HTTP wake | HTTP 200 |
| 4 | 238 | 2026-11-15 23:56:24 | B：先请求 session/尝试 wake，再加载页面 | HTTP 200 |
| 5 | 238 | 2026-11-15 23:57 | 认证 HTML/公开 bundle 地址读取；公共静态资源下载随后被上游重置 | HTTP 200（下载资产前已完成） |
| 6 | 235 | 2026-11-16 00:01:30 | 页面协议及失败 cookie 轮换复核 | HTTP 200 |

第 1、2 次探测因一次性脚本在结果汇总阶段调用了错误的只读 helper，页面结果未保留；cookie 写回和上下文销毁均已在此之前的 `finally` 完成。为遵守单账号上限，没有在 235 上重跑 A/B。第 3、4 次形成有效 A/B 记录；第 6 次使用 235 的最后一次额度补足前端协议证据。

## muse.ai 前端协议

取证来源为 2026-11-15 页面实际加载的公开 Next.js bundle：

- `3e-p5628-9165.js`：VM assignment、wake 与恢复流程。
- `0e7r790tskdhg.js`：gateway token 获取流程。
- `1edy9lfamzbt5.js`、`1hp39f-4m10fz.js`：`/api/session` 刷新和 VM 列表读取。

静态代码与网络事件给出的顺序如下：

1. 页面从服务端初始数据或 `GET /api/session` 读取 assignment。只有 `status=assigned` 才能得到 `endpoint_url`、`vm_id`/`vm_name` 等目标信息；`status=unavailable` 会进入 recovery，继续请求 session。
2. 页面调用 `POST /api/hatch/vm/wake`。请求体包含 `vm_id`、`retry_count`；连接流程存在时还包含同一流程生成的 `connect_attempt_id`，以及 `wake_trigger`、`open_id`、`away_ms`。HTTP 200 只代表 wake 被接受。
3. 页面调用 `POST /api/hatch/token`，请求体包含目标 `vmAddress`，可选 `vmName`、`force_refresh`。成功响应的 token 只在页面内用于建立 gateway WebSocket；本次取证脚本从未读取或输出 token。
4. token 失败会按响应的 `code`/`error` 分类；`hatch_vm_auth_no_match` 表示 gateway 无法把 token 请求匹配到可用 VM 连接。

这解释了为什么服务自己另发随机 `connect_attempt_id` 不安全：它与页面后续 token 请求所属的连接流程没有共享状态。即使它不是本次故障的唯一根因，也可能改变“最新连接尝试”并扩大 no-match 窗口。

## 假设 1：我们的 HTTP wake 抢占页面连接

### 方法

- 静态检查 `engine.renew_session_http`、`_renew_and_persist`、`ensure_page`、自动保活和浏览器预热调用点。
- 解析公开 bundle，核对 wake 的参数和它与 session/token 的关系。
- 同一账号 238 做 A/B：A 不做外部 wake；B 先执行服务原有 session/wake 路径，再加载独立页面。
- 账号 235 额外记录页面自己的 wake、session 和 token 状态。

### 脱敏原始结果

- A（238）：页面只观察到 `GET /api/session -> 200`，正文为 `status=unavailable`、`vm_resolution_issue.kind=retryable`、无 `vm_id`；页面最终为错误页。
- B（238）：前置 `GET /api/session` 同样为 `unavailable`、无 `vm_id`，因此服务没有实际发送 wake；随后页面结果与 A 相同。
- 页面原生流程（235）：两次 `POST /api/hatch/vm/wake -> 200`，请求均包含 `vm_id`、`retry_count`、`connect_attempt_id`、`wake_trigger`、`open_id`、`away_ms`；随后 `GET /api/session -> 200 status=unavailable`，`POST /api/hatch/token -> 401`，分类为 `hatch_vm_auth_no_match`。
- 服务原代码会在任务前、`ensure_page`、15 分钟保活和预热路径调用 `wake_vm=True`，其 `connect_attempt_id` 每次由独立 UUID 随机生成。

### 结论

**部分成立（加重因素），但不是已证实的唯一根因。** 当前 session 经常不返回 `vm_id`，导致 B 无法形成真正“外部 wake 已发出”的有效因果对照；同时 A 组不做外部 wake 仍失败。另一方面，bundle 证明页面的 ID 属于自己的连接流程，我们的独立随机 wake 不具备正确的关联关系。代码已停止所有正常链路的外部 wake，保留 `renew_session_http(..., wake_vm=True)` 仅作为显式底层能力和离线测试对象。

## 假设 2：失败页面丢掉浏览器轮换 cookie

### 方法

- 静态追踪 `_apply_cookies`、`ensure_page`、`_close_page`、`read_cookies` 和 `_sync_cookies`。
- 检查 `/api/session` 已有轮换处理及离线回归 `test_session_cookie_rotation.py`。
- 第 6 次页面探测在销毁上下文前比较 cookie 名和值是否变化，只输出变化的 cookie 名，不输出值。

### 脱敏原始结果

- 原代码仅在生成成功后由 app 的 `_sync_cookies` 读回浏览器 cookie；`ensure_page` 的崩溃/超时分支会直接 `_close_page`，失败上下文中的新值没有通用回存路径。
- 已有线上证据显示 `/api/session` 即使 `status=unavailable` 也会通过 Set-Cookie 轮换 `hatch_sess`/`hatch_gw`；`2fd83b8` 只覆盖 HTTP session 路径，并不覆盖浏览器页面收到的所有 Set-Cookie。
- 本次样本中，两个 B 组的直接 session 均报告 `rotated=false`；第 6 次页面关闭前比较结果为 `changed_cookie_names=[]`。因此本轮小样本没有再次观察到轮换，但代码缺口客观存在。

### 结论

**代码路径成立，本次样本未复现轮换。** 失败时丢 cookie 不是这 6 次探测的直接触发点，但一旦上游轮换发生就会让后续请求继续携带旧值，是明确的持续失败加重因素。现已让 `_close_page` 在销毁任何绑定账号的上下文前读取 httpOnly cookie，并交给现有合并写回函数；没有改动 `2fd83b8` 的 `MuseSessionUnavailable` 保存逻辑。

## 假设 3：同一账号在服务内有多个浏览器上下文竞争

### 方法

- 静态检查 `AccountPoolManager.busy_accounts`、`_account_operation`、生成重试、测试/额度、保活和 `_warmup_browser_sync`。
- 检查 `MuseEngine` 的 thread-local page/context、`_active_contexts` 和关闭路径。
- 运行并发与代理隔离离线测试。

### 脱敏原始结果

- 生成任务会先占用账号；同一账号在 `busy_accounts` 中时不会被另一个任务选中。
- 管理检测、额度读取、保活均使用同一账号租约；并发配置修改会被 409 拒绝。
- 浏览器页和 context 按线程隔离；预热持有 `GEN_LOCK` 和账号租约，并在 `finally` 中关闭页面、释放账号，不存在长期保留的 warm tab。
- `test_concurrency.py` 与 `test_account_proxy_routing.py` 通过。

### 结论

**不成立（就当前服务代码而言）。** 未发现服务内部让同一账号同时持有 warm tab、任务页、额度页或保活页的路径。外部用户浏览器不受该互斥控制，仍属于假设 4 的未排除因素。

## 假设 4：muse.ai 分配、出口 IP、风控或外部浏览器占用

### 方法

- 比较无外部 wake 的页面、前置 session 路径和页面原生 wake/token 流程。
- 结合 2026-11-15 已知统计：8 个账号、200 个任务中 198 个 VM unavailable，包含刚导入且导入测试通过的账号；11 月 7 日前同一部署曾成功。
- 不更改出口 IP、不关闭用户浏览器、不调整 Railway 配置，以免扩大生产影响。

### 脱敏原始结果

- 238 在完全不做外部 wake 时即得到 `status=unavailable`、`retryable`、无 `vm_id`。
- 235 的页面原生 wake 两次均为 HTTP 200，但 token 仍连续 401 no-match；wake 接受并未形成可用 token 匹配。
- 同一部署历史上能成功，因此不是“CDP/容器架构从未被支持”。
- 故障跨 8 个账号且包含新导入账号，更像共享条件（muse.ai 容量/匹配服务、出口 IP/地区策略）或所有账号共有的外部使用模式，而不像单一 cookie 失效。

### 结论

**成立为当前主要剩余方向，但内部子原因无法确认。** 本次证据无法区分 muse.ai 容量/匹配故障、服务器出口 IP 风控和用户浏览器占用。需要用户侧确认所有账号是否在其它浏览器打开 muse.ai；若已全部关闭，建议把脱敏时间线和 wake 200/token 401 证据提交 muse.ai，并在不改生产配置的前提下由人工评估换出口 IP 或等待上游恢复。

## 代码修复

- `engine.py`
  - `renew_session_http` 默认不 wake；`ensure_page` 明确以 `wake_vm=False` 预续签，让页面拥有完整 wake/token 生命周期。
  - 页面一创建就绑定账号 ID；`_close_page` 在关闭页面和销毁 BrowserContext 前读取最新 httpOnly cookie 并调用既有 cookie sink 合并保存。
  - `read_cookies` 支持读取指定页面，确保失败页在清理前也能同步。
- `app.py`
  - 生成/对话重试、保活探测和浏览器预热全部改为 `wake_vm=False`。
- 测试
  - 新增 `test_vm_connection_ownership.py`，覆盖“不主动 wake”和“失败上下文关闭前回存 cookie”。
  - 更新 `test_wake_confirmation.py`，显式传 `wake_vm=True` 继续覆盖底层 wake 确认语义。

## 建议

1. 合并修复后观察 `status=unavailable` 与 `hatch_vm_auth_no_match` 比例；该修复只消除客户端干扰，不应被当作上游已恢复的证明。
2. 用户确认所有关联账号均关闭其它 muse.ai 页面，等待数分钟后再做一次人工只加载页面验证。
3. 若仍能稳定复现，向 muse.ai 提供：时间、服务器地区、`wake HTTP 200 -> session unavailable -> token 401 hatch_vm_auth_no_match` 的脱敏序列；不要提供 cookie/token。
4. 只有在确认外部浏览器未占用且 muse.ai 无服务故障后，再评估受控更换出口 IP。不要在生产任务进行中改 Railway 配置或部署。

## 自测结果

使用临时虚拟环境安装现有 `requirements.txt`，macOS Chromium 测试通过 `exec` 包装器指向本机 Google Chrome；未改依赖文件。

- `python tests/test_*.py`：38/38 通过，0 失败（逐个独立执行）。
- `node tests/test_admin_api_error_messages.mjs`：通过。
- 新增定向测试覆盖：应用主链路不再主动 wake；失败页面销毁前回存浏览器 cookie；原有 session cookie 轮换、VM 错误分类、并发互斥、代理隔离和显式 wake 确认测试均通过。
