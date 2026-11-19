# 2026-11-16 “每个账号只能成功一次”公开资料与代码调研

## 结论摘要

**公开资料没有直接证明 `hatch_vm_auth_no_match` 是销毁 BrowserContext 后丢失 `hatch-cvm-*` IndexedDB 所致，但现有证据强烈支持“客户端状态生命周期不匹配”是首要假设。** 置信度为中高，仍需用新账号连续完成第 1、2、3 条视频来实证。

关键依据：

1. 用户观察具有很强的状态边界特征：同一批新账号都在首次成功、第二次开始稳定失败；账号在用户自己的长期浏览器里持续正常。账号、Cookie 和出口本身不能很好解释这个整齐的一次性边界，而“首次绑定状态只留在随后被销毁的上下文”可以。
2. Muse 前端公开 bundle 中的 `hatch-cvm-credentials`、`hatch-cvm-provisioning`、`hatch-cvm-replacement` 会按 `ownerId`、`sessionBindingId`、`envId` 保存 CVM 恢复/置换状态；当前 `engine.py` 每个任务创建无痕 BrowserContext，结束即销毁，只回存 Cookie，必然丢掉 IndexedDB、localStorage、Service Worker 和 Cache Storage。
3. 找到的 Muse 浏览器自动化项目中，`magpie-muse-web` 明确为每账号创建一次并长期保留 BrowserContext 和主页；`muse_cli` 也为每账号保留上下文、默认同账号串行，并在任务后把浏览器状态原子写盘、重启后恢复。两者都避免了本仓库“每任务新建且销毁账号上下文”的做法。
4. Playwright 官方从 1.51 起明确支持 `storageState({ indexedDB: true })`，并指出默认快照**不含 IndexedDB**。`muse_cli` 虽使用 Playwright 1.64.1，但调用无参数 `StorageStateAsync()`，测试只覆盖 Cookie/localStorage，因此不能作为已保存 `hatch-cvm-*` 的证据，反而提示实现时必须显式打开 IndexedDB。
5. 公开社区只找到一条完全相同错误码的报告：`/api/session` 能返回 VM，`/api/hatch/token` 持续 401 `hatch_vm_auth_no_match`。该帖子没有给出浏览器状态根因或可复现修复；上游 `czg86389-hub/muse2api` 截至 2026-11-16 14:37 CST 也没有同类 issue 或修复。

**推荐采用“两阶段 C”：先用 B（同账号长期 BrowserContext）做因果验证，确认后落地 C（账号级、含 IndexedDB 的加密浏览器状态快照）作为耐重启方案。** A（每账号持久 user-data-dir）保真度最高但在 8 GB 内存、约 4.6 GB 数据卷上扩展性差，保留为 C 无法可靠恢复复杂记录时的兜底；仅长期保留上下文的 B 不能跨 Railway 重启，不应作为最终方案。

## 范围、时间与限制

- 调研时间：2026-11-16，最后检查上游时间为 14:37 CST。
- 只读取本仓库代码、公开网页和公开 GitHub 仓库；没有访问生产服务，没有登录任何账号，没有调用 muse.ai `/api/*`，没有生成或付费调用。
- 搜索了任务书列出的英文/中文关键词，并对 GitHub 做代码搜索。精确的三个 `hatch-cvm-*` 名称和 `sessionBindingId` 没有找到独立公开讨论；搜索结果主要来自 Muse 前端静态分析、同类项目代码和浏览器自动化官方文档。
- 下文的内存/磁盘数字是容量规划估算，不是本仓库在 Railway 上的实测值；上线前必须压测。

## 公开网页调研

### Muse / Meta 官方信息

| 来源（访问日 2026-11-16） | 日期 | 要点 |
|---|---:|---|
| [Meta：Introducing Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/) | 2026-09 | 每个用户的 Muse 运行在独立云端电脑中；官方称未来的 Confidential VM 会由“只有用户持有”的密钥加密整个 VM。该表述支持客户端密钥对 CVM 可用性很重要，但没有说明 Web 客户端如何跨设备恢复密钥。 |
| [Muse：How We Built Safety Into Muse](https://muse.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) | 2026-09 | Web UI、iOS、Android 客户端通过安全传输直接连接用户 VM；文中称 Confidential VM 当时仍是小范围测试、尚待正式推出。不能把当前 bundle 中的 CVM 代码等同于所有账号已经启用该功能。 |
| [Meta Engineering：WhatsApp Private Processing](https://engineering.fb.com/2025/04/29/security/whatsapp-private-processing-ai-tools/) | 2025-04-29 | Meta 的另一套 CVM 设计让设备和预选 TEE 持有端到端会话密钥，并采用远程证明、失败关闭。它说明“客户端密钥丢失后认证失败”在同类架构上合理，但不是 Muse 接口契约，本文只将其作为架构旁证。 |

没有找到 Muse / Meta 官方关于“一账号只能一台设备”、`hatch_vm_auth_no_match`、`session_binding_id` 或浏览器 IndexedDB 恢复流程的说明。官方同时宣称 iOS、Android、Web 都能作为客户端，因此不能据公开文案推导“账号永久只允许一个设备”；更合理的可能是每个客户端需要一套可恢复/可置换的绑定状态。

### 社区结果

| 来源（访问日 2026-11-16） | 日期 | 要点 |
|---|---:|---|
| [LINUX DO：获取到的 Muse 节点，不能用作 AI](https://linux.do/t/topic/3018489) | 2026-10-13 | 用户报告 `/api/session` 正常返回 VM，但 `/api/hatch/token` 一直 401 `hatch_vm_auth_no_match`，VM 为 SUSPENDED；讨论没有确认 IndexedDB 根因，也没有可验证的修复。 |
| [V2EX：muse.ai 注册方案](https://www.v2ex.com/t/1245571) | 2026-09-29 | 讨论把注册失败可能性归因于地区、IP、账号/设备环境，另有用户用指纹浏览器和家宽代理注册多个账号。内容是经验讨论，不能证明生成阶段的 VM 客户端绑定机制。 |
| [Reddit：Muse bricked please help](https://www.reddit.com/r/MetaAI/comments/1x1g49f/muse_bricked_please_help/) | 2026-10 | 有用户称同账号在 App、Web 和新无痕窗口均无法连接；这说明服务端 VM 状态也可能造成跨客户端故障，不能把所有 no-match 都归因于本地存储。帖子没有错误码和修复结果。 |
| [V2EX：把 Muse VM 变成 VPS](https://www.v2ex.com/t/1245998) | 2026-10-01 | 社区观察到 VM 会休眠/重建，而 `/home/hatch/workspace` 持久化。它解释了 SUSPENDED/唤醒现象，但没有涉及 Web 客户端认证状态。 |

对 linux.do、V2EX、Reddit、X 及通用搜索引擎检索 `muse2api 只能用一次`、`muse 反代 第二次 失败`、`muse.ai only works once`、`muse.ai one device`，没有找到与“首条成功、第二条必败”同样模式且带修复验证的报告。X 搜索没有返回可核验的一手帖子。

### 浏览器状态的官方能力与约束

| 来源（访问日 2026-11-16） | 要点 |
|---|---|
| [Playwright Authentication](https://playwright.dev/docs/auth) | `storageState` 默认不包含 IndexedDB；应用把认证材料放在 IndexedDB 时必须显式设置 `indexedDB: true`。官方也建议并行 worker 使用不同账号，避免共享账号修改服务端状态。 |
| [Playwright BrowserContext API](https://playwright.dev/docs/api/class-browsercontext#browser-context-storage-state) | IndexedDB 快照能力自 1.51 加入；当前 API 还能选择 OPFS 和虚拟 WebAuthn 凭据。C 方案应锁定最低版本并对实际 `CryptoKey`/记录类型做往返测试。 |
| [Playwright BrowserType API](https://playwright.dev/java/docs/api/class-browsertype#browser-type-launch-persistent-context) | `launchPersistentContext(userDataDir)` 使用磁盘持久状态，且浏览器不允许多个实例同时使用同一 user-data-dir。A 方案必须把“每账号目录锁”作为正确性约束，而不只是性能优化。 |
| [ChromeDriver capabilities](https://developer.chrome.com/docs/chromedriver/capabilities#h.p_ID_106) | Chrome 官方支持用 `--user-data-dir` 创建/复用自定义资料目录；路径不存在时会创建新 profile。不能复用用户日常 Chrome 的默认资料目录，应使用专用目录。 |
| [MDN：structured clone](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Structured_clone_algorithm) | IndexedDB 使用 structured clone，`CryptoKey` 属于可序列化类型。它提高了 C 可行性，但不能保证任意 CDP/第三方序列化器都能无损搬运密钥，仍需浏览器实测。 |

## GitHub 项目代码对比

### `JohnWangggg/magpie-muse-web`

检查版本：[0d74d859（2026-11-11）](https://github.com/JohnWangggg/magpie-muse-web/commit/0d74d859dacbe0c56a753c94f3de3ac4fbe97891)。

- [`engine/muse.mjs`](https://github.com/JohnWangggg/magpie-muse-web/blob/0d74d859dacbe0c56a753c94f3de3ac4fbe97891/engine/muse.mjs) 的注释明确写着账号 BrowserContext “created once and kept”，同一账号保留一个主页，让 VM 连接保持在线；切换对话复用该页，而不是每任务销毁上下文。
- 它仍使用单 Chromium、每账号一个 `Target.createBrowserContext`；浏览器退出后这些上下文全部丢失。浏览器启动时传 `temporary: true`，[`engine/browser.mjs`](https://github.com/JohnWangggg/magpie-muse-web/blob/0d74d859dacbe0c56a753c94f3de3ac4fbe97891/engine/browser.mjs) 会创建并在退出时删除 `run-*` profile，所以它是 B 的公开实例，不是耐重启的 A。
- 账号对象只有一个 `home` 页面；`opening` promise 合并并发打开，但 `chat()` 本身未见显式账号互斥。若外围没有串行器，同账号并发仍可能争用同一页面；不能原样照搬。

### `thanhtaiinguyen/muse_cli`

检查版本：[908cd4d6（2026-11-02）](https://github.com/thanhtaiinguyen/muse_cli/commit/908cd4d6770c6d70a9d23ca32062ccf000967e2a)。

- [`BrowserDriver.cs`](https://github.com/thanhtaiinguyen/muse_cli/blob/908cd4d6770c6d70a9d23ca32062ccf000967e2a/src/Muse2Api/BrowserDriver.cs) 采用一个 Chromium、每账号一个长期 BrowserContext、每个 tab 跨请求复用；注释明确说明默认 `MUSE2API_ACCOUNT_MAX_CONCURRENCY=1` 保证同账号串行。
- 创建上下文有账号级 `SemaphoreSlim`，tab 分配有锁和 Busy 标志。这个模型与本仓库已有 `ACCOUNT_POOL.busy_accounts` 很接近，说明 B/C 不需要取消现有账号租约。
- 每次请求结束调用 `SaveSession`：先读取最新 Cookie，再将 `context.StorageStateAsync()` 写到账号绑定的文件；[`BrowserSessionStore.cs`](https://github.com/thanhtaiinguyen/muse_cli/blob/908cd4d6770c6d70a9d23ca32062ccf000967e2a/src/Muse2Api/BrowserSessionStore.cs) 用账号 ID 定位、用会话 Cookie 哈希防止错配、原子写入，并在 Windows 用 DPAPI 保护私密数据。
- 它使用 Playwright 1.64.1，却没有给 `StorageStateAsync` 传 `IndexedDB=true`；[`SessionPersistenceTests.cs`](https://github.com/thanhtaiinguyen/muse_cli/blob/908cd4d6770c6d70a9d23ca32062ccf000967e2a/tests/Muse2Api.Tests/SessionPersistenceTests.cs) 只验证 Cookie/localStorage。因此这是 C 的有用骨架，但尚未覆盖本问题最关键的 `hatch-cvm-*`。

### `Bao-qing/muse-im-bridge`

检查版本：[ee62a72e（2026-11-15）](https://github.com/Bao-qing/muse-im-bridge/commit/ee62a72e3aebc86f1f0ac1a3749ad344480edb09)。

- [`token_manager.py`](https://github.com/Bao-qing/muse-im-bridge/blob/ee62a72e3aebc86f1f0ac1a3749ad344480edb09/muse_bridge/muse/token_manager.py) 不驱动网页，而是把 gateway token / notary token 原子保存到 `.mint.json`（0600），过期或握手拒绝时刷新。
- 遇到 `hatch_vm_auth_no_match` 时，它重新从页面 HTML 发现 VM ID 后只重试一次；重复 mismatch 被视为可恢复的上游/VM 错误，不把 Cookie 判死。该 D 路线可能减少重复绑定，但它没有保存 `hatch-cvm-*`，也没有证据证明可解决“首次绑定密钥丢失”。

### 其他检查结果

- [`sanhaji182/lintasan`](https://github.com/sanhaji182/lintasan/blob/251fd7be99147d51ab39a9d56228e73ea5b49649/internal/server/muse_browser.go) 的远程登录流程使用临时 `Target.createBrowserContext`，取得 Cookie 后销毁，只适合导入 Cookie，不是多次任务状态保存方案。
- GitHub 代码搜索还检查了 `dots2api`、`9router`、`muse-bridge`、`muse_cli`、`magpie-muse-web` 及 muse2api forks。没有发现 Muse 项目显式用 `indexedDB: true` / `setIndexedDB(true)` 导出并恢复 `hatch-cvm-*`；也没有发现按账号使用 `launchPersistentContext` 的 Muse 反代实现。

## 上游 `czg86389-hub/muse2api` 状态

截至 2026-11-16 14:37 CST：

- [issues / PR 列表](https://github.com/czg86389-hub/muse2api/issues) 中没有标题或正文公开命中“只能成功一次”、`hatch_vm_auth_no_match`、IndexedDB 或持久 BrowserContext 的报告。
- 最新主分支提交为 [19db32a3](https://github.com/czg86389-hub/muse2api/commit/19db32a3d6ef50dc87567a8ee0e35dd50c8f7837)，时间 2026-11-16 01:16 UTC，内容是更新提示和媒体 UI；此前 v1.6.11 合并 Cookie 轮换、导入、排队预算等修复，没有浏览器状态持久化。
- 当前日期就是 11 月 16 日，因此不存在可检查的“11-16 之后”自然日提交；按时间戳检查到上述时点，没有发现当日后续修复。

## 与本仓库 `engine.py` 的差异

当前生命周期为：

1. `MuseEngine.start()` 启动一个带全局 `cfg.profile_dir` 的 Chromium。
2. 每个任务线程在 `_open_page()` 调用 `Target.createBrowserContext`，为账号创建无痕上下文；只向该上下文写 Cookie。
3. `ensure_page()` 导航 `/thread/new`，任务结束后各入口都会调用 `close_current_page()`。
4. `_close_page()` 在销毁前只用 `Network.getCookies` 回存 Cookie，随后 `Target.disposeBrowserContext`；没有保存 localStorage、IndexedDB、Service Worker 或 Cache Storage。
5. `AccountPoolManager` 已用 `busy_accounts` 保证同一账号不会被两个任务同时租用，多账号可并行。这一互斥应继续覆盖状态装载、使用、快照和清理的完整事务。

全局 `--user-data-dir` 只保存默认 profile；任务使用的是临时 BrowserContext，所以不能让账号站点存储跨 `disposeBrowserContext` 存活。换句话说，当前命令行已有 user-data-dir 并不等于 A，也不能修复本问题。

## 方案评估

容量估算假设：8 GB 内存、约 4.6 GB 数据卷；以下范围是 Chromium 常见量级的保守规划值，需在 Railway 以实际账号数和页面负载复测。

| 方案 | 跨服务重启 | 内存 / 磁盘 | 并发与互斥 | 复杂度与可验证性 | 安全性 | 结论 |
|---|---|---|---|---|---|---|
| A：每账号独立持久 user-data-dir + Chromium 进程 | 是，保留最完整（IDB、SW、Cache 等） | 每个活跃浏览器粗估 300–800 MiB；8 个并发约 2.4–6.4 GiB，逼近整机上限。profile 含缓存后粗估 50–300 MiB/账号，20 个账号可能 1–6 GB，可能超过数据卷 | 每目录只能被一个 Chrome 使用；账号租约外还需跨进程/重启文件锁。多账号可并行，但必须限制活跃进程并 LRU 关闭 | 对现有单 CDP 端口/单 browser 重构最大；保真度最高，验收最直观 | profile 是完整凭据仓；目录 0700、文件最小权限、卷级加密/应用加密、删除账号即安全擦除；严禁打包下载或入日志 | C 无法无损恢复密钥时的兜底，不首选 |
| B：单 Chromium，每账号长期 BrowserContext / 页面 | 否；Chromium 或服务重启全部丢失 | 每个空闲上下文/页面粗估 30–150 MiB；账号多时仍会线性增长，磁盘几乎不增加 | 继续使用 `busy_accounts`；账号 ID → context/page 映射需加锁。空闲超时只能关页面，若销毁 context 就再次丢绑定 | 最贴近 `magpie-muse-web`，改动中等；能最快验证“第 1 次建立、第 2/3 次复用” | 密钥只在内存，泄露面较小；账号删除/失效时立即销毁 context | 适合作为因果验证和 C 的热缓存，不是最终耐重启方案 |
| C：任务后导出、下次恢复账号状态（显式含 IndexedDB） | 是 | 运行时维持现有每任务上下文；快照通常应为 KB–数 MB/账号，不含大缓存时最适合 4.6 GB 卷。必须设单文件/总量上限并监控 | 现有账号租约必须覆盖“加载 → 任务 → 原子快照”；同账号不得并行。多进程部署还需文件锁或单写者 | 中高。Playwright 1.51+ 有官方往返能力；当前自研 CDP 要么引入该能力，要么用同源受控页逐库恢复。可以用合成 IDB + `CryptoKey` 离线测试，再做新账号 1/2/3 验收 | 快照包含 VM 恢复密钥，应视同 Cookie：账号派生文件名、0600/0700、应用层 AEAD 或平台 KMS、原子写、身份哈希绑定、删除/换登录即清除；绝不输出值 | **推荐的耐重启目标方案** |
| D1：只持久化 gateway token/notary token | 是，但只到 token 过期/撤销 | 很小 | 每账号刷新锁；拒绝时只允许一次有界刷新 | 实现相对小，但本仓库依赖网页，注入/复用 token 仍需新设计；无法恢复 CVM 私钥 | 同样是高敏凭据，需加密和过期清理 | 可作为优化，不能替代 C |
| D2：只保存 Cookie/localStorage（`muse_cli` 当前做法） | 是 | 很小 | 同 C | 已有公开实现与测试，但遗漏 IndexedDB；若首要假设正确则仍会失败 | 高敏状态，需加密 | 不足以解决本问题 |

### C 的具体实现形态（供后续任务书使用）

不在本任务改代码；建议后续实现按以下边界设计：

1. 在 `/app/data/browser-state/` 为每账号保存一个版本化加密快照，文件名只用账号 ID 的 SHA-256；元数据含 schema 版本、账号会话 Cookie 哈希、创建/更新时间，不保存邮箱或标签。
2. 快照至少包含 muse.ai 的 Cookie、localStorage、`hatch-cvm-credentials`、`hatch-cvm-provisioning`、`hatch-cvm-replacement`；`sessionStorage` 中 `hatch_saved_account_registered` 若验证为必要，则通过 init script 单独恢复。不要默认收集其他域名。
3. 优先采用 Playwright 1.51+ 等经过浏览器真实往返验证的 `storageState(indexedDB=true)` 能力。若继续纯 CDP，不能只 JSON.stringify 记录：必须覆盖 `CryptoKey`、ArrayBuffer、Date 等 structured-clone 类型，并在真实 Chromium 离线夹具中验证；可先拦截一个 muse.ai 同源导航并返回空白页，在任何 Muse 应用脚本执行前完成 IDB 写入，再放行真实导航。
4. `ACCOUNT_POOL` 租约必须从读取快照前开始，到 Cookie 回写和状态快照原子替换后结束。部署若可能多进程/多副本，还需账号级文件锁或外部租约；仅线程内 set 不够。
5. 新账号无快照时正常创建空上下文；只有页面稳定取得 token/输入框后才发布首次快照。失败任务可以更新已经存在的 Cookie，但不能用空/半写快照覆盖最后一个成功版本。
6. 账号删除、核心会话 Cookie 身份变化、管理员明确重新导入不同登录时删除旧快照；普通 Cookie 轮换不能误删绑定状态。保留一个加密的 last-known-good 文件并原子替换，失败时回退一次，禁止无限重试。
7. 指标只记录账号脱敏 ID、快照版本、字节数、装载/保存成功与错误分类；不得记录 Cookie、IDB key/value、token、VM 完整 ID。加总量水位清理，但不能像媒体一样按年龄随意删仍在用账号的快照。

## 推荐验证顺序与验收

### 阶段 0：离线能力验证

1. 用本地测试页面建立三个同名 `hatch-cvm-*` IndexedDB，写入普通对象、ArrayBuffer 和不可导出的 `CryptoKey` 夹具；保存、关闭浏览器、重开并恢复。
2. 断言数据库版本、object store/index、键、记录数和密钥可执行一次预期加解密操作；不在测试输出密钥材料。
3. 验证快照文件 0600、目录 0700、原子替换、损坏文件不覆盖 last-known-good、换账号/换会话哈希不能误加载。

### 阶段 1：B 只做因果验证

选一个**全新导入且官网正常**的账号，在同一长期 BrowserContext、同一账号严格串行完成 3 条视频：

- 第 1 条成功后不销毁 context；第 2、3 条必须成功。
- 记录无敏感值的 token HTTP 状态和错误分类；若仍在第 2 条得到 `hatch_vm_auth_no_match`，首要假设被削弱，应停止 C 上线并转查服务端 VM replacement / session binding。
- 同时做对照：另一个新账号第 1 条成功后销毁 context，再开新 context 做第 2 条。若对照失败而长期 context 成功，才形成强因果证据。

### 阶段 2：C 耐重启验收

1. 新账号第 1 条视频成功并落盘快照；显式关闭 context，创建新 context 恢复快照，第 2 条成功。
2. 重启 Chromium，第 3 条成功；再重启整个服务/容器，第 4 条成功，证明跨进程和跨 Railway 重启。
3. 两个账号并行，各自连续 3 条成功；同一账号两个并发请求必须排队，不能同时操作快照或上下文。
4. 账号 A/B 的快照交换测试必须失败关闭且不访问 Muse；删除 A 后快照立即删除，B 不受影响。
5. 测试损坏快照、磁盘满、写入中断、Cookie 正常轮换、重新导入不同登录；任何情况下都不能把敏感值写日志，也不能大量重试上游。
6. 记录峰值 RSS、每账号快照 p50/p95、总磁盘占用和恢复耗时。若单账号快照异常增大，拒绝写入并保留 last-known-good。

验收门槛应写成结果而不是“页面能打开”：同一新账号第 1、2、3 条（跨 context）全部生成成功，重启后第 4 条仍成功，期间 `/api/hatch/token` 不出现 `hatch_vm_auth_no_match`；多账号并行时没有串号、错载或同账号并发。

## 未决问题与风险

1. 目前没有一次“成功 token 后读取 `hatch-cvm-*` 记录数/类型”的安全实验，因此不知道真正必要的库、记录和 `CryptoKey.extractable` 属性；这决定 C 是否可由 storageState 无损完成。
2. `hatch_vm_auth_no_match` 也可能来自 VM replacement、旧 VM ID、SUSPENDED 状态或服务端 session binding 撤销。`Bao-qing/muse-im-bridge` 的“重新发现 VM ID 后有界重试一次”值得作为独立对照，但不能与状态恢复同时上线，否则难以判断因果。
3. 官方文档称 Confidential VM 尚在逐步推出，账号可能分批进入不同路径。验收至少要覆盖一个出现过“一次成功”模式的新账号，不能用未启用 CVM 的账号得出阴性结论。
4. Railway 数据卷约 4.6 GB，没有空间保存无限 profile/cache。即使选择 C，也必须先测快照分布并设配额；若转 A，则必须限制活跃账号和清理可重建缓存，绝不能清理仍在用的凭据状态。
5. 浏览器状态文件的敏感级别不低于 `accounts.json`。任何后续实现都需要单独安全审查、备份策略和删除语义；不能把快照加入 git、PR artifact、测试夹具或诊断包。

