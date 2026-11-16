# 任务书 10：本机对照实验——区分"服务器出口 IP/地区" vs "无头浏览器" vs "绑定在用户浏览器"

分支：`docs/egress-headless-experiment` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：本目录有 `.env.local`（`MUSE2API_PROD_URL`、`MUSE2API_ADMIN_KEY`）；`railway link -p 05776d1b-86a1-4217-b5eb-6efaa5f2f54d -e production -s muse2api` 成功；本机有 `/Applications/Google Chrome.app`；`railway-v1.6.9` 含 `8f9fa17`（cookie 单份注入）。不满足就停下说明。

## 现状
- 2026-11-16 14:24 部署 `8f9fa17` 后，生产提交 1 个图片任务，200 秒后仍失败：`hatch_vm_auth_no_match`。服务器上页面流程为 `/api/session` 200 → `/api/hatch/vm/wake` 200 → `/api/hatch/token` 401。
- 用户说：同一账号在**自己的浏览器**里手动使用完全正常，且已关闭浏览器里的 muse.ai 标签页。
- 已排除：外部 wake 干扰（已停用）、cookie 丢弃（已保存轮换）、重复 cookie（已修复）、页面未进入工作区流程。

## 实验（在用户本机运行，不在生产容器里加载页面）
账号：从当前启用账号中选 **1 个**（优先标签 217 或 237；在报告里只写标签和 ID 前 6 位）。**实验前用 `PATCH /admin/accounts/{aid}` 把它设为 `enabled=false`，实验结束恢复为原值**，避免生产任务同时使用它。
cookie 获取：通过 `railway ssh` 在容器里读取该账号 cookie，**只经 stdout 管道读入本机 Python 进程内存**（不写本机磁盘、不打印、不进日志）；或在本机直接调用服务代码已有的接口（如有导出接口，读 `app.py` 确认）——不得把 cookie 写入任何文件。
每次加载：用本机 Chrome 新建临时 user-data-dir（实验后删除），按 `engine._apply_cookies` 的**新**规则注入（每个 cookie 单份，`__Host-` host-only，其余 `.muse.ai`），加载 `https://muse.ai/thread/new`，浏览器级 CDP（全 target）记录 `/api/session` 状态与 `status`、wake 状态、`/api/hatch/token` 状态与 `code`（只读取 code 字段，不读 token）、页面最终是否崩溃；结束前读取最新 cookie 并通过 `POST /admin/accounts/{aid}/cookies` 写回生产，记录 HTTP 状态；然后关闭 Chrome、删除临时目录。

- L1：本机 **headless**（`--headless=new`，参数尽量与 `engine.py` 启动 Chromium 的参数一致）。
- L2：本机 **非 headless**（正常窗口，可最小化），其余同 L1。
- 若 L1、L2 都失败：L3 可选——在用户允许前**不要**读取用户日常 Chrome 资料；只在报告中建议下一步。
- 总加载次数不超过 3 次；每次间隔至少 60 秒。

## 结论判定
- L1 成功 → 根因是服务器出口（IP/地区/机房）。报告给出建议：为账号配置住宅/本地出口代理（服务已支持每账号 HTTP/SOCKS5 代理，读 `proxy.py` / `app.py` 写清配置方式）。
- L1 失败、L2 成功 → 无头/指纹识别。报告列出 headless 与 headful 的差异（UA、`navigator.webdriver`、Client Hints 等，用页面 JS 读取的非敏感值），给出服务器可行的修改方案。
- 都失败 → 很可能是工作机绑定在用户日常浏览器（如 CVM IndexedDB 密钥）；写出需要用户配合的下一步。

## 安全规则
- 不发起任何生成；不调用 `/v1/*` 生成接口。
- 不打印、不写盘、不提交任何 cookie、token、Key、IndexedDB 内容、完整账号 ID、VM 地址。
- 实验结束确认账号 `enabled` 恢复原值、临时 user-data-dir 已删除、本机没有残留含 cookie 的文件。
- 不改代码、不改 Railway 配置、不部署、不 push `railway-v1.6.9`、不合并。

## 交付
- 新建 `docs/investigations/2026-11-16-egress-headless-experiment.md`：方法、L1/L2(/L3) 脱敏结果、cookie 写回记录、结论与建议。
- `git add -A && git commit`，`git push -u origin docs/egress-headless-experiment`，`gh pr create --base railway-v1.6.9`
- **不要合并，不要 push `railway-v1.6.9`**
