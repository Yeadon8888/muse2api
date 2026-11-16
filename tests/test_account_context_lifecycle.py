"""账号长期 BrowserContext 生命周期离线回归；不访问 muse.ai。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine as engine_mod  # noqa: E402


class FakeBrowser:
    def __init__(self):
        self.next_context = 0
        self.disposed = []
        self.targets = {}
        self.storage = {}

    def send(self, method, params=None):
        params = params or {}
        if method == "Target.createBrowserContext":
            self.next_context += 1
            context_id = f"ctx-{self.next_context}"
            self.storage[context_id] = {}
            return {"result": {"browserContextId": context_id}}
        if method == "Target.createTarget":
            target_id = f"target-{len(self.targets) + 1}"
            self.targets[target_id] = params["browserContextId"]
            return {"result": {"targetId": target_id}}
        if method == "Target.disposeBrowserContext":
            self.disposed.append(params["browserContextId"])
            return {"result": {}}
        if method == "Target.closeTarget":
            self.targets.pop(params["targetId"], None)
            return {"result": {}}
        return {"result": {}}


class FakePage:
    browser = None

    def __init__(self, url, timeout=180):
        self.target_id = url.rsplit("/", 1)[-1]
        self.context_id = self.browser.targets[self.target_id]
        self.closed = False

    def send(self, method, params=None):
        if method == "Network.getCookies":
            return {"result": {"cookies": []}}
        return {"result": {}}

    def js(self, expression, *args, **kwargs):
        if expression == "IDB_WRITE":
            self.browser.storage[self.context_id]["indexeddb-record"] = "kept"
            return True
        if expression == "IDB_READ":
            return self.browser.storage[self.context_id].get("indexeddb-record")
        if "something went wrong" in expression.lower():
            return False
        if "querySelector('textarea')" in expression:
            return True
        return False

    def close(self):
        self.closed = True


def build_engine(home, keep=True, limit=8):
    cfg = SimpleNamespace(
        profile_dir=home,
        download_dir=str(Path(home) / "downloads"),
        cdp_port=19210,
        login_wait=1,
        keep_account_contexts=keep,
        max_account_contexts=limit,
    )
    instance = engine_mod.MuseEngine(cfg)
    instance.browser = FakeBrowser()
    FakePage.browser = instance.browser
    instance._last_http_renew = {name: 10**20 for name in ("a", "b", "c")}
    return instance


def ready_patches(instance):
    clock = [0.0]

    def fast_time():
        clock[0] += 1.0
        return clock[0]

    return (
        patch.object(engine_mod, "CDP", FakePage),
        patch.object(instance, "_apply_cookies"),
        patch.object(instance, "_wait_ws_ready", return_value=True),
        patch.object(instance, "_report_page_cookies"),
        patch.object(engine_mod.time, "time", side_effect=fast_time),
    )


with tempfile.TemporaryDirectory(prefix="m2a-context-") as home:
    engine = build_engine(home)
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        first = engine.ensure_page({}, account_id="a")
        first_context = engine.current_context_id
        first.js("IDB_WRITE")
        engine.close_current_page()
        second = engine.ensure_page({}, account_id="a")
        assert second is first
        assert engine.current_context_id == first_context
        assert second.js("IDB_READ") == "kept", "同账号第二次任务丢失 IndexedDB 模拟记录"
        engine.close_current_page()

        other = engine.ensure_page({}, account_id="b")
        assert engine.current_context_id != first_context
        assert other is not first
        engine.close_current_page()

    assert engine.retained_context_count() == 2
print("PASS: 同账号复用上下文与 IndexedDB，不同账号隔离")


with tempfile.TemporaryDirectory(prefix="m2a-context-auth-") as home:
    engine = build_engine(home)
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
            patch.object(engine, "_is_crash_page", return_value=True), \
            patch.object(engine, "_crash_page_exception",
                         return_value=engine_mod.MuseAuthError("fixture")):
        try:
            engine.ensure_page({}, account_id="a")
        except engine_mod.MuseAuthError:
            pass
        else:
            raise AssertionError("认证崩溃未抛出 MuseAuthError")
    assert engine.retained_context_count() == 0
    old_context = engine.browser.disposed[-1]
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
            patch.object(engine, "_is_crash_page", return_value=False):
        engine.ensure_page({}, account_id="a")
        assert engine.current_context_id != old_context
        engine.close_current_page()
print("PASS: 认证失败销毁上下文并在下次重建")


with tempfile.TemporaryDirectory(prefix="m2a-context-workspace-") as home:
    engine = build_engine(home)
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4], \
            patch.object(engine, "_is_crash_page", return_value=True), \
            patch.object(engine, "_crash_page_exception",
                         return_value=engine_mod.MuseWorkspaceUnavailable("fixture")):
        try:
            engine.ensure_page({}, account_id="a")
        except engine_mod.MuseWorkspaceUnavailable:
            pass
        else:
            raise AssertionError("工作区异常未抛出")
    assert engine.retained_context_count() == 1
    assert not engine.browser.disposed
print("PASS: 工作区不可用保留账号上下文")


with tempfile.TemporaryDirectory(prefix="m2a-context-lru-") as home:
    engine = build_engine(home, limit=2)
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        engine.ensure_page({}, account_id="a")
        context_a = engine.current_context_id
        engine.close_current_page()
        engine.ensure_page({}, account_id="b")
        context_b = engine.current_context_id
        engine.close_current_page()
        with engine._contexts_lock:
            engine._account_contexts["b"]["in_use"] = True
        engine.ensure_page({}, account_id="c")
        engine.close_current_page()
    assert context_a in engine.browser.disposed
    assert context_b not in engine.browser.disposed
    assert set(engine._account_contexts) == {"b", "c"}
print("PASS: LRU 淘汰最旧空闲上下文且不关闭使用中的上下文")


with tempfile.TemporaryDirectory(prefix="m2a-context-off-") as home:
    engine = build_engine(home, keep=False)
    patches = ready_patches(engine)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        engine.ensure_page({}, account_id="a")
        first_context = engine.current_context_id
        engine.close_current_page()
        engine.ensure_page({}, account_id="a")
        second_context = engine.current_context_id
        engine.close_current_page()
    assert first_context != second_context
    assert engine.browser.disposed == [first_context, second_context]
    assert engine.retained_context_count() == 0
print("PASS: MUSE2API_KEEP_ACCOUNT_CONTEXTS=0 恢复每任务销毁")
