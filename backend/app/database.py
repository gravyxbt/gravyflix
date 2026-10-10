import sqlite3
from contextlib import contextmanager
from . import config

@contextmanager
def connection():
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DATABASE_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def initialize():
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
            title TEXT NOT NULL, year INTEGER, date_added TEXT NOT NULL,
            file_size INTEGER NOT NULL, modification_time INTEGER NOT NULL,
            available INTEGER NOT NULL DEFAULT 1,
            container TEXT, video_codec TEXT, audio_codec TEXT,
            width INTEGER, height INTEGER, duration REAL, probe_error TEXT
        )""")

        # Additive migration: preserve movie IDs and all existing library rows.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(movies)")}
        for name, declaration in {
            "video_profile":"TEXT", "video_level":"INTEGER", "pixel_format":"TEXT", "frame_rate":"REAL", "bitrate":"INTEGER", "color_transfer":"TEXT",
            "audio_channels": "INTEGER", "audio_profile": "TEXT",
            "audio_tracks": "TEXT", "probe_version": "INTEGER NOT NULL DEFAULT 0"
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE movies ADD COLUMN {name} {declaration}")
