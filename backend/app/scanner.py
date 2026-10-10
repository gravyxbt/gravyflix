import json
import logging
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from . import config
from .database import connection, initialize
from .media_tools import inspect_media, probe_fields, PROBE_VERSION
from .titles import clean_release, reviewed_title

log = logging.getLogger("media")
SCAN_LOCK = threading.Lock()
EXTENSIONS = {".mp4", ".mkv", ".m4v", ".mov", ".avi"}

def parse_filename(filename):
    stem = clean_release(Path(filename).stem)
    match = re.search(r"[([]((?:19|20)\d{2})[)\]]", stem)
    if not match:
        match = next((m for m in re.finditer(r"(?<!\d)((?:19|20)\d{2})(?!\d)", stem) if m.start() > 0), None)
    year = int(match[1]) if match else None
    title = stem[:match.start()] if match and match.start() > 0 else stem
    title = clean_release(title).rstrip(" ([") or Path(filename).stem
    return reviewed_title(filename, title), year

def probe(path):
    try:
        return probe_fields(inspect_media(path))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, RuntimeError) as exc:
        log.warning("PROBE: %s: %s", path.name, exc)
        fields = dict.fromkeys(["container", "video_codec", "audio_codec", "width", "height",
                               "duration", "audio_channels", "audio_profile"])
        fields.update(audio_tracks="[]", probe_version=0, probe_error=str(exc)[:500])
        return fields

def scan_library():
    with SCAN_LOCK:
        initialize()
        root = config.MOVIES_DIR.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Movie directory unavailable: {root}")
        paths = []
        for path in root.rglob("*"):
            if path.suffix.lower() in EXTENSIONS and path.is_file():
                resolved = path.resolve()
                if resolved.is_relative_to(root):
                    paths.append(resolved)
        paths = sorted(set(paths))
        log.info("SCAN: Found %d video files", len(paths))
        added = updated = 0
        with connection() as db:
            db.execute("UPDATE movies SET available=0")
            for path in paths:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                old = db.execute("SELECT * FROM movies WHERE file_path=?", (str(path),)).fetchone()
                if old and old["file_size"] == stat.st_size and old["modification_time"] == stat.st_mtime_ns and not old["probe_error"] and old["probe_version"] == PROBE_VERSION:
                    title, year = parse_filename(path.name)
                    changed = title != old["title"] or year != old["year"]
                    db.execute("UPDATE movies SET available=1, title=?, year=? WHERE id=?", (title, year, old["id"]))
                    if changed:
                        updated += 1
                        log.info("SCAN: Cleaned title: %s -> %s", old["title"], title)
                    continue
                title, year = parse_filename(path.name)
                data = dict(file_path=str(path), filename=path.name, title=title, year=year,
                            date_added=datetime.now(timezone.utc).isoformat(), file_size=stat.st_size,
                            modification_time=stat.st_mtime_ns, **probe(path))
                columns = list(data)
                updates = ", ".join(f"{key}=excluded.{key}" for key in columns if key not in {"file_path", "date_added"})
                db.execute(f"""INSERT INTO movies ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})
                    ON CONFLICT(file_path) DO UPDATE SET {updates}, available=1""", tuple(data.values()))
                if old:
                    updated += 1
                else:
                    added += 1
                    log.info("SCAN: Added movie: %s", title)
        return {"found": len(paths), "added": added, "updated": updated}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(scan_library(), indent=2))
