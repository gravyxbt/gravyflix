"""Receiver preparation runs outside the Cast control lock; stop stays responsive."""
import threading
import time
from . import watch_history
from .playback_policy import decide, media_row
from .roku_audio import cache

class Preparation:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.RLock()
        self.generation = 0
        self.pending = None
        self.error = None
        self.thread = None
        self.stop = threading.Event()

    def snapshot(self):
        with self.lock:
            if self.pending:
                return dict(self.pending)
            if self.error:
                return dict(state='ERROR', active=False, preparation_error=self.error)

    def cancel(self):
        with self.lock:
            self.generation += 1
            self.pending = None
            self.error = None

    def start(self, row, position=0, manual=True, intent='resume', mode='auto'):
        # Only one receiver exists. A new request supersedes preparation, never blocks on FFmpeg.
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError('A title is preparing. Cancel it before choosing another.')
            self.generation += 1
            generation = self.generation
            self.error = None
            self.pending = dict(state='PREPARING', active=False, title=row['title'], movie_id=row['id'],
                                preparation_progress=0, preparation_message='Checking playback compatibility')
            self.thread = threading.Thread(target=self.run, args=(dict(row), position, manual, intent, mode, generation), daemon=True, name='cast-prepare')
            self.thread.start()
            return dict(self.pending)

    def run(self, row, position, manual, intent, mode, generation):
        token = None
        sid = None
        ready = False
        started = time.monotonic()
        def current():
            with self.lock:
                return generation == self.generation and not self.stop.is_set()
        try:
            row = media_row(row)
            if not current(): return
            session = watch_history.create(row, 'vizio', 'cast', intent)
            sid = session['session_id']
            if intent == 'resume' and not position: position = session['resume_position']
            plan = decide(row, 'cast', mode)
            watch_history.delivery(sid, plan)
            if plan['delivery'] == 'unsupported':
                raise ValueError('This HDR title needs verified tone mapping. Choose an SDR copy or try original playback on a capable receiver.')
            for attempt in range(2):
                url = None
                if plan['delivery'] != 'direct':
                    token = cache.prepare(row, plan=plan)
                    while current():
                        status = cache.status(token)
                        with self.lock:
                            if self.pending and current():
                                self.pending.update(preparation_progress=status['progress'], preparation_message=status['message'])
                        if status['state'] == 'ready':
                            url = self.manager.stream_base() + '/api/playback/roku/media/' + status['key']
                            break
                        if status['state'] in {'failed','cancelled'}:
                            raise RuntimeError(status['message'])
                        self.stop.wait(.5)
                    if not current(): return
                watch_history.delivery(sid, plan, time.monotonic()-started)
                try:
                    # Only command setup is locked. Conversion above never holds this lock.
                    with self.manager.lock:
                        if not current(): return
                        self.manager._play_movie(row, position, manual, prepared_url=url, session_id=sid, plan=plan, valid=current)
                        ready = True
                        if token:
                            self.manager.features.prepared_token = token
                            token = None
                    break
                except RuntimeError as exc:
                    if attempt or mode == 'original' or plan['delivery'] == 'video_convert' or 'could not decode' not in str(exc):
                        raise
                    if token:
                        cache.release(token)
                        token = None
                    plan = decide(row, 'cast', 'compatible')
                    if plan['delivery'] == 'unsupported': raise
                    plan['reason'] = 'receiver_decoder_rejected_source'
                    watch_history.delivery(sid, plan)
            with self.lock:
                if current(): self.pending = None
        except Exception:
            import logging
            logging.getLogger('media').exception('CAST: preparation failed')
            with self.lock:
                if current():
                    # Do not expose FFmpeg commands, paths, or credentials to browser/export.
                    self.error = 'TV playback could not start. Check Playback diagnostics; retry or use compatible playback.'
                    self.pending = None
        finally:
            if token: cache.release(token)
            if sid and not ready:
                try: watch_history.record(sid, 0, 0, 0, 'error' if current() else 'cancelled')
                except (KeyError, ValueError): pass
