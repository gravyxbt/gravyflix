"""One configured LAN Cast receiver; phone never carries video bytes."""
import logging
import socket
import threading
import time
from pathlib import Path
from uuid import UUID
import requests
import pychromecast
from . import config
from .streaming import MIME

log = logging.getLogger("media")

class CastManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.cast = None
        self.media_url = None
        from .cast_features import CastFeatures
        self.features = CastFeatures(self)
        from .cast_preparation import Preparation
        self.preparation = Preparation(self)

    def close(self):
        with self.lock:
            self.features.running = False
            if self.cast:
                self.cast.disconnect(timeout=2)
                self.cast = None

    def shutdown(self):
        self.preparation.stop.set()
        self.preparation.cancel()
        if self.preparation.thread:self.preparation.thread.join(timeout=3)
        self.features.close()
        self.close()

    def connect(self):
        if not config.CAST_HOST:
            raise RuntimeError("No TV configured. Set CAST_HOST in .env.")
        if self.cast and self.cast.socket_client.is_connected:
            return self.cast
        self.close()
        # Fixed administrator-configured host; clients cannot supply arbitrary URLs.
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(f"http://{config.CAST_HOST}:8008/setup/eureka_info", timeout=4)
            response.raise_for_status()
            info = response.json()
        cast = pychromecast.get_chromecast_from_host(
            (config.CAST_HOST, 8009, UUID(info["ssdp_udn"]), None, info.get("name", config.CAST_NAME)),
            tries=1, retry_wait=1, timeout=4)
        try:
            cast.wait(timeout=6)
        except Exception:
            cast.disconnect(timeout=1)
            raise
        self.cast = cast
        log.info("CAST: Connected to %s", cast.name)
        return cast

    def stream_base(self):
        if config.PUBLIC_BASE_URL:
            return config.PUBLIC_BASE_URL
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((config.CAST_HOST, 8009))
            host = sock.getsockname()[0]
        return f"http://{host}:{config.PORT}"

    def snapshot(self):
        pending = self.preparation.snapshot()
        if pending: return pending
        with self.lock:
            cast = self.connect()
            status = cast.media_controller.status
            owned = bool(status.content_id and status.content_id.startswith((self.stream_base() + "/stream/", self.stream_base() + "/api/playback/roku/media/")))
            result = {
                "name": cast.name, "connected": True,
                "state": status.player_state if owned else "IDLE",
                "title": status.title if owned else "",
                "position": (status.adjusted_current_time or 0) if owned else 0,
                "duration": (status.duration or 0) if owned else 0,
                "active": owned and status.player_state in {"PLAYING", "PAUSED", "BUFFERING"},
                "idle_reason": status.idle_reason if owned else None,
            }

            if owned:
                result.update(self.features.status_fields(status))
            else:
                result.update(movie_id=None, next_item=None, still_watching=False, subtitle_tracks=[], subtitle_active=None, autoplay_enabled=self.features.enabled)
            return result

    def play_movie(self, row, position=0, manual=True, intent=None, mode="auto"):
        if intent is not None:
            return self.preparation.start(row, position, manual, intent, mode)
        return self._play_movie(row, position, manual)

    def _play_movie(self, row, position=0, manual=True, prepared_url=None, session_id=None, plan=None, valid=None):
        with self.lock:
            path = Path(row["file_path"]).resolve()
            if not path.is_relative_to(config.MOVIES_DIR.resolve()) or not path.is_file():
                raise RuntimeError("Movie file is unavailable. Rescan the library.")
            cast = self.connect()
            url = prepared_url or f"{self.stream_base()}/stream/{row['id']}"
            controller = cast.media_controller
            log.info("CAST: Starting %s on %s: %s", row["title"], cast.name, url)
            if self.cast and self.media_url == controller.status.content_id and self.features.current:
                self.features.save(controller.status, completed=controller.status.player_state == "IDLE" and controller.status.idle_reason == "FINISHED")
            tracks = self.features.prepare(row, manual)
            self.features.session_id = session_id
            self.features.plan = plan
            options = {"media_info": {"tracks": tracks}} if tracks else {}
            if position:
                options["current_time"] = min(position, max(0, (row["duration"] or position + 1) - 1))
            controller.play_media(url, "video/mp4" if prepared_url else MIME.get(path.suffix.lower(), "video/mp4"),
                                  title=row["title"], stream_type="BUFFERED", **options)
            # Confirm this load rather than a previous media session.
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                if valid and not valid():
                    controller.stop(timeout=2)
                    raise RuntimeError("Preparation cancelled")
                status = controller.status
                if status.content_id == url:
                    if status.player_state in {"PLAYING", "PAUSED"}:
                        self.media_url = url
                        self.features.loaded()
                        if session_id:self.features.save(status)
                        result = self.snapshot()
                        result.update(state=status.player_state,active=True)
                        return result
                    if status.player_state == "IDLE" and status.idle_reason == "ERROR":
                        raise RuntimeError("TV could not decode this file. Try an H.264/AAC MP4.")
                time.sleep(.15)
            raise RuntimeError("TV has not confirmed playback. Check the TV and try the sample MP4.")

    def command(self, action, position=None):
        pending = self.preparation.snapshot()
        if pending:
            if action != "stop":raise RuntimeError("Playback is still preparing. Stop cancels preparation.")
            self.preparation.cancel()
            # The current playback, if any, remains under normal server ownership.
            return {"state":"IDLE", "active":False}
        with self.lock:
            cast = self.connect()
            if not self.snapshot()["active"]:
                raise RuntimeError("No GRAVYFLIX title is playing on the TV.")
            controller = cast.media_controller
            if action == "seek":
                duration = controller.status.duration or 0
                if duration <= 0:
                    raise RuntimeError("Seeking is not available for this video yet.")
                controller.seek(min(position, max(0, duration - .1)), timeout=5)
            else:
                if action == "stop":
                    self.features.save(controller.status,state_override="stopped")
                    self.features.running = False
                    self.features.confirm = False
                getattr(controller, action)(timeout=5)
            if action in {"seek", "pause", "play"}:self.features.save(controller.status)
            log.info("CAST: %s", action)
            return self.snapshot()

manager = CastManager()
