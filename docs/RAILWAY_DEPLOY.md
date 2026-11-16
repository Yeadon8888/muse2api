# Railway 部署与运维

本文只描述 `Yeadon8888/muse2api` 的 `railway-v1.6.9` 部署。配置、接口和故障判断均以当前分支代码为准。

## 部署方式

Railway 从 `Yeadon8888/muse2api` 的 `railway-v1.6.9` 分支读取 `Dockerfile` 构建。该分支是生产部署分支，push 后会立即重新部署并中断正在执行的生成任务，因此只能通过功能分支提交 PR，审核后再合入；不要直接 push 或在运行任务期间安排部署。

Railway 数据卷挂载到 `/app/data`。镜像把 `MUSE2API_HOME` 设为 `/app`，程序因而在数据卷内使用以下路径：

| 路径 | 内容 |
| --- | --- |
| `/app/data/accounts.json` | 账号、Cookie、状态和代理配置；按密钥管理，禁止打印、提交或外传 |
| `/app/data/tasks.json` | 任务记录 |
| `/app/data/media/` | 对外提供的生成媒体 |
| `/app/data/downloads/` | 浏览器下载文件，也是自动清理范围 |

`Dockerfile` 只创建这些目录，没有声明 `VOLUME`。这是有意为之：Railway 的卷由平台在运行时挂载，Dockerfile 的 `VOLUME` 不能替代平台挂载，而且该 fork 的基线已因 Railway 不接受该声明而移除它。部署时应在 Railway 服务设置中把持久卷明确挂到 `/app/data`。

## 更新流程

1. 从 `railway-v1.6.9` 创建功能分支，不在生产部署分支直接工作。
2. 对上游 `czg86389-hub/muse2api` 的变更逐个审阅、逐个 cherry-pick；解决冲突并在功能分支完成验证。
3. 创建以 `railway-v1.6.9` 为 base 的 PR，写清改动、验证结果与风险。
4. 由审核者决定是否以及何时合并。合并会触发 Railway 部署，并把排队中或执行中的图片、视频任务在启动时标记为“服务重启中断了任务，请重新提交”。

特别注意：

- 上游提交 `8213b3d` 包含静默自动升级及管理界面隐藏，禁止整体合入。本分支只单独取过其中与管理页禁用缓存有关的修复。
- 上游提交 `1795dab` 只取 `engine.py` 相关修复，不取账号严格轮询行为。
- 不要使用管理页在线升级代替 PR。升级逻辑会用上游 `main` 覆盖当前镜像代码，默认还会调用 `os._exit(0)`；Railway 可能不会把这个正常退出的进程重新拉起，服务会持续返回 502，同时本 fork 的修复也会被覆盖。
- `MUSE2API_ALLOW_SELF_UPDATE` 默认是 `0`。只有值严格等于 `1` 时，`POST /admin/update/upgrade`、`POST /admin/repo/pull` 和 `POST /admin/repo/push` 才放行；否则返回 403。更新检查也会返回 `self_update_disabled=true` 并隐藏可升级状态。Railway 部署不要把它设为 `1`。

## 环境变量

下面列出运行时代码读取的全部 `MUSE2API_*` 变量。Railway 应在服务变量中配置，不要把真实密钥写进仓库。

| 变量 | 代码默认值 | 含义与边界 |
| --- | --- | --- |
| `MUSE2API_HOME` | 代码文件所在目录；镜像固定为 `/app` | 基础目录；其下的 `data/` 存放账号、任务和媒体，`.env` 也从这里读取 |
| `MUSE2API_HOST` | `0.0.0.0` | 监听地址；镜像同样设为 `0.0.0.0` |
| `MUSE2API_PORT` | `18610` | 应用端口；Docker 启动命令也固定使用 `18610` |
| `MUSE2API_CHROMIUM` | 自动探测，最终回退 `chromium`；镜像固定为 `/usr/bin/chromium` | Chromium/Chrome 可执行文件路径或命令名 |
| `MUSE2API_CDP_PORT` | `19210` | Chromium DevTools Protocol 内部端口 |
| `MUSE2API_HOME_DIR` | 当前用户主目录 | 浏览器运行时使用的主目录 |
| `MUSE2API_EXTRA_PATH` | `/snap/bin` | 启动浏览器时补入的 PATH |
| `MUSE2API_SITE` | `https://muse.ai/` | muse.ai 站点地址 |
| `MUSE2API_LOGIN_WAIT` | `60` | 等待 muse.ai 聊天输入框出现的秒数；超时不等于账号已失效 |
| `MUSE2API_UPLOAD_WAIT` | `30` | 等待上传控件的秒数；实际最少等待 5 秒 |
| `MUSE2API_PROFILE_ROOT` | `~/muse2api-profiles` | Chromium profile 根目录；镜像预建 `/root/muse2api-profiles` |
| `MUSE2API_KEY` | 空 | 管理接口和 `/v1` API 的 Bearer Key。为空时启动代码会自动生成、写入 `/app/.env` 并输出到启动日志；Railway 上应显式设置稳定的强随机值，避免重新部署后变化，也不要在工单或日志中粘贴真实值 |
| `MUSE2API_PUBLIC_BASE` | 空 | 对外完整 URL 前缀；为空时管理页按当前访问来源兜底，状态接口中的 `base_url` 为空 |
| `MUSE2API_CORS_ORIGINS` | `https://muse.ai,https://www.muse.ai` | 配置对象会读取该值；但当前中间件实际使用 `allow_origins=["*"]`，因此修改它不会收紧当前版本的 CORS |
| `MUSE2API_IMAGE_TIMEOUT` | `240` | 图片生成超时，秒 |
| `MUSE2API_VIDEO_TIMEOUT` | `600` | 视频生成超时，秒 |
| `MUSE2API_CHAT_TIMEOUT` | `300` | 对话生成超时，秒 |
| `MUSE2API_CONCURRENCY` | `2` | 全局最大并发任务槽位，最小为 1；同一账号仍不会同时被多个任务占用。调大前确认 Railway 内存、CPU 与账号数足够 |
| `MUSE2API_WORKSPACE_COOLDOWN_SECONDS` | `300` | 账号遇到工作区未分配后的冷却秒数；冷却期间不参与业务调度，到期自动恢复，不改变账号 `ok` 状态 |
| `MUSE2API_WORKSPACE_REDISCOVERY_DELAY_SECONDS` | `15` | 首次遇到工作区 no-match 后，关闭页面并再次查询 `/api/session` 前的等待秒数；同一任务、同一账号只重新发现一次且不调用 wake |
| `MUSE2API_WORKSPACE_CIRCUIT_BREAKER_ENABLED` | `1` | 非 `0` 时启用上游故障熔断；所有可调度账号都在冷却时立即失败，不再打开页面或请求 muse.ai |
| `MUSE2API_VIDEO_QUOTA_COOLDOWN_HOURS` | `24` | muse.ai 明确回复视频额度达到上限时，该账号暂停视频任务的默认小时数；若回复含可解析的恢复时间则优先使用回复时间 |
| `MUSE2API_IMAGE_QUOTA_COOLDOWN_HOURS` | `24` | muse.ai 明确回复图片额度达到上限时，该账号暂停图片任务的默认小时数；若回复含可解析的恢复时间则优先使用回复时间 |
| `MUSE2API_REF_IMAGE_LOCAL_FILES` | `0` | 严格等于 `1` 时才允许服务器本地路径作为参考素材；仅适合可信单用户部署 |
| `MUSE2API_REF_IMAGE_PRIVATE_FETCH` | `0` | 严格等于 `1` 时才允许抓取私网/本机参考图 URL；默认只允许经过检查的公网 URL |
| `MUSE2API_TOOL_PROTOCOL` | `0` | 非 `0` 时启用工具调用协议适配；默认只兼容参数，不注入协议 |
| `MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS` | `0` | 非 `0` 时，手动禁用的账号仍参加自动保活，但仍不参加业务任务调度 |
| `MUSE2API_MEDIA_HIGH_WATERMARK` | `80` | 数据卷使用率达到或超过此百分比时触发清理；运行时限制在 5%～99% |
| `MUSE2API_MEDIA_LOW_WATERMARK` | `60` | 触发后删除到此数据卷水位；运行时限制在 1%～“高水位减 1 个百分点” |
| `MUSE2API_MEDIA_MIN_AGE_MINUTES` | `30` | 小于此文件年龄的媒体不删除，单位分钟 |
| `MUSE2API_MEDIA_MAX_GB` | `0` | `media/` 与 `downloads/` 文件总大小上限，单位 GiB；`0` 表示不启用容量上限 |
| `MUSE2API_MEDIA_JANITOR_INTERVAL` | `300` | 自动清理检查间隔，秒；实际最小为 30 秒 |
| `MUSE2API_ALLOW_SELF_UPDATE` | `0` | 严格等于 `1` 才允许在线拉取、升级和推送；Railway 保持 `0` |

改动变量后应通过一次正常的 Railway 重新部署使配置生效。不要通过在线升级接口重启。

## 管理接口速查

除另有说明外，管理数据接口使用与业务 API 相同的 `Authorization: Bearer <MUSE2API_KEY>` 鉴权。以下只列运维常用行为；不要把真实 Key 放入命令历史、截图或文档。

| 方法与路径 | 行为 |
| --- | --- |
| `GET /admin/status` | 总览：脱敏账号列表、统计、最近 20 个任务摘要、媒体数量、浏览器状态和部分配置 |
| `GET /admin/accounts` | 返回脱敏账号列表与统计；Cookie 和代理凭据不会返回，仅给出 Cookie 数量和脱敏代理信息 |
| `POST /admin/accounts` | 导入单个或批量 Cookie；`hatch_sess` 是代码要求的核心 Cookie。遇到崩溃页时仍应重新导入浏览器扩展取得的完整 Cookie |
| `PATCH /admin/accounts/{aid}` | 修改标签、启用状态或代理；账号忙时不能改代理 |
| `DELETE /admin/accounts/{aid}` | 删除账号 |
| `POST /admin/accounts/{aid}/test` | 真实打开 muse.ai 检查登录状态，并尝试同步 Cookie、读取额度；明确认证错误会把账号标为异常，其他未确认错误保留原状态 |
| `POST /admin/accounts/{aid}/cookies` | 为已有账号替换 Cookie，并重置新会话的有效期估算锚点 |
| `POST /admin/accounts/{aid}/proxy/test` | 检查代理出口，再经该代理检查 Muse 会话；不代表真实生成一定成功 |
| `POST /admin/accounts/{aid}/quota` | 实时打开设置面板读取指定账号额度并缓存；读取失败不会覆盖旧缓存 |
| `DELETE /admin/accounts/{aid}/quota-cooldown?kind=video` | 清除指定账号的额度冷却；`kind` 可为 `video`、`image`、`any`，省略时清除全部，适合确认套餐升级或额度已恢复后使用 |
| `POST /admin/accounts/keepalive` | 手动运行全账号保活；默认查询参数 `force=true`。已有保活任务时返回 `busy` |
| `POST /admin/accounts/{aid}/keepalive` | 对单个账号执行 `/api/session` 续签和 VM 唤醒 |
| `GET /admin/keepalive/status` | 查看保活协程最近一次、下一次运行及结果 |
| `GET /admin/tasks?limit=50` | 按创建时间倒序返回任务摘要：去掉内部 `api_prompt`，并把超过 300 字符的 `prompt` 截断 |
| `GET /admin/tasks?limit=50&full=1` | 返回完整任务对象，包括未截断提示词和内部 `api_prompt`；其中可能含敏感业务内容，应限制访问和转发 |
| `DELETE /admin/tasks/{tid}` | 删除一条任务记录；任务不存在时返回 404 |
| `POST /admin/tasks/clear` | 清理任务记录；JSON 的 `keep` 表示保留最新多少条，默认 0 |
| `GET /admin/media` | 列出 `media/` 中的文件、URL、大小、修改时间和媒体类型 |
| `POST /admin/media/delete` / `DELETE /admin/media/{name}` | 批量或单个删除媒体文件 |
| `GET /admin/storage` | 返回数据卷容量、使用率、媒体文件数与大小、清理阈值及最近清理结果 |
| `POST /admin/storage/cleanup` | 立即执行一次水位检查；未达到高水位且未超过容量上限时不会删除文件，不是无条件强制清空 |
| `GET /admin/update/check` / `GET /admin/repo/status` | 检查上游版本；当前代码没有给这两个读接口加 Bearer 依赖。Railway 默认会隐藏升级状态 |
| `POST /admin/update/upgrade` / `POST /admin/repo/pull` / `POST /admin/repo/push` | Railway 默认返回 403；不要启用或调用 |

`GET /admin/apikey` 会向已鉴权调用方返回当前 Key，`POST /admin/apikey/rotate` 会立即使旧 Key 失效并写入 `.env`。Railway 的稳定配置应以平台环境变量为准，避免用这两个接口做常规密钥管理。

## 账号故障排查

### `Something went wrong`

程序识别的崩溃页特征是页面没有输入框，只剩 `Something went wrong` 与 `Try again`。代码把它解释为工作区令牌 `/api/hatch/token` 被拒，常见于 Cookie 不完整，或会话已在别处失效。该错误属于明确认证错误，业务链路或账号测试会把账号标记为异常，调度时优先绕开。

处理步骤：

1. 在 muse.ai 官网确认账号当前可以正常登录。
2. 使用本项目浏览器扩展重新导入该账号的**完整 Cookie**，不要只手工补一个字段。
3. 在管理页对该账号执行“测试”；确认会话有效后再恢复任务。
4. 若仍出现同一页面，检查是否有其他登录挤掉会话或触发上游风控。上游账号状态超出本仓库可确认范围时，记录为“未确认”，不要反复发起真实生成验证。

### `/api/session` 轮换 Cookie

muse.ai 会在 `/api/session` 响应中轮换 `hatch_sess`、`hatch_gw` 等 Cookie；即使响应 JSON 的工作区状态不是 `assigned`，旧值也可能已经作废。旧实现先按工作区未分配报错，丢掉响应里的新 Cookie，所以账号常在随后约 10 分钟需要重新导入。

当前实现先合并响应 Cookie 和到期时间并写回 `accounts.json`，再报告工作区未分配；已有 Cookie 中未被轮换的项不会丢失。日志出现“工作区暂未分配，已保留 muse.ai 轮换下发的新 cookie”时，不要用旧 Cookie 覆盖数据卷中的新值。

### 上游故障熔断

页面返回 `hatch_vm_auth_no_match` / `MuseWorkspaceUnavailable` 表示 muse.ai 暂未给该账号分配工作区，不等同于 Cookie 失效。程序会先关闭页面并回存轮换 Cookie，等待 `MUSE2API_WORKSPACE_REDISCOVERY_DELAY_SECONDS` 后，仅用一次无 wake 的 `/api/session` 查询重新发现工作区；只有状态恢复为 `assigned` 才为同一账号重开页面重试一次。

重新发现仍不可用或失败时，账号进入 `MUSE2API_WORKSPACE_COOLDOWN_SECONDS` 冷却。冷却不会修改账号 `ok`，也不需要重新导入 Cookie；`GET /admin/accounts` 的 `workspace_cooldown_remaining_seconds` 可查看剩余秒数。若所有可调度账号都在冷却且熔断开关开启，新任务会立即返回上游故障及预计自动恢复时间，不会启动浏览器或继续请求 muse.ai。应等待冷却自动结束；只有出现明确登录页、`/api/session` 401 等认证证据时才重新导入 Cookie。

### 图片与视频额度冷却

muse.ai 明确回复 `视频上限`、`video limit`、`usage limit`、`额度已用完` 等额度文案时，程序会把它与普通内容拒绝区分：只为当前账号记录对应图片或视频种类的额度冷却，然后在现有重试次数内自动切换到仍有该种类额度的账号。额度冷却与工作区冷却并列，不修改账号 `ok`，也不表示 Cookie 失效；视频冷却不会影响该账号继续承担图片或对话任务。

`GET /admin/accounts` 会返回 `video_quota_cooldown_remaining_seconds`、`image_quota_cooldown_remaining_seconds` 和 `any_quota_cooldown_remaining_seconds`。冷却到期后账号自动恢复调度；若模型回复包含可解析的恢复时长则按该时间，否则分别使用 `MUSE2API_VIDEO_QUOTA_COOLDOWN_HOURS` 或 `MUSE2API_IMAGE_QUOTA_COOLDOWN_HOURS`。所有账号都处于当前种类额度冷却时，请求会在打开页面前立即失败，并报告最早预计恢复时间。

免费账号的视频额度生产观察约为每账号每 24 小时 1 条。运维上应预留足够账号并错峰使用，不要通过连续重试消耗浏览器资源；确认账号升级套餐或额度已提前恢复后，可使用额度冷却清除接口让它立即重新参与调度。普通模型内容拒绝仍是终止错误，不会为了绕过拒绝而自动换号。

### 常见生成错误

| 错误 | 代码含义 | 处理 |
| --- | --- | --- |
| `找不到上传控件` | 页面输入框可用后，上传控件仍可能因冷页面、刚切号或 VM 唤醒而尚未挂载。程序会等待 `MUSE2API_UPLOAD_WAIT`，中途尝试点击 Attach，最终仍找不到才停止，并把页面快照写到 `/app/data/debug-no-upload-control.json` | 先检查同一时刻是否有崩溃页认证错误，再查看快照和上游 UI 是否变化；若只是 Railway/VM 偏慢，可谨慎调大上传等待。不要把此错误单独当成 Cookie 失效 |
| `muse.ai 页面加载超时（未出现聊天输入框）` | 在 `MUSE2API_LOGIN_WAIT` 内未出现输入框，且没有识别到登录页或崩溃页；会话失效**未确认** | 检查 Railway 出口、账号代理和 muse.ai 可达性后重试；持续发生时再执行账号测试。若日志是 `Connecting...`，表示页面网关连接超时并会切换账号 |
| `提示词没有发出去` | 发送 25 秒后内容仍留在输入框，程序会补点一次发送；60 秒后仍未送出才报错并交给外层换号重试 | 检查页面网关、上游 UI 与账号状态；这表示 composer/网关未接收消息，不等同于认证失效。避免人工连续重试造成重复任务 |

### 查看日志

只读查看当前服务日志：

```bash
railway logs --service muse2api
```

重点搜索以下不含凭据的关键字：

- `Something went wrong`、`/api/hatch/token`、`会话认证失败`、`会话已被 muse.ai 登出`：明确认证方向；
- `/api/session`、`工作区暂未分配`、`轮换后的新 cookie`、`保存轮换后的 cookie 失败`：会话续签与轮换保存；
- `页面加载超时`、`Connecting...`、`浏览器预热`：页面或网关可达性；
- `找不到上传控件`、`上传控件未就绪`、`debug-no-upload-control.json`：上传 UI；
- `提示词没有发出去`、`仍在输入框`、`Delivery not confirmed`：发送未被确认；
- `【自动保活】`、`【媒体清理】`、`【媒体清理守护进程】`：后台保活和存储清理。

不要粘贴完整启动日志到公开工单：当 `MUSE2API_KEY` 未配置时，当前启动代码会把自动生成的 Key 输出到日志。任何 Cookie、Key、代理认证信息或账号 ID 都应在转发前删除。

## 存储清理

启动时会创建媒体清理守护协程，并立即检查一次，之后按 `MUSE2API_MEDIA_JANITOR_INTERVAL` 周期检查。清理扫描 `/app/data/media` 和 `/app/data/downloads`，忽略以 `.` 开头的占位文件，并按修改时间从旧到新删除。

触发与停止规则：

- 数据卷使用率 `>= MUSE2API_MEDIA_HIGH_WATERMARK` 时触发，删除到使用量不高于低水位；
- `MUSE2API_MEDIA_MAX_GB > 0` 且媒体总量超过上限时也触发，容量目标按“上限 × 低水位 ÷ 高水位”计算；
- 两个条件同时触发时，要同时满足磁盘水位目标和媒体容量目标才停止；
- 修改时间晚于“当前时间减最短保留时间”的文件会跳过，因此可删除文件不足时，清理后仍可能高于目标；
- 删除失败只计入错误并继续处理其他文件；`GET /admin/storage` 的 `last_cleanup` 可查看最近结果。

清理是永久删除本地文件。文件被删除后，原 `/v1/media/{name}` 链接会返回 404；任务记录里的旧结果地址不会因此自动改写。需要长期保存的成品应在到达清理水位前下载或复制到独立对象存储。
