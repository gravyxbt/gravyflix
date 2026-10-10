"""Bounded disk reads. Multiple ranges are deliberately ignored (HTTP 200)."""
import logging
import os
import re
from email.utils import formatdate
from pathlib import Path
from fastapi import HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse
from . import config

log = logging.getLogger("media")
MIME = {".avi": "video/x-msvideo", ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska"}

def parse_range(value, size):
    """None means ignore unsupported/malformed range; unsatisfiable -> ValueError."""
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()):
        return None
    first, last = match.groups()
    # Saturate large decimal values without Python's integer-string size limit.
    # Huge ends/suffixes remain valid; only a start beyond EOF is unsatisfiable.
    def number(token):
        token = token.lstrip("0") or "0"
        return size + 1 if len(token) > len(str(size)) + 1 else int(token)
    if first:
        start = number(first)
        end = number(last) if last else size - 1
        if start >= size or (last and end < start):
            raise ValueError("Unsatisfiable")
        return start, min(end, size - 1)
    suffix = number(last)
    if suffix == 0 or size == 0:
        raise ValueError("Unsatisfiable")
    return max(0, size - suffix), size - 1

def stream_movie(row, request: Request, allowed_root=None, on_close=None):
    root = (allowed_root or config.MOVIES_DIR).resolve()
    path = Path(row["file_path"]).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(404, "Movie is outside the configured library")
    try:
        file = path.open("rb")
    except OSError as exc:
        raise HTTPException(404, "Movie file unavailable; rescan library") from exc
    released = False
    def close():
        nonlocal released
        file.close()
        if not released:
            released = True
            if on_close:
                on_close()
    try:
        stat = os.fstat(file.fileno())
        size = stat.st_size
        etag = f'"{stat.st_mtime_ns:x}-{size:x}"'
        modified = formatdate(stat.st_mtime, usegmt=True)
        headers = {"Accept-Ranges": "bytes", "ETag": etag, "Last-Modified": modified}
        selected = None
        range_header = request.headers.get("range")
        if request.method == "GET" and request.headers.get("if-range", etag) in {etag, modified}:
            try:
                selected = parse_range(range_header, size)
            except ValueError:
                close()
                return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}", "Content-Length": "0"})
        start, end = selected if selected else (0, size - 1)
        length = max(0, end - start + 1)
        status = 206 if selected else 200
        headers["Content-Length"] = str(length)
        if selected:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")
        log.info("STREAM: Starting %s; Range %s; Serving %d (%d bytes)", row["title"], range_header, status, length)
        if request.method == "HEAD":
            close()
            return Response(status_code=200, headers=headers, media_type=mime)

        def chunks():
            try:
                file.seek(start)
                remaining = length
                while remaining:
                    block = file.read(min(256 * 1024, remaining))
                    if not block:
                        break
                    remaining -= len(block)
                    yield block
            finally:
                close()
        return StreamingResponse(chunks(), status_code=status, headers=headers, media_type=mime,
                                 background=BackgroundTask(close))
    except BaseException:
        close()
        raise
