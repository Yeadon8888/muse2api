# 任务书 08：验证"账号用过一次后，新浏览器环境就匹配不上工作机"，并在证实后修复

分支：`fix/vm-client-binding` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：本目录有 `.env.local`（`MUSE2API_PROD_URL`、`MUSE2API_ADMIN_KEY`，只用变量名引用，绝不打印值）；`railway whoami` 已登录；`railway link -p 05776d1b-86a1-4217-b5eb-6efaa5f2f54d -e production -s muse2api` 成功；`railway-v1.6.9` 含 `14b6327`（停止外部 wake、页面关闭前回存 cookie）。另有 PR #6（退避/冷却，未合并）——本任务不要依赖它，也不要改它改过的逻辑。不满足就停下说明。

## 用户观察与已知证据
- 用户：新导入的账号第一次任务能成功（00:16:59 账号 238 / `db44fb` 生成图片成功，耗时 31.5 秒）；之后同一账号上的任务都在 2–3 秒内以 `hatch_vm_auth_no_match` 失败。管理页单独点"测试"有时成功、有时也报同样错误。
- 服务每个任务都新建一个隐身 `BrowserContext`（`Target.createBrowserContext`），任务结束 `close_current_page()` 关闭；新上下文的 localStorage / sessionStorage 为空，只注入 cookie。该机制自 v1.6.0 就存在，11-07 时同账号连续成功过，所以可能是 muse.ai 近期改了工作机绑定规则。
- 调研：muse.ai 前端 wake 请求带 `connect_attempt_id`、`wake_trigger`、`open_id`、`away_ms`；`/api/hatch/token` 提交 `vmAddress`/`vmName`。`open_id` 等可能保存在浏览器存储中（未确认）。
- 详见 `docs/investigations/2026-11-15-vm-auth-no-match.md` 与 `docs/investigations/2026-11-15-vm-no-match-web-research.md`。

## 要做
1. **静态分析**（不访问生产）：从 muse.ai 公开前端资源（调查报告里已识别的 chunk，可无凭据下载）找出 `open_id`、`connect_attempt_id`、VM 客户端标识的来源和存储位置（localStorage / sessionStorage / IndexedDB / cookie / 内存），以及 token 匹配依赖哪些字段。
2. **对照实验**（生产容器内，只加载页面、不发提示词）。用当前能拿到工作机的账号（先用一次页面加载确认；若所有启用账号都拿不到，就停下汇报）：
   - E1：上下文 A 加载页面直到 `/api/hatch/token` 成功（或失败）→ 记录前端存储里与 VM/连接相关的键名（只记录键名和是否存在，不记录值，除非确认值不是凭据）→ 关闭 A → 立即新建 B 加载 → 记录 token 结果。
   - E2：与 E1 相同，但把 A 的相关存储（localStorage/sessionStorage 中与 hatch/vm/open_id 相关的键）复制到 B 再加载，比较结果。
   - E3：A 保持打开，新建 B 加载 → token 结果（判断是否同时只允许一个客户端）。
   - E4：关闭 A 后等待 5 分钟再新建 B → token 结果（判断绑定是否超时释放）。
   - 每次实验后都按下面的安全规则回存 cookie。
3. **结论与修复**：
   - 若证实"新上下文缺少存储标识导致 no-match"（E2 成功而 E1 失败）：在 `engine.py` 里为每个账号持久化这些存储键（存到账号数据里或 `/app/data` 下按账号的小文件，不含 cookie 值），新上下文打开前通过 `Page.addScriptToEvaluateOnNewDocument` 或 `DOMStorage` 写回；或改为每个账号复用一个持久的 BrowserContext（选更简单可靠的方案，在 PR 说明取舍）。
   - 若证实"同一时间只允许一个客户端，关闭后需要等待释放"（E3 失败、E4 成功）：把等待时长写进报告，并实现：同账号连续任务优先复用同一上下文/页面，或在关闭后按实测间隔冷却该账号（与 PR #6 的冷却兼容，不要重复造冷却机制——如需配合，在 PR 里写明合并顺序）。
   - 若都不成立：只写报告，不改代码。
   - 离线测试覆盖修复点；全量运行 `tests/test_*.py` 与 node 测试。
4. 报告写到 `docs/investigations/2026-11-16-vm-client-binding.md`：实验方法、脱敏结果、结论。

## 安全规则（必须遵守）
- **不发起任何生成**（不调 `/v1/images*`、`/v1/videos`、`/v1/chat*`）。
- 只在生产容器做"只加载页面"的探测，用独立上下文，用完 `Target.disposeBrowserContext`；**总探测次数不超过 12 次**，单账号不超过 6 次。
- 每次页面加载结束、销毁上下文前，读取该上下文最新 cookie 并通过管理接口 `POST /admin/accounts/{aid}/cookies` 写回（格式读 `app.py`）；不打印 cookie / token / Key / 完整账号 ID（报告里用标签或 ID 前 6 位）。复制到 B 的存储内容同样不打印值。
- 不改 Railway 配置或环境变量，不部署，不 push `railway-v1.6.9`，不合并 PR。
- 脚本用 base64 传入容器，文件名不要与 Python 标准库重名，用 `python -I` 运行。

## 允许 / 禁止
允许：新建 `docs/investigations/2026-11-16-vm-client-binding.md`；为修复改 `engine.py`、`app.py`（最小范围）；新增/修改相关 `tests/*`。
禁止：`store.py`、`config.py`（PR #6 正在改，避免冲突；确需改先停下说明）、`admin.html`、`Dockerfile`、`requirements.txt`、`media_janitor.py`、其他 docs。不要恢复外部 wake，不要改 cookie 轮换保存逻辑。

## 验收
- [ ] E1–E4 都有脱敏结果（或写明为什么做不了）；探测次数与 cookie 回写记录在报告里
- [ ] 结论明确：成立 / 不成立 / 无法确认，并说明依据
- [ ] 若改代码：离线测试覆盖、全量测试通过（列出逐个结果）
- [ ] 全程未发起生成、未输出任何凭据

## 交付
- `git add -A && git commit`，`git push -u origin fix/vm-client-binding`，`gh pr create --base railway-v1.6.9`
- PR 正文：实验结论、修复方案与取舍、测试结果、与 PR #6 的合并顺序建议
- **不要合并，不要 push `railway-v1.6.9`**
