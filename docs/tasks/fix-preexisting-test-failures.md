# 任务书 01：修复两个长期失败的测试

分支：`fix/preexisting-test-failures` · 负责人：Codex · 审核：Claude
**前置**：`git pull` 后确认 `tests/test_admin_layout.py`、`tests/test_vm_wait.py` 存在，且 `git log` 里有提交 `22ab417`（no-store 管理页）。不满足就停下说明。

## 目标
这两个测试在本分支和上游 v1.6.9 基线上都失败，导致每次全量自测都有"已知失败"，掩盖真正的回归。查清每个失败是**测试本身的问题**还是**代码的问题**，做最小修复，让全量测试干净通过。

当前现象（macOS + 本机 Google Chrome）：
- `python tests/test_admin_layout.py` → `AssertionError: Page overflows the viewport`
- `python tests/test_vm_wait.py` → `IndexError: list index out of range`（脚本读取 `sys.argv[1]` 作为待测 engine 路径，直接运行时没有参数）

## 要做
1. `test_vm_wait.py`：没有参数时默认使用仓库根目录的 `engine.py`（保留传参能力），然后确认测试真正跑通；如果跑通后暴露出 engine 的真实问题，先在 PR 里说明，再修。
2. `test_admin_layout.py`：定位是哪个元素、在哪个视口宽度溢出。区分：
   - 测试环境差异（例如 macOS 滚动条宽度、字体）→ 修测试，使判断与平台无关，但不能放宽到检测不出真实溢出；
   - `admin.html` 真实布局问题（例如最近加的媒体库"再加载"按钮、存储相关文案）→ 只改 `admin.html` 的 CSS/结构，修复溢出。
   在 PR 里写清结论和依据（元素选择器、宽度数值）。
3. 全量运行所有 `tests/test_*.py` 和 `node tests/test_admin_api_error_messages.mjs`。

## 允许 / 禁止
允许：`tests/test_admin_layout.py`、`tests/test_vm_wait.py`、`admin.html`（仅限修复溢出所需的 CSS/结构）。
禁止：`app.py`、`engine.py`、`store.py`、`media_janitor.py`、`config.py`、`Dockerfile`、`requirements.txt`、其他测试文件、`AGENTS.md`、`docs/**`。
必须改范围外的文件时，先停下说明，不要自己扩大范围。

## 验收
- [ ] `python tests/test_vm_wait.py`（不带参数）通过
- [ ] `python tests/test_admin_layout.py` 通过，且对真实溢出仍然敏感（在 PR 里说明怎么确认的，例如临时加一个超宽元素能让它失败）
- [ ] 全量 `tests/test_*.py` 全部通过，PR 列出逐个结果
- [ ] 若改了 `admin.html`：附 375px 和 1440px 宽度的截图

## 自测
- 依赖：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Chromium：`export MUSE2API_CHROMIUM="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`，并在 PATH 上放一个名为 `google-chrome` 的包装脚本 exec 该路径
- 不发起任何真实 muse.ai 调用，不访问生产服务

## 交付
- 自己 `git add -A && git commit`，`git push -u origin fix/preexisting-test-failures`，`gh pr create --base railway-v1.6.9`
- PR 正文：每个失败的根因、改了什么、全量测试结果（命令和输出摘要）、截图、已知问题
- **不要合并，不要 push `railway-v1.6.9`**（push 它会直接部署生产）
