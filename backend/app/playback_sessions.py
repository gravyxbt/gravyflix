from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from . import watch_history as store
router=APIRouter()

def authorize(request:Request):
    if request.headers.get('x-media-client')!='roku' and request.headers.get('x-media-control')!='1':raise HTTPException(403,'A media client header is required')
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Same-origin access required')

class Start(BaseModel):
    model_config=ConfigDict(extra='forbid')
    movie_id:int=Field(gt=0)
    client_id:str=Field(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    client_type:Literal['roku','cast']='roku'
    intent:Literal['resume','restart','autoplay']='resume'

class Progress(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sequence:int=Field(ge=0,le=2147483647)
    position:float=Field(ge=0,allow_inf_nan=False)
    duration:float=Field(ge=0,allow_inf_nan=False)
    state:Literal['requested','playing','paused','buffering','seek','finished','stopped','error','cancelled','next']
    event:Literal['requested','playing','paused','buffering','seek','finished','stopped','error','cancelled','next']|None=None

@router.get('/api/history')
def history():return store.history()
@router.post('/api/playback/sessions',dependencies=[Depends(authorize)])
def start(body:Start):
    if body.client_type!='roku':raise HTTPException(403,'Cast sessions are server-owned')
    from .main import get_movie
    return store.create(get_movie(body.movie_id),body.client_id,body.client_type,body.intent)
@router.post('/api/playback/sessions/{sid}/progress',dependencies=[Depends(authorize)])
@router.post('/api/playback/sessions/{sid}/end',dependencies=[Depends(authorize)])
def progress(sid:str,body:Progress):
    if len(sid)!=32:raise HTTPException(404,'Session expired')
    from .database import connection
    with connection() as db:s=db.execute('SELECT movie_id,client_type FROM playback_sessions WHERE id=?',(sid,)).fetchone()
    if not s:raise HTTPException(404,'Session expired')
    if s['client_type']!='roku':raise HTTPException(403,'Cast progress is server-owned')
    from .credits import start_for
    from .main import get_movie
    return store.record(sid,body.sequence,body.position,body.duration,body.state,body.event,credits_start=start_for(get_movie(s['movie_id'])))
