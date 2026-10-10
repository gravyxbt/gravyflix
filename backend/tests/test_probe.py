import json
import subprocess
from app import scanner, media_tools

def test_probe_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(media_tools, "binary", lambda _: "/fake/ffprobe")
    payload = {"format":{"format_name":"mov,mp4", "duration":"12.5"}, "streams":[
        {"codec_type":"video", "codec_name":"mjpeg", "disposition":{"attached_pic":1}},
        {"codec_type":"video", "codec_name":"h264", "width":1280, "height":720},
        {"codec_type":"audio", "codec_name":"aac"}]}
    def run(args, **kwargs):
        assert args[-1] == str(tmp_path / "test.mp4")
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
    monkeypatch.setattr(media_tools.subprocess, "run", run)
    result = scanner.probe(tmp_path / "test.mp4")
    assert result["video_codec"] == "h264"
    assert result["audio_codec"] == "aac"
    assert result["duration"] == 12.5
    assert result["width"] == 1280 and result["height"] == 720
    assert result["probe_error"] is None

def test_probe_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(media_tools, "binary", lambda _: "/fake/ffprobe")
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffprobe", 30)
    monkeypatch.setattr(media_tools.subprocess, "run", run)
    assert scanner.probe(tmp_path / "bad.mkv")["probe_error"]
