# 2026-11-16 CVM 密钥浏览器 IndexedDB 实验

## 结论摘要

**结论：无法确认“CVM 密钥只存在于创建它的浏览器 IndexedDB”。**

实验账号 238 的初次 X1 在页面级 fetch/XHR 观察器中没有看到 `/api/session`、wake 或 `/api/hatch/token`，IndexedDB 数据库列表为空。补充实验改用浏览器级 CDP Network 事件并自动附加所有 target 后，两次新上下文均明确观察到 `/api/session` HTTP 200、wake HTTP 200 和 `/api/hatch/token` HTTP 401；页面最终显示 `Something went wrong / Try again`。

因此，原先“页面可能没有进入工作区流程”的解释被排除；初次 X1 的页面级观察器漏掉了请求。前三次加载都没有取得 token HTTP 200；第四次也是最后一次加载用于 cookie 单份注入实验，但最终结构化结果在 Railway SSH stdout 回收时丢失，无法安全断言是否出现过 200。现有证据仍然既不能证明浏览器 IndexedDB 中存在恢复密钥，也不能证明复制该状态可以恢复 token。

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

## 补充实验：浏览器级全 target 网络观察

### 方法

- 在原 X1 已使用 1 次加载的基础上，再创建两个全新隔离 BrowserContext，各加载 `/thread/new` 一次并观察 60 秒；账号累计使用 3/4 次加载。
- 在 browser target 上启用 `Target.setAutoAttach`，并对自动附加的 page / iframe / worker / service worker target 启用 Network 事件。实际附加到的 target 类型只有 `page` 和 Chromium 的 `browser_ui`，没有出现 service worker target，因此没有观察到 service worker 发出的请求。
- 重定向和请求只记录 muse.ai 的路径与状态码；查询参数全部丢弃，UUID、长标识和疑似敏感路径段在输出前打码。
- 标题与正文先在容器内用完整账号 ID、当前 cookie 值、邮箱、JWT、命名 token/cookie 值及长不透明字符串做匹配和替换，再输出最多 600 个字符。本次两轮均未命中需打码内容。
- 只读取明显“继续 / 开始 / 下一步”类控件的文字，不点击任何控件。每个上下文销毁前均读取最新 cookie 并回写。

### 两次加载的页面结果

| 项目 | 补充加载 1 | 补充加载 2 |
|---|---|---|
| 最终路径 | `/thread/new` | `/thread/new` |
| 重定向链 | `/thread/new` → HTTP 200；无重定向 | `/thread/new` → HTTP 200；无重定向 |
| `document.title` | `Muse` | `Muse` |
| 可见文字前 600 字符 | `Something went wrong` / `Try again` | `Something went wrong` / `Try again` |
| 敏感信息打码 | 未命中 | 未命中 |
| 页面 target 崩溃 | 否 | 否 |
| 明显继续/开始类按钮 | 无 | 无 |
| cookie 回写 | HTTP 200 | HTTP 200 |

两次页面都没有显示登录、注册、新用户引导、同意条款、选择套餐、额度用尽、等待列表或地区不可用界面。页面 target 本身没有崩溃，但应用渲染了通用错误页。

### 请求路径与状态

下表是两轮浏览器级采集的合并去重结果；同一路径重复请求不重复展开，静态 immutable 资源按路径族归并。除 `/api/hatch/token` 和 `/monitoring` 外，没有观察到其他 4xx/5xx。

| 路径 | 状态 | target / 说明 |
|---|---:|---|
| `/thread/new` | 200 | page，主文档 |
| `/api/session` | 200 | page |
| `/api/hatch/vm/wake` | 200 | page；每轮均出现 |
| `/api/hatch/token` | 401 | page；每轮重复出现 |
| `/api/hatch/stateful-sharing` | 200 | page |
| `/api/auth/check` | 200 | page；每轮重复出现 |
| `/api/auth/save-account` | 200 | page |
| `/api/consent/status` | 200 | page |
| `/api/falco` | 200 | page；每轮重复出现 |
| `/monitoring` | 200、429 | page；429 为唯一的非 token 4xx |
| `/_vercel/speed-insights/script.js` | 200 | page |
| `/favicon.ico` | 200 | page |
| `/images/favicon/app-squiggle.svg` | 200 | page |
| `/images/hatch/muse-logo.svg` | 200 | page |
| `/_next/static/immutable/chunks/*` | 200 | page；JS/CSS 静态资源，所有已响应项均为 200 |
| `/_next/static/immutable/media/*` | 200 | page；字体资源 |
| `/<静态标识>/script.js` | 200 | page；路径标识已打码归并 |

补充实验没有读取 token 响应体，因此这里只能确认 HTTP 401，不能从本轮数据确认其 `code`。两次加载后独立复核账号仍为 `enabled=false`、`use_count=0`，临时脚本已删除。

## Cookie 单份注入假设实验

### 假设与方法

新的强假设是：`engine.py::_apply_cookies` 对每个名称分别用 `domain=.muse.ai` 和 `domain=muse.ai` 注入，会产生同名的 domain cookie 与 host-only cookie；后续轮换可能只覆盖其中一份，旧值继续随请求发送并导致 token 401。另一个子假设是 `__Host-` cookie 因携带 Domain 而完全缺失。

- Y1：新建隔离上下文，仅在 `about:blank` 中按现有 `_apply_cookies` 方式注入，不导航 muse.ai；用 `Network.getCookies` 只记录名称、份数、domain、由 domain 前导点推导的 host-only、path、secure。
- Y2：另建隔离上下文，每个 cookie 只用 `url=https://muse.ai/` 注入一次，不传 domain；同样读取无值元数据。
- Y3：再建隔离上下文，使用 Y2 方式注入后加载 `/thread/new` 一次。这是账号第 4/4 次、也是最后一次页面加载；没有生成、点击或追加重试。

CDP 的 cookie 结果没有单独的 `hostOnly` 字段，报告中的 host-only 根据 domain 是否以 `.` 开头推导：`muse.ai` 为 host-only，`.muse.ai` 为 domain cookie。

### Y1：现有双 domain 注入

账号存储中共有 14 个 cookie 名称。结果如下：

- 13 个普通名称都出现两份：一份 `.muse.ai` domain cookie，加一份 `muse.ai` host-only cookie；两份均为 `path=/`、`secure=true`。
- 重复名称为：`__stripe_mid`、`__stripe_sid`、`_fbp`、`datr`、`dpr`、`hatch_gw`、`hatch_native_auth_device`、`hatch_native_auth_temp`、`hatch_sess`、`hatch_vml`、`layout_state`、`theme`、`wd`。
- 输入中唯一的 `__Host-` 名称为 `__Host-hatch_one_tap`。其 `.muse.ai` 写入被 Chromium 拒绝，但 `domain=muse.ai` 写入被接受并显示为一份 host-only cookie，`path=/`、`secure=true`。
- 14 个输入名称最终全部存在；因此“普通 cookie 重复”成立，但“`__Host-` cookie 完全缺失”不成立。

### Y2：单份 host-only 注入

- 14/14 个输入名称均存在，全部只有一份。
- 所有条目都显示为 `domain=muse.ai`、host-only、`path=/`、`secure=true`。
- `__Host-hatch_one_tap` 存在；没有注入拒绝，也没有重复名称。

Y1/Y2 可重复、无需页面加载，构成了确定性的 cookie jar 差分：现有实现确实制造普通 cookie 双份，Y2 注入方式可以完全消除双份。

### Y3：最后一次页面加载

Y3 已按 Y2 的单份 host-only 方式注入并完成一次 60 秒页面观察。浏览器级采集进入了非 200 token 响应体的有限读取队列；为避免输出 token，只尝试提取 `code`。部分响应体已被 Chromium 回收，逐项读取完成后，远端脚本正常结束并删除临时文件，但 Railway SSH 客户端没有返回最终 JSON；本地连接回收后也没有留下可恢复的 stdout。

因此下列字段不能在不违反 4 次加载上限的前提下重新取得，报告不作推测：

- `/api/session`、wake、`/api/hatch/token` 的完整状态计数，以及是否曾出现 token 200；
- token 错误 `code`；
- 页面结束后 `hatch_vml` / `hatch_sess` 等是否再次形成重复；
- 本次 cookie 回写的 HTTP 状态码。

脚本的控制流在销毁上下文前执行了 `Network.getCookies` 与管理接口回写；事后只读复核确认账号仍为 `enabled=false`、`use_count=0`，账号备注保持“已更新 cookie”，临时脚本已删除。由于最终状态码丢失，不能把备注单独当成本次回写 HTTP 200 的证明。

### Cookie 假设结论

**结论：注入重复现象成立，但“重复导致 token 401、单份注入可恢复 token 200”无法确认。**

Y1 证明现有实现会制造两种作用域的同名普通 cookie；Y2 证明单份 host-only 注入能消除重复并正确保留 `__Host-hatch_one_tap`。但任务约定只有 Y3 明确取得 token 200 才修改代码，而 Y3 最终结果不可恢复，也不能再加载页面复验。因此本分支不修改 `engine.py`、`read_cookies` 或 `_report_page_cookies`，PR 继续保持文档实验性质。

## 结论与风险

本次只能得出“无法确认”：

1. 没有 token 200 成功基线，无法比较空白上下文与恢复 IndexedDB 后的差异。
2. 补充实验确认 token HTTP 401，但没有读取响应体，不能据此认定其 `code` 为 `hatch_vm_auth_no_match`，也不能把失败归因于浏览器缺少 CVM 密钥。
3. IndexedDB 为空只说明本次上下文在观察窗口内没有建立这些数据库，不能说明用户原浏览器是否持有 CVM 恢复状态。
4. 浏览器级事件确认 `/api/session` HTTP 200、wake HTTP 200 和 token HTTP 401，说明页面确实进入了工作区连接流程；原 X1 的页面级观察方法不完整。
5. 现有 cookie 注入会产生 13 个普通名称的 domain/host-only 双份；`__Host-hatch_one_tap` 并未缺失。单份注入能修正 cookie jar 形态，但最后一次 Y3 遥测丢失，无法证明它能修复 token。

如果后续账号能在同一生产出口稳定取得 token 200，应沿用本任务的 A/B/C 对照，并保持最多 4 次加载：X1 A、X2 B、X3 C 的同源引导页与应用页。只有当“空白 B 失败、恢复 A 的 `hatch-cvm-*` 后 C 成功”可重复出现时，才有证据考虑每账号持久化 BrowserContext / 用户数据目录，或让用户浏览器在安全通道中连同 IndexedDB 一起导出；在此之前不建议扩大凭据持久化范围。

## 离线自测

- `python tests/test_*.py`：39/39 个独立脚本通过，0 失败。
- `node tests/test_admin_api_error_messages.mjs`：通过。
- Python 测试使用 `/tmp` 虚拟环境安装现有 `requirements.txt`；需要真实 Chromium 的测试通过临时 `google-chrome` 包装器调用本机 Google Chrome。没有修改项目依赖。
