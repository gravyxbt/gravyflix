import json
import time
from pathlib import Path
from typing import Literal
from .playback_policy import decide,media_row
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, StrictBool
from . import config
from .roku_audio import cache, fingerprint

router = APIRouter(prefix="/api/playback/roku")

class Capabilities(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_video_supported: StrictBool | None = None

class PlaybackRequest(BaseModel):
    movie_id: int = Field(gt=0)
    mode: Literal["auto", "original", "compatible"] = "auto"
    capabilities: Capabilities = Field(default_factory=Capabilities)
    session_id: str | None = Field(default=None,max_length=32)
    purpose: Literal["playback", "prefetch"] = "playback"

def authorize(request):
    if request.headers.get("x-media-client") != "roku":
        raise HTTPException(403, "A Roku client header is required.")

def result(token, request):
    from .main import base_url
    try:
        data = cache.status(token)
    except KeyError as exc:
        raise HTTPException(404, "Playback request expired. Press Play again.") from exc
    data["token"] = token
    with cache.lock:
        job=cache.leases[token][0]
        if job.plan and data['state']=='ready':
            from .database import connection
            with connection() as db:
                db.execute("UPDATE playback_sessions SET preparation_seconds=? WHERE movie_id=? AND delivery=? AND state='requested' AND ended=0 AND preparation_seconds IS NULL",(max(0,time.time()-job.started_at),job.row['id'],job.plan['delivery']))
    if data["state"] == "ready":
        data.update(stream_url=f"{base_url(request)}/api/playback/roku/media/{data['key']}",
                    stream_format="mp4")
    data.pop("key", None)
    return data

@router.post("")
def prepare(body: PlaybackRequest, request: Request):
    authorize(request)
    from .main import get_movie, base_url
    row=media_row(get_movie(body.movie_id))
    mode=body.mode
    if config.ROKU_AUDIO_MODE=='original' and mode=='auto' and row['filename'].lower().endswith('.mkv'): mode='original'
    plan=decide(row,'roku',mode,body.capabilities.model_dump(exclude_none=True))
    if body.session_id:
        from .database import connection
        with connection() as db:
            session=db.execute('SELECT movie_id,client_type,ended FROM playback_sessions WHERE id=?',(body.session_id,)).fetchone()
        if not session or session['movie_id']!=body.movie_id or session['client_type']!='roku' or session['ended']:
            raise HTTPException(409, 'Playback session does not match this title')
        from .watch_history import delivery
        delivery(body.session_id,plan)
    if plan['delivery']=='unsupported':raise HTTPException(422, 'This HDR file requires verified tone mapping; original playback may work on a capable device.')
    if plan['delivery']=='direct':
        return {'state':'ready','stream_url':f"{base_url(request)}/stream/{row['id']}",
                'stream_format': Path(row['filename']).suffix.lower().lstrip('.'),**plan}
    try:
        response=result(cache.prepare(row,background=body.purpose=='prefetch',plan=plan),request)
        response.update(reason=plan['reason'],planned_delivery=plan['delivery'])
        return response
    except (ValueError,OSError) as exc:raise HTTPException(503,str(exc)) from exc

@router.get("/status/{token}")
def status(token: str, request: Request):
    return result(token, request)

@router.delete("/status/{token}", status_code=204)
def release(token: str, request: Request):
    authorize(request)
    cache.release(token)

@router.api_route("/media/{key}", methods=["GET", "HEAD"])
def media(key: str, request: Request):
    from .main import get_movie
    from .streaming import stream_movie
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise HTTPException(404, "Prepared movie not found")
    with cache.lock:
        output, metadata = cache.paths(key)
        if not output.is_file() or not metadata.is_file():
            raise HTTPException(404, "Prepared movie expired; press Play again")
        try:
            info = json.loads(metadata.read_text())
            if info["key"] != key or info["size"] != output.stat().st_size:
                raise ValueError("Invalid cache metadata")
            movie_id = int(info["movie_id"])
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise HTTPException(409, "Prepared movie needs rebuilding; press Play again") from exc
        row = get_movie(movie_id)
        try:
            if fingerprint(row,info.get("plan")) != key:
                raise ValueError("Source changed")
        except (ValueError, OSError) as exc:
            raise HTTPException(409, "Source movie changed; press Play again") from exc
        # Pin for the lifetime of the HTTP transfer, in addition to the Roku heartbeat.
        token = cache.prepare(row, persistent=True,plan=info.get("plan"))
        try:
            response = stream_movie({"file_path":str(output),"title":row["title"]}, request,
                                    allowed_root=config.ROKU_CACHE_DIR,
                                    on_close=lambda: cache.release(token))
        except BaseException:
            cache.release(token)
            raise
        return response
