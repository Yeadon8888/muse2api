"""将视频流式上传到现有 R2 网关，保留本地文件作为失败回退。"""
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit

import requests

log = logging.getLogger(__name__)
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}


class MediaOffload:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.attempts = {}
        self.directory = Path(cfg.data_dir) / "media-offload"

    @property
    def enabled(self):
        return bool(self.cfg.media_upload_token and
                    urlsplit(self.cfg.media_upload_url).scheme == "https" and
                    urlsplit(self.cfg.media_public_base).scheme == "https")

    def _valid(self, name):
        return bool(re.fullmatch(r"[A-Za-z0-9._-]+", name) and ".." not in name)

    def _record(self, name):
        if not self.enabled or not self._valid(name):
            return None
        try:
            record = json.loads((self.directory / (name + ".json")).read_text())
            local = Path(self.cfg.media_dir) / name
            if local.exists():
                stat = local.stat()
                if stat.st_size != record["bytes"] or stat.st_mtime_ns != record["mtime_ns"]:
                    return None
            return record
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def url(self, name):
        if self._record(name):
            return self.cfg.media_public_base.rstrip("/") + "/v1/media/" + quote(name)
        return None

    def publish(self, name):
        if not self.enabled or not self._valid(name) or Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
            return None
        with self.lock:
            if existing := self.url(name):
                return existing
            self.attempts[name] = time.monotonic()
            path = Path(self.cfg.media_dir) / name
            try:
                stat = path.stat()
                if not 0 < stat.st_size <= 100 * 1024 * 1024:
                    return None
                headers = {"x-muse-media-token": self.cfg.media_upload_token,
                           "Content-Type": mimetypes.guess_type(name)[0] or "application/octet-stream",
                           "Content-Length": str(stat.st_size)}
                with path.open("rb") as body:
                    response = requests.put(self.cfg.media_upload_url.rstrip("/") + "/" + quote(name),
                                            data=body, headers=headers, timeout=(10, 120),
                                            allow_redirects=False)
                try:
                    if response.status_code != 200 or response.json().get("ok") is not True:
                        raise ValueError("上传未确认")
                finally:
                    response.close()
                # 文件在上传过程中变化时不记录成功，避免重定向到过期内容。
                after = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    return None
                self.directory.mkdir(parents=True, exist_ok=True)
                record = {"name": name, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                          "mtime": int(stat.st_mtime), "kind": "video"}
                fd, temp = tempfile.mkstemp(dir=self.directory, prefix=".upload-")
                try:
                    with os.fdopen(fd, "w") as output:
                        json.dump(record, output)
                    os.replace(temp, self.directory / (name + ".json"))
                finally:
                    if os.path.exists(temp):
                        os.unlink(temp)
                return self.url(name)
            except Exception as exc:
                # 不将网关地址、请求头或 token 写入日志；生成成功不因上传失败而重试。
                log.warning("R2 上传未完成，保留本地视频供下载：%s", type(exc).__name__)
                return None

    def delete(self, name):
        with self.lock:
            if not self._record(name):
                return False
            response = requests.delete(self.cfg.media_upload_url.rstrip("/") + "/" + quote(name),
                                       headers={"x-muse-media-token": self.cfg.media_upload_token},
                                       timeout=(10, 30), allow_redirects=False)
            try:
                if response.status_code != 200:
                    raise OSError("R2 删除失败，保留本地文件")
            finally:
                response.close()
            (self.directory / (name + ".json")).unlink(missing_ok=True)
            return True

    def records(self):
        records = []
        for path in self.directory.glob("*.json"):
            name = path.name[:-5]
            if record := self._record(name):
                records.append({**record, "url": self.url(name)})
        return records

    def backfill(self, limit=3):
        if not self.enabled:
            return
        pending = []
        for path in Path(self.cfg.media_dir).iterdir():
            if path.suffix.lower() in VIDEO_EXTENSIONS and path.is_file() and not self.url(path.name):
                if (time.time() - path.stat().st_mtime > 60
                        and 0 < path.stat().st_size <= 100 * 1024 * 1024
                        and time.monotonic() - self.attempts.get(path.name, -3600) > 600):
                    pending.append(path)
        # 优先迁移最新视频，单次最多三个，避免启动时突发上传占用资源。
        for path in sorted(pending, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            self.publish(path.name)
