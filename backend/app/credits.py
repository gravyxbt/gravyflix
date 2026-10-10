"""Movie credits from chapters, bounded local visual recognition, and manual overrides."""
import fcntl
import hashlib
import os
import signal
import sys
import json
import logging
import math
import subprocess
import threading
import time
from . import config
from .database import connection
from .media_tools import binary

log = logging.getLogger('media')
VERSION = 1
from .credit_detection import VERSION as VISUAL_VERSION

NAMES = {'credits', 'end credits', 'ending credits', 'closing credits', 'closing titles', 'end titles', 'credit roll', 'rolling credits'}


def initialize():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS credit_markers (
            movie_id INTEGER PRIMARY KEY, signature TEXT NOT NULL, state TEXT NOT NULL,
            start REAL, method TEXT NOT NULL, note TEXT NOT NULL, updated_at REAL NOT NULL)''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(credit_markers)')}
        for name, declaration in {'analysis_version': 'INTEGER NOT NULL DEFAULT 0', 'confidence':'REAL', 'details':'TEXT', 'retry_at':'REAL NOT NULL DEFAULT 0'}.items():
            if name not in columns:
                db.execute(f'ALTER TABLE credit_markers ADD COLUMN {name} {declaration}')


def signature(row):
    return hashlib.sha256(f"{VERSION}:{row['file_path']}:{row['file_size']}:{row['modification_time']}".encode()).hexdigest()


def movie_ids():
    from .models import movie_response
    from .catalog import build_catalog
    with connection() as db:
        rows = db.execute("SELECT * FROM movies WHERE available=1 AND substr(filename,1,2) != '._'").fetchall()
    catalog = build_catalog([movie_response(r, '', include_credits=False).model_dump() for r in rows])
    return {i['id'] for i in catalog if i['kind'] == 'movie'}


def marker_from_chapters(chapters, duration):
    if not duration or not math.isfinite(duration) or duration < 600:
        return None
    candidates = []
    for chapter in chapters:
        title = str(chapter.get('tags', {}).get('title', '')).strip().casefold().replace('_', ' ')
        if title not in NAMES:
            continue
        try: start = float(chapter['start_time'])
        except (KeyError, ValueError, TypeError): continue
        # Ignore opening credits and implausible/malformed chapter metadata.
        if math.isfinite(start) and duration * .65 <= start < duration - 5:
            candidates.append(start)
    return min(candidates, default=None)


def available(row):
    from .intros import checked
    try: checked(row)
    except (ValueError, OSError):
        return dict(state='pending', start=None, method=None, note='Media changed or unavailable; rescan the library')
    with connection() as db:
        saved = db.execute('SELECT * FROM credit_markers WHERE movie_id=?', (row['id'],)).fetchone()
    if not saved or saved['signature'] != signature(row):
        return dict(state='pending', start=None, method=None, note='Credits have not been checked yet')
    duration = row['duration'] or 0
    start = saved['start']
    if start is not None and not 0 < start < duration:
        return dict(state='pending', start=None, method=None, note='Credits timing needs review')
    return {k:saved[k] for k in ('state', 'start', 'method', 'note', 'confidence', 'analysis_version', 'retry_at')}


def start_for(row):
    # During old-schema tests/migrations, unknown credits retain the original behavior.
    import sqlite3
    try: result = available(row)
    except sqlite3.OperationalError: return None
    return result['start'] if result['state'] == 'ready' else None


def save(row, start, method, note, *, confidence=None, details=None, state=None, retry_at=0, analysis_version=0):
    state = state or ('ready' if start is not None else 'disabled' if method == 'manual' else 'no_match')
    with connection() as db:
        db.execute('''INSERT INTO credit_markers (movie_id,signature,state,start,method,note,updated_at,analysis_version,confidence,details,retry_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(movie_id) DO UPDATE SET
            signature=excluded.signature,state=excluded.state,start=excluded.start,
            method=excluded.method,note=excluded.note,updated_at=excluded.updated_at,
            analysis_version=excluded.analysis_version,confidence=excluded.confidence,details=excluded.details,retry_at=excluded.retry_at
            WHERE credit_markers.method != 'manual' OR credit_markers.signature != excluded.signature OR excluded.method = 'manual'
        ''', (row['id'], signature(row), state, start, method, note, time.time(), analysis_version, confidence, json.dumps(details) if details else None, retry_at))


def manual(row, start=None):
    from .intros import checked
    checked(row)
    if row['id'] not in movie_ids():
        raise ValueError('Credits timing is available for movies only')
    if start is not None and (not math.isfinite(start) or not 0 < start < (row['duration'] or 0)):
        raise ValueError('Credits start must be greater than zero and before the movie ends')
    save(row, start, 'manual', 'Credits start reviewed by user' if start is not None else 'Early next-movie prompt disabled for this movie')


class CreditWorker:
    def __init__(self):
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        if not config.AUTO_CREDITS: return
        self.thread = threading.Thread(target=self.loop, name='movie-credits', daemon=True)
        self.thread.start()

    def request(self):
        self.wake.set()

    def close(self):
        self.stop.set(); self.wake.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                try: os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
        if self.thread: self.thread.join(timeout=5)

    def loop(self):
        while not self.stop.is_set():
            try:
                result = self.run_once()
            except Exception:
                result = {}
                log.exception('CREDITS: Could not analyze movie endings')
            self.wake.wait(1 if result.get("checked",0) >= 3 else config.AUTO_LIBRARY_SCAN_SECONDS)
            self.wake.clear()

    def chapters(self, path):
        executable = binary('ffprobe')
        if not executable: raise RuntimeError('ffprobe is unavailable')
        with self.lock:
            if self.stop.is_set(): raise InterruptedError('Credits scan cancelled')
            self.process = subprocess.Popen([executable, '-v', 'error', '-show_chapters', '-of', 'json', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            output, _ = self.process.communicate(timeout=30)
            if self.process.returncode: raise RuntimeError('Chapter probe failed')
            return json.loads(output).get('chapters', [])
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.communicate()
            raise RuntimeError('Chapter probe timed out')
        finally:
            with self.lock: self.process = None

    def visual(self, path, duration):
        import importlib.util
        if not importlib.util.find_spec('rapidocr') or not importlib.util.find_spec('onnxruntime'):
            raise RuntimeError('Install backend requirements to enable visual credits detection')
        env = dict(os.environ, PYTHONPATH=str(config.ROOT/'backend'), OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
        with self.lock:
            if self.stop.is_set(): raise InterruptedError('Credits scan cancelled')
            self.process = subprocess.Popen([sys.executable, '-m', 'app.credit_detection', '--path', str(path),
                '--duration', str(duration), '--timeout', str(config.CREDIT_ANALYSIS_TIMEOUT)],
                cwd=config.ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            output, error = self.process.communicate(timeout=config.CREDIT_ANALYSIS_TIMEOUT+10)
            if self.stop.is_set(): raise InterruptedError('Credits scan cancelled')
            if self.process.returncode:
                log.warning('CREDITS: Visual analyzer failed (%s)', error.decode(errors='replace')[-300:])
                raise RuntimeError('Visual credits analyzer did not complete')
            data = json.loads(output)
            start = data.get('start')
            if start is not None and not duration*.65 <= start < duration-5:
                raise ValueError('Visual credit timing outside movie ending')
            return data
        except subprocess.TimeoutExpired:
            try: os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.process.communicate()
            raise RuntimeError('Visual credits analysis timed out')
        finally:
            with self.lock: self.process = None

    def run_once(self, limit=3):
        # Dashboard and automatic worker share this cross-process lock.
        path = config.ROOT/'data/credit-analysis.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as guard:
            try: fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return dict(checked=0, found=0, busy=True)
            return self._run_once(limit)

    def _run_once(self, limit):
        from .intros import checked
        eligible = movie_ids()
        found = checked_count = attempted = 0
        with connection() as db:
            rows = db.execute('SELECT * FROM movies WHERE available=1 ORDER BY date_added DESC,id').fetchall()
        for row in rows:
            if self.stop.is_set() or attempted >= limit: break
            if row['id'] not in eligible or not row['duration'] or row['duration'] < 600: continue
            state = available(row)
            if state.get('method') == 'manual' or state['state'] == 'ready': continue
            if state.get('retry_at',0)>time.time(): continue
            if state['state'] != 'pending':
                if not config.AUTO_VISUAL_CREDITS or state.get('analysis_version',0) == VISUAL_VERSION: continue
            attempted += 1
            try:
                path = checked(row)
                start = marker_from_chapters(self.chapters(path), row['duration'])
                if start is not None:
                    save(row, start, 'chapter', 'Named end-credits chapter', confidence=1.0)
                elif config.AUTO_VISUAL_CREDITS:
                    # Foreground/next-episode compatibility conversion takes priority.
                    from .roku_audio import cache
                    with cache.lock:
                        converting = any(j.state in {'queued','preparing'} for j in cache.jobs.values())
                    if converting:
                        log.info('CREDITS: Deferring visual analysis while playback preparation is active')
                        continue
                    save(row,None,'visual','Analyzing movie ending automatically',state='analyzing')
                    log.info('CREDITS: Analyzing %s',row['title'])
                    result = self.visual(path,row['duration'])
                    checked(row)
                    start = result['start']
                    save(row,start,'visual',result['note'],confidence=result['confidence'],
                        details=result.get('evidence'),analysis_version=VISUAL_VERSION)
                else:
                    save(row,None,'chapter','No named credits chapter; visual analysis is disabled')
                checked_count += 1
                if start is not None:
                    found += 1
                    log.info('CREDITS: %s starts at %.1f seconds', row['title'], start)
            except InterruptedError:
                break
            except Exception:
                log.exception('CREDITS: Analysis failed for movie id %s; will retry', row['id'])
                save(row,None,'visual','Analysis could not complete; automatic retry is scheduled',state='error',retry_at=time.time()+3600)
        return dict(checked=checked_count, found=found)
