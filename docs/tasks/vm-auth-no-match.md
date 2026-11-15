# 任务书 03：区分"工作区不可用"和"cookie 失效"，不要误判账号

分支：`fix/vm-auth-no-match` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：`git pull` 后确认 `engine.py` 里有 `CRASH_PAGE_MESSAGE`、`_is_crash_page`、`MuseSessionUnavailable`，`tests/test_upload_control_wait.py` 存在。不满足就停下说明。

## 背景（线上实测证据，2026-11-15）
- 线上一小时内 40 条视频任务全部失败，37 条是 `CRASH_PAGE_MESSAGE`（页面崩溃为 Something went wrong），每次失败都把账号标记为 `ok=False` 并提示"请重新导入完整 cookie"。
- 刚导入、导入测试通过的账号，2 分钟后同样崩溃。
- 在容器里只加载页面（不发送提示词）抓到：页面在"有输入框"和"崩溃"之间反复切换，`POST /api/hatch/token` 每次都返回
  `HTTP 401 {"error": "Gateway VM auth token unavailable", "code": "hatch_vm_auth_no_match"}`。
- 同时 `GET /api/session` 返回 `HTTP 200 {"status": "unavailable", "vm_resolution_issue": {"kind": "retryable"}}`。
- 结论：这是 muse.ai 暂时没有给账号分配/匹配云端工作区 VM，**不是 cookie 失效**。现在的代码（`c15c6f1` 引入）把所有崩溃页都当成 `MuseAuthError`，误把账号标为失效、误导用户反复重新导入。

## 目标
崩溃页按 `/api/hatch/token` 的真实错误分类：
- `code == "hatch_vm_auth_no_match"`（或 error 含 `VM auth token unavailable`）→ **工作区暂不可用**：抛 `MuseGenerationError` 的子类（例如 `MuseWorkspaceUnavailable`），不调用 `store.mark(..., False)`，不提示重新导入；交给现有的换号重试逻辑。
- 其他明确的认证失败（例如 401 但 code 指向登录/会话失效，或页面出现登录界面）→ 维持 `MuseAuthError`。
- 拿不到 token 接口的结果时 → 保守处理：按"工作区暂不可用/未确认"处理，**不要**标记账号失效。

## 要做
1. 在 `engine.py` 打开页面前（`Page.addScriptToEvaluateOnNewDocument`，在 `_open_page` 或 `ensure_page` 导航前）注入一个只读的 fetch/XHR 钩子，记录最近一次 `/api/hatch/token` 响应的 HTTP 状态和 JSON 里的 `code` / `error`（只记录这两个字段，**绝不记录 token 本身**）到 `window` 上的一个变量。
2. 新增分类函数，读取该变量判断崩溃原因；在 `ensure_page`（稳定性检查和失败分支）、`_wait_ws_ready(fail_on_crash=True)` 的调用处、`_wait_file_input` 里，用它决定抛 `MuseAuthError` 还是工作区不可用异常。
3. 工作区不可用的错误信息写清楚："muse.ai 暂时无法为该账号分配云端工作区（hatch_vm_auth_no_match），不是 cookie 失效，无需重新导入；常见原因：同一账号正在别处（例如浏览器里打开的 muse.ai）占用工作区，或 muse.ai 暂时无法分配"。
4. 确认 `app.py` 的生成重试循环对这个新异常走"换号重试、不标记失效"的分支；如需改 `app.py`，只改异常分类相关的几行，并在 PR 说明。
5. 测试：新增 `tests/test_vm_auth_classification.py`，用真实 Chromium（参考 `tests/test_upload_control_wait.py` 的写法）在本地页面上模拟：
   - `/api/hatch/token` 返回 401 + `hatch_vm_auth_no_match` 且页面崩溃 → 抛工作区不可用异常，不是 `MuseAuthError`；
   - 返回其他 401 code 且页面崩溃 → `MuseAuthError`；
   - 没有 token 响应记录但页面崩溃 → 不是 `MuseAuthError`；
   - 钩子记录的内容里不包含 token 字段值。
   同时更新 `tests/test_upload_control_wait.py` 中"崩溃页 → MuseAuthError"的断言，使其符合新规则（保留"3 秒内快速失败"的检查）。
6. 全量运行 `tests/test_*.py` 和 `node tests/test_admin_api_error_messages.mjs`。

## 允许 / 禁止
允许：`engine.py`、`app.py`（仅异常分类与重试分支相关行）、`tests/test_vm_auth_classification.py`（新建）、`tests/test_upload_control_wait.py`。
禁止：`store.py`、`media_janitor.py`、`admin.html`、`config.py`、`Dockerfile`、`requirements.txt`、`docs/**`（本任务书除外不需要改）、其他测试文件。不要修改 `MuseSessionUnavailable` / cookie 轮换保存逻辑（`2fd83b8`）。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 上面 5 中的四个场景测试通过
- [ ] `hatch_vm_auth_no_match` 崩溃不会把账号标为 `ok=False`，错误信息不再提示重新导入（PR 里贴出相关代码路径说明）
- [ ] 钩子不记录、不打印 token 或 cookie 值
- [ ] 全量测试通过（列出逐个结果）；`test_admin_layout`、`test_vm_wait` 若在本分支基线就失败，写明是已知问题（PR #2 修复中）

## 自测
- 依赖：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Chromium：`export MUSE2API_CHROMIUM="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`，PATH 上放 `google-chrome` 包装脚本
- **不访问生产服务，不调用 muse.ai，不发起任何生成**；所有场景用本地页面模拟

## 交付
- 自己 `git add -A && git commit`，`git push -u origin fix/vm-auth-no-match`，`gh pr create --base railway-v1.6.9`
- PR 正文：分类规则、改了哪些函数、测试结果、已知限制
- **不要合并，不要 push `railway-v1.6.9`**（push 它会直接部署生产）
