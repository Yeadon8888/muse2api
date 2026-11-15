# 任务书 07：工作区不可用时退避 / 冷却，遇到 no_match 只重新发现一次

分支：`fix/vm-unavailable-backoff` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：`git pull` 后确认 `railway-v1.6.9` 含 `14b6327`（停止外部 wake、页面关闭前回存 cookie）和 `bc0e8a3`（调研报告 `docs/investigations/2026-11-15-vm-no-match-web-research.md`），`engine.py` 有 `MuseWorkspaceUnavailable`。不满足就停下说明。

## 背景
- 线上曾在 2 小时内提交 200 个任务全部失败（198 个 `MuseWorkspaceUnavailable` / `hatch_vm_auth_no_match`）。现在的重试逻辑在每个任务里换号重试，所有账号都不可用时会对 muse.ai 快速轮番请求，可能加重限流。
- 调研报告（上面的文件，"可借鉴的修复方案" 第 3、6 条）建议：遇到 no-match 只重新发现一次；`unavailable/retryable` 用有界退避和熔断，所有账号同时不可用时直接返回上游故障，不轮转重登。

## 要做
1. **账号级冷却**：账号报 `MuseWorkspaceUnavailable` 后进入冷却（默认 5 分钟，`MUSE2API_WORKSPACE_COOLDOWN_SECONDS`），冷却期内账号池不分配它（不改 `ok` 状态，不提示重新导入）；冷却结束自动恢复参与调度。管理接口 `/admin/accounts` 返回冷却剩余时间字段，供页面后续展示（本任务不改 `admin.html`）。
2. **全局熔断**：当所有可调度账号都在冷却中时，新任务**立即失败**，错误信息写清"muse.ai 当前没有为任何账号分配工作区（上游故障），已暂停请求，约 X 分钟后自动重试；无需重新导入 cookie"，不要再打开页面或请求 muse.ai。可配置开关与时长。
3. **no_match 只重新发现一次**：同一任务、同一账号首次遇到 `MuseWorkspaceUnavailable` 时：关闭页面（已有逻辑会回存 cookie）→ 等待短暂间隔（默认 15 秒，可配置）→ 重新 `GET /api/session`（不 wake）→ 若返回 `assigned` 才重开页面重试一次；仍失败或仍 `unavailable` 则交给换号逻辑并进入冷却。**绝不循环重试同一账号，绝不重新登录。**
4. 换号重试：每个任务最多尝试的账号数保持现状或更少，跳过冷却中的账号。
5. 测试（离线，本地模拟，不访问生产、不调用 muse.ai）：冷却生效与到期恢复；全部冷却时快速失败且不调用 `engine.generate`；no-match 后 session 变 `assigned` 时重试一次成功、仍 `unavailable` 时不再重试并进入冷却；冷却不改变 `ok`。全量运行 `tests/test_*.py` 与 node 测试，列出结果。
6. 在 `docs/RAILWAY_DEPLOY.md` 的环境变量表与故障排查里补充新变量和"上游故障熔断"的说明（只改相关段落）。

## 允许 / 禁止
允许：`app.py`、`store.py`、`engine.py`（仅与重试/冷却相关的最小改动）、`config.py`（新增配置项）、`docs/RAILWAY_DEPLOY.md`、新增或修改相关 `tests/*`。
禁止：`admin.html`、`Dockerfile`、`requirements.txt`、`media_janitor.py`、`AGENTS.md`、其他 docs；不要恢复外部 wake（`14b6327` 已停用），不要改 cookie 轮换保存逻辑。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 上述测试场景全部通过；全量测试通过（列出逐个结果）
- [ ] 所有账号冷却时，任务在 1 秒内失败且没有任何对 muse.ai 的请求（测试证明）
- [ ] 冷却与熔断不改变账号 `ok`，错误信息不提示重新导入 cookie
- [ ] 新配置项有默认值、写进文档

## 自测
- 依赖：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`；Chromium 测试按 `AGENTS.md` 设置
- **不访问生产服务，不调用 muse.ai，不发起任何生成**

## 交付
- `git add -A && git commit`，`git push -u origin fix/vm-unavailable-backoff`，`gh pr create --base railway-v1.6.9`
- PR 正文：设计说明（冷却/熔断/单次重新发现的状态流转）、配置项、测试结果、已知限制
- **不要合并，不要 push `railway-v1.6.9`**
