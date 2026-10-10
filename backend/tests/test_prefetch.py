import threading
from unittest.mock import Mock
import pytest
from test_library import library, client
from test_roku_audio import audio_cache, generate, terminal
from app import playback_api
from app.playback_policy import decide
from app.main import get_movie
from app.database import connection
from app.scanner import scan_library
from app.roku_audio import fingerprint, LEASE_TTL

HEADERS={'X-Media-Client':'roku'}


def test_real_prefetch_handoff_reuses_prepared_file(client,library,audio_cache,monkeypatch):
    source=library/'Show.S01E02.mkv';generate(source)
    original=source.read_bytes();scan_library()
    row=get_movie(client.get('/api/movies').json()[0]['id'])
    convert=Mock(wraps=audio_cache.convert);monkeypatch.setattr(audio_cache,'convert',convert)
    response=client.post('/api/playback/roku',json={'movie_id':row['id'],'purpose':'prefetch'},headers=HEADERS)
    token=response.json()['token']
    assert token in audio_cache.background_tokens
    ready=terminal(audio_cache,token)
    assert ready['state']=='ready'
    foreground=client.post('/api/playback/roku',json={'movie_id':row['id']},headers=HEADERS).json()
    assert foreground['state']=='ready'
    foreground_token=foreground['token']
    assert foreground_token not in audio_cache.background_tokens
    assert audio_cache.leases[token][0] is audio_cache.leases[foreground_token][0]
    client.delete('/api/playback/roku/status/'+token,headers=HEADERS)
    assert foreground_token in audio_cache.leases
    result=client.get(foreground['stream_url'],headers={'Range':'bytes=0-1023'})
    assert result.status_code==206 and len(result.content)==1024
    assert convert.call_count==1 and source.read_bytes()==original


def rows_for_priority(client,library):
    for name in ['Show.S01E02.mkv','Other.S01E01.mkv']:(library/name).write_bytes(b'fake source')
    scan_library()
    with connection() as db:
        db.execute('UPDATE movies SET video_codec="h264",video_profile="High",audio_codec="ac3",probe_error=NULL,duration=20')
        return [dict(r) for r in db.execute('SELECT * FROM movies ORDER BY id')]


def blocked_worker(cache,first_id,monkeypatch):
    entered=threading.Event();finish=threading.Event();started=[]
    def convert(job):
        started.append(job.row['id']);job.state='preparing'
        if job.row['id']==first_id:
            entered.set()
            while not finish.wait(.02) and not job.cancel.is_set():pass
        job.state='cancelled' if job.cancel.is_set() else 'ready'
        job.reserved=0;job.done.set()
    monkeypatch.setattr(cache,'convert',convert)
    return entered,finish,started


def test_foreground_playback_preempts_only_speculative_conversion(client,library,audio_cache,monkeypatch):
    first,second=rows_for_priority(client,library)
    entered,finish,started=blocked_worker(audio_cache,first['id'],monkeypatch)
    token=audio_cache.prepare(first,background=True,plan=decide(first))
    assert entered.wait(2)
    response=client.post('/api/playback/roku',json={'movie_id':second['id']},headers=HEADERS)
    assert response.status_code==200
    assert terminal(audio_cache,response.json()['token'])['state']=='ready'
    assert terminal(audio_cache,token)['state']=='cancelled'
    assert started==[first['id'],second['id']]


def test_promoted_prefetch_is_not_cancelled_when_another_viewer_requests_playback(client,library,audio_cache,monkeypatch):
    first,second=rows_for_priority(client,library)
    entered,finish,started=blocked_worker(audio_cache,first['id'],monkeypatch)
    background=audio_cache.prepare(first,background=True,plan=decide(first))
    assert entered.wait(2)
    foreground=client.post('/api/playback/roku',json={'movie_id':first['id']},headers=HEADERS).json()['token']
    assert audio_cache.leases[background][0] is audio_cache.leases[foreground][0]
    another=audio_cache.prepare(second,plan=decide(second))
    assert not audio_cache.leases[foreground][0].cancel.is_set()
    assert audio_cache.status(another)['state']=='queued'
    audio_cache.release(background)
    assert not audio_cache.leases[foreground][0].cancel.is_set()
    finish.set()
    assert terminal(audio_cache,foreground)['state']=='ready'
    assert terminal(audio_cache,another)['state']=='ready'


def test_prefetch_validation_direct_play_and_expiry(client,library,audio_cache):
    (library/'Show.S01E02.mp4').write_bytes(b'video');scan_library()
    body={'movie_id':client.get('/api/movies').json()[0]['id'],'purpose':'prefetch'}
    assert client.post('/api/playback/roku',json=body).status_code==403
    assert client.post('/api/playback/roku',json={**body,'purpose':'unknown'},headers=HEADERS).status_code==422
    data=client.post('/api/playback/roku',json=body,headers=HEADERS).json()
    assert data['delivery']=='direct' and 'token' not in data
    assert not audio_cache.background_tokens


def test_abandoned_prefetch_lease_expires_and_stops_conversion(client,library,audio_cache,monkeypatch):
    import time
    first,second=rows_for_priority(client,library)
    entered,finish,started=blocked_worker(audio_cache,first['id'],monkeypatch)
    token=audio_cache.prepare(first,background=True,plan=decide(first))
    assert entered.wait(2)
    with audio_cache.lock:
        job,_=audio_cache.leases[token]
        audio_cache.leases[token]=(job,time.monotonic()-LEASE_TTL-1)
        audio_cache.expire()
    assert token not in audio_cache.background_tokens
    assert token not in audio_cache.leases and job.cancel.is_set()
    assert job.done.wait(2)
