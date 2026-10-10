"""One managed background worker; no scraping on request or Roku render threads."""
import logging
import os
import subprocess
import sys
import threading
from . import config
from .scanner import scan_library

log = logging.getLogger('media')

class ArtworkWorker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        if not config.AUTO_ARTWORK:
            return
        self.thread = threading.Thread(target=self._loop, name='artwork-worker', daemon=True)
        self.thread.start()

    def request(self):
        self.wake_event.set()

    def _loop(self):
        first = True
        while not self.stop_event.is_set():
            try:
                if not first:
                    scan_library()
                first = False
                env = dict(os.environ, PYTHONPATH=str(config.ROOT/'backend'))
                with self.lock:
                    if self.stop_event.is_set():
                        return
                    self.process = subprocess.Popen([sys.executable, '-m', 'app.public_artwork'],
                        cwd=config.ROOT, env=env)
                code = self.process.wait()
                with self.lock:
                    self.process = None
                if code:
                    log.warning('ART: Importer exited %s; existing artwork retained', code)
                else:
                    log.info('ART: Background artwork pass complete')
            except Exception:
                log.exception('ART: Background scan/import failed; will retry')
            self.wake_event.wait(config.AUTO_LIBRARY_SCAN_SECONDS)
            self.wake_event.clear()

    def close(self):
        self.stop_event.set()
        self.wake_event.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
        if self.thread:
            self.thread.join(timeout=10)
