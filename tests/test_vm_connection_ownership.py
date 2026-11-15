"""离线回归：页面拥有 VM wake 流程，失败关闭前仍回存浏览器 cookie。"""
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules["cdp"] = SimpleNamespace(CDP=object, http_json=lambda *args, **kwargs: {})

from engine import MuseEngine, MuseGenerationError  # noqa: E402


class FakePage:
    def __init__(self):
        self.closed = False

    def send(self, method, params=None, timeout=None):
        if method == "Network.getCookies":
            return {"result": {"cookies": [
                {"name": "hatch_sess", "value": "rotated", "expires": 1900000000},
                {"name": "hatch_gw", "value": "new-gateway", "expires": -1},
            ]}}
        return {}

    def js(self, script):
        if "document.body" in script:
            return "Connecting..."
        return False

    def close(self):
        self.closed = True


cfg = SimpleNamespace(
    profile_dir=tempfile.mkdtemp(prefix="m2a-vm-owner-"),
    login_wait=1,
    site_url="https://muse.ai/",
)
engine = MuseEngine(cfg)
page = FakePage()
reported = []
engine.cookie_sink = lambda aid, cookies, expires: reported.append((aid, cookies, expires))

with patch.object(engine, "renew_session_http", return_value={
        "cookies": {"hatch_sess": "before-page"}, "cookies_exp": {}}) as renew, \
     patch.object(engine, "_open_page", return_value=page), \
     patch.object(engine, "_apply_cookies"), \
     patch.object(engine, "_wait_ws_ready", return_value=False), \
     patch.object(engine, "_is_crash_page", return_value=False):
    try:
        engine.ensure_page({"hatch_sess": "stored"}, {}, account_id="acc-fixture")
    except MuseGenerationError:
        pass
    else:
        raise AssertionError("连接超时应失败")

assert renew.call_args.kwargs["wake_vm"] is False, renew.call_args
assert page.closed is True
assert reported and reported[-1][0] == "acc-fixture", reported
assert reported[-1][1] == {"hatch_sess": "rotated", "hatch_gw": "new-gateway"}, reported
assert reported[-1][2] == {"hatch_sess": 1900000000}, reported
print("PASS 页面负责 wake，失败上下文关闭前回存轮换 cookie")


source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
assert "wake_vm=True" not in source, "应用主链路不得发送独立随机 connect_attempt_id 的 VM wake"
print("PASS 生成、保活和预热链路均不再主动 wake VM")
