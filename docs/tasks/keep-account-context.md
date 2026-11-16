# 任务书 12：每个账号保留长期浏览器上下文（阶段 B：验证"每账号只能成功一次"的因果）

分支：`fix/keep-account-context` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：`git pull` 后确认 `railway-v1.6.9` 含 `8f9fa17`（cookie 单份注入）与 `6e9ba99`（工作区冷却/熔断）；阅读 PR #9 的报告 `docs/investigations/2026-11-16-one-use-research.md`（在分支 `docs/one-use-research`，可用 `git fetch origin docs/one-use-research` 后查看）。不满足就停下说明。

## 背景
用户：每个新导入账号都能成功生成一条视频，第二条起 `/api/hatch/token` 401 `hatch_vm_auth_no_match`；用户自己的长期浏览器一直正常。
我们的 `engine.py` 每个任务 `Target.createBrowserContext` 新建隐身上下文，任务结束 `close_current_page()` → `Target.disposeBrowserContext`，IndexedDB（含 `hatch-cvm-*`）、localStorage 等全部丢弃。公开的同类项目（`magpie-muse-web`、`muse_cli`）都为每个账号长期保留上下文。
目标：先用最小改动验证因果——**同一账号的后续任务复用该账号首次创建的上下文与页面**，不再每任务销毁。耐重启的加密快照（阶段 C）不在本任务范围。

## 要做
1. `engine.py`：维护"账号 ID → {browserContextId, targetId, CDP 页, 代理快照}"的注册表（线程安全）。
   - `ensure_page(account_id=...)`：若该账号已有存活上下文/页面（代理配置一致），直接复用（必要时导航到 `/thread/new` 或沿用 `reset_thread`）；否则新建并登记。cookie 仍按现有单份规则注入，但**复用时不要清空**上下文里已有的 cookie / 存储（只在新建时注入；复用时可用账号池里更新的 cookie 覆盖同名 cookie）。
   - `close_current_page()` 改为"释放"：保留该账号的上下文与页面，只清理本线程引用；**只有**以下情况才真正 `disposeBrowserContext`：页面崩溃且分类为认证失败、代理配置变化、账号被删除/禁用、显式重置、超过保留上限（LRU）、引擎停止。
   - 工作区不可用（`MuseWorkspaceUnavailable`）时：**不要**销毁该账号上下文（避免丢失可能的绑定状态），只关闭/重置页面内容；把这一行为写进代码注释。
   - 新增配置 `MUSE2API_KEEP_ACCOUNT_CONTEXTS`（默认 `1` 开启，`0` 恢复旧行为）和 `MUSE2API_MAX_ACCOUNT_CONTEXTS`（默认 8，超过时按最近最少使用关闭最旧的空闲上下文；正在被任务使用的不关）。
2. `app.py`：确保生成、对话、额度读取、测试、预热、保活等路径与新生命周期兼容；同一账号仍由 `ACCOUNT_POOL` 保证同一时间只有一个任务使用；额度读取等"一次性页面"不要污染或关闭账号的长期上下文（可以在同一上下文开临时页面，用完关该页面但不销毁上下文）。
3. 管理接口 `/admin/status` 增加当前保留的账号上下文数量（不暴露 ID 全称）。
4. 测试（离线，真实 Chromium 或现有的模拟方式，不访问生产）：同账号两次任务复用同一 browserContextId；不同账号不同上下文；认证失败崩溃会销毁并重建；工作区不可用不销毁；LRU 上限生效且不关闭使用中的上下文；`MUSE2API_KEEP_ACCOUNT_CONTEXTS=0` 时回到每任务销毁；IndexedDB 中写入的测试记录在同账号第二次任务时仍存在（用本地页面模拟）。全量运行 `tests/test_*.py` 与 node 测试。
5. 更新 `docs/RAILWAY_DEPLOY.md`：新配置项、内存影响（每个保留上下文约数百 MB）、重启后会丢失（阶段 C 解决）。

## 允许 / 禁止
允许：`engine.py`、`app.py`、`config.py`、`docs/RAILWAY_DEPLOY.md`、新增/修改相关 `tests/*`。
禁止：`store.py`（如确需改先停下说明）、`admin.html`、`Dockerfile`、`requirements.txt`、`media_janitor.py`；不要恢复外部 wake；不要改 cookie 作用域规则（`8f9fa17`）与轮换保存逻辑。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 上述离线测试全部通过；全量测试通过（列出逐个结果）
- [ ] PR 说明生命周期状态图（创建 / 复用 / 释放 / 销毁的条件）和内存估算
- [ ] 不访问生产、不调用 muse.ai、不发起生成；不输出任何凭据

## 交付
- `git add -A && git commit`，`git push -u origin fix/keep-account-context`，`gh pr create --base railway-v1.6.9`
- PR 正文写清：上线后的验收方法（用户导入新账号，同一账号连续生成第 1、2、3 条视频）
- **不要合并，不要 push `railway-v1.6.9`**
