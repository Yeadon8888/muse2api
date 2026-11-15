# 任务书 05：调查线上所有账号持续 hatch_vm_auth_no_match（工作区无法分配）的根因，并修复我们代码造成的部分

分支：`fix/vm-no-match-root-cause` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：本目录有 `.env.local`（`MUSE2API_PROD_URL`、`MUSE2API_ADMIN_KEY`，只用变量名引用，绝不打印值）；`railway whoami` 已登录；`railway link -p 05776d1b-86a1-4217-b5eb-6efaa5f2f54d -e production -s muse2api` 能成功。不满足就停下说明。

## 现状（2026-11-15，Claude 实测）
- 生产服务 `muse2api`（Railway，部署分支 `railway-v1.6.9`，当前提交 `7af3286`）19:56–21:44 共 200 个任务，**0 成功**；198 个报 `MuseWorkspaceUnavailable`（`hatch_vm_auth_no_match`），2 个页面加载超时。8 个账号全部如此，包括刚导入、导入时测试通过的账号。
- 只加载页面（不发提示词）时：页面在"有输入框"和"Something went wrong"之间反复；`POST /api/hatch/token` 每次 `401 {"error":"Gateway VM auth token unavailable","code":"hatch_vm_auth_no_match"}`。
- `GET /api/session` 对所有账号返回 `200 {"status":"unavailable","vm_resolution_issue":{"kind":"retryable"}}`，并经常在 Set-Cookie 里轮换 `hatch_sess` / `hatch_gw`（`2fd83b8` 起会保存）。
- 11-07 前后同一服务能成功生成（单参考图、多参考图都成功过），所以不是"完全不能用"的架构问题。

## 待验证的假设（按怀疑程度排序，逐一给出证据：成立 / 不成立 / 无法确认）
1. **我们自己的 VM 唤醒抢占了页面连接**：`engine.renew_session_http(..., wake_vm=True)` 会 `POST /api/hatch/vm/wake`，每次带随机 `connect_attempt_id`；它在每个任务开页面前（`_renew_and_persist`、`ensure_page`）和每 15 分钟保活时都会被调用。页面自己的前端也会做 VM 连接/取 token。若 muse.ai 只认"最新一次连接尝试"，我们的 HTTP wake 会让页面拿 token 时 `no_match`。
   - 先读 muse.ai 网页前端公开的 JS（页面加载的 bundle），弄清 `/api/hatch/vm/wake`、`/api/hatch/token`、`/api/session` 的调用顺序和参数（`connect_attempt_id`、`vm_id`、相关 header / cookie 如 `hatch_vml`），写进报告。
   - 再做对照实验（见"安全规则"）：同一账号，A 组页面加载前不做 HTTP wake；B 组先做一次 HTTP wake 再加载页面；比较 token 结果。
2. **失败的页面丢掉了浏览器里轮换的 cookie**：`ensure_page` 用 `_apply_cookies` 注入 cookie，页面前端加载时会调 `/api/session` 并可能轮换 `hatch_sess`；但只有生成成功后 `_sync_cookies` 才回存，失败/崩溃时上下文直接关闭，新值丢失，服务里存的旧值可能已作废。核对代码路径和实际 Set-Cookie 行为。
3. **同一账号同时有多个浏览器上下文**（热备标签页 warm tab、任务页、额度页、保活）在抢同一台 VM。核对 `engine.py` 里的预热/复用逻辑与账号池互斥范围。
4. **muse.ai 侧原因**：对服务器出口 IP 不分配 VM、账号被风控、或用户浏览器正占用该账号的 VM。这一项只能记录证据，不能在代码里修；用户浏览器的情况由 Claude 另行和用户确认。

## 安全规则（必须遵守）
- **不发起任何生成**（不调 `/v1/images*`、`/v1/videos`、`/v1/chat*`），不消耗额度。
- 在生产容器里只做"只加载页面、不发提示词"的探测，用独立的浏览器上下文（参考 `Target.createBrowserContext` 的现有写法），用完立即 `Target.disposeBrowserContext`。**每个账号最多 3 次**探测，总共不超过 20 次。
- 任何直接请求 muse.ai `/api/session`、`/api/hatch/*` 的探测，或任何页面加载，**结束前都要把该上下文里的最新 cookie 写回服务**：用管理接口 `POST /admin/accounts/{aid}/cookies`（请求体格式读 `app.py`），或在容器里调用服务自己的代码路径。不能让探测造成 cookie 被作废而服务不知道。写回前后都不要打印 cookie 值。
- 只用 `.env.local` 里的变量；**不打印、不提交、不写日志**任何 Key、cookie、token、账号完整 ID（报告里账号用标签如 "217" 或 ID 前 6 位）。
- 不改 Railway 配置、环境变量，不部署，不 push `railway-v1.6.9`，不合并任何 PR。
- 生产容器访问：`railway ssh --service muse2api --environment production -- <cmd>`；脚本先在本地写好，用 base64 传进去，文件名不要和 Python 标准库重名（例如不要叫 `inspect.py`），用 `python -I` 运行。

## 要做
1. 按上面的假设逐一取证，写报告 `docs/investigations/2026-11-15-vm-auth-no-match.md`：时间线、每个假设的实验方法和原始结果（脱敏）、结论、建议。
2. 如果根因（或明显加重因素）在我们代码里（例如假设 1、2、3），在同一分支实现修复：
   - 改 `engine.py` / `app.py` / `store.py` 中相关最小范围；
   - 新增或更新测试（离线、本地模拟，不访问生产）；
   - 全量运行 `tests/test_*.py` 与 `node tests/test_admin_api_error_messages.mjs`，列出逐个结果。
3. 如果根因只在 muse.ai 侧，不要改代码；报告里写清证据和建议（例如需要用户关闭浏览器里的 muse.ai、换出口 IP、等待等）。

## 允许 / 禁止
允许：新建 `docs/investigations/2026-11-15-vm-auth-no-match.md`；为修复需要改 `engine.py`、`app.py`、`store.py`；新增/修改与修复直接相关的 `tests/*`。
禁止：`Dockerfile`、`requirements.txt`、`admin.html`、`media_janitor.py`、`config.py`、`AGENTS.md`、`docs/RAILWAY_DEPLOY.md`、其他 `docs/tasks/**`；不改 `MuseSessionUnavailable` 的 cookie 保存逻辑（`2fd83b8`），除非证据表明它就是问题，并在 PR 里先说明。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 报告覆盖 4 个假设，每个有实验方法、脱敏的原始结果和结论
- [ ] 探测次数在上限内，且每次探测后 cookie 都已写回（报告里列出写回记录：账号标签 + 时间 + HTTP 状态）
- [ ] 若有代码修复：测试覆盖修复点并全量通过；PR 说明修复依据对应报告里的哪条证据
- [ ] 全程未发起生成、未打印任何密钥 / cookie / token

## 交付
- `git add -A && git commit`，`git push -u origin fix/vm-no-match-root-cause`，`gh pr create --base railway-v1.6.9`
- PR 正文：结论摘要、根因证据、修复内容（如有）、测试结果、仍需用户/muse.ai 侧处理的事项
- **不要合并，不要 push `railway-v1.6.9`**
