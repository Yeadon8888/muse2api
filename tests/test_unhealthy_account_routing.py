"""Concurrent picks must wait for a busy healthy account instead of routing to accounts
already marked unhealthy (e.g. a rejected workspace token), and fall back only when no
healthy account exists at all."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Store  # noqa: E402

with tempfile.TemporaryDirectory() as home:
    accounts = [
        {"id": "good", "label": "218", "enabled": True, "ok": True, "cookies": {"hatch_sess": "x"}},
        {"id": "bad1", "label": "217", "enabled": True, "ok": False, "cookies": {"hatch_sess": "x"}},
        {"id": "bad2", "label": "220", "enabled": True, "ok": False, "cookies": {"hatch_sess": "x"}},
    ]
    acc_file, task_file = Path(home, "accounts.json"), Path(home, "tasks.json")
    acc_file.write_text(json.dumps(accounts))
    task_file.write_text("{}")
    store = Store(SimpleNamespace(accounts_file=str(acc_file), tasks_file=str(task_file)))

    # Healthy account free: it is chosen.
    assert store.pick_account(exclude_ids=set(), record_use=False)["id"] == "good"
    # Healthy account busy: wait (None) rather than hand out an unhealthy one.
    assert store.pick_account(exclude_ids={"good"}, record_use=False) is None
    assert store.pick_account(exclude_ids={"good"}, force_rotate=True, record_use=False) is None
    # Non-concurrent callers keep the old fallback behaviour.
    assert store.pick_account(exclude_id="good", record_use=False)["id"] in {"bad1", "bad2"}

    # Nothing healthy anywhere: still fall back to live accounts instead of stalling.
    store.mark("good", False, "token rejected")
    assert store.pick_account(exclude_ids={"bad1"}, record_use=False)["id"] in {"good", "bad2"}

    # Unknown health (ok=None) counts as healthy, so fresh imports are used immediately.
    store.mark("bad2", True, "")
    store.accounts[2]["ok"] = None
    assert store.pick_account(exclude_ids={"good"}, record_use=False)["id"] == "bad2"
    print("PASS: busy healthy account waits, unhealthy skipped, fallbacks preserved")
