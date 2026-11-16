# 任务书 13：识别 muse.ai 视频额度上限，按账号冷却并自动换号

分支：`fix/video-quota-cooldown` · 负责人：Codex · 审核：Claude · PR base：`railway-v1.6.9`
**前置**：`git pull` 后确认 `railway-v1.6.9` 含 `6e9ba99`（工作区冷却/熔断，`store.py` 有冷却相关字段）。不满足就停下说明。

## 背景（2026-11-16 生产实测）
- 账号配上住宅出口 SOCKS5 代理后，工作区可分配、图片任务成功；但视频任务失败，模型回复文本（被当作 `MuseModelRefusalError`，错误"模型未生成媒体，仅返回文本"）：
  "这次没生成出来 — 撞到 24 小时视频上限了，按规则停下，没有重试。"
- 用户观察：免费账号每个大约 24 小时内只能生成 1 条视频。
- 现有逻辑：`MuseModelRefusalError` 不换号重试（见 `tests/test_refusal_rotation.py`），也不标记账号，账号池会继续把视频任务派给已到上限的账号。另有图片额度回复（例如 "You've reached your usage limit"）也走同一路径。

## 要做
1. 在 `engine.py` 识别"额度/上限"类回复（中英文，至少覆盖：`24 小时视频上限`、`视频上限`、`video limit`、`reached your usage limit`、`usage limit`、`额度用完/已用完`、`每日/24 小时` + `上限`；用可维护的正则列表），抛出新的异常（如 `MuseQuotaLimitError(MuseModelRefusalError 或 MuseGenerationError 的子类)`，携带 `kind`：video / image / any），与普通"模型拒绝"区分（普通拒绝仍不换号）。
2. `store.py` / `app.py`：账号收到额度上限后，按任务种类进入**额度冷却**（视频默认 24 小时，`MUSE2API_VIDEO_QUOTA_COOLDOWN_HOURS`；图片默认 24 小时，`MUSE2API_IMAGE_QUOTA_COOLDOWN_HOURS`）；若回复里能解析出重置时间则用它。冷却不改 `ok`，不提示重新导入 cookie。
3. 调度：选择账号时跳过对应种类处于额度冷却的账号（视频冷却不影响图片/对话）；当前任务遇到额度上限时**换一个还有该种类额度的账号重试**（受现有最大尝试次数约束）；所有账号都在该种类冷却时，立即失败并返回清晰信息："所有账号的 muse.ai 视频额度已用完（免费账号约每 24 小时 1 条），最早约 X 小时后恢复"，不打开页面、不请求 muse.ai。
4. `/admin/accounts` 返回每账号各种类额度冷却剩余秒数（供后续页面显示，本任务不改 `admin.html`）；增加管理接口清除某账号额度冷却（例如管理员确认已升级套餐）。
5. 测试（离线，不访问生产、不调用 muse.ai、不生成）：中英文上限文本识别；普通拒绝仍不换号；视频上限换号成功；全部冷却时快速失败且不调用 `engine.generate`；视频冷却不影响图片；冷却到期恢复；清除接口生效。全量运行 `tests/test_*.py` 与 node 测试。
6. 更新 `docs/RAILWAY_DEPLOY.md`：新配置项、额度冷却说明、"免费账号视频额度"运维建议。

## 允许 / 禁止
允许：`engine.py`、`app.py`、`store.py`、`config.py`、`docs/RAILWAY_DEPLOY.md`、新增/修改相关 `tests/*`。
禁止：`admin.html`、`Dockerfile`、`requirements.txt`、`media_janitor.py`；不改代理、cookie 作用域、工作区冷却/熔断的现有行为（只在其基础上并列增加额度冷却）。
必须改范围外的文件时，先停下说明。

## 验收
- [ ] 上述测试全部通过；全量测试通过（列出逐个结果）
- [ ] 所有账号视频冷却时，视频任务 1 秒内失败且无 muse.ai 请求；图片任务不受影响
- [ ] 错误信息不提示重新导入 cookie

## 交付
- `git add -A && git commit`，`git push -u origin fix/video-quota-cooldown`，`gh pr create --base railway-v1.6.9`
- **不要合并，不要 push `railway-v1.6.9`**
