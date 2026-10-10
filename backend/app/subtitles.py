"""Managed local text captions and bounded, persistent background discovery."""
import hashlib
import fcntl
import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from . import config
from .database import connection
from .media_tools import binary, inspect_media

log = logging.getLogger('media')
TEXT = {'subrip', 'srt', 'ass', 'ssa', 'webvtt', 'mov_text', 'text', 'ttml'}
LANGUAGES = {'en':'eng','eng':'eng','es':'spa','spa':'spa','fr':'fre','fra':'fre','fre':'fre','de':'ger','deu':'ger','ger':'ger','it':'ita','pt':'por','ja':'jpn','zh':'chi','ru':'rus'}
MAX_SIZE = 8 * 1024 * 1024
STAMP = re.compile(r'(?m)^\s*\d{2,}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2,}:\d{2}:\d{2}[,.]\d{3}')

def initialize():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS subtitle_jobs (
            movie_id INTEGER PRIMARY KEY, signature TEXT NOT NULL, tracks TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', retry_at REAL NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS subtitle_provider_budget (
            day TEXT PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0)''')

def root():
    path = config.ROOT / 'data/subtitles'
    path.mkdir(parents=True, exist_ok=True)
    return path

def checked_path(row):
    path = Path(row['file_path']).resolve()
    if not path.is_relative_to(config.MOVIES_DIR.resolve()) or not path.is_file():
        raise ValueError('Media file unavailable')
    return path

def sidecars(path):
    return sorted(p for p in path.parent.iterdir() if p.is_file() and not p.name.startswith('._')
        and p.suffix.lower() in {'.srt','.vtt','.ass','.ssa'}
        and (p.stem == path.stem or p.stem.startswith(path.stem + '.'))
        and p.resolve().is_relative_to(config.MOVIES_DIR.resolve()))

def signature(path, local):
    data = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in [path, *local]]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()

def validate_srt(data):
    if not data or len(data) > MAX_SIZE:
        raise ValueError('Subtitle is empty or exceeds size limit')
    text = data.decode('utf-8-sig')
    if not STAMP.search(text) or '\x00' in text:
        raise ValueError('Invalid UTF-8 SRT timestamps')
    return text.replace('\r\n','\n')

def publish(track_id, data):
    text = validate_srt(data)
    output = root() / (track_id + '.srt')
    temporary = output.with_suffix('.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(output)

def track(track_id, language, forced, sdh, source, label=''):
    language = LANGUAGES.get(language.lower(), language.lower() if len(language) == 3 else 'und')
    kind = 'forced' if forced else 'sdh' if sdh else 'regular'
    description = label or {'eng':'English','spa':'Spanish','fre':'French','und':'Unknown language'}.get(language, language)
    if kind != 'regular': description += ' (' + kind.upper() + ')'
    return dict(id=track_id, language=language, kind=kind, description=description, source=source)

def convert(path, output, stream=None):
    executable = binary('ffmpeg')
    if not executable: raise RuntimeError('FFmpeg unavailable')
    command = [executable,'-v','error','-nostdin','-y','-i',str(path)]
    if stream is not None: command += ['-map',f'0:{stream}']
    command += ['-c:s','srt','-f','srt',str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    if output.stat().st_size > MAX_SIZE: raise ValueError('Subtitle too large')
    return output.read_bytes()

def discover(row, sig, local):
    path = checked_path(row)
    tracks = []
    sources = []
    for p in local:
        tags = p.stem[len(path.stem):].strip('.').lower().split('.')
        language = next((x for x in tags if x in LANGUAGES), 'und')
        sources.append((p, None, language, 'forced' in tags, 'sdh' in tags or 'hi' in tags, 'sidecar', ''))
    info = inspect_media(path)
    for s in info.get('streams',[]):
        if s.get('codec_type') != 'subtitle' or s.get('codec_name') not in TEXT: continue
        tags, flags = s.get('tags',{}), s.get('disposition',{})
        sources.append((path, s['index'], tags.get('language','und'), bool(flags.get('forced')),
                        bool(flags.get('hearing_impaired')), 'embedded', tags.get('title','')))
    for p, index, lang, forced, sdh, source, label in sources:
        key = hashlib.sha256(f'{row["id"]}:{sig}:{p}:{index}'.encode()).hexdigest()
        temporary = root() / (key + '.extract')
        try:
            data = p.read_bytes() if index is None and p.suffix.lower() == '.srt' and p.stat().st_size <= MAX_SIZE else convert(p, temporary, index)
            publish(key, data)
            tracks.append(track(key, lang, forced, sdh, source, label))
            log.info('SUBTITLE: Ready %s %s %s', row['filename'], source, lang)
        except (OSError, ValueError, UnicodeError, RuntimeError, subprocess.SubprocessError):
            log.warning('SUBTITLE: Could not extract %s stream=%s', p.name, index)
        finally:
            temporary.unlink(missing_ok=True)
    return tracks

def saved(movie_id):
    with connection() as db:
        row = db.execute('SELECT * FROM subtitle_jobs WHERE movie_id=?',(movie_id,)).fetchone()
    return dict(row) if row else None

def store(movie_id, sig, tracks, state, note='', retry=0):
    with connection() as db:
        db.execute('''INSERT INTO subtitle_jobs VALUES (?,?,?,?,?,?) ON CONFLICT(movie_id)
            DO UPDATE SET signature=excluded.signature,tracks=excluded.tracks,state=excluded.state,
            note=excluded.note,retry_at=excluded.retry_at''', (movie_id,sig,json.dumps(tracks),state,note,retry))

def available(row, base):
    old = saved(row['id'])
    if not old: return {'tracks':[], 'state':'pending'}
    try:
        path = checked_path(row)
        if old['signature'] != signature(path, sidecars(path)): return {'tracks':[], 'state':'pending'}
    except (OSError,ValueError): return {'tracks':[], 'state':'unavailable'}
    tracks = [dict(t, url=f'{base}/subtitles/{t["id"]}.srt') for t in json.loads(old['tracks']) if (root()/(t['id']+'.srt')).is_file()]
    return dict(tracks=tracks,state=old['state'],note=old['note'])

class SubtitleWorker:
    def __init__(self):
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
    def start(self):
        if not config.AUTO_SUBTITLES: return
        initialize()
        self.thread = threading.Thread(target=self.loop, name='subtitle-worker',daemon=True)
        self.thread.start()
    def request(self): self.wake.set()
    def close(self):
        self.stop.set(); self.wake.set()
        if self.thread: self.thread.join(timeout=3)
    def loop(self):
        while not self.stop.is_set():
            try: self.run_once()
            except Exception: log.exception('SUBTITLE: Background pass failed')
            self.wake.wait(60); self.wake.clear()
    def run_once(self):
        # Serialize the daemon and administrative CLI across processes.
        with (root()/'.worker.lock').open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return
            try: self._process()
            finally: fcntl.flock(lock, fcntl.LOCK_UN)
    def _process(self):
        with connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM movies WHERE available=1 ORDER BY date_added DESC,id DESC')]
        from .opensubtitles import enrich
        for row in rows:
            if self.stop.is_set(): return
            if row['filename'].startswith('._'): continue
            sig = None
            try:
                path = checked_path(row); local = sidecars(path); sig = signature(path, local)
                old = saved(row['id'])
                same = old and old['signature'] == sig
                tracks = json.loads(old['tracks']) if same else discover(row,sig,local)
                if same and any(not (root()/(t['id']+'.srt')).is_file() for t in tracks):
                    tracks = discover(row,sig,local); same = False
                key_added = same and old['state'] == 'configuration_required' and config.OPENSUBTITLES_API_KEY
                if same and old['retry_at'] > time.time() and not key_added: continue
                if same and old['state'] == 'ready': continue
                tracks, state, note, retry = enrich(row,path,sig,tracks,self.stop)
                # A file copied/replaced during work is retried rather than publishing stale metadata.
                if sig != signature(path,sidecars(path)): continue
                store(row['id'],sig,tracks,state,note,retry)
            except Exception as exc:
                log.warning('SUBTITLE: Could not process movie id %s (%s)',row['id'],type(exc).__name__)
                # Bound retries for corrupt/unreadable files; no raw credential-bearing exception text.
                if sig is not None: store(row['id'],sig,[], 'failed','Local processing failed',time.time()+3600)
