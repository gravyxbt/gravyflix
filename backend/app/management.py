"""Same-origin LAN management; jobs reuse the existing media pipeline."""
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from . import config
from .database import connection
from .media_tools import binary

log = logging.getLogger('media')

def same_origin(request: Request):
    if request.headers.get('x-gravyflix-manage') != '1':
        raise HTTPException(403, 'Use the Gravyflix management dashboard.')
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Management requests must come from this server.')

router = APIRouter(prefix='/api/manage', dependencies=[Depends(same_origin)])
lock = threading.RLock()
jobs = {}


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def atomic_write(path, text, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(text)
        if not private and path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def submit(label, function):
    with lock:
        if any(j['state'] in {'queued', 'running'} for j in jobs.values()):
            raise HTTPException(409, 'A management job is already running. Wait for it to finish.')
        while len(jobs) >= 20:
            del jobs[next(iter(jobs))]
        job = dict(id=uuid.uuid4().hex, label=label, state='queued', started_at=time.time(), message='Waiting to start')
        jobs[job['id']] = job
        def run():
            with lock:
                job.update(state='running', message='Working in the background. You can leave this page.')
            try:
                result = function()
                with lock:
                    job.update(state='done', message='Finished', result=result)
            except Exception:
                log.exception('MANAGE: %s failed', label)
                with lock:
                    job.update(state='error', message='Job failed. Check the server journal for details.')
        # A long metadata pass must not hold up server shutdown.
        threading.Thread(target=run, name="manage-job", daemon=True).start()
        return dict(job)


@router.get('/jobs')
def job_list():
    with lock:
        return [dict(j) for j in reversed(list(jobs.values()))]


@router.get('/overview')
def overview(request: Request):
    from .main import browse
    catalog = browse(request)
    with connection() as db:
        count = db.execute("SELECT count(*) FROM movies WHERE available=1 AND substr(filename,1,2) != '._'").fetchone()[0]
        missing = db.execute('SELECT count(*) FROM movies WHERE available=0').fetchone()[0]
        subtitle_states = {r['state']: r['n'] for r in db.execute('SELECT s.state,count(*) n FROM subtitle_jobs s JOIN movies m ON m.id=s.movie_id WHERE m.available=1 GROUP BY s.state')}
        intro_states = {r['state']: r['n'] for r in db.execute('SELECT s.state,count(*) n FROM intro_markers s JOIN movies m ON m.id=s.movie_id WHERE m.available=1 GROUP BY s.state')}
    disk = shutil.disk_usage(config.MOVIES_DIR if config.MOVIES_DIR.exists() else config.ROOT)
    cached = sum(p.stat().st_size for p in config.ROKU_CACHE_DIR.glob('*.mp4') if p.is_file())
    return dict(status='ok', files=count, movies=sum(i['kind']=='movie' for i in catalog),
        shows=sum(i['kind']=='show' for i in catalog), missing_files=missing,
        artwork_ready=sum(bool(i.get('artwork_source')) for i in catalog), titles=len(catalog),
        subtitles=subtitle_states, intros=intro_states,
        ffmpeg=bool(binary('ffmpeg')), ffprobe=bool(binary('ffprobe')),
        media_directory=str(config.MOVIES_DIR), disk_free=disk.free, disk_total=disk.total,
        cache_bytes=cached, cache_limit=config.ROKU_CACHE_MAX_BYTES,
        scan_seconds=config.AUTO_LIBRARY_SCAN_SECONDS,
        watch_url=str(request.base_url).rstrip('/'), project_directory=str(config.ROOT))


@router.get('/library')
def library(request: Request):
    from .main import browse, base_url
    from .models import movie_response
    from . import intros, subtitles, credits
    with connection() as db:
        rows = db.execute("SELECT * FROM movies WHERE available=1 AND substr(filename,1,2) != '._' ORDER BY title COLLATE NOCASE").fetchall()
    files = []
    for row in rows:
        item = movie_response(row, base_url(request)).model_dump()
        item.update(file_path=row['file_path'], intro=intros.available(row), subtitles=subtitles.available(row, base_url(request)), credits=credits.available(row))
        files.append(item)
    return dict(catalog=browse(request), files=files)


@router.post('/scan')
def scan(request: Request):
    from .main import scan as run_scan
    return submit('Scan media library', lambda: run_scan(request))


@router.get('/artwork')
def artwork_review():
    return read_json(config.ROOT / 'data/artwork-reports/matching.json', [])


class ArtworkChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)


@router.post('/artwork/choose')
def choose_artwork(body: ArtworkChoice):
    from .public_artwork import run
    with lock:
        if any(j['state'] in {'queued', 'running'} for j in jobs.values()):
            raise HTTPException(409, 'Wait for the current management job to finish.')
        report = artwork_review()
        review = next((r for r in report if str(r['id']) == body.id), None)
        candidate = next((c for c in (review or {}).get('candidates', []) if c['url'] == body.url), None)
        if not candidate or not re.fullmatch(r'https://www\.themoviedb\.org/(movie|tv)/\d+[^?#]*', body.url):
            raise HTTPException(422, 'Choose a candidate from the current artwork review list.')
        path = config.ROOT / 'config/artwork-matches.json'
        overrides = read_json(path, {})
        overrides[body.id] = dict(query=candidate['title'], year=candidate.get('year'), url=body.url, matched_title=candidate['title'])
        atomic_write(path, json.dumps(overrides, indent=2) + '\n')
        return submit('Fetch selected artwork', lambda: run(refresh=[body.id]))


@router.post('/artwork/process')
def process_artwork():
    from .public_artwork import run
    return submit('Find missing artwork', run)


@router.post('/subtitles/process')
def process_subtitles():
    from .subtitles import SubtitleWorker
    return submit('Discover subtitles', SubtitleWorker().run_once)


@router.post('/intros/process')
def process_intros():
    from .intros import IntroWorker
    return submit('Analyze series intros', IntroWorker().run_once)


class IntroEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    disabled: bool = False
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, ge=0, allow_inf_nan=False)


@router.put('/intros/{movie_id}')
def edit_intro(movie_id: int, body: IntroEdit):
    from .main import get_movie
    from . import intros
    row = get_movie(movie_id)
    if not body.disabled and (body.start is None or body.end is None):
        raise HTTPException(422, 'Provide both intro times in seconds.')
    try:
        intros.manual(row, None if body.disabled else body.start, None if body.disabled else body.end)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return intros.available(row)


# Deliberately exclude listener, database, executable paths, and arbitrary environment keys.
DEFAULTS = dict(MOVIES_DIR='media/Movies', CAST_HOST='', CAST_NAME='Living Room',
    AUTO_LIBRARY_SCAN_SECONDS='300', AUTO_CREDITS='true', AUTO_VISUAL_CREDITS='true', AUTO_ARTWORK='true', AUTO_SUBTITLES='true', AUTO_INTROS='true',
    SUBTITLE_LANGUAGES='en', SUBTITLE_DAILY_DOWNLOAD_LIMIT='5', ROKU_CACHE_MAX_GB='50',
    ROKU_VIDEO_ENCODER='libx264', PUBLIC_BASE_URL='')


def running_settings():
    values = {}
    for key in DEFAULTS:
        value = getattr(config, key, None)
        if key == 'ROKU_CACHE_MAX_GB': value = config.ROKU_CACHE_MAX_BYTES / 1024**3
        if isinstance(value, list): value = ','.join(value)
        if isinstance(value, bool): value = str(value).lower()
        values[key] = str(value)
    return values


@router.get('/settings')
def settings():
    saved = dotenv_values(config.ROOT / '.env', interpolate=False)
    running = running_settings()
    values = {k: saved.get(k, running[k]) or '' for k in DEFAULTS}
    return dict(values=values, running=running, key_configured=bool(config.OPENSUBTITLES_API_KEY),
        saved_key_configured=bool(saved.get('OPENSUBTITLES_API_KEY', config.OPENSUBTITLES_API_KEY)),
        restart_command='systemctl --user restart roku-media-server.service',
        environment_overrides=[k for k in DEFAULTS if k in config.ENVIRONMENT_KEYS and saved.get(k) is not None and os.environ[k] != saved[k]])


class SettingsEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    values: dict[str, str]
    opensubtitles_key: str | None = Field(default=None, max_length=500)


def validate_setting(key, value):
    if key not in DEFAULTS or len(value) > 1000 or any(c in value for c in '\r\n\x00'):
        raise HTTPException(422, 'Unknown setting or invalid value.')
    if key.startswith('AUTO_') and key != 'AUTO_LIBRARY_SCAN_SECONDS':
        if value not in {'true', 'false'}: raise HTTPException(422, f'{key}: use true or false.')
    elif key in {'AUTO_LIBRARY_SCAN_SECONDS', 'SUBTITLE_DAILY_DOWNLOAD_LIMIT', 'ROKU_CACHE_MAX_GB'}:
        limits = {'AUTO_LIBRARY_SCAN_SECONDS': (10, 86400), 'SUBTITLE_DAILY_DOWNLOAD_LIMIT': (1, 100), 'ROKU_CACHE_MAX_GB': (1, 10000)}
        try: n = int(value)
        except ValueError: raise HTTPException(422, f'{key}: enter a whole number.')
        if not limits[key][0] <= n <= limits[key][1]: raise HTTPException(422, f'{key}: outside the supported range.')
    elif key == 'MOVIES_DIR':
        path = Path(value).expanduser()
        if not path.is_absolute(): path = config.ROOT / path
        if not value or not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
            raise HTTPException(422, 'Media folder must already exist and be readable by the server.')
    elif key == 'PUBLIC_BASE_URL' and value:
        parsed = urlsplit(value)
        try: parsed.port
        except ValueError: raise HTTPException(422, 'Invalid server URL port.')
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'} or any(c.isspace() for c in value):
            raise HTTPException(422, 'Enter an HTTP(S) server base URL without credentials, path, or query.')
    elif key == 'CAST_HOST' and value and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.\-]{0,252}', value):
        raise HTTPException(422, 'TV address must be an IPv4 address or hostname, without http:// or a port.')
    elif key == 'SUBTITLE_LANGUAGES' and not re.fullmatch(r'[a-z]{2,3}(,[a-z]{2,3})*', value):
        raise HTTPException(422, 'Use comma-separated language codes such as en,es.')
    elif key == 'ROKU_VIDEO_ENCODER' and value not in {'libx264', 'h264_nvenc'}:
        raise HTTPException(422, 'Choose libx264 or h264_nvenc.')
    elif key == 'CAST_NAME' and not value.strip():
        raise HTTPException(422, 'Enter a TV name.')


@router.put('/settings')
def save_settings(body: SettingsEdit):
    for key, value in body.values.items(): validate_setting(key, value)
    updates = dict(body.values)
    if body.opensubtitles_key:
        if not re.fullmatch(r'[A-Za-z0-9_\-\.]+', body.opensubtitles_key):
            raise HTTPException(422, 'API key contains unsupported characters.')
        updates['OPENSUBTITLES_API_KEY'] = body.opensubtitles_key
    with lock:
        path = config.ROOT / '.env'
        lines = path.read_text().splitlines() if path.exists() else []
        output = []
        remaining = dict(updates)
        for line in lines:
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
            if match and match[1] in updates:
                if match[1] in remaining:
                    output.append(match[1] + '=' + "'" + remaining.pop(match[1]).replace('\\', '\\\\').replace("'", "\\'") + "'")
            else: output.append(line)
        for key, value in remaining.items():
            output.append(key + '=' + "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'")
        atomic_write(path, '\n'.join(output) + '\n', private=True)
    return dict(saved=True, restart_required=True, message='Settings saved. Restart the server to apply them; then scan if you changed the media folder.')


@router.get('/roku-package')
def roku_package(request: Request):
    # Package per request in memory: never overwrite the existing ZIP/configuration.
    url = str(request.base_url).rstrip('/')
    if any(c in url for c in '"\r\n'): raise HTTPException(422, 'Invalid server address.')
    source = config.ROOT / 'roku'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if not path.is_file() or any(p.startswith('.') for p in path.relative_to(source).parts): continue
            name = path.relative_to(source).as_posix()
            content = path.read_bytes()
            if name == 'source/Config.brs':
                content = re.sub(r'return "[^"]*"', lambda _: 'return "' + url + '"', content.decode()).encode()
            archive.writestr(name, content)
    return Response(buffer.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="gravyflix-roku.zip"', 'Cache-Control': 'no-store'})


class CreditEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    disabled: bool = False
    start: float | None = Field(default=None, gt=0, allow_inf_nan=False)


@router.put('/credits/{movie_id}')
def edit_credits(movie_id: int, body: CreditEdit):
    from .main import get_movie
    from . import credits
    row = get_movie(movie_id)
    if not body.disabled and body.start is None:
        raise HTTPException(422, 'Provide the credits start in seconds.')
    try:
        credits.manual(row, None if body.disabled else body.start)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return credits.available(row)


@router.post('/credits/process')
def process_credits():
    from .credits import CreditWorker
    def run():
        worker = CreditWorker()
        try: return worker.run_once()
        finally: worker.close()
    return submit('Analyze movie endings (up to 3 movies)', run)

@router.get('/playback')
def playback_diagnostics():
    from .playback_diagnostics import report
    return report()

@router.get('/playback/export')
def playback_export():
    from .playback_diagnostics import report
    return Response(json.dumps(report(), indent=2), media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="gravyflix-playback-diagnostics.json"','Cache-Control':'no-store'})
