"""Server-owned Cast session, captions, resume history and bounded autoplay."""
import logging
import threading
import time
from datetime import datetime, timezone
from . import config
from .database import connection
from .cast_autoplay import load_catalog, find_item, next_item
from . import subtitles
log = logging.getLogger('media')
LANG = {'eng': 'en', 'spa': 'es', 'fre': 'fr', 'ger': 'de', 'ita': 'it', 'por': 'pt', 'jpn': 'ja', 'chi': 'zh', 'rus': 'ru', 'und': 'und'}

def initialize():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS cast_history (\n            movie_id INTEGER PRIMARY KEY, position REAL NOT NULL, duration REAL NOT NULL,\n            completed INTEGER NOT NULL, updated_at TEXT NOT NULL)')

def history():
    from .watch_history import history as shared_history
    return shared_history()

class CastFeatures:

    def __init__(self, manager):
        self.manager = manager
        self.catalog = []
        self.current = None
        self.next = None
        self.visited = set()
        self.transitions = 0
        self.confirm = False
        self.enabled = True
        self.caption_language = None
        self.error = ''
        self.running = False
        self.suspended = False
        self.stop = threading.Event()
        self.thread = None
        self.last_save = 0
        self.last_player_state = None
        self.last_position = 0
        self.finishing = False
        self.prepared_token = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self.loop, name='cast-autoplay', daemon=True)
        self.thread.start()

    def release_prepared(self):
        if self.prepared_token:
            from .roku_audio import cache
            cache.release(self.prepared_token)
            self.prepared_token = None

    def close(self):
        self.release_prepared()
        self.stop.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def prepare(self, row, manual):
        self.release_prepared()
        base = self.manager.stream_base()
        self.catalog = load_catalog(base)
        if manual:
            self.visited = set()
            self.transitions = 0
            self.confirm = False
        self.last_player_state = None
        self.last_position = 0
        self.session_id=None
        self.sequence=0
        self.current = find_item(row['id'], self.catalog) or dict(row, kind='movie')
        self.visited.add(row['id'])
        self.next = next_item(self.current, self.catalog, self.visited)
        self.error = ''
        self.suspended = False
        self.running = False
        self.finishing = False
        data = subtitles.available(row, base)
        tracks = [dict(trackId=index + 1, type='TEXT', subtype='SUBTITLES', name=t['description'], language=LANG.get(t['language'], t['language']), trackContentId=t['url'][:-4] + '.vtt', trackContentType='text/vtt', _language=t['language']) for index, t in enumerate(data['tracks'])]
        self.tracks = tracks
        return [{k: v for k, v in t.items() if not k.startswith('_')} for t in tracks]

    def loaded(self):
        self.running = True
        self.start()
        if self.caption_language:
            selected = next((t for t in getattr(self, 'tracks', []) if t['_language'] == self.caption_language), None)
            if selected:
                try:
                    self.manager.cast.media_controller.enable_subtitle(selected['trackId'], timeout=5)
                except Exception:
                    log.exception('CAST: Could not restore captions')

    def status_fields(self, status):
        tracks = getattr(status, 'subtitle_tracks', []) or []
        if not isinstance(tracks, list):
            tracks = []
        active = getattr(status, 'current_subtitle_tracks', []) or []
        duration = getattr(status, 'duration', 0) or 0
        position = getattr(status, 'adjusted_current_time', 0) or 0
        credits_start = self.current.get('credits_start') if self.current and self.current.get('kind') == 'movie' else None
        up_next_visible = duration > 0 and (position >= credits_start if credits_start is not None and 0 < credits_start < duration else duration - position <= 30)
        return dict(up_next_visible=up_next_visible, credits_start=credits_start, movie_id=self.current['id'] if self.current else None, next_item={k: self.next.get(k) for k in ('id', 'title', 'kind', 'show_title', 'landscape_url', 'poster_url')} if self.next else None, remaining=max(0, int(duration - position + 0.999)), autoplay_enabled=self.enabled, autoplay_suspended=self.suspended, autoplay_count=self.transitions, still_watching=self.confirm, autoplay_error=self.error, subtitle_tracks=[dict(id=t['trackId'], label=t.get('name', t.get('language', 'Subtitle')), language=t.get('language', 'und')) for t in tracks if t.get('type') == 'TEXT' and isinstance(t.get('trackId'), int)], subtitle_active=active[0] if active else None)

    def captions(self, track_id):
        if not self.manager.snapshot()['active']:
            raise RuntimeError('No GRAVYFLIX title is playing.')
        controller = self.manager.cast.media_controller
        if track_id is None:
            controller.disable_subtitle(timeout=5)
            self.caption_language = None
        else:
            offered = self.manager.snapshot()['subtitle_tracks']
            if not any((t['id'] == track_id for t in offered)):
                raise ValueError('Subtitle track is not available.')
            controller.enable_subtitle(track_id, timeout=5)
            chosen = next((t for t in getattr(self, 'tracks', []) if t['trackId'] == track_id), None)
            self.caption_language = chosen['_language'] if chosen else None
        return self.manager.snapshot()

    def save(self, status, completed=False, state_override=None):
        if not self.current:
            return
        duration = float(getattr(status, 'duration', 0) or 0)
        position = float(getattr(status, 'adjusted_current_time', 0) or 0)
        if duration <= 0:
            return
        if completed:
            position = duration
        from . import watch_history
        if not getattr(self,'session_id',None):
            from .main import get_movie
            try:
                row=get_movie(self.current['id'])
            except Exception:
                log.warning('HISTORY: title is unavailable; skipping progress update')
                return
            self.session_id=watch_history.create(row,'vizio','cast','resume')['session_id']
            self.sequence=0
            watch_history.record(self.session_id,0,position,duration,'playing')
        self.sequence+=1
        state=state_override or ('finished' if completed else status.player_state.lower())
        if state not in {'playing','paused','buffering','finished','next','error','stopped'}: state='stopped'
        watch_history.record(self.session_id,self.sequence,position,duration,state,credits_start=self.current.get('credits_start'))
        if state in {'finished','stopped','error'}:self.release_prepared()
        self.last_player_state = status.player_state
        self.last_position = position
        self.last_save = time.monotonic()

    def advance(self, confirm=False):
        if not self.next:
            raise RuntimeError('No next title available.')
        if self.transitions >= 3 and (not confirm):
            self.confirm = True
            status = self.manager.cast.media_controller.status
            if status.player_state == 'PLAYING':
                self.manager.cast.media_controller.pause(timeout=5)
            return self.manager.snapshot()
        if confirm:
            self.transitions = 0
        self.confirm = False
        if self.current and self.manager.cast:self.save(self.manager.cast.media_controller.status,state_override='next')
        row_id = self.next['id']
        self.transitions += 1
        self.running = False
        from .main import get_movie
        return self.manager.play_movie(get_movie(row_id), manual=False, intent="autoplay")

    def loop(self):
        while not self.stop.wait(1):
            try:
                with self.manager.lock:
                    self.tick()
            except Exception:
                self.error = 'Autoplay stopped. Open the next title to retry.'
                self.running = False
                log.exception('CAST: Autoplay stopped')

    def tick(self):
        """Only advance our own finished session; never take over other Cast apps."""
        if not self.running or not self.manager.cast:
            return
        if self.prepared_token:
            from .roku_audio import cache
            cache.status(self.prepared_token)
        status = self.manager.cast.media_controller.status
        if status.content_id != self.manager.media_url:
            self.running = False
            return
        if status.player_state in {'PLAYING', 'PAUSED', 'BUFFERING'}:
            if status.player_state != self.last_player_state or (status.adjusted_current_time or 0) < self.last_position-1 or (status.adjusted_current_time or 0) > self.last_position+20 or time.monotonic() - self.last_save >= 15:
                self.save(status)
        elif status.player_state == 'IDLE':
            if status.idle_reason == 'FINISHED' and (not self.finishing):
                self.finishing = True
                self.save(status, True)
                if self.enabled and (not self.suspended) and self.next and (not self.confirm):
                    self.advance()
                elif not self.confirm:
                    self.running = False
            elif status.idle_reason in {'ERROR', 'CANCELLED', 'INTERRUPTED'}:
                self.save(status,state_override='error' if status.idle_reason=='ERROR' else 'stopped')
                self.running = False
