"""视频/图片额度识别、按种类冷却与换号；全程离线。"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import MuseQuotaLimitError, detect_quota_limit  # noqa: E402


samples = (
    ("这次没生成出来 — 撞到 24 小时视频上限了，按规则停下，没有重试。", "video"),
    ("已达到视频上限，请稍后再试", "video"),
    ("You have reached your usage limit for video generation.", "video"),
    ("Video limit reached. Try again in 2 hours.", "video"),
    ("You've reached your usage limit", "image"),
    ("图片额度已用完，24 小时后恢复", "image"),
    ("每日生成上限已达到", "image"),
)
for text, kind in samples:
    error = detect_quota_limit(text, "image")
    assert isinstance(error, MuseQuotaLimitError), text
    assert error.kind == kind, (text, error.kind)
assert detect_quota_limit("我不能按这个要求生成内容", "video") is None
reset_error = detect_quota_limit("Video limit reached. Try again in 2 hours.", "video")
assert 7190 <= reset_error.reset_at - time.time() <= 7200


with tempfile.TemporaryDirectory(prefix="m2a-video-quota-") as home:
    os.environ.update(
        MUSE2API_HOME=home,
        MUSE2API_PROFILE_ROOT=home,
        MUSE2API_KEY="test-only",
        MUSE2API_VIDEO_QUOTA_COOLDOWN_HOURS="24",
        MUSE2API_IMAGE_QUOTA_COOLDOWN_HOURS="24",
    )
    spec = importlib.util.spec_from_file_location("video_quota_candidate", ROOT / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)

    first = app.store.add_account({"hatch_sess": "one"}, "one")
    second = app.store.add_account({"hatch_sess": "two"}, "two")
    calls = []
    success = {"filename": "fixture.mp4", "kind": "video", "size": 1}

    def generate(cookies, prompt, **kwargs):
        calls.append(cookies["hatch_sess"])
        if len(calls) == 1:
            raise app.MuseQuotaLimitError("24 小时视频上限", kind="video")
        return success

    with patch.object(app, "_renew_and_persist",
                      side_effect=lambda ident, **_: app.store.get_account(ident)), \
         patch.object(app.engine, "start"), \
         patch.object(app.engine, "generate", side_effect=generate), \
         patch.object(app.engine, "close_current_page"), \
         patch.object(app, "_sync_cookies", return_value={}):
        result, account_id = app._run_generation_locked(
            "fixture", "video", 30, account_id=first["id"],
            deadline=time.monotonic() + 30,
        )
    assert result == success and account_id == second["id"]
    assert calls == ["one", "two"]
    assert app.store.quota_cooldown_remaining(first, "video") > 0
    assert first.get("ok") is None

    # 视频冷却不影响图片，管理列表同时公开各种类剩余秒数。
    assert app.store.pick_account(task_kind="image", record_use=False)["id"] in {
        first["id"], second["id"]}
    listed = next(item for item in app.store.list_accounts() if item["id"] == first["id"])
    assert listed["video_quota_cooldown_remaining_seconds"] > 0
    assert listed["image_quota_cooldown_remaining_seconds"] == 0
    assert listed["any_quota_cooldown_remaining_seconds"] == 0

    # 所有账号视频额度冷却时，在打开浏览器前快速失败。
    app.store.set_quota_cooldown(second["id"], "video", seconds=3600)
    started = time.monotonic()
    with patch.object(app.engine, "start") as start, \
         patch.object(app.engine, "generate") as engine_generate:
        try:
            app._run_generation("fixture", "video", timeout=30)
        except app.MuseQuotaLimitError as exc:
            message = str(exc)
        else:
            raise AssertionError("全部额度冷却时未快速失败")
    assert time.monotonic() - started < 1
    assert "所有账号的 muse.ai 视频额度已用完" in message
    assert "最早约" in message and "重新导入" not in message
    start.assert_not_called()
    engine_generate.assert_not_called()

    # 到期自动恢复；管理接口可清除指定种类的冷却。
    first["quota_cooldown_until"]["video"] = time.time() - 1
    assert app.store.quota_cooldown_remaining(first, "video") == 0
    assert app.store.pick_account(task_kind="video", record_use=False)["id"] == first["id"]
    app.store.set_quota_cooldown(first["id"], "video", seconds=3600)
    cleared = app.clear_account_quota_cooldown(first["id"], "video", True)
    assert cleared["cleared"] and cleared["kind"] == "video"
    assert app.store.quota_cooldown_remaining(first, "video") == 0

print("PASS: quota text detection, rotation, typed cooldown, fast failure, expiry and clearing")


# Review follow-up: page text (`tail`) can contain the user's own prompt or sidebar history.
# The broad quota patterns must only run on the model's reply, never on page text, or a
# prompt such as "视频时长上限 5 秒" would put a healthy account into a 24h cooldown.
import re as _re
from pathlib import Path as _Path
_src = (_Path(__file__).resolve().parents[1] / "engine.py").read_text(encoding="utf-8")
assert not _re.search(r"detect_quota_limit\(\s*tail\b", _src), "broad quota patterns must not scan page text"
import engine as _engine
assert _engine.detect_quota_limit("请生成 16:9 视频，视频时长上限 5 秒，不要文字") is not None, \
    "documents why page text is excluded: the broad patterns do match prompt-like text"
print("PASS: broad quota patterns are not applied to page text")
