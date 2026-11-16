"""真实 Chromium + 本地页面：账号上下文释放后 IndexedDB 记录仍存在。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import shutil
import tempfile
import threading
import time

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import Config  # noqa: E402
from engine import MuseEngine  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b"<!doctype html><meta charset=utf-8><title>local idb fixture</title>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


chromium = os.environ.get("MUSE2API_CHROMIUM") or shutil.which("chromium") \
    or shutil.which("google-chrome")
if not chromium:
    print("SKIP: 未找到 Chromium；设置 MUSE2API_CHROMIUM 后运行真实 IndexedDB 回归")
    raise SystemExit(0)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

with tempfile.TemporaryDirectory(prefix="m2a-idb-browser-") as home:
    cfg = Config(base_dir=home, profile_root=home, chromium=chromium,
                 cdp_port=19421, keep_account_contexts=True,
                 max_account_contexts=2, login_wait=2)
    cfg.ensure_dirs()
    engine = MuseEngine(cfg)
    try:
        engine.start()
        page = engine._open_page(account_id="fixture-account")
        engine.page = page
        engine.current_acc_id = "fixture-account"
        page.send("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/"})
        deadline = time.time() + 5
        while time.time() < deadline and page.js("document.readyState") != "complete":
            time.sleep(0.05)
        written = page.js("""new Promise((resolve, reject) => {
          const request = indexedDB.open('muse2api-context-fixture', 1);
          request.onupgradeneeded = () => request.result.createObjectStore('records');
          request.onerror = () => reject(request.error);
          request.onsuccess = () => {
            const tx = request.result.transaction('records', 'readwrite');
            tx.objectStore('records').put('kept', 'binding');
            tx.oncomplete = () => { request.result.close(); resolve(true); };
            tx.onerror = () => reject(tx.error);
          };
        })""", await_promise=True)
        assert written is True
        context_id = engine.current_context_id
        engine.close_current_page()

        reused = engine._claim_account_context("fixture-account", None)
        assert reused is page
        assert engine.current_context_id == context_id
        value = reused.js("""new Promise((resolve, reject) => {
          const request = indexedDB.open('muse2api-context-fixture', 1);
          request.onerror = () => reject(request.error);
          request.onsuccess = () => {
            const tx = request.result.transaction('records', 'readonly');
            const get = tx.objectStore('records').get('binding');
            get.onsuccess = () => { request.result.close(); resolve(get.result || null); };
            get.onerror = () => reject(get.error);
          };
        })""", await_promise=True)
        assert value == "kept", value
    finally:
        engine.stop()
        server.shutdown()
        server.server_close()
        thread.join(2)

print("PASS: 真实 Chromium 同账号第二次租约保留本地页面 IndexedDB 记录")
