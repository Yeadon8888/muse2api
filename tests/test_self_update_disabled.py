"""In-app upgrade overwrites the image's code with upstream main and calls os._exit(0);
on Railway a clean exit is not restarted, so the service goes 502. It must be off by
default and opt-in with MUSE2API_ALLOW_SELF_UPDATE=1."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MUSE2API_HOME"] = tempfile.mkdtemp(prefix="m2a-selfupdate-")
os.environ.pop("MUSE2API_ALLOW_SELF_UPDATE", None)
import app  # noqa: E402
from fastapi import HTTPException  # noqa: E402

calls = []
with patch.object(app, "_upgrade_from_github_sync", side_effect=lambda: calls.append("upgrade") or {"ok": True}), \
     patch.object(app.os, "_exit", side_effect=lambda code: calls.append(("exit", code))):
    for coro in (lambda: app.admin_upgrade_now({"restart": True}), lambda: app.admin_repo_push({})):
        try:
            asyncio.run(coro())
        except HTTPException as e:
            assert e.status_code == 403 and "已禁用在线升级" in e.detail, e.detail
        else:
            raise AssertionError("self-update endpoint should be refused by default")
    assert calls == [], calls

    with patch.object(app, "_check_update_sync", return_value={"has_update": True, "remote_sha": "abc"}):
        st = asyncio.run(app.admin_check_update())
        assert st["has_update"] is False and st["self_update_disabled"] is True, st

    os.environ["MUSE2API_ALLOW_SELF_UPDATE"] = "1"
    with patch.object(app, "_check_update_sync", return_value={"has_update": True}):
        assert asyncio.run(app.admin_check_update())["has_update"] is True
    res = asyncio.run(app.admin_upgrade_now({"restart": False}))
    assert res == {"ok": True} and calls == ["upgrade"], (res, calls)
print("PASS: upgrade/push refused by default, banner suppressed, explicit opt-in still works")
