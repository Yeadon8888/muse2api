# 2026-11-16 CVM 密钥浏览器 IndexedDB 实验

## 结论摘要

**结论：无法确认“CVM 密钥只存在于创建它的浏览器 IndexedDB”。**

实验账号 238 的全新隔离 BrowserContext 在 `https://muse.ai/thread/new` 观察 60 秒后，没有发出 `/api/session`、wake、`/api/hatch/token` 或 CVM provisioning / replacement / credentials 相关请求；页面未崩溃，IndexedDB 数据库列表为空。由于 X1 没有取得 token HTTP 200，按任务书停止，没有执行 X2/X3，也没有读取或导出任何 IndexedDB 记录内容。

这个结果既不能证明浏览器 IndexedDB 中存在恢复密钥，也不能证明复制该状态可以恢复 token。更直接的事实是，本次页面加载没有进入可供比较的 CVM token 流程。

## 安全边界与前置检查

- 只使用标签 238、ID 前缀 `ad3998` 的实验账号；完整账号 ID 未输出或写入报告。
- 实验前确认前缀唯一匹配、标签正确、`enabled=false`、`use_count=0`、cookie 存在，且导入时保活留下 `unavailable` 标记。
- Railway CLI 已成功链接指定 project、production 环境与 `muse2api` 服务。
- 脚本以 base64 传入生产容器，使用不与标准库重名的 `/tmp/cvm_key_probe_238.py`，通过 `python -I` 执行；结束后确认脚本已删除。
- 只加载页面，没有填写或发送提示词，没有调用任何 `/v1/*` 生成接口，没有启用账号，没有更改 Railway 配置或部署代码。
- 探测只保留允许的状态码、错误分类、字段名、数据库名和记录条数；没有打印、记录或写盘 cookie、token、Key、IndexedDB 记录内容、完整账号 ID、VM 完整 ID或地址。

## 方法

1. 在容器内启动一次性 headless Chromium，并创建全新隔离 BrowserContext A。
2. 从 `/app/data/accounts.json` 在内存中按 ID 前缀匹配账号，注入其 cookie，然后导航到 `https://muse.ai/thread/new`。
3. 在页面脚本执行前安装脱敏的 fetch/XHR 观察器，仅记录：
   - `/api/session` 的 HTTP 状态、`status`、`kind`、顶层字段名，以及 VM 字段是否存在和字段名；
   - wake、`/api/hatch/token` 和 CVM 相关路径的路径与 HTTP 状态；
   - token 响应的 HTTP 状态与 `code`，不保留 token 值。
4. 观察 60 秒后，通过 IndexedDB API 列出数据库名；仅对 `hatch-cvm-*` 数据库逐 object store 执行 `count()`，不读取记录内容。
5. 在销毁 A 前通过 CDP 读取最新 cookie，并调用本机管理接口 `POST /admin/accounts/{aid}/cookies` 回写。
6. X1 未取得 token HTTP 200，因此按任务书停止，没有执行 X2/X3。

首次启动探测器时，Chromium 在导航前拒绝了一个不适用于显式 Domain 的 cookie，页面加载计数为 0。随后采用仓库现有引擎相同的逐 cookie 容错方式重新执行；下文只把实际导航到 muse.ai 的第二次执行计为 X1。

## 脱敏结果

### X1：新上下文 A

| 项目 | 结果 |
|---|---|
| 页面加载次数 | 1 |
| 观察窗口 | 60 秒 |
| 页面崩溃 | 否 |
| 页面 JS error / unhandled rejection 计数 | 0 / 0 |
| `/api/session` | 未观察到请求 |
| VM 描述 | 无 session 响应可检查 |
| wake | 未观察到请求 |
| `/api/hatch/token` | 未观察到请求 |
| provisioning / replacement / credentials 相关接口 | 未观察到请求 |
| IndexedDB 数据库名列表 | 空 |
| `hatch-cvm-*` object store 记录条数 | 无此类数据库 |
| cookie 回写 | HTTP 200 |

实验后的独立只读复核确认：账号仍为 `enabled=false`、`use_count=0`，实验脚本已删除。cookie 回写接口会更新账号备注，因此导入时的 `unavailable` 备注不再适合作为实验后的持续断言；这不影响实验前门禁或 X1 观察结果。

### X2 / X3

未执行。任务书要求只有 X1 取得 token HTTP 200 时才导出 A 的 `hatch-cvm-*` 记录并继续对照；本次没有成功 token 基线，也没有可导出的 `hatch-cvm-*` 数据库。继续加载页面既不满足实验分支，也会无意义消耗账号预算。

## 结论与风险

本次只能得出“无法确认”：

1. 没有 token 200 成功基线，无法比较空白上下文与恢复 IndexedDB 后的差异。
2. 没有出现 `hatch_vm_auth_no_match`，不能把失败归因于浏览器缺少 CVM 密钥。
3. IndexedDB 为空只说明本次上下文在观察窗口内没有建立这些数据库，不能说明用户原浏览器是否持有 CVM 恢复状态。
4. `/api/session` 也未在页面侧出现；因此无法判断导入时的 `status=unavailable` 是否在本次页面生命周期内发生变化。

如果后续账号能在同一生产出口稳定取得 token 200，应沿用本任务的 A/B/C 对照，并保持最多 4 次加载：X1 A、X2 B、X3 C 的同源引导页与应用页。只有当“空白 B 失败、恢复 A 的 `hatch-cvm-*` 后 C 成功”可重复出现时，才有证据考虑每账号持久化 BrowserContext / 用户数据目录，或让用户浏览器在安全通道中连同 IndexedDB 一起导出；在此之前不建议扩大凭据持久化范围。

## 离线自测

- `python tests/test_*.py`：39/39 个独立脚本通过，0 失败。
- `node tests/test_admin_api_error_messages.mjs`：通过。
- Python 测试使用 `/tmp` 虚拟环境安装现有 `requirements.txt`；需要真实 Chromium 的测试通过临时 `google-chrome` 包装器调用本机 Google Chrome。没有修改项目依赖。
