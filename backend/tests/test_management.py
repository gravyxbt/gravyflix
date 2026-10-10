import io
import json
import time
import zipfile
from pathlib import Path
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from app import config, database, intros, subtitles, management, credits
from app.main import app

HEADERS = {'X-Gravyflix-Manage': '1'}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    movies = tmp_path / 'Movies'
    movies.mkdir()
    monkeypatch.setattr(config, 'MOVIES_DIR', movies)
    monkeypatch.setattr(config, 'DATABASE_PATH', tmp_path / 'library.db')
    monkeypatch.setattr(config, 'ROKU_CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(config, 'ENVIRONMENT_KEYS', frozenset())
    database.initialize(); intros.initialize(); subtitles.initialize(); credits.initialize()
    from app import watch_history
    watch_history.initialize()
    management.jobs.clear()
    return TestClient(app)


def test_management_requires_same_origin_header(client):
    assert client.get('/api/manage/settings').status_code == 403
    assert client.get('/api/manage/settings', headers={**HEADERS, 'Origin':'https://elsewhere.example'}).status_code == 403
    assert client.get('/api/manage/settings', headers={**HEADERS, 'Origin':'http://testserver'}).status_code == 200


def test_settings_preserve_secrets_and_unrelated_lines(client):
    path=config.ROOT/'.env'
    path.write_text('# keep this comment\nOPENSUBTITLES_API_KEY=hidden-secret\nUNRELATED=keep\nCAST_NAME=Old\nCAST_NAME=Duplicate\n')
    before=client.get('/api/manage/settings', headers=HEADERS)
    assert 'hidden-secret' not in before.text
    assert before.json()['saved_key_configured']
    response=client.put('/api/manage/settings', headers=HEADERS, json={'values':{'CAST_NAME':"Mom's TV", 'AUTO_ARTWORK':'false'}})
    assert response.json()['restart_required']
    values=dotenv_values(path)
    assert values['CAST_NAME']=="Mom's TV"
    assert values['OPENSUBTITLES_API_KEY']=='hidden-secret'
    assert values['UNRELATED']=='keep'
    assert '# keep this comment' in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    assert config.CAST_NAME!="Mom's TV"  # Saving never silently mutates live workers.


@pytest.mark.parametrize('key,value', [('HOST','0.0.0.0'),('MOVIES_DIR','missing'),('CAST_HOST','http://tv/'),('CAST_NAME','bad\nvalue'),('AUTO_ARTWORK','maybe'),('SUBTITLE_LANGUAGES','en,../../'),('ROKU_CACHE_MAX_GB','0'),('PUBLIC_BASE_URL','http://user:secret@host/'),('ROKU_VIDEO_ENCODER','custom-command')])
def test_bad_settings_are_atomic(client,key,value):
    response=client.put('/api/manage/settings', headers=HEADERS, json={'values':{'CAST_NAME':'Good',key:value}})
    assert response.status_code==422
    assert not (config.ROOT/'.env').exists()


def test_new_api_key_is_write_only_and_blank_preserves(client):
    for key in ['a-secret-key', '']:
        response=client.put('/api/manage/settings', headers=HEADERS,json={'values':{},'opensubtitles_key':key})
        assert response.status_code==200
    assert dotenv_values(config.ROOT/'.env')['OPENSUBTITLES_API_KEY']=='a-secret-key'
    assert 'a-secret-key' not in client.get('/api/manage/settings',headers=HEADERS).text


def test_artwork_only_accepts_current_candidates(client, monkeypatch):
    from app import public_artwork
    report=config.ROOT/'data/artwork-reports/matching.json';report.parent.mkdir(parents=True)
    report.write_text(json.dumps([{'id':42,'title':'Example','candidates':[{'title':'Example','year':2024,'url':'https://www.themoviedb.org/movie/42-example'}]}]))
    path=config.ROOT/'config/artwork-matches.json';path.parent.mkdir();path.write_text('{"keep":{"query":"Keep"}}')
    refreshed=[]
    monkeypatch.setattr(public_artwork,'run',lambda refresh=():refreshed.extend(refresh))
    assert client.post('/api/manage/artwork/choose',headers=HEADERS,json={'id':'42','url':'http://localhost/private'}).status_code==422
    response=client.post('/api/manage/artwork/choose',headers=HEADERS,json={'id':'42','url':'https://www.themoviedb.org/movie/42-example'})
    assert response.status_code==200
    for _ in range(100):
        if refreshed:break
        time.sleep(.01)
    assert refreshed==['42']
    assert json.loads(path.read_text())['keep']=={'query':'Keep'}
    assert json.loads(path.read_text())['42']['year']==2024


def test_job_reports_errors_without_leaking_exception(client):
    def fail():raise ValueError('secret exception body')
    job=management.submit('Test job',fail)
    for _ in range(100):
        state=client.get('/api/manage/jobs',headers=HEADERS).json()[0]
        if state['state']=='error':break
        time.sleep(.01)
    assert state['id']==job['id'] and state['state']=='error'
    assert 'secret exception body' not in json.dumps(state)


def test_job_limit_and_conflicts(client):
    from threading import Event
    started=Event();finish=Event()
    def wait():started.set();finish.wait(3)
    management.submit('Wait',wait);started.wait(1)
    try:
        with pytest.raises(Exception) as exc:management.submit('Conflict',lambda:None)
        assert exc.value.status_code==409
    finally:
        finish.set()
        for _ in range(100):
            if not any(j['state']=='running' for j in management.jobs.values()):break
            time.sleep(.01)


def test_roku_zip_configured_without_changing_source(client):
    source=config.ROOT/'roku';(source/'source').mkdir(parents=True)
    (source/'manifest').write_text('title=Gravyflix')
    original='function BackendUrl()\n return "http://old:8080"\nend function'
    (source/'source/Config.brs').write_text(original)
    response=client.get('/api/manage/roku-package',headers=HEADERS)
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert 'http://testserver' in archive.read('source/Config.brs').decode()
        assert archive.read('manifest')==b'title=Gravyflix'
    assert (source/'source/Config.brs').read_text()==original


def test_intro_edit_and_disabled_are_persistent(client,monkeypatch):
    from app.scanner import scan_library
    file=config.MOVIES_DIR/'Example S01E01.mp4';file.write_bytes(b'fake media')
    scan_library()
    with database.connection() as db:
        db.execute('UPDATE movies SET duration=1200')
        movie_id=db.execute('SELECT id FROM movies').fetchone()[0]
    url=f'/api/manage/intros/{movie_id}'
    assert client.put(url,headers=HEADERS,json={'start':200,'end':100}).status_code==422
    assert client.put(url,headers=HEADERS,json={'start':30,'end':90}).json()['intro']['end']==90
    assert client.put(url,headers=HEADERS,json={'disabled':True}).json()['state']=='disabled'
    with database.connection() as db:assert db.execute('SELECT scope FROM intro_markers').fetchone()[0]=='manual'


def test_overview_and_library_empty(client):
    result=client.get('/api/manage/overview',headers=HEADERS)
    assert result.status_code==200
    assert result.json()['files']==0
    assert client.get('/api/manage/library',headers=HEADERS).json()=={'catalog':[],'files':[]}

@pytest.mark.parametrize('host,command',[('darwin','python3 scripts/macos-service.py restart'),
                                        ('linux','systemctl --user restart roku-media-server.service')])
def test_platform_specific_restart_instructions(client,monkeypatch,host,command):
    monkeypatch.setattr(management.sys,'platform',host)
    response=client.get('/api/manage/settings',headers=HEADERS).json()
    assert response['restart_command']==command
    assert 'foreground server' in response['restart_description']
    assert response['platform']==('macOS' if host=='darwin' else 'Linux')
