# AGENTS.md — muse2api（Yeadon8888 fork，部署在 Railway）

## 分支与部署（最重要）
- `railway-v1.6.9` 是**生产部署分支**：push 到它会立刻触发 Railway 重新部署，并打断正在生成的任务。
- Agent 只在自己的功能分支上工作，用 PR 合入 `railway-v1.6.9`；**不要 push、不要合并 `railway-v1.6.9`**。合并由 Claude 审核后决定。
- 上游是 `czg86389-hub/muse2api`。只能逐个 cherry-pick 审过的提交。上游 `8213b3d`（静默自动升级：定时拉取上游 main 覆盖代码并重启，同时对界面隐藏）**禁止合并**；`1795dab` 只取了 engine.py 部分，账号严格轮询没有取。
- 在线升级接口默认禁用（`MUSE2API_ALLOW_SELF_UPDATE` 未设为 1 时返回 403），不要改掉这个保护。

## 代码结构
- `app.py` FastAPI 服务与管理接口；`engine.py` 通过 CDP 驱动 Chromium 操作 muse.ai；`store.py` 账号池与任务存储；`media_janitor.py` 按磁盘水位清理旧媒体；`admin.html` 管理页面（单文件）。
- 运行数据在 `/app/data`（Railway 数据卷）：`accounts.json` 含账号 cookie，属于密钥，绝不输出、提交或写进日志。

## 测试
- 测试是独立脚本，逐个运行：`python tests/<name>.py`（不是 pytest）。依赖：`pip install -r requirements.txt`。
- 需要真实 Chromium 的测试：设置 `MUSE2API_CHROMIUM` 为 Chrome 可执行文件路径，并让 `google-chrome` 在 PATH 上可用（macOS 可用一个 shell 包装脚本 exec Chrome）。
- `tests/test_admin_api_error_messages.mjs` 用 `node` 运行。
- 提交前把所有 `tests/test_*.py` 跑一遍，PR 里写清通过/失败数量和失败原因。

## 约定
- 不发起任何真实的 muse.ai 生成或付费调用；不访问生产服务（`muse2api-production.up.railway.app`）的写接口。
- 修改范围以任务书为准；需要改范围外的文件时先停下说明。
- 提交说明写清"为什么"；代码注释与界面文案用中文，和现有风格一致。
