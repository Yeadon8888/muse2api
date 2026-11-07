"""Actual Chromium regression: the composer's file input may mount after the textarea.

Cold pages (fresh account context, VM still waking) expose an interactive textarea before
the upload control exists. _set_input_files must wait for it, click "Attach file" when
the input only mounts on demand, and still refuse ambiguous pages. No Muse login.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import requests

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from cdp import CDP  # noqa: E402

CHROME = (os.environ.get("CHROME_BIN") or shutil.which("chromium") or shutil.which("google-chrome")
          or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

with tempfile.TemporaryDirectory(prefix="muse-upload-wait-", dir=Path.home()) as home:
    os.environ.update(MUSE2API_HOME=home, MUSE2API_PROFILE_ROOT=home, MUSE2API_UPLOAD_WAIT="6")
    spec = importlib.util.spec_from_file_location("upload_wait_engine", root / "engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Engine, MuseGenerationError = module.MuseEngine, module.MuseGenerationError

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = open(Path(home) / "chromium.log", "wb")
    proc = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                             "--remote-allow-origins=*", "--remote-debugging-port=" + str(port),
                             "--user-data-dir=" + str(Path(home) / "browser"), "about:blank"],
                            stdout=log, stderr=log, start_new_session=True)
    session = requests.Session()
    session.trust_env = False
    page = None
    try:
        for _ in range(150):
            try:
                tabs = session.get(f"http://127.0.0.1:{port}/json/list", timeout=1).json()
                tab = next(x for x in tabs if x.get("type") == "page")
                page = CDP(tab["webSocketDebuggerUrl"], timeout=15)
                break
            except (requests.RequestException, StopIteration):
                time.sleep(.1)
        assert page, "fixture Chromium did not start"
        page.send("Page.enable")
        page.send("Runtime.enable")

        engine = Engine(SimpleNamespace(profile_dir=home, data_dir=home))
        engine.page = page
        upload = Path(home) / "fixture.txt"
        upload.write_text("fixture file visible to the browser")

        def load(html, script=""):
            page.js("document.body.innerHTML=" + json.dumps(html))
            if script:
                page.js(script)

        # 1) Input mounts 2 s after the textarea (hydration / VM wake lag).
        load('<main><section id="c"><div><textarea></textarea>'
             '<button aria-label="Attach file"></button></div></section></main>',
             "setTimeout(function(){var i=document.createElement('input');i.type='file';i.id='late';"
             "document.querySelector('#c div').appendChild(i);},2000)")
        t0 = time.monotonic()
        engine._set_input_files([str(upload)])
        assert page.js("document.querySelector('#late').files.length") == 1
        print(json.dumps({"case": "late_mount", "waited_s": round(time.monotonic() - t0, 2)}))

        # 2) Input only mounts when "Attach file" is clicked.
        load('<main><section id="c"><div><textarea></textarea>'
             '<button aria-label="Attach file"></button></div></section></main>',
             "document.querySelector('[aria-label=\"Attach file\"]').addEventListener('click',function(){"
             "if(document.querySelector('#ondemand'))return;var i=document.createElement('input');"
             "i.type='file';i.id='ondemand';document.querySelector('#c div').appendChild(i);})")
        engine._set_input_files([str(upload)])
        assert page.js("document.querySelector('#ondemand').files.length") == 1
        print(json.dumps({"case": "mount_on_attach_click"}))

        # 3) Never appears, and the page has two unrelated inputs: must refuse, not guess.
        load('<main><section><div><textarea></textarea></div></section></main>'
             '<aside><div class="chat-user-bubble"><input type="file"></div><input type="file"></aside>')
        try:
            engine._set_input_files([str(upload)])
        except MuseGenerationError as e:
            assert "找不到上传控件" in str(e)
            assert Path(home, "debug-no-upload-control.json").exists(), "debug snapshot not written"
            print(json.dumps({"case": "ambiguous_refused"}))
        else:
            raise AssertionError("ambiguous page should be refused")

        # 4) Existing immediate path still works and picks the composer input over history.
        load('<main><div class="chat-user-bubble"><input type="file" id="old"></div>'
             '<section><div><textarea></textarea><input type="file" id="now"></div></section></main>')
        engine._set_input_files([str(upload)])
        assert page.js("document.querySelector('#now').files.length") == 1
        assert page.js("document.querySelector('#old').files.length") == 0
        print(json.dumps({"case": "immediate_composer_input"}))
        print("PASS: late mount, attach-click mount, ambiguous refusal, immediate path")
    finally:
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
