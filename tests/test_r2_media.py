"""R2-only media retention regression; no network or real account required."""
import base64
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
from unittest.mock import patch


class FakeResponse:
    def __init__(self, *, content=b"", payload=None):
        self.content = content
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


with tempfile.TemporaryDirectory(prefix="muse-r2-test-") as tmp:
    os.environ.update(
        MUSE2API_HOME=tmp,
        MUSE2API_PROFILE_ROOT=tmp,
        MUSE2API_MEDIA_PUBLIC_BASE="https://media.example",
        MUSE2API_MEDIA_UPLOAD_URL="https://media.example/_internal/media",
        MUSE2API_MEDIA_UPLOAD_TOKEN="test-token",
        MUSE2API_MEDIA_LOCAL_RETENTION="0",
    )
    source = Path(__file__).resolve().parents[1] / "app.py"
    sys.path.insert(0, str(source.parent))
    spec = importlib.util.spec_from_file_location("r2_media_test_target", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    media = Path(module.CFG.media_dir) / "fixture.webp"
    payload = b"webp fixture"
    media.write_bytes(payload)
    result = {"filename": media.name, "path": str(media), "size": len(payload),
              "kind": "image", "mime": "image/webp"}

    with patch.object(module.requests, "put", return_value=FakeResponse()):
        assert module._mirror_media(result)
    assert result["storage"] == "r2" and not media.exists()

    request = SimpleNamespace(prompt="fixture", size="1:1", response_format="b64_json")
    with patch.object(module.requests, "get", return_value=FakeResponse(content=payload)):
        response = module._image_response(request, result)
    assert base64.b64decode(response["data"][0]["b64_json"]) == payload

    listing = {"objects": [{"name": media.name, "bytes": len(payload),
                             "uploaded": "2026-10-27T00:00:00.000Z",
                             "content_type": "image/webp"}]}
    module._invalidate_media_list_cache()
    with patch.object(module.requests, "get", return_value=FakeResponse(payload=listing)):
        items = module.admin_media()
    assert items["count"] == 1 and items["media"][0]["storage"] == "r2"

    with patch.object(module.requests, "delete", return_value=FakeResponse()):
        assert module.delete_single_media(media.name)["deleted"] == media.name

print("PASS: R2 upload, local eviction, remote base64 fallback, listing and deletion")
