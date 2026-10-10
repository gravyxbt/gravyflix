import json
from pathlib import Path
from . import config
from .catalog import episode_identity, grouping_hint
from pydantic import BaseModel, Field

class Movie(BaseModel):
    id: int
    title: str
    filename: str
    year: int | None
    date_added: str
    file_size: int
    modification_time: int
    container: str | None
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    duration: float | None
    probe_error: str | None
    audio_channels: int | None = None
    video_profile: str | None = None
    video_level: int | None = None
    pixel_format: str | None = None
    frame_rate: float | None = None
    bitrate: int | None = None
    color_transfer: str | None = None
    audio_profile: str | None = None
    audio_tracks: list[dict] = Field(default_factory=list)
    poster_url: str | None = None
    backdrop_url: str | None = None
    landscape_url: str | None = None
    artwork_source: str | None = None
    genres: list[str] = Field(default_factory=list)
    stream_url: str
    stream_format: str
    series_info: dict | None = None
    grouping_hint: dict | None = None
    credits_start: float | None = None
    direct_play: str
    compatibility_note: str

def movie_response(row, base, include_credits=True):
    data = dict(row)
    path = Path(data.pop("file_path"))
    try:
        folders = path.parent.relative_to(config.MOVIES_DIR).parts
    except ValueError:
        folders = ()
    data['series_info'] = episode_identity(data['filename'], folders)
    data['grouping_hint'] = grouping_hint(data['filename'], folders)
    data.pop("available")
    data.pop("probe_version", None)
    data["audio_tracks"] = json.loads(data.get("audio_tracks") or "[]")
    data["stream_url"] = f"{base}/stream/{data['id']}"
    data["stream_format"] = "mkv" if data["filename"].lower().endswith(".mkv") else "mp4"
    video, audio = data["video_codec"], data["audio_codec"]
    if data["filename"].lower().endswith(".avi"):
        data["stream_format"] = "avi"
        status, note = "unlikely", "AVI requires a Roku-compatible H.264/AAC MP4 copy; prepared automatically when you press Play."
    elif data["probe_error"] or not video:
        status, note = "unknown", "No usable probe data. Direct playback will be attempted."
    elif video == "h264" and audio == "aac" and data.get("audio_channels") in {1, 2}:
        status, note = "likely", "H.264/AAC is a good direct-play candidate; profile, bitrate and device limits still apply."
    elif video in {"h264", "hevc", "vp9", "av1"}:
        status, note = "device_dependent", "Audio/video support depends on Roku model and connected audio equipment; compatible MKV playback copies H.264 video or converts other codecs to H.264 with AAC stereo."
    else:
        status, note = "unlikely", "Video codec is outside the MVP direct-play candidates; transcoding is not implemented."
    data.update(direct_play=status, compatibility_note=note)
    from .artwork import decorate, show_id
    decorate(data, base, show_id(data.get("series_info")) or show_id(data.get("grouping_hint")))
    if include_credits:
        from .credits import start_for
        data["credits_start"] = start_for(row)
    return Movie(**data)
