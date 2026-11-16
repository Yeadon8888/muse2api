# 任务书 09：用全新账号验证"机密工作机（CVM）密钥只存在浏览器 IndexedDB"——只做实验、只写报告

分支：`docs/cvm-key-experiment` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：本目录有 `.env.local`（`MUSE2API_PROD_URL`、`MUSE2API_ADMIN_KEY`，只用变量名）；`railway link -p 05776d1b-86a1-4217-b5eb-6efaa5f2f54d -e production -s muse2api` 成功。实验账号：标签 **238**，ID 前缀 **`ad3998`**（完整 ID 从 `/app/data/accounts.json` 按前缀匹配，不要打印），**已被停用（enabled=false），服务不会使用它**；`use_count=0`，从未在服务器上加载过页面。导入时保活查询 `/api/session` 已返回 `status=unavailable`。不满足就停下说明。不要启用或修改这个账号的其他设置。

## 背景
见 `docs/investigations/2026-11-16-vm-client-binding.md`：页面有 IndexedDB `hatch-cvm-credentials` / `hatch-cvm-provisioning` / `hatch-cvm-replacement`，按 `ownerId` / `sessionBindingId` / `envId` 保存机密 VM 的恢复密钥与状态；`session_binding_id` 来自认证 / session 响应。
假设：CVM 密钥只保存在**创建它的浏览器**的 IndexedDB 里；服务器每个任务新建隐身 BrowserContext，没有密钥，于是 `/api/hatch/token` 返回 401 `hatch_vm_auth_no_match`。用户导出 cookie 时在自己浏览器登录过 muse.ai，可能已在其浏览器中创建了 CVM。

## 实验（生产容器内，只加载页面，不发提示词）
- X1：新建上下文 A，注入该账号 cookie，加载 `https://muse.ai/thread/new`，观察 60 秒：记录 `/api/session` 的 `status`、是否有 VM 描述（只记字段名 / 是否存在）、wake 请求与状态、`/api/hatch/token` 的状态与 `code`；页面是否崩溃；IndexedDB 数据库名列表，以及 `hatch-cvm-*` 各 object store 的**记录条数**（只计数，不读取 / 打印内容）；与 CVM 相关的前端请求路径与状态（例如 provisioning / replacement / credentials 相关接口，只记路径和状态码）。
- 若 X1 拿到 token 200：在**容器进程内存中**导出 A 的 `hatch-cvm-*` IndexedDB 记录（绝不打印、不写磁盘、不出容器），关闭 A；
  - X2：新建空白上下文 B 加载页面 → 记录 token 结果；
  - X3：新建上下文 C：先打开同源的非应用页面（例如 `https://muse.ai/robots.txt`），用 `Runtime.evaluate` 把 A 的 `hatch-cvm-*` 记录写入同名 IndexedDB（结构与键路径照搬），再导航到 `/thread/new` → 记录 token 结果。
- 若 X1 就失败：再观察页面是否走了 CVM provisioning / replacement 流程以及其结果（路径 + 状态码），然后停止，不做 X2/X3。
- 每个上下文结束、销毁前：读取最新 cookie，通过 `POST /admin/accounts/{aid}/cookies` 写回（格式读 `app.py`），记录写回 HTTP 状态。
- **本账号最多 4 次页面加载**；不使用其他账号。

## 安全规则
- 不发起任何生成；不调 `/v1/*` 生成接口；不启用账号。
- 不打印 / 不提交 / 不写日志：Key、cookie、token、IndexedDB 记录内容、完整账号 ID、VM 完整 ID / 地址。报告只写字段名、计数、状态码。
- 脚本 base64 传入容器，文件名不与 Python 标准库重名，`python -I` 运行；结束后删除容器内脚本文件。
- 不改代码、不改 Railway 配置、不部署、不 push `railway-v1.6.9`、不合并。

## 交付
- 新建 `docs/investigations/2026-11-16-cvm-key-experiment.md`：方法、每次加载的脱敏结果、cookie 写回记录、结论（假设成立 / 不成立 / 无法确认）以及若成立的修复建议（例如每账号持久化 BrowserContext / 用户数据目录，或从用户浏览器连同 IndexedDB 一起导出）。
- `git add -A && git commit`，`git push -u origin docs/cvm-key-experiment`，`gh pr create --base railway-v1.6.9`
- **不要合并，不要 push `railway-v1.6.9`**
