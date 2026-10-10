"""Conservative filename cleanup plus reviewed, exact-filename title overrides."""
import json
import re
from functools import lru_cache
from . import config

QUALITY = re.compile(r"(?i)\b(?:2160p|1080[pi]|720p|576p|480p|hdtv|blu[ .-]?ray|brrip|bdrip|webrip|web[ .-]?dl|dvd[ .-]?rip|dvd[ .-]?scr|tvrips?|x264|x265|h264|h265|xvid|divx)\b")

def clean_release(text):
    text = re.sub(r"^\s*\[\s*(?:www[ .]|https?://)[^\]]+\]\s*[- ]*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d{1,3}-\d{1,3}\s+(?=[A-Za-z])", "", text)
    text = text.replace(".", " ").replace("_", " ")
    text = QUALITY.split(text)[0]
    text = re.sub(r"(?i)\s+(?:proper|repack)\s*$", "", text)
    return re.sub(r"\s+", " ", text).strip(" -")

@lru_cache(maxsize=8)
def _overrides(path, stamp):
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or any(not isinstance(k,str) or not isinstance(v,str) or not v.strip() for k,v in data.items()):
        raise ValueError("title-overrides.json must map exact filenames to nonempty titles")
    return data

def reviewed_title(filename, fallback):
    path = config.ROOT / "config/title-overrides.json"
    if not path.exists():
        return fallback
    return _overrides(path, path.stat().st_mtime_ns).get(filename, fallback)
