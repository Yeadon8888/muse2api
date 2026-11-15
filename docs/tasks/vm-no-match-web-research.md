# 任务书 06：网上调研 muse.ai "hatch_vm_auth_no_match / 工作区无法分配" 的经验与其他项目做法

分支：`docs/vm-no-match-web-research` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：无。另有一个并行任务（`fix/vm-no-match-root-cause`）在线上做实验并可能改代码；本任务**只做网上调研、只写报告**，不要碰代码，避免冲突。

## 背景
我们部署在 Railway 上的 muse2api（fork 自 czg86389-hub/muse2api）从 2026-11-15 晚起所有账号都失败：
- 页面里 `POST /api/hatch/token` → `401 {"error":"Gateway VM auth token unavailable","code":"hatch_vm_auth_no_match"}`，页面崩溃为 "Something went wrong"；
- `GET /api/session` → `200 {"status":"unavailable","vm_resolution_issue":{"kind":"retryable"}}`，并常常轮换 `hatch_sess` / `hatch_gw`；
- 用户已关闭浏览器里所有该账号的 muse.ai 页面，仍然失败；
- 我们的代码在开页面前和每 15 分钟保活时会 `POST https://muse.ai/api/hatch/vm/wake`（带随机 `connect_attempt_id`、`vm_id`），怀疑与页面自身的连接冲突（另一任务在验证）。

## 要做
1. 搜索并阅读（记录链接、日期、要点；引用原文每处不超过 2 句）：
   - `czg86389-hub/muse2api` 的 issues（open 和 closed）、PR、讨论、提交说明里与 `hatch_vm`、`hatch/token`、`vm/wake`、`unavailable`、`Something went wrong`、"工作区"、"VM"、"Connecting"、"会话" 相关的内容；
   - 其他 Muse 反代 / 网关项目：`www222fff/muse2api`、`bynne2602/muse2api`、`sewall2025/muse2api`、`KinX-ai/muse2api`、`linuxing3/muse2api`、`belfaranet-debug/muse2api`、`lvluu/museai`、`liemgumball/museai`、`d4ncboz/museai`，以及用 GitHub 代码搜索找到的其他项目（关键词：`hatch_vm_auth_no_match`、`api/hatch/token`、`api/hatch/vm/wake`、`connect_attempt_id`、`vm_resolution_issue`、`hatch_vml`、`hatch_sess muse.ai`）；
   - 社区帖子：linux.do、V2EX、Reddit、X 等（关键词同上，以及 "muse.ai 反代"、"muse2api 工作区"、"muse.ai Something went wrong"、"muse.ai VM"）；
   - 若能找到 muse.ai 官方的状态页、更新公告、免费额度 / 工作区 / VM 限制说明，也记录。
2. 对每个找到的项目，读代码说明：它们怎么处理会话续签、VM 唤醒（是否调用 `vm/wake`、用什么 `connect_attempt_id`、是否等待 `RUNNING`）、取 token、并发 / 多标签页、cookie 回存；与我们的 `engine.py`（`renew_session_http`、`ensure_page`、预热/保活逻辑）做对比，列出差异。
3. 汇总：已知的触发原因、别人验证过的解决办法、可以直接借鉴的代码做法（标明来源文件和行号/提交）、仍然未知的点。

## 安全与范围
- **不访问我们的生产服务**，不调用 muse.ai 的任何 `/api/*` 接口，不登录任何账号；只读公开网页、GitHub 和搜索结果。
- 不复制大段受版权保护的文字；代码引用只摘必要片段并注明来源与许可证。
- 只新建 `docs/investigations/2026-11-15-vm-no-match-web-research.md`；**不要修改任何代码、测试或其他文档**。

## 验收
- [ ] 报告列出搜索过的来源和关键词（包括没有结果的），每条结论都有链接
- [ ] 至少覆盖上面列出的项目；每个项目写清是否涉及 VM 唤醒 / token 处理，以及与我们代码的差异
- [ ] 结尾给出"可借鉴的修复方案"清单，按可信度排序，并标注证据强弱
- [ ] 不包含任何密钥、cookie、账号信息

## 交付
- `git add -A && git commit`，`git push -u origin docs/vm-no-match-web-research`，`gh pr create --base railway-v1.6.9`
- PR 正文：主要发现摘要 + 报告路径
- **不要合并，不要 push `railway-v1.6.9`**
