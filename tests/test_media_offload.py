"""R2 上传失败回退、幂等与远端副本删除回归。"""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from media_offload import MediaOffload

with tempfile.TemporaryDirectory() as directory:
    cfg = SimpleNamespace(data_dir=directory, media_dir=directory, media_upload_token='fixture',
                          media_upload_url='https://fixture.invalid/_internal/media',
                          media_public_base='https://fixture.invalid')
    offload = MediaOffload(cfg)
    video = Path(directory) / 'fixture.mp4'
    video.write_bytes(b'fixture-video')
    response = Mock(status_code=200)
    response.json.return_value = {'ok': True, 'url': 'https://untrusted.invalid'}
    with patch('media_offload.requests.put', side_effect=OSError('fixture')):
        assert offload.publish(video.name) is None
        assert video.exists() and offload.url(video.name) is None
    def upload(url, *, data, **kwargs):
        assert hasattr(data, 'read') and data.read() == b'fixture-video'
        assert kwargs['allow_redirects'] is False
        return response
    with patch('media_offload.requests.put', side_effect=upload) as put:
        assert offload.publish(video.name) == 'https://fixture.invalid/v1/media/fixture.mp4'
        assert offload.publish(video.name) == offload.url(video.name)
        assert put.call_count == 1
        assert offload.publish('../bad.mp4') is None
        assert offload.publish('image.png') is None
    with patch('media_offload.requests.delete', return_value=Mock(status_code=503)):
        try: offload.delete(video.name)
        except OSError: pass
        else: raise AssertionError('must retain on failure')
        assert video.exists() and offload.url(video.name)
    video.unlink()
    assert len(offload.records()) == 1 and offload.url(video.name)
    with patch('media_offload.requests.delete', return_value=Mock(status_code=200)):
        assert offload.delete(video.name)
    assert not offload.url(video.name)
    cfg.media_upload_token = ''
    assert not offload.enabled
print('media offload: passed')
