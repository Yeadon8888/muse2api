# 任务书 11：网上调研"每个账号只能成功一次，之后 hatch_vm_auth_no_match"——经验与可行修复

分支：`docs/one-use-research` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：无。另有并行任务 `docs/egress-headless-experiment`（本机对照实验）在跑；本任务**只做网上调研和代码阅读、只写报告**，不访问我们的生产服务，不调用 muse.ai 的任何 `/api/*`，不改代码。

## 用户最新观察（关键）
导入一批新账号后，**每个账号都能成功生成一条视频，第二条开始就失败**（`/api/hatch/token` 401 `hatch_vm_auth_no_match`，页面 "Something went wrong"）。同一账号在用户自己的浏览器里一直正常。

## 我们服务的做法
每个任务用 CDP `Target.createBrowserContext` 新建隐身上下文，只注入 cookie（每个单份，`.muse.ai`），任务结束 `Target.disposeBrowserContext` 销毁——IndexedDB、localStorage、Service Worker、Cache Storage 全部丢弃。
muse.ai 前端存在 IndexedDB `hatch-cvm-credentials` / `hatch-cvm-provisioning` / `hatch-cvm-replacement`（按 `ownerId` / `sessionBindingId` / `envId` 保存机密 VM 恢复密钥与状态），以及 localStorage `hatch:debug:device-id`、sessionStorage `hatch_saved_account_registered`。详见 `docs/investigations/2026-11-16-vm-client-binding.md`、`2026-11-16-cvm-key-experiment.md`、`2026-11-15-vm-no-match-web-research.md`。

**当前首要假设**：首次使用时 muse.ai 为账号创建/绑定机密 VM，凭据只存于该浏览器上下文的 IndexedDB；上下文销毁后凭据丢失，之后新上下文无法匹配 VM。

## 要做
1. 搜索（记录链接、日期、要点；引用每处不超过 2 句）：
   - 上次调研没覆盖的关键词：`hatch-cvm-credentials`、`hatch-cvm-provisioning`、`hatch-cvm-replacement`、`sessionBindingId`、`session_binding_id`、`confidential vm muse`、`muse.ai CVM`、`muse.ai "only works once"`、`muse2api 只能用一次`、`muse 反代 第二次 失败`、`muse.ai persistent context`、`muse.ai userDataDir`；
   - GitHub 代码搜索：哪些项目操作 muse.ai 时使用**持久浏览器资料**（Playwright `launchPersistentContext`、Puppeteer `userDataDir`、Chrome `--user-data-dir` 每账号一份），哪些导出 / 导入 IndexedDB；
   - linux.do、V2EX、Reddit、X、muse.ai / Meta 官方关于 "confidential VM"、"workspace"、"device"、"one device" 的说明；
   - 上游 `czg86389-hub/muse2api` 最新 issues / commits（11-16 之后）是否有人报告同样现象或已修复。
2. 读代码对比：其他项目在"同一账号多次任务"之间是否保留浏览器存储；如何避免多个进程/上下文同时用同一账号资料；是否对每账号串行化。
3. 技术方案评估（结合我们的 `engine.py` 结构写具体做法）：
   - A：每账号一个持久 Chromium user-data-dir（独立进程或按需启动），任务复用；
   - B：保留现有单 Chromium，但每账号维持一个长期 BrowserContext 不销毁（注意隐身上下文进程重启后仍会丢）；
   - C：任务结束前导出该账号上下文的 IndexedDB（`hatch-cvm-*`）与相关 localStorage，下次新上下文在应用脚本运行前写回；
   - D：其他资料里出现的做法。
   每个方案写：是否能跨服务重启保存、内存/磁盘开销（Railway 8GB 内存、数据卷约 4.6GB）、并发与互斥、实现复杂度、安全性（这些数据是凭据，如何存储与清理）、可验证性。给出推荐方案与验证步骤（例如"新导入账号做第 1、2、3 条视频"的验收）。

## 安全与范围
- 只读公开网页、GitHub、搜索结果；不访问生产、不调用 muse.ai `/api/*`、不登录任何账号。
- 只新建 `docs/investigations/2026-11-16-one-use-research.md`；不改代码、测试或其他文档。

## 交付
- `git add -A && git commit`，`git push -u origin docs/one-use-research`，`gh pr create --base railway-v1.6.9`
- PR 正文：主要发现、推荐方案、验收步骤
- **不要合并，不要 push `railway-v1.6.9`**
