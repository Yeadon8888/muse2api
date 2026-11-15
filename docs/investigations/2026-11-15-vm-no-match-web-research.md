# muse.ai `hatch_vm_auth_no_match` / 工作区无法分配：公开资料调研

> 调研日期：2026-11-15 至 2026-11-16（Asia/Shanghai）
>
> 范围：只读公开网页与公开 GitHub 仓库；未登录账号，未访问本项目生产服务，未调用 muse.ai `/api/*`，未发起生成
>
> 结论强度：中等。能确认“登录会话”和“VM 分配/绑定”是两个状态，也找到真实恢复案例与两种处理实现；但没有找到 muse.ai 官方对错误码的说明，也没有公开证据证明主动 `vm/wake` 与页面连接必然冲突。

## 结论摘要

1. **`hatch_vm_auth_no_match` 不应直接等同于 Cookie 失效。** 两个独立项目都把它与普通登录失效分开：`muse-guardian` 明确认为重新登录不能修复，遇到它就停止自动重登；`muse-im-bridge` 则把它解释为当前 VM 标识可能过期，重新发现 VM 后只重试一次，若仍失败也保留 Cookie，不转成登录失效。来源：[muse-guardian 的熔断逻辑](https://github.com/bytehola/muse-guardian/blob/b6241874bc85f85790b62cfca672852ec1389343/MuseAutoApprove/work/login-guard.cjs#L49-L57)、[说明](https://github.com/bytehola/muse-guardian/blob/b6241874bc85f85790b62cfca672852ec1389343/MuseAutoApprove/README.md#L159-L178)、[muse-im-bridge 的恢复逻辑](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L325-L369)及其[回归测试](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/tests/test_token_recovery.py#L131-L158)。
2. **`GET /api/session` 的 `status: unavailable`、`vm_resolution_issue.kind: retryable` 是真实的上游 VM 未分配状态。** Berserk Muse 记录：2026-10-23 两个既有会话都得到该响应，浏览器新会话也显示错误；2026-10-25 VM 又被分配并完成生成。换 VPN 与恢复同时发生，但作者明确说因果未确认。来源：[资格验证记录](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/docs/QUALIFICATION.md#L34-L55)、[排障说明](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/docs/TROUBLESHOOTING.md#L32-L38)。这与本次“所有账号同时失败”更像上游分配/路由问题，而不是所有 Cookie 同时过期。
3. **`unavailable` 响应仍可能轮换并立即作废 `hatch_sess` / `hatch_gw`。** 上游 PR #60 的复现是 HTTP 200、`status: unavailable`，同时 `Set-Cookie` 下发新值；旧实现先抛异常再读 Cookie，导致后续页面使用旧值。当前部署分支已包含同类保护。来源：[PR #60](https://github.com/czg86389-hub/muse2api/pull/60)、[本 fork 的处理](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/engine.py#L595-L665)与[持久化调用](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/app.py#L355-L393)。这是必须保留的正确性修复，但它本身不能让上游重新分配 VM。
4. **“主动 `vm/wake` 与页面自身连接冲突”目前仍是待验证假设。** 检索到的多个实现都沿用 `GET /api/session` → `POST /api/hatch/vm/wake`，且每次用随机 UUID 作为 `connect_attempt_id`；没有公开项目说明随机 ID 必须与页面后续连接共用，也没有公开案例证明并发 wake 会制造 `hatch_vm_auth_no_match`。反证也不充分：这些实现并未专门测试 wake 与页面同时连接。
5. **现有代码比多数 fork 更积极地 wake。** `ensure_page` 在最近 10 分钟未续签时会先 `wake_vm=True`，启动预热也会 wake，后台循环每 15 分钟检查、在需要探测的账号上 wake。相比之下，最值得做的低风险实验是“页面打开前不主动 wake，由官方页面完成连接”，而不是立即重登或清 Cookie；但这仍需并行实验任务给出因果证据。

## 现象的协议含义

公开实现呈现出三层状态，不能混为一谈：

1. **登录会话层**：`hatch_sess` 等 Cookie 是否仍被 `/api/session` 接受。明确的 `/api/session` HTTP 401/419 才是强登录失效信号。上游 issue #16 讨论的是这种情况；其解决方案是完整导入 HttpOnly Cookie，而不是本次 VM 错误。来源：[issue #16](https://github.com/czg86389-hub/muse2api/issues/16)。
2. **VM 解析/分配层**：有效登录会话可能得到 HTTP 200 但 `status: unavailable` / `none`，没有可用 VM。Berserk 的解析器明确把 `none` 和 `unavailable` 单列，不把它当登录失败；同时兼容旧的顶层 `endpoint_url` 和新的 `vms[]` 结构。来源：[VM 解析器](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/src/muse/vm.mjs#L26-L48)。
3. **VM token 绑定层**：`POST /api/hatch/token` 用 `vmAddress` / `vmName` 换取网关 token。如果提交的 VM 标识与账号当前分配不一致，至少一个项目观察到 `hatch_vm_auth_no_match`，并采用“重新发现 VM 后重试一次”。来源：[token 请求与单次重发现](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L325-L355)。

因此，本次组合信号——`/api/session` 为 `unavailable/retryable`、页面 `/api/hatch/token` 为 `hatch_vm_auth_no_match`、页面崩为 “Something went wrong”——可一致解释为：登录 Cookie 仍被接受且可能继续轮换，但当前没有稳定的 VM 描述符，或页面/token 请求仍在使用一个已经变化的 VM 绑定。此解释是基于多源实现的综合推断，不是 muse.ai 官方定义。

## 本仓库当前实现基线

基线为 `Yeadon8888/muse2api` 的 `7af3286`：

- `renew_session_http` 先 `GET /api/session`，合并响应 Cookie；只有 `status == assigned` 才取顶层 `vm_id` / `vm_state`。随后在 `vm_state != DISABLED` 时无条件调用 `POST /api/hatch/vm/wake`，请求体为 `vm_id`、`retry_count: 0`、随机 `connect_attempt_id`；成功后只再查一次 `/api/session`，仅 `RUNNING` 算 wake 成功。[engine.py L554-L665](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/engine.py#L554-L665)
- `ensure_page` 对同账号热页先复用；否则关页。超过 10 分钟未 HTTP 续签时会带 `wake_vm=True` 预续签，再打开隔离上下文、注入 Cookie、导航到 `/thread/new`。`unavailable` 时保留轮换 Cookie并仍尝试页面加载。[engine.py L928-L1008](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/engine.py#L928-L1008)
- 页面通过注入 hook 只记录 `/api/hatch/token` 的 `status/code/error`；`hatch_vm_auth_no_match` 被分类为 `MuseWorkspaceUnavailable`，不再误标 Cookie 失效。[engine.py L722-L835](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/engine.py#L722-L835)
- 启动预热先 `_renew_and_persist(..., wake_vm=True)`，随后 `ensure_page`；后台守护每 15 分钟检查一次，但账号只有在强制、未探测，或距上次成功超过 6 小时且临期/不健康时才真正调用 wake，并非稳定状态下每 15 分钟对每个账号都 POST。[app.py L2400-L2500](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/app.py#L2400-L2500)、[L2505-L2544](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/app.py#L2505-L2544)
- Cookie 回存已覆盖 `unavailable`、wake 和 verify 响应，且未确认工作区时不刷新 `synced_at` / `last_keepalive`。[app.py L336-L393](https://github.com/Yeadon8888/muse2api/blob/7af32866e3d262185c27fc020361ab65219efef1/app.py#L336-L393)

非显然差异：代码当前只识别顶层 `vm_id`，没有兼容公开项目已处理的 `vms[]` / preferred VM 结构；若 muse.ai 正在灰度响应结构，这可能导致“有 VM 但本代码看不到”。不过本次已观察到的响应明确是 `status: unavailable`，所以这不是现象的充分解释。

## 上游 `czg86389-hub/muse2api`

### Issues、PR、提交

- 2026-09-26 提交 [`eab6898`](https://github.com/czg86389-hub/muse2api/commit/eab6898ca95ec4cd59e089c6d91eb522a4e3e197) 首次加入 `/api/session` 续签、`vm/wake`、随机 `connect_attempt_id`，并把后台周期从 30 分钟缩到 15 分钟。提交没有说明该 ID 与页面连接之间的关联，也没有针对多连接冲突的验证。
- 2026-10-10 issue [#16](https://github.com/czg86389-hub/muse2api/issues/16) 是 `/api/session` HTTP 401 与频繁重导 Cookie，和本次 HTTP 200 `unavailable` 不同。
- 2026-10-17 至 10-22 PR [#26](https://github.com/czg86389-hub/muse2api/pull/26) 的脱敏实测表明缺少 `hatch_gw` 仍能 `/api/session`、wake 到 `RUNNING` 并生成；因此“没有/变化的 `hatch_gw` 必然导致 VM 错误”不成立。后续 issue [#29](https://github.com/czg86389-hub/muse2api/issues/29) 与 [#34](https://github.com/czg86389-hub/muse2api/issues/34) 也确认 `hatch_gw` 不是必要导入项。
- 2026-11-05 PR [#42](https://github.com/czg86389-hub/muse2api/pull/42) 首次明确区分“登录有效”和“工作区可用”，只有 `/api/session` 为 `assigned` 才把新登录账号保存为可用；作者注明真实验证码与生成链路尚未端到端验证。
- 2026-11-15 PR [#60](https://github.com/czg86389-hub/muse2api/pull/60) 给出了本次同型 `unavailable/retryable` 响应，并修复未分配响应中的 Cookie 轮换丢失。它修复会话连续性，不声称能恢复 VM 分配。
- 对 `hatch_vm_auth_no_match` 的 issues/PR/讨论搜索没有命中；`unavailable` / “工作区”只命中 #42、#60。公开 Discussions 未发现相关条目。

### 与本 fork 的差异

上游 `main` 截至 2026-11-11 的 [`b60f474`](https://github.com/czg86389-hub/muse2api/tree/b60f474977f125210eb7c71b0fc6668b2f1dd700) 仍是在 wake 后只确认一次 `/api/session`，也未捕获页面 token 错误分类；本 fork 已提前包含 #60 型 Cookie 回存与 `hatch_vm_auth_no_match` 分类，因此当前问题不是简单落后于上游 main。

## 指定项目逐项对比

下表中的代码均为公开 MIT 仓库（若仓库页面未声明许可证，则未摘录代码）；“取 token”指项目是否自行调用 `/api/hatch/token`，否则由 muse.ai 页面脚本完成。

| 项目（检查版本） | 会话续签 / VM 唤醒 | token、并发与 Cookie 回存 | 与本仓库的主要差异 |
|---|---|---|---|
| [`www222fff/muse2api`](https://github.com/www222fff/muse2api) `3a20b5e` | `GET /api/session` 后 POST wake，随机 UUID；无论 wake HTTP 结果如何，最长 20 秒轮询 session 至 `RUNNING`。[muse.py L79-L170](https://github.com/www222fff/muse2api/blob/3a20b5e7aa4056c99c0eb8c732d73ce3804d5dbf/src/muse2api/upstream/muse.py#L79-L170) | 页面自行取 token；每账号独立 browser context，可配置多标签并发；轮换 Cookie 可写入共享 context，失败则把 tabs 标 stale。[driver.py L118-L250](https://github.com/www222fff/muse2api/blob/3a20b5e7aa4056c99c0eb8c732d73ce3804d5dbf/src/muse2api/drivers/browser/driver.py#L118-L250)、[L865-L890](https://github.com/www222fff/muse2api/blob/3a20b5e7aa4056c99c0eb8c732d73ce3804d5dbf/src/muse2api/drivers/browser/driver.py#L865-L890) | 比本仓库多次轮询并保留诊断状态。其真实观察是 RUNNING VM 的 wake 可能返回 403，所以不能以 wake HTTP 200 判断结果。[测试 L122-L142](https://github.com/www222fff/muse2api/blob/3a20b5e7aa4056c99c0eb8c732d73ce3804d5dbf/tests/test_wake_confirmation.py#L122-L142) |
| [`bynne2602/muse2api`](https://github.com/bynne2602/muse2api) `14c2ab9` | 早期 `czg` fork；session 后 wake，随机 UUID，只看 wake HTTP 200，不等待 `RUNNING`。[engine.py L231-L291](https://github.com/bynne2602/muse2api/blob/14c2ab985dd20ba6644340e6aad69528b31a185e/engine.py#L231-L291) | 页面取 token；线程局部单热页；CDP `Network.getCookies` 读回并持久化。[engine.py L324-L459](https://github.com/bynne2602/muse2api/blob/14c2ab985dd20ba6644340e6aad69528b31a185e/engine.py#L324-L459) | 比本仓库旧：没有 `unavailable` 轮换保护、token 错误分类或 wake 后确认。
| [`sewall2025/muse2api`](https://github.com/sewall2025/muse2api) `4cba62c` | session 后 wake，随机 UUID，只看 HTTP 200，不确认 `RUNNING`。[muse.py L39-L83](https://github.com/sewall2025/muse2api/blob/4cba62c46ca3cd8b0e4ae1b5ebb2ae86cefa1807/src/muse2api/upstream/muse.py#L39-L83) | 页面取 token；每账号隔离 context、按配置多 tab；续签后将旧 tab 标 stale。 | `www222fff` 的早期 fork；无本问题专门处理。
| [`KinX-ai/muse2api`](https://github.com/KinX-ai/muse2api) `76104e0` | 与 `sewall2025` 的相关文件相同：随机 ID wake、仅看 HTTP 200。[muse.py L39-L83](https://github.com/KinX-ai/muse2api/blob/76104e0923da98854a64f1c4b40323347f6e7a3c/src/muse2api/upstream/muse.py#L39-L83) | 页面取 token；每账号 context / 多 tab；轮换后废弃 tabs。 | 无 `RUNNING` 轮询、无 VM mismatch 恢复。
| [`linuxing3/muse2api`](https://github.com/linuxing3/muse2api) `8ee207c` | 随机 ID wake 后最长 20 秒轮询 session；轮询响应中的 Cookie 也合并。[muse.py L75-L170](https://github.com/linuxing3/muse2api/blob/8ee207c18d82f6038a4999b083fdc4225a8323a9/src/muse2api/upstream/muse.py#L75-L170) | 页面取 token；每账号 context / 多 tab；轮换后废弃 tabs。 | 比本仓库的单次确认更稳健，但仍不识别 `hatch_vm_auth_no_match`。
| [`belfaranet-debug/muse2api`](https://github.com/belfaranet-debug/muse2api) `ae17131` | 相关实现与 `www222fff` 相同：随机 ID wake + 轮询 `RUNNING`。[muse.py L79-L170](https://github.com/belfaranet-debug/muse2api/blob/ae17131976aec95a49f21dfcccebce1b42706880/src/muse2api/upstream/muse.py#L79-L170) | 页面取 token；支持把轮换 Cookie直接写回当前 context，保持热页；必要时才 stale tabs。 | Cookie 热更新比本仓库“关闭再开页”更平滑；没有 VM mismatch 专项。
| [`d4ncboz/museai`](https://github.com/d4ncboz/museai) `b470724` | session 后 wake，随机 UUID，只看 HTTP 200。[muse.py L41-L85](https://github.com/d4ncboz/museai/blob/b470724716ac923fa0de1f743c3c6310dcd0d5d1/src/museai/upstream/muse.py#L41-L85) | 页面取 token；每账号独立 context、单 tab 串行；续签后强制重开 tab。 | 早期实现，`hatch_gw` 仍列为必要；无本问题专门处理。
| [`lvluu/museai`](https://github.com/lvluu/museai) `dd6fc6e` | session 后 wake，随机 UUID，只看 HTTP 200。[muse.py L69-L113](https://github.com/lvluu/museai/blob/dd6fc6ec448f18b56e4e21b22ff4973dd7f26310/src/museai/upstream/muse.py#L69-L113) | 页面取 token；每账号 context，可多 tab；轮换 Cookie 时 busy tab 结束后关闭。[driver.py L192-L280](https://github.com/lvluu/museai/blob/dd6fc6ec448f18b56e4e21b22ff4973dd7f26310/src/museai/drivers/browser/driver.py#L192-L280) | `hatch_gw` 已改为非必要；仍无 `RUNNING` 轮询与 mismatch 恢复。
| [`liemgumball/museai`](https://github.com/liemgumball/museai) `f0a9aed` | 相关 `muse.py` 与 `lvluu` 相同：随机 ID wake、只看 HTTP 200。[muse.py L69-L113](https://github.com/liemgumball/museai/blob/f0a9aedd98105baf40e72fa3cab34cfa6f45a03d/src/museai/upstream/muse.py#L69-L113) | 页面取 token；每账号 context / 多 tab，轮换后 stale tabs。 | 无本问题专门处理；应用其他功能变化不影响 VM 路径。

这些 fork 多数共享祖先，不能当作九份独立验证。它们一致使用随机 `connect_attempt_id`，只说明这种写法广泛复制；不能证明它在当前上游版本仍正确。

## 代码搜索发现的其他项目

### `Bao-qing/muse-im-bridge`：最直接的错误码恢复实现

该项目不依赖页面取 token，而是自行 POST `/api/hatch/token`：

- 从 token 或登录 HTML 的 `*.metaaivm.com` 地址发现 VM ID；请求体同时带 `vmAddress` 和 `vmName`。[token_manager.py L42-L46、L184-L201](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L42-L46)
- 若第一次返回 `hatch_vm_auth_no_match`，且 VM 不是用户显式固定的，就重新扫描当前 HTML 得到 VM ID并重试一次；第二次仍失败则作为可恢复的 refresh error 返回，不清 Cookie、不触发登录。[token_manager.py L325-L369](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L325-L369)
- 测试明确断言：VM mismatch 会重发现一次；重复 mismatch 仍保留 credentials；显式 VM 不覆盖。[test_token_recovery.py L131-L158](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/tests/test_token_recovery.py#L131-L158)
- 用进程内锁做单航班 mint，避免多个并发请求同时刷新相同 token。[token_manager.py L307-L320](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L307-L320)

这证明“旧 VM 描述符”是至少一个项目认真处理的触发原因，但测试是模拟响应，未附同日真实错误恢复日志，证据强度为中等。

### `bytehola/muse-guardian`：防止错误地反复登录

该项目直接 mint token，并将 `hatch_vm_auth_no_match` 归入“重新登录解决不了”的类别；守护进程遇到它会写持久熔断标记，停止自动发 OTP。[login-guard.cjs L1-L20、L49-L57](https://github.com/bytehola/muse-guardian/blob/b6241874bc85f85790b62cfca672852ec1389343/MuseAutoApprove/work/login-guard.cjs#L1-L20) 这不是 VM 恢复方案，但强力支持本仓库现有“不提示重导 Cookie”的方向。仓库未在 GitHub 元数据中声明许可证，本报告不复制其代码。

### `ForgetMeAI/berserk-muse`：真实 `unavailable/retryable` 记录

该项目把 VM 不可用与登录状态分开，保留已写入的 session，不发送模型请求，提示稍后重试；不会自动重建账号 VM。[排障说明 L32-L38](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/docs/TROUBLESHOOTING.md#L32-L38) 其 HTTP transport 仍会先 wake，再由官方网页 vendor runtime 调 `/api/hatch/token`，并将响应 Cookie集中写回。[http.mjs L303-L340](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/src/muse/http.mjs#L303-L340)。它最大的价值是提供了 10 月 23 日失败、10 月 25 日恢复的真实时间序列，而不是某段实现本身。

### 其他代码搜索命中

对 `/api/hatch/token`、`/api/hatch/vm/wake` 的全局 GitHub 代码搜索还命中 `nikships/muse-cli`、`ForgetMeAI/berserk-muse`、`lichao199208/muse2api`、`suncodevn/muse-api-server` 等。抽查结果主要是两种路线：

- 浏览器/vendor runtime 复用网页协议，按 session 返回的 VM 描述符请求 token；
- 纯协议客户端缓存短期 token，并在过期或服务器拒绝后单航班刷新。

除 `muse-im-bridge` 和 `muse-guardian` 外，没有找到另一个公开仓库明确解释或修复 `hatch_vm_auth_no_match`。GitHub 精确搜索在 2026-11-16 只返回上述四个文件。

## 社区与官方资料

### 社区搜索

搜索了 linux.do、V2EX、Reddit、X 的公开索引，关键词包括：

- `hatch_vm_auth_no_match`
- `api/hatch/token`、`api/hatch/vm/wake`、`connect_attempt_id`
- `vm_resolution_issue`、`hatch_vml`、`hatch_sess muse.ai`
- `muse.ai 反代`、`muse2api 工作区`、`muse.ai Something went wrong`、`muse.ai VM`

未找到可核实、能直接支撑触发原因或解决办法的社区帖子。linux.do 与 Reddit 的站内 JSON 搜索被反机器人页面拦截；X 的公开搜索需要登录；V2EX 与通用公开索引没有返回精确相关结果。因此不能把“社区没有报告”解释为问题不存在，只能记为本轮没有获得可引用证据。

### 官方资料

- [`muse.ai/status`](https://muse.ai/status) 返回通用应用页面，没有公开组件状态或 incident 记录；`status.muse.ai` 在本次检查中无法建立 TLS 连接。
- [Meta Status](https://metastatus.com/) 标题与内容面向 Meta business products，未找到 Muse 组件。
- 未找到 muse.ai 官方对免费额度、VM/工作区数量、并发标签页限制、`hatch_vm_auth_no_match` 或 `vm_resolution_issue` 的公开说明。Muse 首页只说明它是 Meta 的个人 AI Agent；不能据此推断内部 VM 调度规则。

## 已知触发原因与已验证做法

### 有直接证据

1. **上游暂时不分配 VM**：`/api/session` 为 HTTP 200 + `unavailable/retryable`；真实案例可跨天恢复。解决办法是保留会话、不要发模型请求、退避后再查，而不是立即重登。[Berserk 记录](https://github.com/ForgetMeAI/berserk-muse/blob/892cf5b25bfff3b4e18286b644eb8954b83946ec/docs/QUALIFICATION.md#L47-L55)
2. **token 请求使用了过期/错误的 VM 标识**：精确错误码下重新发现 VM并单次重试是已有实现；重复失败不清 Cookie。[muse-im-bridge](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py#L325-L369)
3. **未分配响应仍轮换 Cookie**：必须先合并并持久化 `Set-Cookie`，否则会把一次 VM 问题扩大成真正的会话失效。[上游 PR #60](https://github.com/czg86389-hub/muse2api/pull/60)
4. **wake HTTP 状态不代表 VM 最终状态**：`www222fff` 记录 RUNNING VM 的 wake 可能返回 403；应查 session 的 `vm_state`。[实现与测试](https://github.com/www222fff/muse2api/blob/3a20b5e7aa4056c99c0eb8c732d73ce3804d5dbf/tests/test_wake_confirmation.py#L122-L142)

### 只有间接证据或尚未验证

- **同时打开多个页面/多标签占用工作区**：没有找到官方限制或公开复现。多个 fork 甚至明确支持同账号多 tab 并发，因此不能把它列为“已知原因”。这些项目也未针对当前错误做压力验证，所以同样不能排除。
- **主动 wake 与页面自动连接竞争**：本仓库、上游和多 fork 都主动 wake；没有项目证明不同随机 `connect_attempt_id` 会相互取消或造成 no-match。当前只能作为高价值实验假设。
- **出口地区 / VPN**：Berserk 记录换 VPN 后恢复，但同时指出 `isGeoGated=true` 时也能成功，因果未确认。不能把它写成确定解决方案。
- **Cookie 缺失或重新登录**：普通 HTTP 401 确实可能由 Cookie 不完整导致，但 `hatch_vm_auth_no_match` 的公开处理恰恰避免重登。除非 `/api/session` 明确 401/419或页面显示登录，否则不应重导。
- **免费额度或 VM 数量限制**：没有官方公开资料，未建立证据。

## 可借鉴的修复方案（按可信度排序）

1. **高可信：保留并完善“登录失效 / VM 不可用”分层，未分配响应始终回存 Cookie。** 当前分支已经实现，应保留；再确认所有调用路径都不会把 `unavailable` 标记为账号无效。证据：上游 PR #60、Berserk 真实记录、muse-guardian/muse-im-bridge 的错误分类。
2. **高可信：以 `/api/session` 的 VM 状态为准，不以 wake 的 HTTP 200 为准；在合理窗口内轮询到 `RUNNING`。** 可参考 `www222fff` 的 20 秒、有界轮询、每次合并 Cookie、网络错误只影响该轮的实现和测试。当前本仓库只确认一次，容易把 `STARTING` 当失败。[提交 `7ee60cb`](https://github.com/www222fff/muse2api/commit/7ee60cb9c739edeacdd8b10ca42b0c81a46a09b5)
3. **中高可信：每次 token 获取前使用最新 session VM 描述符；遇到 `hatch_vm_auth_no_match` 只重新发现并重试一次，绝不循环重登。** 如果继续依赖网页取 token，可在 hook 捕获 no-match 后关闭该页、重新 GET session/打开新页一次；若仍 `unavailable`，进入退避。纯协议方案可直接参考 `muse-im-bridge` 的单次重发现和单航班锁。需要同时兼容顶层字段与 `vms[]` preferred 结构。
4. **中可信：降低主动 wake 的侵入性并做 A/B。** 首选实验：`ensure_page` 打开官方页面前只续签/回存 Cookie，设置 `wake_vm=False`；让页面完成自己的 wake/token/WS 流程。后台只对明确 `SUSPENDED/STOPPED` 且没有活跃页的账号 wake，`RUNNING` 不再 POST。依据是当前主动 wake 缺少必要性证据、RUNNING wake 可能 403；但“这样能修复 no-match”尚未被公开资料验证。
5. **中可信：同账号的 session refresh、wake、开页/token 建连做单航班串行化。** 借鉴 `muse-im-bridge` 的 refresh lock 和 `www222fff` 的每账号条件锁：同一账号同一时刻只允许一条“发现 VM →（可选）wake → 开页/取 token”初始化链；业务生成仍可按已确认能力另行并发。这样可消除本仓库自身竞争变量，但没有证据证明上游要求单连接。
6. **中可信：对 `unavailable/retryable` 使用有界指数退避与熔断，不轮转重登。** 例如 15 秒、30 秒、1 分钟后重查，随后冷却 10–30 分钟；所有账号同时 unavailable 时返回上游工作区故障而不是逐账号快速轰击。证据是 Berserk 的跨天恢复与 guardian 的防重登熔断。具体间隔没有官方依据，应可配置。
7. **低到中可信：允许配置出口并做单变量地区实验。** 只在其他改动固定时比较同账号不同出口，记录 `/api/session` 状态与 VM descriptor；不能仅根据 `isGeoGated` 或一次恢复下结论。

## 建议给并行根因实验任务的最小矩阵

这不是本报告的代码修改建议，而是为了把尚未证实的假设变成证据：

| 组别 | session 前置 | 主动 wake | 页面 | 观察 |
|---|---|---|---|---|
| A（现状） | GET + 回存 | 随机 ID POST | 随后打开 | session 状态、VM 描述符摘要、token code、时间线 |
| B | GET + 回存 | 不 POST | 随后打开 | 是否仍 no-match；页面是否自行成功分配 |
| C | GET + 回存 | 仅非 RUNNING POST；轮询 RUNNING | 确认后打开 | 状态转换与 token 结果 |
| D | 不做 HTTP 预处理 | 不 POST | 直接打开 | 官方页面原生基线 |

同一账号每组只做一次、组间充分冷却；不要并行，不要重登，不记录 token/Cookie/完整 VM ID。若 D 成功而 A 稳定失败，才有力支持预 wake 冲突；若四组都 `unavailable/retryable`，更支持上游分配问题；若 session 给出新 VM 后单次重开成功，则支持 VM descriptor 过期。

## 仍然未知与风险

- 错误码由 muse.ai 官方如何定义、VM 绑定的生命周期、`connect_attempt_id` 是否必须跨 wake/token/WS 共享，均无官方文档。
- “所有账号同时失败”究竟是全局/地区性容量事件、出口风控，还是本服务共同执行路径触发，公开资料无法定因。
- 多个 fork 共用祖先，广泛复制的随机 UUID 和主动 wake 不是独立验证。
- Berserk 的真实恢复案例证明暂时性，但不能证明本次事故必然同因；其 VPN 变化是混杂变量。
- `muse-im-bridge` 的 no-match 恢复有良好单元测试，但未附真实现场前后响应，不能直接视为已验证修复。
- 官方没有公开免费计划 VM/工作区或并发标签限制；任何精确限制数字都不应进入产品提示。

## 搜索记录

| 来源 | 关键词 / 范围 | 结果 |
|---|---|---|
| `czg86389-hub/muse2api` issues、PR | `hatch`、`VM`、`wake`、`token`、`unavailable`、`Connecting`、`Something went wrong`、`工作区`、`会话`、精确错误码 | 相关：#16、#26、#29、#34、#42、#60；精确错误码无命中 |
| `czg86389-hub/muse2api` commits | `session`、`workspace`、`vm/wake`、`hatch_vm` | 相关：`eab6898`、`6fa0678`、`09ed4bd`、`8213b3d`；后者与本错误无直接证据 |
| 指定 9 个项目 | 全仓库搜索任务书全部关键词，并阅读 session/wake/browser driver/account pool | 全部覆盖，结论见逐项表；未见精确错误码 |
| GitHub 全局代码搜索 | `hatch_vm_auth_no_match`、`Gateway VM auth token unavailable` | 精确命中 `muse-guardian`、`muse-im-bridge` 共 4 文件 |
| GitHub 全局代码搜索 | `/api/hatch/token`、`/api/hatch/vm/wake`、`connect_attempt_id`、`vm_resolution_issue`、`hatch_vml`、`hatch_sess muse.ai` | 发现 Berserk、muse-cli、lichao199208 等；抽查见上文 |
| linux.do、V2EX、Reddit、X | 精确错误码及中英文现象词 | 无可引用结果；部分站点被登录/反机器人限制 |
| muse.ai / Meta 官方 | status、公告、free plan、workspace、VM、limits | 未找到 Muse 专用状态页、错误码或 VM 限制说明 |

## 引用与许可证说明

报告只描述公开代码的控制流并链接到固定提交与行号，没有复制成段代码。指定的 `muse2api` / `museai` 仓库及 `Bao-qing/muse-im-bridge` 在检查时声明 MIT；`bytehola/muse-guardian` 未在 GitHub 元数据中声明许可证，因此仅引用其公开文档和行为描述。所有日期均为来源页面或提交记录显示的日期。
