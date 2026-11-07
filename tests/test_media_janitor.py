"""Watermark media cleanup: oldest files go first, recent files and placeholders stay,
nothing is touched below the high watermark, and the optional size cap works."""
import os
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from media_janitor import MediaJanitor  # noqa: E402

Usage = namedtuple("Usage", "total used free")
MB = 1024 * 1024
NOW = 2_000_000_000.0


def build(home, sizes_ages):
    media = Path(home, "media")
    downloads = Path(home, "downloads", "job")
    media.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    (media / ".gitkeep").write_text("")
    os.utime(media / ".gitkeep", (NOW - 10 * 86400, NOW - 10 * 86400))
    paths = []
    for i, (size_mb, age_min) in enumerate(sizes_ages):
        folder = downloads if i == 1 else media  # one file lives in a nested downloads dir
        p = folder / f"f{i}.mp4"
        p.write_bytes(b"\0" * int(size_mb * MB))
        t = NOW - age_min * 60
        os.utime(p, (t, t))
        paths.append(p)
    return media, Path(home, "downloads"), paths


def janitor(home, media, downloads, used_mb, total_mb=1000, **kw):
    def usage(_):
        # Simulated volume: fixed non-media usage plus whatever media files still exist.
        current = sum(f.stat().st_size for d in (media, downloads) for f in d.rglob("*") if f.is_file())
        return Usage(total_mb * MB, int(used_mb * MB) + current, 0)
    kw.setdefault("high_pct", 80)
    kw.setdefault("low_pct", 60)
    kw.setdefault("min_age_s", 1800)
    kw.setdefault("max_media_bytes", 0)
    return MediaJanitor(home, [str(media), str(downloads)], disk_usage=usage, now=lambda: NOW, **kw)


# 1) Below the high watermark: nothing deleted.
with tempfile.TemporaryDirectory() as home:
    media, downloads, paths = build(home, [(100, 600), (100, 500), (100, 400)])
    r = janitor(home, media, downloads, used_mb=400).run_once()  # 700/1000 = 70%
    assert r["deleted"] == 0 and all(p.exists() for p in paths), r
print("PASS below watermark: untouched")

# 2) Above: delete oldest first until <= low watermark; keep recent files and .gitkeep.
with tempfile.TemporaryDirectory() as home:
    # base 300 MB + media 600 MB = 90%. Oldest -> newest: f0, f1(downloads), f2, f3, f4(recent), f5(recent)
    media, downloads, paths = build(home, [(100, 900), (100, 800), (100, 700), (100, 600), (100, 10), (100, 5)])
    j = janitor(home, media, downloads, used_mb=300)
    r = j.run_once()
    exists = [p.exists() for p in paths]
    # Needs to reach <= 600 MB used: delete f0, f1, f2 (300 MB) -> 600/1000 = 60%.
    assert exists == [False, False, False, True, True, True], (exists, r)
    assert r["deleted"] == 3 and r["freed_bytes"] == 300 * MB and r["disk_used_pct_after"] == 60.0, r
    assert (media / ".gitkeep").exists()
    assert j.status()["last_cleanup"]["deleted"] == 3
print("PASS above watermark: oldest deleted to low watermark, nested downloads included, placeholder kept")

# 3) Only recent files left: they are kept even if still above the watermark.
with tempfile.TemporaryDirectory() as home:
    media, downloads, paths = build(home, [(200, 20), (200, 10), (200, 1)])
    r = janitor(home, media, downloads, used_mb=300).run_once()  # 90%, all younger than 30 min
    assert r["deleted"] == 0 and r["skipped_recent"] == 3 and all(p.exists() for p in paths), r
print("PASS recent files protected")

# 4) Optional media size cap triggers cleanup even with plenty of disk.
with tempfile.TemporaryDirectory() as home:
    media, downloads, paths = build(home, [(100, 900), (100, 800), (100, 700), (100, 600)])
    r = janitor(home, media, downloads, used_mb=0, total_mb=100000,
                max_media_bytes=300 * MB).run_once()  # cap 300 MB, target 300*60/80 = 225 MB
    exists = [p.exists() for p in paths]
    assert exists == [False, False, True, True], (exists, r)
print("PASS media size cap")

# 5) Env defaults and clamping.
with tempfile.TemporaryDirectory() as home:
    os.environ.update(MUSE2API_MEDIA_HIGH_WATERMARK="85", MUSE2API_MEDIA_LOW_WATERMARK="90",
                      MUSE2API_MEDIA_MIN_AGE_MINUTES="15", MUSE2API_MEDIA_JANITOR_INTERVAL="5")
    j = MediaJanitor(home, [home])
    assert j.high == 0.85 and j.low == 0.84 and j.min_age_s == 900 and j.interval_s == 30, vars(j)
print("PASS env config with low < high and interval floor")
print("ALL MEDIA JANITOR TESTS PASSED")
