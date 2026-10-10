import logging
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .casting import manager

router = APIRouter(prefix="/api/cast")
log = logging.getLogger("media")

class PlayRequest(BaseModel):
    movie_id: int = Field(gt=0)
    position: float = Field(default=0, ge=0, allow_inf_nan=False)
    intent: Literal["resume", "restart", "autoplay"] = "resume"
    mode: Literal["auto", "original", "compatible"] = "auto"

class ControlRequest(BaseModel):
    action: Literal["play", "pause", "stop", "seek"]
    position: float | None = Field(default=None, ge=0, allow_inf_nan=False)

def require_control(request):
    # Cross-origin webpages cannot send this header without a CORS preflight.
    # Cast routes deliberately do not allow cross-origin access.
    if request.headers.get("x-media-control") != "1":
        raise HTTPException(403, "Use the My Media webpage to control the TV.")

def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        log.exception("CAST: %s", exc)
        raise HTTPException(503, f"TV unavailable or playback failed: {exc}") from exc

@router.get("/status")
def status():
    return invoke(manager.snapshot)

@router.post("/play")
def play(body: PlayRequest, request: Request):
    require_control(request)
    from .main import get_movie
    return invoke(manager.play_movie, get_movie(body.movie_id), body.position, intent=body.intent, mode=body.mode)

@router.post("/control")
def control(body: ControlRequest, request: Request):
    require_control(request)
    if body.action == "seek" and body.position is None:
        raise HTTPException(422, "A seek position is required.")
    return invoke(manager.command, body.action, body.position)

class CaptionRequest(BaseModel):
    track_id: int | None = Field(default=None, gt=0)

class QueueRequest(BaseModel):
    action: Literal["next", "confirm", "cancel", "enable", "disable"]

@router.get("/history")
def watch_history():
    from .cast_features import history
    return history()

@router.post("/captions")
def captions(body: CaptionRequest, request: Request):
    require_control(request)
    with manager.lock:
        return invoke(manager.features.captions, body.track_id)

@router.post("/queue")
def queue(body: QueueRequest, request: Request):
    require_control(request)
    with manager.lock:
        # Refresh connection/ownership before any queue operation.
        status = invoke(manager.snapshot)
        if body.action == "confirm" and not status.get("still_watching"):
            raise HTTPException(409, "No still-watching prompt is pending.")
        if body.action in {"next", "confirm"}:
            if not status.get("active") and not status.get("still_watching"):
                raise HTTPException(409, "No GRAVYFLIX session to advance.")
            return invoke(manager.features.advance, body.action == "confirm")
        if body.action == "cancel":
            manager.features.suspended = True
            manager.features.confirm = False
        else:
            manager.features.enabled = body.action == "enable"
        return invoke(manager.snapshot)
