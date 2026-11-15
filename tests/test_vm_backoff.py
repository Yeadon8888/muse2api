"""工作区不可用退避与单次重新发现回归测试；全程不访问 muse.ai。"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


with tempfile.TemporaryDirectory(prefix="m2a-vm-backoff-") as home:
    os.environ.update(
        MUSE2API_HOME=home,
        MUSE2API_PROFILE_ROOT=home,
        MUSE2API_KEY="test-only",
        MUSE2API_WORKSPACE_COOLDOWN_SECONDS="300",
        MUSE2API_WORKSPACE_REDISCOVERY_DELAY_SECONDS="0",
        MUSE2API_WORKSPACE_CIRCUIT_BREAKER_ENABLED="1",
    )
    spec = importlib.util.spec_from_file_location("vm_backoff_candidate", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)

    def add_account(label, ok=None):
        account = app.store.add_account({"hatch_sess": label}, label=label, cookies_exp={})
        account["ok"] = ok
        return account

    # 冷却期间跳过，到期后无需改 ok 即自动恢复；管理接口字段给出剩余秒数。
    cooldown_account = add_account("cooldown", ok=None)
    app.store.set_workspace_cooldown(cooldown_account["id"], 30, "fixture")
    assert app.store.pick_account(record_use=False) is None
    listed = next(a for a in app.store.list_accounts() if a["id"] == cooldown_account["id"])
    assert 1 <= listed["workspace_cooldown_remaining_seconds"] <= 30
    assert listed["ok"] is None
    cooldown_account["workspace_cooldown_until"] = time.time() - 1
    assert app.store.pick_account(record_use=False)["id"] == cooldown_account["id"]
    assert app.store.get_account(cooldown_account["id"])["ok"] is None

    # 所有账号冷却时在 1 秒内快速失败，且不会启动浏览器或调用 generate。
    app.store.set_workspace_cooldown(cooldown_account["id"], 300, "fixture")
    started = time.monotonic()
    with patch.object(app.engine, "start") as start, patch.object(app.engine, "generate") as generate:
        try:
            app._run_generation("fixture", "image", timeout=30)
        except app.MuseWorkspaceUnavailable as exc:
            message = str(exc)
        else:
            raise AssertionError("all-cooling circuit breaker did not open")
    assert time.monotonic() - started < 1
    assert "上游故障" in message and "无需重新导入 cookie" in message
    start.assert_not_called()
    generate.assert_not_called()

    # 清空 fixture，验证首次 no-match 后 session 变 assigned 时仅同号重试一次并成功。
    app.store.accounts.clear()
    assigned_account = add_account("assigned", ok=True)
    unavailable = app.MuseWorkspaceUnavailable(app.MuseEngine.WORKSPACE_UNAVAILABLE_MESSAGE)
    success = {"filename": "fixture.png", "kind": "image", "size": 1}
    assigned_session = {
        "ok": True, "status": "assigned", "vm_state": "RUNNING",
        "cookies": {"hatch_sess": "rotated"}, "cookies_exp": {},
    }
    with patch.object(app, "_renew_and_persist", side_effect=lambda aid, **_: app.store.get_account(aid)), \
         patch.object(app.engine, "start"), \
         patch.object(app.engine, "generate", side_effect=[unavailable, success]) as generate, \
         patch.object(app.engine, "renew_session_http", return_value=assigned_session) as renew, \
         patch.object(app.engine, "close_current_page") as close_page, \
         patch.object(app, "_sync_cookies", return_value={}):
        result, account_id = app._run_generation_locked(
            "fixture", "image", 30, account_id=assigned_account["id"],
            deadline=time.monotonic() + 30,
        )
    assert result == success and account_id == assigned_account["id"]
    assert generate.call_count == 2
    renew.assert_called_once()
    assert renew.call_args.kwargs["wake_vm"] is False
    assert close_page.call_count >= 1
    assert app.store.workspace_cooldown_remaining(app.store.get_account(account_id)) == 0

    # session 仍 unavailable 时不再开页重试，账号进入冷却且 ok 保持不变。
    app.store.accounts.clear()
    still_account = add_account("still-unavailable", ok=None)
    session_unavailable = app.MuseSessionUnavailable(
        "status=unavailable", {"hatch_sess": "rotated-again"}, {}, True,
    )
    with patch.object(app, "_renew_and_persist", side_effect=lambda aid, **_: app.store.get_account(aid)), \
         patch.object(app.engine, "start"), \
         patch.object(app.engine, "generate", side_effect=unavailable) as generate, \
         patch.object(app.engine, "renew_session_http", side_effect=session_unavailable) as renew, \
         patch.object(app.engine, "close_current_page"), \
         patch.object(app, "_bind_account_proxy"):
        try:
            app._run_generation_locked(
                "fixture", "video", 30, account_id=still_account["id"],
                deadline=time.monotonic() + 30,
            )
        except app.MuseWorkspaceUnavailable:
            pass
        else:
            raise AssertionError("still-unavailable account should fail")
    generate.assert_called_once()
    renew.assert_called_once()
    state = app.store.get_account(still_account["id"])
    assert app.store.workspace_cooldown_remaining(state) > 0
    assert state["ok"] is None
    assert state["cookies"]["hatch_sess"] == "rotated-again"

    print("PASS: workspace cooldown, fast circuit breaker, and single rediscovery")
