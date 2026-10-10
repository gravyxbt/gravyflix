import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_KEYS = frozenset(os.environ)
load_dotenv(ROOT / ".env")

def path_setting(name, default):
    path = Path(os.getenv(name, default)).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()

MOVIES_DIR = path_setting("MOVIES_DIR", "media/Movies")
DATABASE_PATH = path_setting("DATABASE_PATH", "data/library.sqlite3")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

CAST_HOST = os.getenv("CAST_HOST", "")
CAST_NAME = os.getenv("CAST_NAME", "Living Room")

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "")
ROKU_CACHE_DIR = path_setting("ROKU_CACHE_DIR", "data/roku-cache")
ROKU_CACHE_MAX_BYTES = int(float(os.getenv("ROKU_CACHE_MAX_GB", "50")) * 1024**3)
ROKU_AUDIO_MODE = os.getenv("ROKU_AUDIO_MODE", "auto")
ROKU_PREPARE_TIMEOUT = int(os.getenv("ROKU_PREPARE_TIMEOUT", "3600"))

# Background library scans and public-source artwork enrichment.
AUTO_ARTWORK = os.getenv("AUTO_ARTWORK", "true").lower() in {"1", "true", "yes"}
AUTO_LIBRARY_SCAN_SECONDS = max(10, int(os.getenv("AUTO_LIBRARY_SCAN_SECONDS", "300")))
ARTWORK_RETRY_SECONDS = max(60, int(os.getenv("ARTWORK_RETRY_SECONDS", "86400")))

ROKU_VIDEO_ENCODER = os.getenv("ROKU_VIDEO_ENCODER", "libx264")

AUTO_SUBTITLES = os.getenv("AUTO_SUBTITLES", "true").lower() in {"1", "true", "yes"}
SUBTITLE_LANGUAGES = [s.strip().lower() for s in os.getenv("SUBTITLE_LANGUAGES", "en").split(",") if s.strip()]
SUBTITLE_PREFER_SDH = os.getenv("SUBTITLE_PREFER_SDH", "false").lower() in {"1", "true", "yes"}
SUBTITLE_DAILY_DOWNLOAD_LIMIT = max(1, int(os.getenv("SUBTITLE_DAILY_DOWNLOAD_LIMIT", "5")))
OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY", "")

# Conservative repeated-audio intro detection runs off the request threads.
AUTO_INTROS = os.getenv("AUTO_INTROS", "true").lower() in {"1", "true", "yes"}

# Cheap chapter metadata checks for movie-specific Up next timing.
AUTO_CREDITS = os.getenv("AUTO_CREDITS", "true").lower() in {"1", "true", "yes"}

AUTO_VISUAL_CREDITS = os.getenv("AUTO_VISUAL_CREDITS", "true").lower() in {"1", "true", "yes"}
CREDIT_ANALYSIS_TIMEOUT = max(60, min(900, int(os.getenv("CREDIT_ANALYSIS_TIMEOUT", "300"))))
