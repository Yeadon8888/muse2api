"""用本地 HTTP 页面验证 hatch token 捕获与崩溃页分类，不访问 muse.ai。"""
import importlib.util
import json
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

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from cdp import CDP  # noqa: E402

CHROME = (os.environ.get("MUSE2API_CHROMIUM") or os.environ.get("CHROME_BIN")
          or shutil.which("chromium") or shutil.which("google-chrome")
          or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SECRET_TOKEN = "must-never-be-recorded"


class Handler(BaseHTTPRequestHandler):
    response = None

    def do_GET(self):
        if self.path == "/":
            body = b"<main><h2>Something went wrong</h2><button>Try again</button></main>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/hatch/token" and self.response is not None:
            body = json.dumps({**self.response, "token": SECRET_TOKEN}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, *_args):
        pass


with tempfile.TemporaryDirectory(prefix="muse-vm-auth-", dir=Path.home()) as home:
    os.environ.update(MUSE2API_HOME=home, MUSE2API_PROFILE_ROOT=home)
    spec = importlib.util.spec_from_file_location("vm_auth_engine", root / "engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    site = f"http://127.0.0.1:{httpd.server_port}/"

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        cdp_port = sock.getsockname()[1]
    log = open(Path(home) / "chromium.log", "wb")
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                             "--remote-allow-origins=*", "--remote-debugging-port=" + str(cdp_port),
                             "--user-data-dir=" + str(Path(home) / "browser"), "about:blank"],
                            stdout=log, stderr=log, start_new_session=True)
    session = requests.Session()
    session.trust_env = False
    page = None
    try:
        for _ in range(150):
            try:
                tabs = session.get(f"http://127.0.0.1:{cdp_port}/json/list", timeout=1).json()
                tab = next(x for x in tabs if x.get("type") == "page")
                page = CDP(tab["webSocketDebuggerUrl"], timeout=15)
                break
            except (requests.RequestException, StopIteration):
                time.sleep(.1)
        assert page, "fixture Chromium did not start"
        page.send("Page.enable")
        page.send("Runtime.enable")
        engine = module.MuseEngine(SimpleNamespace(profile_dir=home, data_dir=home))
        engine.page = page
        engine._install_hatch_token_hook(page)

        def load(response, transport="fetch"):
            Handler.response = response
            page.send("Page.navigate", {"url": site})
            deadline = time.time() + 5
            while time.time() < deadline:
                if page.js("document.readyState === 'complete'"):
                    break
                time.sleep(.05)
            assert engine._is_crash_page()
            if response is not None:
                if transport == "xhr":
                    page.js("var x=new XMLHttpRequest();x.open('GET','/api/hatch/token');"
                            "x.responseType='json';x.send()")
                else:
                    page.js("fetch('/api/hatch/token').catch(function(){})")
                deadline = time.time() + 5
                while time.time() < deadline and engine._hatch_token_result() is None:
                    time.sleep(.05)

        # 1) VM 无匹配是工作区问题，不是认证问题。
        load({"code": "hatch_vm_auth_no_match", "error": "Gateway VM auth token unavailable"})
        exc = engine._crash_page_exception()
        assert isinstance(exc, module.MuseWorkspaceUnavailable)
        assert not isinstance(exc, module.MuseAuthError)
        assert "不是 cookie 失效" in str(exc)
        print(json.dumps({"case": "vm_auth_no_match_workspace_unavailable"}))

        # 2) 其它明确 401 code 仍属于认证失败。
        load({"code": "session_expired", "error": "Session expired"})
        exc = engine._crash_page_exception()
        assert isinstance(exc, module.MuseAuthError)
        print(json.dumps({"case": "other_401_auth_error"}))

        # 3) 没有 token 响应记录时保守处理，不误杀账号。
        load(None)
        exc = engine._crash_page_exception()
        assert isinstance(exc, module.MuseWorkspaceUnavailable)
        assert not isinstance(exc, module.MuseAuthError)
        print(json.dumps({"case": "missing_response_not_auth"}))

        # 4) 捕获器只保留分类字段，响应 token 不可见。
        load({"code": "hatch_vm_auth_no_match", "error": "Gateway VM auth token unavailable"},
             transport="xhr")
        captured = page.js("JSON.stringify(window.__muse2apiHatchTokenResponse)")
        assert SECRET_TOKEN not in captured
        assert set(json.loads(captured)) == {"status", "code", "error"}
        assert page.js("Object.isFrozen(window.__muse2apiHatchTokenResponse)") is True
        print(json.dumps({"case": "token_not_recorded", "fields": sorted(json.loads(captured))}))
        print("PASS: VM auth crash classification")
    finally:
        httpd.shutdown()
        httpd.server_close()
        if page:
            try:
                page.send("Browser.close")
            except Exception:
                pass
            page.close()
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
