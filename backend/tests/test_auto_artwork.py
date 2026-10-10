import io
import json
from contextlib import contextmanager
from PIL import Image
import pytest
from app import public_artwork as importer, config
from app.artwork_worker import ArtworkWorker

@pytest.fixture
def automatic(tmp_path,monkeypatch):
    root=tmp_path
    (root/'config').mkdir()
    for name,value in [('ROOT',root),('ART',root/'data/artwork'),('SOURCES',root/'data/source'),
                       ('INDEX',root/'data/artwork/index.json'),('REPORT',root/'data/reports/matching.json'),
                       ('STATE',root/'data/reports/attempts.json')]:
        monkeypatch.setattr(importer,name,value)
    class DB:
        def execute(self,*args):return self
        def fetchall(self):return []
    @contextmanager
    def connection():yield DB()
    monkeypatch.setattr(importer,'connection',connection)
    items=[dict(id=7,title='Arrival',year=2016,kind='movie')]
    monkeypatch.setattr(importer,'build_catalog',lambda rows: items)
    monkeypatch.setattr(importer,'search',lambda q,k:[dict(title=q,year=2016,url='https://www.themoviedb.org/movie/329865')])
    calls=[]
    def download(match):
        calls.append(match)
        (importer.ART/'poster.jpg').write_bytes(b'fixture')
        return dict(poster='poster.jpg',matched_title=match['title'])
    monkeypatch.setattr(importer,'download',download)
    return items,calls

def test_import_once_then_reuse_and_skip_new_episode(automatic):
    items,calls=automatic
    importer.run();importer.run()
    assert len(calls)==1
    assert json.loads(importer.INDEX.read_text())['7']['matched_title']=='Arrival'
    # Catalog IDs, not raw episode IDs, determine the job: more episodes do not redownload art.
    items[:]=[dict(id='show-123',title='Example Show',year=None,kind='show')]
    importer.run();importer.run()
    assert len(calls)==2

def test_ambiguous_matches_are_not_assigned_and_retry_is_bounded(automatic,monkeypatch):
    _,calls=automatic
    monkeypatch.setattr(importer,'search',lambda q,k:[dict(title=q,year=2016,url='one'),dict(title=q,year=2016,url='two')])
    importer.run()
    assert not calls and not importer.INDEX.exists()
    assert json.loads(importer.REPORT.read_text())[0]['status']=='needs_review'
    def no_network(*args):pytest.fail('Unchanged unresolved match retried too soon')
    monkeypatch.setattr(importer,'search',no_network)
    importer.run()
    assert json.loads(importer.REPORT.read_text())[0]['status']=='needs_review'

def test_changed_override_retries_immediately(automatic,monkeypatch):
    _,calls=automatic
    monkeypatch.setattr(importer,'search',lambda q,k:[])
    importer.run()
    (importer.ROOT/'config/artwork-matches.json').write_text(json.dumps({'7':{'query':'Correct Arrival'}}))
    monkeypatch.setattr(importer,'search',lambda q,k:[dict(title=q,year=2016,url='https://www.themoviedb.org/movie/329865')])
    importer.run()
    assert calls[0]['title']=='Correct Arrival'

def test_failed_refresh_preserves_existing_index(automatic,monkeypatch):
    importer.run()
    previous=importer.INDEX.read_bytes()
    def broken(match):raise OSError('offline')
    monkeypatch.setattr(importer,'download',broken)
    importer.run(refresh=['7'])
    assert importer.INDEX.read_bytes()==previous
    assert json.loads(importer.REPORT.read_text())[0]['status']=='error'

def test_show_remake_year_used_for_matching(automatic,monkeypatch):
    items,calls=automatic
    items[:]=[dict(id='show-1',title='Example Show (2020)',year=None,kind='show')]
    def search(query,kind):
        assert query=='Example Show' and kind=='tv'
        return [dict(title=query,year=2005,url='old'),dict(title=query,year=2020,url='new')]
    monkeypatch.setattr(importer,'search',search)
    importer.run()
    assert calls[0]['year']==2020

def test_artwork_is_bounded_and_atomic(automatic,monkeypatch):
    importer.ART.mkdir(parents=True)
    image=Image.new('RGB',(1920,1080),(20,30,40));data=io.BytesIO();image.save(data,'JPEG')
    monkeypatch.setattr(importer,'fetch',lambda url:data.getvalue())
    name=importer.image_file('https://image.tmdb.org/example','landscape')
    with Image.open(importer.ART/name) as result:assert result.size==(480,270)
    assert not list(importer.ART.glob('*.tmp'))

def test_background_worker_requests_and_shutdown():
    worker=ArtworkWorker()
    worker.start() # Disabled by the test fixture; no network or subprocess.
    assert worker.thread is None
    worker.request()
    assert worker.wake_event.is_set()
    worker.close()
    assert worker.stop_event.is_set()

def test_worker_periodic_scan_and_api_wake(monkeypatch):
    from app import artwork_worker as module
    worker=ArtworkWorker()
    scans=[]; jobs=[]
    monkeypatch.setattr(module,'scan_library',lambda:scans.append('scan'))
    class Process:
        def __init__(self,*args,**kwargs):jobs.append(args)
        def wait(self):return 0
    monkeypatch.setattr(module.subprocess,'Popen',Process)
    class Wake:
        def wait(self,seconds):
            assert seconds==config.AUTO_LIBRARY_SCAN_SECONDS
            if len(jobs)==2:worker.stop_event.set()
        def clear(self):pass
    worker.wake_event=Wake()
    worker._loop()
    assert len(jobs)==2 and len(scans)==1 # Startup is already scanned by lifespan.


def test_worker_shutdown_terminates_active_import():
    worker=ArtworkWorker()
    class Process:
        stopped=False
        def poll(self):return None
        def terminate(self):self.stopped=True
    process=Process();worker.process=process
    worker.close()
    assert process.stopped

@pytest.mark.parametrize('title,expected',[
    ('Saw II UNRATED','Saw II'),('Film (2020)','Film'),
    ('Film Extended Cut [UNRATED]','Film'),("Film Director's Cut",'Film'),
    ('Film Remastered Special Edition','Film'),('The Unrated','The Unrated'),
    ('Uncut Gems','Uncut Gems'),('Unrated','Unrated'),('Rocky IV','Rocky IV'),
])
def test_artwork_release_query(title,expected):
    assert importer.artwork_query(title)==expected


def test_first_installment_alias_requires_known_movie_year(automatic,monkeypatch):
    items,calls=automatic
    items[:]=[dict(id=7,title='Example I UNRATED',year=2016,kind='movie')]
    searches=[]
    def search(query,kind):
        searches.append(query)
        return [] if query.endswith(' I') else [dict(title='Example',year=2016,url='https://www.themoviedb.org/movie/1')]
    monkeypatch.setattr(importer,'search',search)
    importer.run()
    assert searches==['Example I','Example'] and calls[0]['title']=='Example'
    assert importer.search_queries('Example II',2016,'movie')==['Example II']
    assert importer.search_queries('Example I',None,'movie')==['Example I']
    assert importer.search_queries('Example I',2016,'tv')==['Example I']


def test_alias_keeps_year_check_and_ambiguity_guard(automatic,monkeypatch):
    items,calls=automatic
    items[:]=[dict(id=7,title='Example I UNRATED',year=2016,kind='movie')]
    monkeypatch.setattr(importer,'search',lambda q,k:[dict(title='Example',year=2020,url='wrong')])
    importer.run()
    assert not calls and json.loads(importer.REPORT.read_text())[0]['status']=='needs_review'


def test_errors_retry_soon_and_back_off_without_losing_choices(automatic,monkeypatch):
    _,calls=automatic
    now=[100000.0]
    monkeypatch.setattr(importer.time,'time',lambda:now[0])
    searches=[]
    def offline(query,kind):
        searches.append(query)
        raise TimeoutError('temporary connection failure')
    monkeypatch.setattr(importer,'search',offline)
    importer.run()
    state=json.loads(importer.STATE.read_text())['7']
    assert state['next_retry_at']==now[0]+300 and state['failures']==1
    importer.run()
    assert len(searches)==1
    now[0]+=300
    importer.run()
    state=json.loads(importer.STATE.read_text())['7']
    assert len(searches)==2 and state['next_retry_at']==now[0]+600
    now[0]+=600
    monkeypatch.setattr(importer,'search',lambda q,k:[dict(title=q,year=2016,url='https://www.themoviedb.org/movie/1')])
    importer.run()
    assert len(calls)==1 and '7' not in json.loads(importer.STATE.read_text())
    assert json.loads(importer.REPORT.read_text())==[]


def test_legacy_errors_get_shorter_retry_but_reviews_stay_daily():
    assert importer.retry_at({'time':100,'report':{'status':'error'}})==400
    assert importer.retry_at({'time':100,'report':{'status':'needs_review'}})==100+config.ARTWORK_RETRY_SECONDS
