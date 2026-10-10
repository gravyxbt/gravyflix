"""Resolve installed tools only. Downloads happen in the setup script, never a request."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from . import config

PROBE_VERSION = 2

def binary(name):
    configured = getattr(config, name.upper() + "_PATH", "")
    if configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    found = shutil.which(name)
    if found:
        return found
    try:
        from static_ffmpeg.run import get_platform_dir
        path = Path(get_platform_dir()) / name
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    except (ImportError, OSError):
        pass
    return None

def inspect_media(path):
    executable = binary("ffprobe")
    if not executable:
        raise RuntimeError("ffprobe is unavailable; run scripts/setup-media-tools.sh")
    result = subprocess.run([executable, "-v", "error", "-show_format", "-show_streams",
                             "-of", "json", str(path)], capture_output=True, text=True,
                            timeout=30, check=True)
    return json.loads(result.stdout)

def select_tracks(info):
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")]
    audios = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    video = next((s for s in videos if s.get("disposition", {}).get("default")), videos[0] if videos else {})
    audio = next((s for s in audios if s.get("disposition", {}).get("default")), audios[0] if audios else {})
    return video, audio, audios

def probe_fields(info):
    video, audio, audios = select_tracks(info)
    fmt = info.get("format", {})
    tracks = [{"index": s.get("index"), "codec": s.get("codec_name"), "profile": s.get("profile"),
               "channels": s.get("channels"), "sample_rate": s.get("sample_rate"),
               "language": s.get("tags", {}).get("language"), "title": s.get("tags", {}).get("title"),
               "default": bool(s.get("disposition", {}).get("default"))} for s in audios]
    from fractions import Fraction
    try: rate=float(Fraction(video.get('avg_frame_rate','0/1')))
    except (ValueError,ZeroDivisionError): rate=None
    return dict(video_profile=video.get('profile'),video_level=video.get('level'),pixel_format=video.get('pix_fmt'),frame_rate=rate,
                bitrate=int(fmt['bit_rate']) if fmt.get('bit_rate') else None,color_transfer=video.get('color_transfer'),container=fmt.get("format_name"), video_codec=video.get("codec_name"),
                audio_codec=audio.get("codec_name"), width=video.get("width"), height=video.get("height"),
                duration=float(fmt["duration"]) if fmt.get("duration") else None,
                audio_channels=audio.get("channels"), audio_profile=audio.get("profile"),
                audio_tracks=json.dumps(tracks), probe_version=PROBE_VERSION, probe_error=None)
