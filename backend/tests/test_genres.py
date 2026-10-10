import json
from bs4 import BeautifulSoup
from app import genres,public_artwork,config,artwork
from test_artwork import art
from test_library import library,client
from app.scanner import scan_library

def test_movie_tv_genre_normalization():
    soup=BeautifulSoup('<span class="genres"><a href="/genre/10759-action-adventure/tv">Action &amp; Adventure</a><a href="/genre/10765-sci-fi-fantasy/tv">Sci-Fi &amp; Fantasy</a><a href="/genre/28-action/movie">Action</a><a href="/other">Noise</a></span>','html.parser')
    assert genres.parse_genres(soup)==['Action','Adventure','Science Fiction','Fantasy']
    assert genres.parse_genres(BeautifulSoup('<p>No genres</p>','html.parser'))==[]

def test_genre_backfill_preserves_art_and_checks_title(tmp_path,monkeypatch):
    monkeypatch.setattr(public_artwork,'INDEX',tmp_path/'index.json')
    monkeypatch.setattr(public_artwork,'REPORT',tmp_path/'matching.json')
    calls=[]
    def fetch(url):
        calls.append(url)
        return b'<meta property="og:title" content="Arrival"><span class="genres"><a href="/genre/878-science-fiction/movie">Science Fiction</a></span>'
    monkeypatch.setattr(public_artwork,'fetch',fetch)
    index={'1':{'source_url':'https://www.themoviedb.org/movie/329865-arrival','matched_title':'Arrival','poster':'keep.jpg'}}
    items=[{'id':1,'title':'Arrival'}]
    public_artwork.enrich_genres(index,items)
    assert index['1']['genres']==['Science Fiction'] and index['1']['poster']=='keep.jpg'
    public_artwork.enrich_genres(index,items)
    assert len(calls)==1
    index['2']={'source_url':'https://www.themoviedb.org/movie/123-other','matched_title':'Other','poster':'existing.jpg'}
    public_artwork.enrich_genres(index,[{'id':2,'title':'Other'}])
    assert 'genre_version' not in index['2'] and 'genres_error' in index['2']
    assert index['2']['poster']=='existing.jpg'

def test_genres_in_browse_and_episode_inheritance(art,library,client):
    (library/'Example Show.S01E01.mp4').write_bytes(b'video')
    scan_library()
    show=client.get('/api/library/browse').json()[0]
    (art/'index.json').write_text(json.dumps({show['id']:{'genres':['Comedy']}}))
    updated=client.get('/api/library/browse').json()[0]
    assert updated['genres']==['Comedy']
    assert updated['seasons'][0]['episodes'][0]['genres']==['Comedy']
    assert client.get('/api/movies').json()[0]['genres']==['Comedy']

def test_manual_genre_override_reload(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'ROOT',tmp_path)
    (tmp_path/'config').mkdir()
    file=tmp_path/'config/genre-overrides.json'
    file.write_text(json.dumps({'show-1':['Documentary']}))
    assert genres.genres_for(2,'show-1',{'genres':['Drama']})==['Documentary']
    file.write_text(json.dumps({'2':['Comedy','Comedy','Action']}))
    assert genres.genres_for(2,'show-1',{})==['Comedy','Action']
