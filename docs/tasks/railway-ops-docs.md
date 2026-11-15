# 任务书 02：编写 Railway 部署运维文档

分支：`docs/railway-ops` · 负责人：Codex · 审核：Claude
**前置**：`git pull` 后确认存在 `media_janitor.py`、`tests/test_session_cookie_rotation.py`、`tests/test_self_update_disabled.py`。不满足就停下说明。

## 目标
这个 fork 在上游基础上做了不少部署相关的改动（存储自动清理、禁用在线升级、cookie 轮换保存、崩溃页识别、上传控件等待、并发与超时配置），但没有文档。写一份中文运维文档，让维护者知道怎么更新、怎么配置、账号出问题怎么判断和处理。**所有内容必须以代码为准**，不确定的写"未确认"，不要编造。

## 要做
新建 `docs/RAILWAY_DEPLOY.md`，包含：
1. **部署方式**：Railway 从 `Yeadon8888/muse2api` 的 `railway-v1.6.9` 分支构建（Dockerfile），push 即部署；数据卷挂在 `/app/data`；为什么 Dockerfile 里没有 `VOLUME`。
2. **怎么更新**：只通过 PR 合入部署分支；为什么禁用了管理页的在线升级（它会覆盖代码并 `os._exit(0)`，Railway 上服务会 502）、`MUSE2API_ALLOW_SELF_UPDATE` 的作用；从上游 cherry-pick 的注意事项（上游 `8213b3d` 含静默自动升级与界面隐藏，不合并；`1795dab` 只取 engine 部分）。
3. **环境变量表**：从 `config.py`、`app.py`、`engine.py`、`media_janitor.py` 等读出每个 `MUSE2API_*` 变量的含义和默认值（用 `grep -n MUSE2API_` 核对）。重点写清：`MUSE2API_CONCURRENCY`、`MUSE2API_LOGIN_WAIT`、`MUSE2API_UPLOAD_WAIT`、`MUSE2API_MEDIA_HIGH_WATERMARK` / `LOW_WATERMARK` / `MIN_AGE_MINUTES` / `MAX_GB` / `JANITOR_INTERVAL`、`MUSE2API_ALLOW_SELF_UPDATE`、`MUSE2API_KEY`。
4. **管理接口速查**：`/admin/storage`、`/admin/storage/cleanup`、`/admin/status`、`/admin/tasks`（`full=1` 的区别）、`/admin/accounts` 等，读代码确认路径和行为。
5. **账号故障排查**：
   - 页面崩溃为 "Something went wrong"（`/api/hatch/token` 被拒）→ 账号被标记失效，需要用浏览器扩展重新导入**完整** cookie；
   - muse.ai 在 `/api/session` 响应里轮换 `hatch_sess` / `hatch_gw`，现在会被保存（说明以前每约 10 分钟失效的原因）；
   - "找不到上传控件"、"页面加载超时"、"提示词没有发出去" 各自的含义和处理；
   - 读日志的方法（`railway logs --service muse2api`）和要看的关键字。
6. **存储清理**：水位规则、保留时间、被删文件的链接会 404。
在 `README.md` **不要**改动（上游文件，避免以后冲突）。

## 允许 / 禁止
允许：新建 `docs/RAILWAY_DEPLOY.md`。
禁止：修改任何代码、测试、`README.md`、`AGENTS.md`、`docs/tasks/**`、`version.json`。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 文档里出现的每个环境变量、接口路径、默认值都能在代码里找到对应位置（PR 正文附一张"文档项 → 代码位置"的核对表）
- [ ] 没有编造的数字或行为；不确定的明确标注"未确认"
- [ ] 不包含任何密钥、cookie 值、API Key、账号 ID

## 自测
- `grep -n` 核对每一项；不运行服务、不访问生产

## 交付
- 自己 `git add -A && git commit`，`git push -u origin docs/railway-ops`，`gh pr create --base railway-v1.6.9`
- PR 正文：文档结构、核对表、未确认的项
- **不要合并，不要 push `railway-v1.6.9`**
