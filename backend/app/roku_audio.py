"""Bounded on-demand AAC stereo cache. Originals are never modified."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from . import config
from .media_tools import binary, inspect_media, select_tracks

log = logging.getLogger("media")
CACHE_VERSION = "aac-lc-stereo-mp4-v1"
LEASE_TTL = 120
MIN_FREE = 512 * 1024**2

def source_path(row):
    path = Path(row["file_path"]).resolve()
    if not path.is_relative_to(config.MOVIES_DIR.resolve()) or not path.is_file():
        raise ValueError("Movie file unavailable; rescan the library.")
    return path

def needs_video_transcode(path, video):
    return path.suffix.lower() == ".avi" or video.get("codec_name") != "h264"

def fingerprint(row, plan=None):
    row = dict(row)
    path = source_path(row)
    stat = path.stat()
    identity = [CACHE_VERSION + ("-avi-h264-v1" if path.suffix.lower() == ".avi" else "-h264-fallback-v2" if row.get("video_codec") != "h264" else ""), row["id"], str(path), stat.st_size, stat.st_mtime_ns]
    if plan is not None: identity.append({k:v for k,v in plan.items() if k!='client'})
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()

def conversion_command(executable, path, output, progress, video, audio, plan=None):
    command = [executable, "-hide_banner", "-nostdin", "-v", "error", "-y",
               "-i", str(path), "-map", f"0:{video['index']}", "-map", f"0:{audio.get('index',0)}",
               "-map_metadata", "-1", "-map_chapters", "-1", "-sn", "-dn",
               "-c:v", "copy", "-c:a", "aac", "-profile:a", "aac_low",
               "-ac", "2", "-ar", "48000", "-b:a", "192k", "-threads", "2",
               "-disposition:a:0", "default", "-movflags", "+faststart",
               "-progress", str(progress), "-nostats"]
    transcode = plan["delivery"]=="video_convert" if plan else needs_video_transcode(path,video)
    if transcode:
        index = command.index("-c:v")
        command[index:index + 2] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-maxrate", "4M", "-bufsize", "8M", "-profile:v", "high", "-level:v", "3.1",
            "-vf", "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p",
            "-r", "30"]
    if transcode and config.ROKU_VIDEO_ENCODER != "libx264":
        if config.ROKU_VIDEO_ENCODER != "h264_nvenc":
            raise ValueError("ROKU_VIDEO_ENCODER must be libx264 or h264_nvenc")
        index = command.index("-c:v")
        command[index:index + 6] = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                                   "-cq", "20", "-b:v", "3M"]
    language = audio.get("tags", {}).get("language")
    if language:
        command += ["-metadata:s:a:0", f"language={language}"]
    if plan and plan['delivery']=='remux':
        index=command.index('-c:a'); command[index+1]='copy'
        for flag in ['-profile:a','-ac','-ar','-b:a']:
            index=command.index(flag);del command[index:index+2]
    if not audio:
        index=command.index('-map',command.index('-map')+1);del command[index:index+2]
        for flag in ['-c:a','-profile:a','-ac','-ar','-b:a','-disposition:a:0']:
            if flag in command:
                index=command.index(flag);del command[index:index+2]
    if video["codec_name"] == "hevc" and not transcode:
        command += ["-tag:v", "hvc1"]
    return command + ["-f", "mp4", str(output)]

@dataclass
class Job:
    key: str
    row: dict
    state: str = "queued"
    progress: int = 0
    message: str = "Waiting to prepare Roku audio."
    reserved: int = 0
    duration: float = 0
    delivery: str = "aac_stereo_video_copy"
    plan: dict | None = None
    started_at: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)

class AudioCache:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}
        self.leases = {}
        self.background_tokens = set()
        self.executor = None

    def root(self):
        root = config.ROKU_CACHE_DIR
        root.mkdir(parents=True, exist_ok=True)
        return root

    def paths(self, key):
        root = self.root()
        return root / f"{key}.mp4", root / f"{key}.json"

    def expire(self):
        now = time.monotonic()
        for token, (_, touched) in list(self.leases.items()):
            if touched is not None and now - touched > LEASE_TTL:
                self.leases.pop(token)
                self.background_tokens.discard(token)
        alive = {job.key for job, _ in self.leases.values()}
        for key, job in list(self.jobs.items()):
            if key not in alive:
                if job.state in {"queued", "preparing"}:
                    job.cancel.set()
                elif job.done.is_set():
                    self.jobs.pop(key, None)

    def cache_files(self):
        # A configurable cache directory must never make unrelated MP4s evictable.
        return [p for p in self.root().glob("*.mp4")
                if re.fullmatch(r"[0-9a-f]{64}", p.stem) and not p.is_symlink()]

    def reserve(self, amount):
        root = self.root()
        used = sum(p.stat().st_size for p in self.cache_files())
        reserved = sum(j.reserved for j in self.jobs.values() if not j.done.is_set())
        active = {j.key for j, _ in self.leases.values()}
        # Only this generated cache is eligible for eviction.
        for old in sorted(self.cache_files(), key=lambda p: p.stat().st_mtime):
            if used + reserved + amount <= config.ROKU_CACHE_MAX_BYTES:
                break
            if old.stem in active:
                continue
            size = old.stat().st_size
            old.unlink()
            old.with_suffix(".json").unlink(missing_ok=True)
            used -= size
        if used + reserved + amount > config.ROKU_CACHE_MAX_BYTES:
            raise ValueError("Roku cache is full or this movie exceeds its limit. Increase ROKU_CACHE_MAX_GB.")
        if shutil.disk_usage(root).free < reserved + amount + MIN_FREE:
            raise ValueError("Not enough free disk space to prepare this movie safely.")

    def preempt_background(self, wanted_key):
        """A foreground load may stop speculation, never another viewer's load."""
        for job in self.jobs.values():
            if job.key == wanted_key or job.cancel.is_set() or job.state not in {"queued", "preparing"}:
                continue
            holders = [token for token, (leased, _) in self.leases.items() if leased is job]
            if holders and all(token in self.background_tokens for token in holders):
                job.cancel.set()
                log.info("PREFETCH: yielding %s to foreground playback", job.row.get("title", job.key))

    def prepare(self, row, persistent=False, background=False, plan=None):
        row = dict(row)
        key = fingerprint(row,plan)
        with self.lock:
            self.expire()
            job = self.jobs.get(key)
            output, metadata = self.paths(key)
            if job and (job.cancel.is_set() or job.state in {"failed", "cancelled"}) and not job.done.is_set():
                raise ValueError("Previous preparation is stopping. Please retry shortly.")
            if job is None or job.state in {"failed", "cancelled"} or job.cancel.is_set():
                job = Job(key, row,plan=plan)
                if plan:job.delivery=plan["delivery"]
                if output.is_file() and metadata.is_file():
                    try:
                        info = json.loads(metadata.read_text())
                    except (ValueError, OSError):
                        info = {}
                    if isinstance(info, dict) and info.get("key") == key and info.get("size") == output.stat().st_size:
                        job.state, job.progress, job.message = "ready", 100, "Roku audio ready."
                        job.duration = info.get("duration", 0)
                        job.delivery = info.get("delivery", "aac_stereo_video_copy")
                        os.utime(output, None)
                        job.done.set()
                if job.state != "ready":
                    if not background:
                        self.preempt_background(key)
                    if len([j for j in self.jobs.values() if j.state in {"queued", "preparing"} and not j.cancel.is_set()]) >= 4:
                        raise ValueError("The audio preparation queue is full. Please try again shortly.")
                    duration = row.get("duration") or 0
                    amount = int(source_path(row).stat().st_size * 1.1 + duration * 24000 + 64 * 1024**2)
                    if (plan and plan["delivery"]=="video_convert") or source_path(row).suffix.lower() == ".avi" or (row.get("video_codec") and row["video_codec"] != "h264"):
                        if duration <= 0:
                            duration = float(inspect_media(source_path(row)).get("format", {}).get("duration", 0))
                        if duration <= 0:
                            raise ValueError("Cannot determine video duration for disk reservation.")
                        amount = int(duration * 4192000 / 8 * 1.15 + 64 * 1024**2)
                    self.reserve(amount)
                    job.reserved = amount
                    if not binary("ffmpeg") or not binary("ffprobe"):
                        raise ValueError("Install FFmpeg/ffprobe with scripts/setup-media-tools.sh.")
                self.jobs[key] = job
                new_job = job.state == "queued"
            else:
                new_job = False
            if not background and job.state in {"queued", "preparing"}:
                self.preempt_background(key)
            token = secrets.token_hex(16)
            self.leases[token] = (job, None if persistent else time.monotonic())
            if background:
                self.background_tokens.add(token)
            if new_job:
                if self.executor is None:
                    self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="roku-audio")
                self.executor.submit(self.convert, job)
            return token

    def status(self, token):
        with self.lock:
            self.expire()
            if token not in self.leases:
                raise KeyError("Playback preparation expired. Press Play again.")
            job, _ = self.leases[token]
            self.leases[token] = (job, time.monotonic())
            return {"state": job.state, "progress": job.progress, "message": job.message,
                    "key": job.key, "duration": job.duration, "delivery": job.delivery,
                    "reason": (job.plan or {}).get("reason", "legacy_preparation")}

    def release(self, token):
        with self.lock:
            entry = self.leases.pop(token, None)
            self.background_tokens.discard(token)
            if entry:
                job = entry[0]
                if not any(j is job for j, _ in self.leases.values()) and job.state in {"queued", "preparing"}:
                    job.cancel.set()

    def convert(self, job):
        output, metadata = self.paths(job.key)
        # Unique temporary names prevent cancelled/retried jobs from sharing output.
        nonce = secrets.token_hex(6)
        temporary = output.with_name(f"{job.key}.{nonce}.part")
        progress = output.with_name(f"{job.key}.{nonce}.progress")
        error_log = output.with_name(f"{job.key}.{nonce}.log")
        process = None
        try:
            if job.cancel.is_set():
                raise InterruptedError("Preparation cancelled.")
            path = source_path(job.row)
            info = inspect_media(path)
            video, audio, _ = select_tracks(info)
            transcode = job.plan["delivery"]=="video_convert" if job.plan else needs_video_transcode(path, video)
            if not audio and not job.plan:
                raise ValueError("This file contains no audio track.")
            duration = float(info.get("format", {}).get("duration", 0))
            if duration <= 0:
                raise ValueError("Cannot determine movie duration; refusing an unverified conversion.")
            job.duration = duration
            job.state, job.message = "preparing", "Preparing AAC stereo audio; video quality is unchanged."
            if transcode:
                job.delivery = "h264_aac_transcode"
                job.message = "Preparing H.264 video and AAC stereo audio for Roku."
            command = conversion_command(binary("ffmpeg"), path, temporary, progress, video, audio,job.plan)
            log.info("ROKU AUDIO: %s: %s/%s %s channels -> AAC-LC stereo; delivery=%s; track=%s",
                     job.row["title"], audio.get("codec_name"), audio.get("profile"),
                     audio.get("channels"), job.delivery, audio.get("index"))
            started = time.monotonic()
            with error_log.open("wb") as errors:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
                while process.poll() is None:
                    with self.lock:
                        self.expire()
                    if job.cancel.is_set():
                        raise InterruptedError("Preparation cancelled.")
                    if time.monotonic() - started > config.ROKU_PREPARE_TIMEOUT:
                        raise TimeoutError("Audio preparation timed out.")
                    if temporary.exists() and temporary.stat().st_size > job.reserved:
                        raise ValueError("Prepared file exceeded the reserved cache budget.")
                    if shutil.disk_usage(self.root()).free < MIN_FREE:
                        raise ValueError("Preparation stopped to preserve free disk space.")
                    if progress.exists():
                        text = progress.read_text(errors="replace")
                        values = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith("out_time_us=")]
                        if values and values[-1].isdigit():
                            job.progress = min(99, int(float(values[-1]) / 1000000 / duration * 100))
                    time.sleep(.25)
                if process.returncode:
                    tail = error_log.read_text(errors="replace")[-3000:]
                    log.error("ROKU AUDIO: FFmpeg failed: %s", tail)
                    raise ValueError("FFmpeg could not prepare this file; see server logs.")
            if job.cancel.is_set():
                raise InterruptedError("Preparation cancelled.")
            result = inspect_media(temporary)
            out_video, out_audio, _ = select_tracks(result)
            actual_duration = float(result.get("format", {}).get("duration", 0))
            if job.plan: job.delivery=job.plan["delivery"]
            audio_valid=(not audio and not out_audio) or (job.plan and job.plan["delivery"]=="remux" and out_audio.get("codec_name")==audio.get("codec_name")) or (out_audio.get("codec_name")=="aac" and out_audio.get("channels")==2 and out_audio.get("profile")=="LC")
            if (out_video.get("codec_name") != ("h264" if transcode else video.get("codec_name"))
                or not audio_valid or abs(actual_duration - duration) > max(2, duration * .001)):
                raise ValueError("Prepared file failed codec/duration validation.")
            if temporary.stat().st_size > job.reserved:
                raise ValueError("Prepared file exceeded the reserved cache budget.")
            if fingerprint(job.row,job.plan) != job.key:
                raise ValueError("Source movie changed during preparation; please retry.")
            with self.lock:
                os.replace(temporary, output)
                metadata.write_text(json.dumps({"key": job.key, "movie_id": job.row["id"],
                                                 "size": output.stat().st_size, "duration": actual_duration, "delivery": job.delivery,"plan":job.plan}))
                job.state, job.progress, job.message = "ready", 100, "Compatible MP4 ready."
            log.info("ROKU AUDIO: Ready %s in %.1fs (%d bytes)", job.row["title"],
                     time.monotonic() - started, output.stat().st_size)
        except Exception as exc:
            job.state = "cancelled" if isinstance(exc, InterruptedError) else "failed"
            job.message = str(exc)
            log.warning("ROKU AUDIO: %s: %s", job.row["title"], exc)
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            temporary.unlink(missing_ok=True)
            progress.unlink(missing_ok=True)
            error_log.unlink(missing_ok=True)
            job.reserved = 0
            job.done.set()

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                job.cancel.set()
            executor = self.executor
            self.executor = None
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self.leases.clear()
            self.background_tokens.clear()
            self.jobs.clear()

cache = AudioCache()
