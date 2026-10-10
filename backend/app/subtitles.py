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
LOCAL_VERSION = 1
BITMAP = {'dvd_subtitle'}
TEXT = {'subrip', 'srt', 'ass', 'ssa', 'webvtt', 'mov_text', 'text', 'ttml'}
LANGUAGES = {'en':'eng','eng':'eng','es':'spa','spa':'spa','fr':'fre','fra':'fre','fre':'fre','de':'ger','deu':'ger','ger':'ger','it':'ita','pt':'por','ja':'jpn','zh':'chi','ru':'rus'}
MAX_SIZE = 8 * 1024 * 1024
STAMP = re.compile(r'(?m)^\s*\d{2,}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2,}:\d{2}:\d{2}[,.]\d{3}')

def initialize():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS subtitle_jobs (
            movie_id INTEGER PRIMARY KEY, signature TEXT NOT NULL, tracks TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', retry_at REAL NOT NULL DEFAULT 0)''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(subtitle_jobs)')}
        for name, definition in [('embedded', "TEXT NOT NULL DEFAULT '[]'"), ('local_revision', "TEXT NOT NULL DEFAULT ''")]:
            if name not in columns: db.execute(f'ALTER TABLE subtitle_jobs ADD COLUMN {name} {definition}')
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

def discover(row, sig, local, existing=(), info=None, stop=None):
    path = checked_path(row)
    tracks = list(existing)
    sources = []
    for p in local:
        tags = p.stem[len(path.stem):].strip('.').lower().split('.')
        language = next((x for x in tags if x in LANGUAGES), 'und')
        sources.append((p, None, language, 'forced' in tags, 'sdh' in tags or 'hi' in tags, 'sidecar', ''))
    info = info if info is not None else inspect_media(path)
    for s in info.get('streams',[]):
        if s.get('codec_type') != 'subtitle' or s.get('codec_name') not in TEXT: continue
        tags, flags = s.get('tags',{}), s.get('disposition',{})
        sources.append((path, s['index'], tags.get('language','und'), bool(flags.get('forced')),
                        bool(flags.get('hearing_impaired')), 'embedded', tags.get('title','')))
    requested = {LANGUAGES.get(lang, lang) for lang in config.SUBTITLE_LANGUAGES}
    for stream in info.get('streams', []):
        if stream.get('codec_name') not in BITMAP or stream.get('codec_type') != 'subtitle': continue
        tags, flags = stream.get('tags', {}), stream.get('disposition', {})
        lang = LANGUAGES.get(tags.get('language','und'), tags.get('language','und'))
        if lang not in requested: continue
        forced = bool(flags.get('forced'))
        if any(t['language'] == lang and (t['kind'] == 'forced' if forced else t['kind'] != 'forced') for t in tracks): continue
        sources.append((path, stream['index'], lang, forced, bool(flags.get('hearing_impaired')),
                        'embedded_ocr', tags.get('title', '')))
    for p, index, lang, forced, sdh, source, label in sources:
        version = f':ocr{LOCAL_VERSION}' if source == 'embedded_ocr' else ''
        key = hashlib.sha256(f'{row["id"]}:{sig}:{p}:{index}{version}'.encode()).hexdigest()
        if any(t['id'] == key for t in tracks): continue
        if source == 'embedded_ocr' and any(t['language'] == lang and (t['kind'] == 'forced' if forced else t['kind'] != 'forced') for t in tracks): continue
        if stop and stop.is_set(): raise InterruptedError('Subtitle discovery cancelled')
        temporary = root() / (key + '.extract')
        try:
            if source == 'embedded_ocr':
                log.info('SUBTITLE: OCR starting %s stream=%s language=%s', row['filename'], index, lang)
                from .subtitle_ocr import convert as bitmap_convert
                cached = root() / (key + '.srt')
                data = cached.read_bytes() if cached.is_file() else bitmap_convert(p, index, temporary, root() / (key + '.ocr.json'), stop)
            else:
                data = p.read_bytes() if index is None and p.suffix.lower() == '.srt' and p.stat().st_size <= MAX_SIZE else convert(p, temporary, index)
            publish(key, data)
            tracks.append(track(key, lang, forced, sdh, source, label))
            log.info('SUBTITLE: Ready %s %s %s', row['filename'], source, lang)
        except InterruptedError:
            raise
        except (OSError, ValueError, UnicodeError, RuntimeError, subprocess.SubprocessError, TimeoutError):
            log.warning('SUBTITLE: Could not extract %s stream=%s', p.name, index)
        finally:
            temporary.unlink(missing_ok=True)
    return tracks

def saved(movie_id):
    with connection() as db:
        row = db.execute('SELECT * FROM subtitle_jobs WHERE movie_id=?',(movie_id,)).fetchone()
    return dict(row) if row else None

def store(movie_id, sig, tracks, state, note='', retry=0, embedded=None, revision=None):
    with connection() as db:
        db.execute("""INSERT INTO subtitle_jobs(movie_id,signature,tracks,state,note,retry_at,embedded,local_revision)
            VALUES(?,?,?,?,?,?,COALESCE(?,(SELECT embedded FROM subtitle_jobs WHERE movie_id=?),'[]'),
                COALESCE(?,(SELECT local_revision FROM subtitle_jobs WHERE movie_id=?),'')) ON CONFLICT(movie_id)
            DO UPDATE SET signature=excluded.signature,tracks=excluded.tracks,state=excluded.state,
            note=excluded.note,retry_at=excluded.retry_at,embedded=excluded.embedded,local_revision=excluded.local_revision""",
            (movie_id,sig,json.dumps(tracks),state,note,retry,json.dumps(embedded) if embedded is not None else None,
             movie_id,revision,movie_id))


def embedded_info(info):
    return [dict(index=s['index'], codec=s.get('codec_name','unknown'),
                 language=LANGUAGES.get(s.get('tags',{}).get('language','und'),s.get('tags',{}).get('language','und')),
                 image_based=s.get('codec_name') not in TEXT, convertible=s.get('codec_name') in BITMAP)
            for s in info.get('streams',[]) if s.get('codec_type') == 'subtitle']


def local_revision():
    return f'{LOCAL_VERSION}:' + ','.join(sorted(config.SUBTITLE_LANGUAGES))


def available(row, base):
    old = saved(row['id'])
    if not old: return {'tracks':[], 'state':'pending'}
    try:
        path = checked_path(row)
        if old['signature'] != signature(path, sidecars(path)): return {'tracks':[], 'state':'pending'}
    except (OSError,ValueError): return {'tracks':[], 'state':'unavailable'}
    tracks = [dict(t, url=f'{base}/subtitles/{t["id"]}.srt') for t in json.loads(old['tracks']) if (root()/(t['id']+'.srt')).is_file()]
    return dict(tracks=tracks,state=old['state'],note=old['note'],embedded_tracks=json.loads(old['embedded']))

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
        # Inventory the queue before OCR so browsing can distinguish embedded
        # images from absent subtitles while a long initial conversion pass runs.
        inventories = {}
        for row in rows:
            if self.stop.is_set(): return
            old = saved(row['id'])
            if old and old['local_revision'] == local_revision(): continue
            try:
                path = checked_path(row); sig = signature(path, sidecars(path))
                info = inspect_media(path); inventories[row['id']] = info
                embedded = embedded_info(info)
                if not any(e['convertible'] for e in embedded): continue
                same = old and old['signature'] == sig
                tracks = json.loads(old['tracks']) if same else []
                requested = {LANGUAGES.get(v,v) for v in config.SUBTITLE_LANGUAGES}
                needs_ocr = any(e['convertible'] and e['language'] in requested
                    and not any(t['language'] == e['language'] and t['kind'] != 'forced' for t in tracks) for e in embedded)
                store(row['id'],sig,tracks,'queued' if needs_ocr else (old['state'] if same else 'pending'),
                      'Embedded DVD subtitles queued for local conversion.' if needs_ocr else (old['note'] if same else ''),
                      old['retry_at'] if same else 0,embedded,old['local_revision'] if same else '')
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                continue
        for row in rows:
            if self.stop.is_set(): return
            if row['filename'].startswith('._'): continue
            sig = None
            try:
                path = checked_path(row); local = sidecars(path); sig = signature(path, local)
                old = saved(row['id'])
                same = old and old['signature'] == sig
                tracks = json.loads(old['tracks']) if same else []
                if same and old['local_revision'] and old['local_revision'].split(':')[0] != str(LOCAL_VERSION):
                    tracks = [t for t in tracks if t.get('source') != 'embedded_ocr']
                missing_assets = any(not (root()/(t['id']+'.srt')).is_file() for t in tracks)
                embedded = json.loads(old['embedded']) if same else []
                local_retry = same and old['retry_at'] <= time.time() and any(
                    e['convertible'] and e['language'] in {LANGUAGES.get(v,v) for v in config.SUBTITLE_LANGUAGES}
                    and not any(t['language'] == e['language'] and t['kind'] != 'forced' for t in tracks) for e in embedded)
                needs_local = not same or missing_assets or old['local_revision'] != local_revision() or local_retry
                if missing_assets: tracks = [t for t in tracks if (root()/(t['id']+'.srt')).is_file()]
                if needs_local:
                    info = inventories.get(row['id']) or inspect_media(path); embedded = embedded_info(info)
                    if any(t['convertible'] for t in embedded):
                        store(row['id'],sig,tracks,'processing','Converting embedded DVD subtitles locally.',0,
                              embedded=embedded,revision='')
                    tracks = discover(row,sig,local,existing=tracks,info=info,stop=self.stop)
                    same = False
                key_added = same and old['state'] == 'configuration_required' and config.OPENSUBTITLES_API_KEY
                if same and old['retry_at'] > time.time() and not key_added: continue
                if same and old['state'] == 'ready': continue
                tracks, state, note, retry = enrich(row,path,sig,tracks,self.stop)
                # A file copied/replaced during work is retried rather than publishing stale metadata.
                if sig != signature(path,sidecars(path)): continue
                if any(t.get('source') == 'embedded_ocr' for t in tracks) and state == 'ready':
                    note = 'Embedded DVD subtitles converted locally using OCR.'
                store(row['id'],sig,tracks,state,note,retry,embedded,local_revision())
            except InterruptedError:
                return
            except Exception as exc:
                log.warning('SUBTITLE: Could not process movie id %s (%s)',row['id'],type(exc).__name__)
                # Bound retries for corrupt/unreadable files; no raw credential-bearing exception text.
                if sig is not None: store(row['id'],sig,[], 'failed','Local processing failed',time.time()+3600)
