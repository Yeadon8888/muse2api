"""muse.ai rotates hatch_sess/hatch_gw in /api/session responses even when the workspace
is not assigned (status "unavailable"), and the old values stop working. Every renewal
path must keep the rotated cookies instead of dropping them with the error."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MUSE2API_HOME"] = tempfile.mkdtemp(prefix="m2a-rotation-")
import app  # noqa: E402
import engine as engine_mod  # noqa: E402

OLD, NEW = "sess-old", "sess-new"


def response(status_json, set_cookies=None, code=200):
    r = requests.Response()
    r.status_code = code
    r._content = json.dumps(status_json).encode()
    r.headers["Content-Type"] = "application/json"
    for name, value in (set_cookies or {}).items():
        r.cookies.set(name, value, domain=".muse.ai", path="/", expires=int(time.time()) + 30 * 86400)
    return r


def fake_session_server(rotate_to=NEW, status="unavailable"):
    """Rotates once: the first request carrying OLD gets NEW back; NEW is accepted."""
    seen = []

    def get(url, headers=None, **kw):
        cookie = headers.get("Cookie", "")
        seen.append("hatch_sess=" + (NEW if f"hatch_sess={NEW}" in cookie else OLD))
        if f"hatch_sess={OLD}" in cookie:
            return response({"status": status, "vm_resolution_issue": {"kind": "retryable"}},
                            {"hatch_sess": rotate_to, "hatch_gw": "gw-new"})
        return response({"status": status, "vm_resolution_issue": {"kind": "retryable"}})
    return get, seen


# 1) Engine: the error carries the merged, rotated cookies.
get, _ = fake_session_server()
with patch("requests.get", side_effect=get):
    try:
        engine_mod.MuseEngine.renew_session_http({"hatch_sess": OLD, "datr": "d"}, {}, wake_vm=False)
    except engine_mod.MuseSessionUnavailable as e:
        assert e.rotated and e.cookies["hatch_sess"] == NEW and e.cookies["hatch_gw"] == "gw-new", e.cookies
        assert e.cookies["datr"] == "d" and e.cookies_exp.get("hatch_sess"), e.cookies_exp
        assert isinstance(e, engine_mod.MuseGenerationError)  # existing handlers still catch it
    else:
        raise AssertionError("unavailable session should raise MuseSessionUnavailable")
print("PASS engine keeps rotated cookies on an unavailable session")

# 2) App renewal persists them and blocks an immediate second renewal with the stale value.
acc = app.store.add_account({"hatch_sess": OLD, "datr": "d"}, label="rot", cookies_exp={})
aid = acc["id"]
app.store.mark(aid, False, "stale")  # force a renewal regardless of the 10-minute cache
get, seen = fake_session_server()
with patch("requests.get", side_effect=get):
    app._renew_and_persist(aid, wake_vm=False)
    stored = app.store.get_account(aid)
    assert stored["cookies"]["hatch_sess"] == NEW and stored["cookies"]["datr"] == "d", stored["cookies"]
    assert app.engine._last_http_renew.get(aid), "renew timestamp not recorded"
    app._renew_and_persist(aid, wake_vm=False, force=True)  # next call must present NEW
assert seen == ["hatch_sess=" + OLD, "hatch_sess=" + NEW], seen
print("PASS app persists rotation and the next renewal uses the new cookie")

# 3) Keepalive probe persists rotation too.
acc2 = app.store.add_account({"hatch_sess": OLD}, label="rot2", cookies_exp={})
get, _ = fake_session_server()
with patch("requests.get", side_effect=get):
    res = app._probe_account_sync(acc2["id"])
assert res.get("cookies_rotated") is True, res
assert app.store.get_account(acc2["id"])["cookies"]["hatch_sess"] == NEW
print("PASS keepalive persists rotation")

# 4) ensure_page loads the page with the rotated cookie and reports it to the store sink.
e = app.MuseEngine(SimpleNamespace(profile_dir=os.environ["MUSE2API_HOME"], login_wait=1))
reported, applied = [], []
e.cookie_sink = lambda aid_, c, x: reported.append((aid_, c["hatch_sess"]))
page = SimpleNamespace(js=lambda script: "ready" if "readyState" in script else False,
                       send=lambda *a, **k: {}, close=lambda: None)
get, _ = fake_session_server()
with patch("requests.get", side_effect=get), patch.object(e, "_open_page", return_value=page), \
     patch.object(e, "_apply_cookies", side_effect=lambda p, c, x: applied.append(c["hatch_sess"])), \
     patch.object(e, "_wait_ws_ready", return_value=True), patch.object(e, "_is_crash_page", return_value=False), \
     patch("time.sleep"):
    e.ensure_page({"hatch_sess": OLD}, {}, account_id="acc-x")
assert applied == [NEW], applied
assert reported == [("acc-x", NEW)], reported
print("PASS ensure_page uses and reports the rotated cookie")

# 5) No rotation: nothing rewritten, still treated as a non-auth failure.
acc3 = app.store.add_account({"hatch_sess": NEW}, label="steady", cookies_exp={})
before = app.store.get_account(acc3["id"])["synced_at"]
get, _ = fake_session_server()
with patch("requests.get", side_effect=get):
    app._renew_and_persist(acc3["id"], wake_vm=False, force=True)
after = app.store.get_account(acc3["id"])
assert after["cookies"]["hatch_sess"] == NEW and after.get("ok") is not False, after
print("PASS steady session untouched")
print("ALL SESSION COOKIE ROTATION TESTS PASSED")
