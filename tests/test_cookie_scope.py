"""用真实 Chromium 验证 muse.ai cookie 单份作用域；只访问本地页面。"""
import importlib.util
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cdp import CDP  # noqa: E402

CHROME = (os.environ.get("MUSE2API_CHROMIUM") or os.environ.get("CHROME_BIN")
          or shutil.which("chromium") or shutil.which("google-chrome")
          or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<!doctype html><title>cookie scope fixture</title>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def cookies_for_muse(page):
    reply = page.send("Network.getCookies", {"urls": ["https://muse.ai/"]})
    return reply["result"]["cookies"]


with tempfile.TemporaryDirectory(prefix="muse-cookie-scope-", dir=Path.home()) as home:
    os.environ.update(MUSE2API_HOME=home, MUSE2API_PROFILE_ROOT=home)
    spec = importlib.util.spec_from_file_location("cookie_scope_engine", ROOT / "engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fixture_url = f"http://127.0.0.1:{server.server_port}/"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        cdp_port = sock.getsockname()[1]
    log = open(Path(home) / "chromium.log", "wb")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-background-networking", "--remote-allow-origins=*",
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={Path(home) / 'browser'}", "about:blank",
    ], stdout=log, stderr=log, start_new_session=True)
    session = requests.Session()
    session.trust_env = False
    page = None
    try:
        for _ in range(150):
            try:
                tabs = session.get(f"http://127.0.0.1:{cdp_port}/json/list", timeout=1).json()
                tab = next(item for item in tabs if item.get("type") == "page")
                page = CDP(tab["webSocketDebuggerUrl"], timeout=15)
                break
            except (requests.RequestException, StopIteration):
                time.sleep(.1)
        assert page, "fixture Chromium did not start"
        page.send("Network.enable")
        page.send("Page.enable")
        page.send("Page.navigate", {"url": fixture_url})

        engine = module.MuseEngine(SimpleNamespace(profile_dir=home, site_url="https://muse.ai/"))
        original = {
            "hatch_vml": "vml-old",
            "hatch_sess": "sess-old",
            "theme": "dark",
            "__Host-hatch_one_tap": "host-old",
        }
        engine._apply_cookies(page, original)
        jar = cookies_for_muse(page)
        by_name = {}
        for cookie in jar:
            by_name.setdefault(cookie["name"], []).append(cookie)
        assert set(by_name) == set(original), by_name.keys()
        assert all(len(items) == 1 for items in by_name.values()), by_name
        for name, items in by_name.items():
            cookie = items[0]
            assert cookie["path"] == "/" and cookie["secure"] is True, cookie
            expected = "muse.ai" if name.startswith("__Host-") else ".muse.ai"
            assert cookie["domain"] == expected, cookie

        # 模拟页面用 Domain=.muse.ai 轮换 hatch_vml：覆盖规范副本，不产生双份。
        page.send("Network.setCookie", {
            "name": "hatch_vml", "value": "vml-new", "domain": ".muse.ai",
            "path": "/", "secure": True,
        })
        rotated = [item for item in cookies_for_muse(page) if item["name"] == "hatch_vml"]
        assert len(rotated) == 1 and rotated[0]["value"] == "vml-new", rotated

        # 即使历史 host-only 副本意外残留，读取与回存也只选择规范 domain 副本。
        page.send("Network.setCookie", {
            "name": "hatch_vml", "value": "vml-stale", "url": "https://muse.ai/",
            "path": "/", "secure": True,
        })
        live = engine.read_cookies(page)
        assert live["hatch_vml"]["value"] == "vml-new", live
        reported = []
        engine.cookie_sink = lambda aid, values, expires: reported.append(values)
        engine._report_page_cookies("fixture-account", page)
        assert reported == [{name: item["value"] for name, item in live.items()}], reported
        assert reported[0]["hatch_vml"] == "vml-new"
        print("PASS cookie scope injection, rotation and canonical readback")
    finally:
        server.shutdown()
        server.server_close()
        if page:
            try:
                page.send("Browser.close")
            except Exception:
                pass
            page.close()
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log.close()
