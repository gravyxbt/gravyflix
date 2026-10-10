import math
from types import SimpleNamespace
import pytest
from app import credits, scanner
from app.main import get_movie
from app.database import connection
from app.cast_features import CastFeatures
from test_library import library, client

HEADERS={'X-Gravyflix-Manage':'1'}

@pytest.mark.parametrize('title,start,expected',[
    ('End Credits',6600,6600), ('Closing Credits',6500,6500), ('credits',50,None),
    ('Opening Credits',6600,None), ('Chapter 20',6600,None), ('End Credits',float('nan'),None),
    ('End Credits',7200,None), ('End Credits',2000,None), ('Rolling Credits',6900,6900)])
def test_named_chapters_only(title,start,expected):
    assert credits.marker_from_chapters([{'tags':{'title':title},'start_time':str(start)}],7200)==expected
    assert credits.marker_from_chapters([{'tags':{'title':title},'start_time':'bad'}],7200) is None


@pytest.fixture
def movies(client,library,monkeypatch):
    monkeypatch.setattr(scanner,'probe',lambda path:dict(duration=7200,probe_error=None,probe_version=2))
    (library/'A Movie (2020).mkv').write_bytes(b'film')
    (library/'Show S01E01.mkv').write_bytes(b'episode')
    scanner.scan_library()
    with connection() as db:
        rows=db.execute('SELECT id,filename FROM movies WHERE available=1').fetchall()
    return {r['filename']:r['id'] for r in rows}


def test_worker_only_movies_and_persistent_manual_override(client,movies,monkeypatch):
    movie_id=movies['A Movie (2020).mkv']; episode_id=movies['Show S01E01.mkv']
    worker=credits.CreditWorker();seen=[]
    def chapters(path):seen.append(path.name);return [{'tags':{'title':'End credits'},'start_time':'6500'}]
    monkeypatch.setattr(worker,'chapters',chapters)
    assert worker.run_once()=={'checked':1,'found':1}
    assert seen==['A Movie (2020).mkv']
    assert client.get(f'/api/movies/{movie_id}').json()['credits_start']==6500
    assert client.get(f'/api/movies/{episode_id}').json()['credits_start'] is None
    assert client.put(f'/api/manage/credits/{episode_id}',headers=HEADERS,json={'start':6000}).status_code==422
    response=client.put(f'/api/manage/credits/{movie_id}',headers=HEADERS,json={'start':6400})
    assert response.json()['method']=='manual'
    assert worker.run_once()['checked']==0
    credits.save(get_movie(movie_id),6600,'chapter','Background replacement')
    assert client.get(f'/api/movies/{movie_id}/credits').json()['start']==6400
    assert client.put(f'/api/manage/credits/{movie_id}',headers=HEADERS,json={'disabled':True}).json()['state']=='disabled'
    assert client.get(f'/api/movies/{movie_id}').json()['credits_start'] is None


def test_bad_credit_timing_and_media_replacement(client,movies,library):
    movie_id=movies['A Movie (2020).mkv']; url=f'/api/manage/credits/{movie_id}'
    assert client.put(url,json={'start':6000}).status_code==403
    for body in [{},{'start':0},{'start':7200},{'start':-1}]:
        assert client.put(url,headers=HEADERS,json=body).status_code==422
    assert client.put(url,headers=HEADERS,json={'start':6500}).status_code==200
    path=library/'A Movie (2020).mkv';path.write_bytes(b'replaced movie')
    assert client.get(f'/api/movies/{movie_id}/credits').json()['start'] is None
    scanner.scan_library()
    assert client.get(f'/api/movies/{movie_id}').json()['credits_start'] is None


def test_no_chapter_cached_and_new_files_analyzed(client,movies,library,monkeypatch):
    worker=credits.CreditWorker();seen=[]
    monkeypatch.setattr(worker,'chapters',lambda path:seen.append(path.name) or [])
    assert worker.run_once()=={'checked':1,'found':0}
    assert worker.run_once()=={'checked':0,'found':0}
    (library/'New Movie (2021).mp4').write_bytes(b'new file');scanner.scan_library()
    assert worker.run_once()=={'checked':1,'found':0}
    assert seen==['A Movie (2020).mkv','New Movie (2021).mp4']


@pytest.mark.parametrize('kind,marker,position,expected',[
    ('movie',6500,6500,True),('movie',6500,6499,False),('episode',6500,6500,False),
    ('episode',6500,7170,True),('movie',None,7000,False),('movie',None,7180,True),
    ('movie',8000,7000,False)])
def test_cast_prompt_window_is_movie_only(kind,marker,position,expected):
    features=CastFeatures(SimpleNamespace())
    features.current={'id':1,'kind':kind,'credits_start':marker}
    status=SimpleNamespace(duration=7200,adjusted_current_time=position)
    result=features.status_fields(status)
    assert result['up_next_visible']==expected
    assert result['remaining']==7200-position
