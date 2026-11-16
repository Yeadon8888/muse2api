# 本机出口 / 无头浏览器对照实验

日期：2026-11-16（Asia/Shanghai）

## 结论

L1（本机 headless）成功，L2（本机 headful）也成功。两种模式下页面均完成导航，编辑器持续可输入，约 97～99 秒观察期内没有出现 `Something went wrong / Try again` 崩溃页。按任务书的判定规则，当前证据优先指向 **Railway 服务器出口 IP、地区或机房网络信誉限制**，不支持“仅由 headless/浏览器指纹导致”的假设。

本实验没有发起生成，因而结论只覆盖 muse.ai 工作区页面的连接与稳定性；不能据此声称生成链路已经在本机完成端到端验证。

## 方法

- 前置条件：`.env.local` 的生产 URL/管理 Key 均存在；Railway production / muse2api 关联成功；本机 Google Chrome 存在；`origin/railway-v1.6.9` 包含 `8f9fa17`。
- 账号：标签 `217`，账号 ID 前 6 位 `88bb43`，原始状态为启用，且未配置账号代理。
- 每轮开始前通过管理 API 将账号设为 `enabled=false`，避免生产调度并发使用；轮次结束后恢复原始启用状态。
- cookie 通过 `railway ssh` 的 stdout 管道直接读入本机 Python 内存，不打印、不写入报告或仓库文件。每轮使用独立临时 Chrome user-data-dir，结束后关闭 Chrome 并删除目录。
- 注入规则与 `engine._apply_cookies` 保持一致：先清空旧 cookie；`__Host-` cookie 仅注入 `muse.ai` host-only 作用域，其余 cookie 仅注入 `.muse.ai`，每个名称一份。
- Chrome 参数尽量对齐 `engine.py`：`--no-sandbox`、`--disable-gpu`、`--disable-dev-shm-usage`、`--disable-background-networking`、`--no-first-run`、`--no-default-browser-check`、`--autoplay-policy=no-user-gesture-required`、`--window-size=1440,2400`；L1 额外使用新版 headless，L2 使用正常窗口。
- 使用浏览器级 CDP target discovery 与 BrowserContext 全 target 响应监听；只保留任务要求的 HTTP 状态、`status`、`code`，不保存响应正文、token、VM 地址或 IndexedDB 内容。
- 两个正式对照轮次的开始时间相隔 97 秒，满足至少 60 秒的间隔要求。由于首轮安全钩子没有观察到 session/token 响应，又在总加载上限内追加一次 L1 遥测确认；总加载次数为 3。

## 脱敏结果

| 轮次 | 开始时间 | 观察时长 | `/api/session` | wake | `/api/hatch/token` | 页面结果 | cookie 写回 | 临时目录 |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| L1 headless | 14:36:31 | 97.3 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |
| L2 headful | 14:38:08 | 98.9 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |
| L1 headless 遥测确认 | 14:40:36 | 97.5 秒 | 未观察到响应 | HTTP 200 | 未观察到响应 | 编辑器可输入；未崩溃 | HTTP 200 | 已删除 |

“未观察到响应”是原始观测结果，不等同于错误状态，也没有用推测值补齐。三轮均发现 `page` 和 `browser_ui` target；wake 由页面安全钩子捕获。session/token 没有在本机这条加载路径中产生可被页面钩子或 BrowserContext response 事件观察到的响应，因此没有可报告的 `status` / `code`。

### 指纹对比

| 项目 | L1 headless | L2 headful |
| --- | --- | --- |
| User-Agent | Chrome 157，含 `HeadlessChrome` | Chrome 157，不含 `HeadlessChrome` |
| `navigator.webdriver` | `true` | `true` |
| `navigator.platform` | `MacIntel` | `MacIntel` |
| Client Hints platform / architecture / bitness | macOS / arm / 64 | macOS / arm / 64 |
| Client Hints mobile | `false` | `false` |
| 语言 | `zh-CN` | `zh-CN` |

除 User-Agent 的 `HeadlessChrome` 标记外，本次读取的主要 Client Hints 相同；`navigator.webdriver` 在两种模式下均为 `true`。由于 L1 已成功，这些差异不是当前故障的主要解释。

## cookie 写回与安全收尾

- 三次页面加载结束前均读取最新规范作用域 cookie，并通过 `POST /admin/accounts/{aid}/cookies` 写回生产；三次 HTTP 状态均为 200。
- 最终恢复账号启用状态的 PATCH 为 HTTP 200；随后重新读取账号池，确认标签 `217` 为 `enabled=true`。
- 三个临时 user-data-dir 均已删除；收尾检查没有发现 `muse-egress-*` 目录或使用这些 profile 的 Chrome 进程。
- 准备阶段曾有两次在页面导航前停止：一次 Railway SSH 子进程退出超时，一次本机 Playwright cookie 参数校验失败。两次都没有加载 muse.ai，且账号均由 `finally` 恢复；不计入三次加载。
- 未调用 `/v1/*`，未发起生成，未读取用户日常 Chrome 资料，未读取 IndexedDB，未改 Railway 配置或部署。

## 建议

优先给受影响账号配置稳定的住宅或用户本地出口代理，并在保存前测试出口与 Muse 会话。服务已支持每账号独立 HTTP、SOCKS5 和 SOCKS5h 代理，浏览器、会话检测及保活会使用同一路由；代理失败不会静默回退直连。

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

- session/token 响应在本机加载路径中未被观察到，无法与生产的 `/api/session 200 → wake 200 → /api/hatch/token 401` 做逐字段一一对照；结论主要依据 L1 页面在观察期内持续可用且不崩溃。
- 单轮观察约 98 秒，短于现状描述中的 200 秒任务等待；由于不允许发起生成，本实验不能复现完整任务时长。
- 如果切换到合格住宅/本地出口后生产仍出现 `hatch_vm_auth_no_match`，下一步才应考虑用户日常浏览器绑定（例如本机 IndexedDB/CVM 密钥）。读取用户日常 Chrome 资料必须另行取得用户明确许可，本次未执行 L3。
