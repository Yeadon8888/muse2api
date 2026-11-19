# 本机出口 / 无头浏览器对照实验

日期：2026-11-16（Asia/Shanghai）

## 结论

**修正结论：现有实验不能在“Railway 服务器出口限制”和“客户端状态绑定”之间做决定性判定。** 第一轮 L1/L2 使用的标签 `217` 几乎没有在服务器上使用过，存在“新账号首次使用可成功”的混杂因素，因此原先“优先指向服务器出口”的结论已撤回。

补充对照改用已在服务器使用并失败、`use_count=15` 的标签 `238`：L4 本机 headless 与 L5 本机 headful 均稳定 125 秒、编辑器可输入且未崩溃。但是，浏览器级 CDP 的 Network 与 Fetch 全 target 监听均未观察到 `/api/session`、`/api/hatch/vm/wake` 或 `/api/hatch/token` 响应，没有拿到判定必需的 token HTTP 状态与 `code`。因此既不能按“token 200”判为服务器出口，也不能按“401 + hatch_vm_auth_no_match”判为客户端状态绑定。

页面稳定性说明同一个已在服务器失败的账号可以在本机打开工作区界面，这是偏向“本机环境有差异”的证据，但在缺少 token 响应的情况下不够决定性。本实验没有发起生成，结论也不覆盖端到端生成链路。

## 方法

- 前置条件：`.env.local` 的生产 URL/管理 Key 均存在；Railway production / muse2api 关联成功；本机 Google Chrome 存在；`origin/railway-v1.6.9` 包含 `8f9fa17`。
- 账号：标签 `217`，账号 ID 前 6 位 `88bb43`，原始状态为启用，且未配置账号代理。
- 每轮开始前通过管理 API 将账号设为 `enabled=false`，避免生产调度并发使用；轮次结束后恢复原始启用状态。
- cookie 通过 `railway ssh` 的 stdout 管道直接读入本机 Python 内存，不打印、不写入报告或仓库文件。每轮使用独立临时 Chrome user-data-dir，结束后关闭 Chrome 并删除目录。
- 注入规则与 `engine._apply_cookies` 保持一致：先清空旧 cookie；`__Host-` cookie 仅注入 `muse.ai` host-only 作用域，其余 cookie 仅注入 `.muse.ai`，每个名称一份。
- Chrome 参数尽量对齐 `engine.py`：`--no-sandbox`、`--disable-gpu`、`--disable-dev-shm-usage`、`--disable-background-networking`、`--no-first-run`、`--no-default-browser-check`、`--autoplay-policy=no-user-gesture-required`、`--window-size=1440,2400`；L1 额外使用新版 headless，L2 使用正常窗口。
- 使用浏览器级 CDP target discovery 与 BrowserContext 全 target 响应监听；只保留任务要求的 HTTP 状态、`status`、`code`，不保存响应正文、token、VM 地址或 IndexedDB 内容。
- 两个正式对照轮次的开始时间相隔 97 秒，满足至少 60 秒的间隔要求。由于首轮安全钩子没有观察到 session/token 响应，又在总加载上限内追加一次 L1 遥测确认；总加载次数为 3。

### 补充决定性对照方法

- 账号改为标签 `238`、ID 前 6 位 `ad3998`、`use_count=15`；该账号近期在服务器任务中失败，原始状态为启用且未配置账号代理。
- L4 为本机 headless，L5 为本机 headful；L5 仅因 L4 没有得到 token 200 而执行。两次开始时间相隔 131 秒，补充实验总加载次数为 2。
- 直接连接 Chrome browser WebSocket，启用 `Target.setDiscoverTargets` 与 `Target.setAutoAttach`（flatten 模式），对 `page`、`service_worker` 等 target 启用 Network；同时用 Fetch 域在 response stage 匹配三个目标 API。
- session 响应只准备提取 HTTP 状态、`status`、`vm_id`/`vm_state` 字段是否存在；token 响应只准备提取 HTTP 状态和 `code`。不保存或输出响应正文、token 值、VM 字段值。
- 每轮强制观察 125 秒，结束前读取规范作用域 cookie 写回生产，再关闭 Chrome 并删除临时 user-data-dir。

## 脱敏结果

| 轮次 | 开始时间 | 观察时长 | `/api/session` | wake | `/api/hatch/token` | 页面结果 | cookie 写回 | 临时目录 |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| L1 headless | 14:36:31 | 97.3 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |
| L2 headful | 14:38:08 | 98.9 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |
| L1 headless 遥测确认 | 14:40:36 | 97.5 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |

“未观察到响应”是原始观测结果，不等同于错误状态，也没有用推测值补齐。三轮均发现 `page` 和 `browser_ui` target；wake 由页面安全钩子捕获。session/token 没有在本机这条加载路径中产生可被页面钩子或 BrowserContext response 事件观察到的响应，因此没有可报告的 `status` / `code`。

### L4/L5 补充结果

| 轮次 | 账号 | 开始时间 | 观察时长 | `/api/session` | wake | `/api/hatch/token` | 页面结果 | cookie 写回 | 清理 |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| L4 headless | `238` / `ad3998` | 14:54:06 | 125 秒 | 未观察到响应 | 未观察到响应 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | Chrome 已停止；目录已删除 |
| L5 headful | `238` / `ad3998` | 14:56:17 | 125 秒 | 未观察到响应 | 未观察到响应 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | Chrome 已停止；目录已删除 |

两轮 browser target discovery 均发现 `browser_ui`、`page` 和 `service_worker`，脚本未报告导航错误或同步 CDP 命令错误。Network 与 Fetch response-stage 均没有收到三个目标路径的事件，所以 session 的 `status`、VM 字段存在性，以及 token 的状态码/`code` 都没有观测值。加载次数已达到补充实验上限，未继续重试。

判定规则与实际结果：

- token 200 且页面稳定：应判为服务器出口；**本次未观察到 token 响应，条件不成立**。
- token 401 且 `code=hatch_vm_auth_no_match`：应判为客户端状态绑定；**本次未观察到 token 响应，条件不成立**。
- 实际结果：**不可判定**，不得用“页面稳定”替代明确要求的 token 证据。

### 指纹对比

| 项目 | L1 headless | L2 headful |
| --- | --- | --- |
| User-Agent | Chrome 157，含 `HeadlessChrome` | Chrome 157，不含 `HeadlessChrome` |
| `navigator.webdriver` | `true` | `true` |
| `navigator.platform` | `MacIntel` | `MacIntel` |
| Client Hints platform / architecture / bitness | macOS / arm / 64 | macOS / arm / 64 |
| Client Hints mobile | `false` | `false` |
| 语言 | `zh-CN` | `zh-CN` |

除 User-Agent 的 `HeadlessChrome` 标记外，本次读取的主要 Client Hints 相同；`navigator.webdriver` 在两种模式下均为 `true`。原始 L1/L2 页面表现相同，因此没有证据支持“仅由 headless 导致”，但这不能替代补充实验缺失的 token 证据。

## cookie 写回与安全收尾

- 三次页面加载结束前均读取最新规范作用域 cookie，并通过 `POST /admin/accounts/{aid}/cookies` 写回生产；三次 HTTP 状态均为 200。
- 最终恢复账号启用状态的 PATCH 为 HTTP 200；随后重新读取账号池，确认标签 `217` 为 `enabled=true`。
- 三个临时 user-data-dir 均已删除；收尾检查没有发现 `muse-egress-*` 目录或使用这些 profile 的 Chrome 进程。
- 准备阶段曾有两次在页面导航前停止：一次 Railway SSH 子进程退出超时，一次本机 Playwright cookie 参数校验失败。两次都没有加载 muse.ai，且账号均由 `finally` 恢复；不计入三次加载。
- L4/L5 均在结束前写回最新 cookie，HTTP 状态均为 200；标签 `238` 的停用和最终恢复 PATCH 均为 HTTP 200，随后读取账号池确认 `enabled=true`、`use_count=15`。
- L4/L5 的两个临时 user-data-dir 均已删除，对应 Chrome 进程均已停止，收尾检查没有残留。
- 未调用 `/v1/*`，未发起生成，未读取用户日常 Chrome 资料，未读取 IndexedDB，未改 Railway 配置或部署。

## 建议

当前不应把配置住宅代理写成已证实的修复。若要继续区分出口与客户端状态，可以把“同一账号、同一页面流程、不同出口且必须捕获 token 结果”作为下一次独立对照；在拿到 token 证据前，住宅/本地出口代理只是待验证方案。服务已支持每账号独立 HTTP、SOCKS5 和 SOCKS5h 代理，浏览器、会话检测及保活会使用同一路由；代理失败不会静默回退直连。

管理页面配置方式：账号池中打开对应账号的“账号代理”，选择“指定代理”，填写 `http://host:port`、`socks5://host:port` 或 `socks5h://host:port`，按需填写用户名和密码，先点“测试连通性”，确认后保存。部署环境里的 `127.0.0.1` 指 Railway 容器自身，不是用户电脑。

API 配置方式：对 `PATCH /admin/accounts/{aid}` 提交如下结构；凭据应只在安全请求中传递，不写入文档、日志或命令历史。

```json
{
  "proxy": {
    "server": "socks5h://proxy.example.com:1080",
    "username": "<username>",
    "password": "<password>"
  }
}
```

可先向 `POST /admin/accounts/{aid}/proxy/test` 提交相同的 `proxy` 结构做连通性与 Muse 会话检查，再保存配置。修改代理后应重新做账号测试；本实验不授权购买代理、修改生产配置或执行生成验证。

## 已知限制与风险

- 原始 L1/L2 的账号存在首次使用混杂因素，不能用于出口与首次使用的决定性区分。
- L4/L5 虽然使用了已在服务器失败的账号并观察满 125 秒，但三个目标 API 均无 CDP 观测值，未满足预设判定条件。这是当前最主要的未完成项。
- 原始轮次约 98 秒、补充轮次 125 秒，仍未复现完整生产生成任务；按安全约束没有发起生成。
- 读取用户日常 Chrome 资料或 IndexedDB 仍需另行取得明确许可，本次没有执行；也没有配置代理、修改代码、部署或触碰生产分支。
