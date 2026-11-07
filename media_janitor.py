"""按磁盘水位自动清理旧媒体，防止 Railway 数据卷被生成的视频 / 图片写满。

数据卷用量达到高水位（默认 80%）时，从最旧的文件开始删除 media/ 与 downloads/
里的文件，直到降到低水位（默认 60%）。最近生成的文件（默认 30 分钟内）不会删除，
避免客户端还没来得及下载就被清掉。可选再给媒体目录设一个总大小上限。

环境变量：
  MUSE2API_MEDIA_HIGH_WATERMARK     高水位，百分比，默认 80
  MUSE2API_MEDIA_LOW_WATERMARK      低水位，百分比，默认 60
  MUSE2API_MEDIA_MIN_AGE_MINUTES    最短保留时间（分钟），默认 30
  MUSE2API_MEDIA_MAX_GB             媒体总大小上限（GB），默认 0 表示不限制
  MUSE2API_MEDIA_JANITOR_INTERVAL   检查间隔（秒），默认 300
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time

log = logging.getLogger("muse2api")

_GB = 1024 ** 3


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


class MediaJanitor:
    def __init__(self, data_dir: str, dirs: list[str], *, high_pct: float | None = None,
                 low_pct: float | None = None, min_age_s: float | None = None,
                 max_media_bytes: int | None = None, disk_usage=shutil.disk_usage,
                 now=time.time):
        self.data_dir = data_dir
        self.dirs = list(dirs)
        high = _env_float("MUSE2API_MEDIA_HIGH_WATERMARK", 80) if high_pct is None else high_pct
        low = _env_float("MUSE2API_MEDIA_LOW_WATERMARK", 60) if low_pct is None else low_pct
        self.high = min(max(high, 5.0), 99.0) / 100.0
        self.low = min(max(low, 1.0), high - 1.0) / 100.0
        self.min_age_s = (_env_float("MUSE2API_MEDIA_MIN_AGE_MINUTES", 30) * 60
                          if min_age_s is None else min_age_s)
        self.max_media_bytes = (int(_env_float("MUSE2API_MEDIA_MAX_GB", 0) * _GB)
                                if max_media_bytes is None else max_media_bytes)
        self.interval_s = max(30.0, _env_float("MUSE2API_MEDIA_JANITOR_INTERVAL", 300))
        self._disk_usage = disk_usage
        self._now = now
        self._lock = threading.Lock()
        self.last_result: dict | None = None

    def _files(self) -> list[tuple[float, int, str]]:
        out = []
        for d in self.dirs:
            if not os.path.isdir(d):
                continue
            for root, _dirs, names in os.walk(d):
                for name in names:
                    if name.startswith("."):  # .gitkeep 等占位文件
                        continue
                    path = os.path.join(root, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    out.append((st.st_mtime, st.st_size, path))
        out.sort()
        return out

    def status(self) -> dict:
        usage = self._disk_usage(self.data_dir)
        files = self._files()
        return {
            "disk_total_bytes": usage.total, "disk_used_bytes": usage.used,
            "disk_used_pct": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
            "media_files": len(files), "media_bytes": sum(s for _, s, _ in files),
            "high_watermark_pct": round(self.high * 100, 1),
            "low_watermark_pct": round(self.low * 100, 1),
            "min_age_minutes": round(self.min_age_s / 60, 1),
            "max_media_gb": round(self.max_media_bytes / _GB, 2) if self.max_media_bytes else 0,
            "last_cleanup": self.last_result,
        }

    def run_once(self) -> dict:
        with self._lock:
            usage = self._disk_usage(self.data_dir)
            files = self._files()
            media_bytes = sum(s for _, s, _ in files)
            used = usage.used
            over_disk = usage.total > 0 and used / usage.total >= self.high
            over_cap = bool(self.max_media_bytes) and media_bytes > self.max_media_bytes
            result = {"at": int(self._now()), "deleted": 0, "freed_bytes": 0,
                      "disk_used_pct_before": round(used / usage.total * 100, 1) if usage.total else 0.0,
                      "skipped_recent": 0, "errors": 0}
            if not (over_disk or over_cap):
                result["disk_used_pct_after"] = result["disk_used_pct_before"]
                self.last_result = result if self.last_result is None else self.last_result
                return result

            target_used = usage.total * self.low
            target_media = (self.max_media_bytes * self.low / self.high
                            if self.max_media_bytes else None)
            cutoff = self._now() - self.min_age_s
            for mtime, size, path in files:
                disk_ok = not over_disk or used <= target_used
                cap_ok = target_media is None or media_bytes <= target_media
                if disk_ok and cap_ok:
                    break
                if mtime > cutoff:
                    result["skipped_recent"] += 1
                    continue
                try:
                    os.remove(path)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    result["errors"] += 1
                    log.warning("【媒体清理】删除失败 %s: %s", os.path.basename(path), exc)
                    continue
                used -= size
                media_bytes -= size
                result["deleted"] += 1
                result["freed_bytes"] += size
            result["disk_used_pct_after"] = (round(used / usage.total * 100, 1)
                                             if usage.total else 0.0)
            result["reason"] = ("disk_watermark" if over_disk else "media_size_cap")
            if result["deleted"] or result["skipped_recent"]:
                why = (f"数据卷 {result['disk_used_pct_before']:.1f}% ≥ 高水位 {self.high * 100:.0f}%"
                       if over_disk else
                       f"媒体占用超过上限 {self.max_media_bytes / _GB:.2f} GB")
                log.warning("【媒体清理】%s：删除最旧文件 %d 个，释放 %.1f MB，清理后数据卷约 %.1f%%"
                            "（%d 个文件因生成不足 %.0f 分钟被保留）",
                            why, result["deleted"], result["freed_bytes"] / 1024 / 1024,
                            result["disk_used_pct_after"], result["skipped_recent"], self.min_age_s / 60)
            self.last_result = result
            return result
