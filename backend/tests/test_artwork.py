import json
from pathlib import Path
import pytest
from test_library import library, client
from app import artwork, config
from app.catalog import episode_identity
from app.scanner import scan_library

@pytest.fixture
def art(tmp_path,monkeypatch):
    folder=tmp_path/'artwork';folder.mkdir()
    monkeypatch.setattr(artwork,'root',lambda:folder)
    monkeypatch.setattr(artwork,'_stamp',None)
    monkeypatch.setattr(artwork,'_index',{})
    return folder

def asset(art,role):
    name='a'*24+'-'+role+'.jpg'
    (art/name).write_bytes(b'jpeg-test-fixture')
    return name

def test_movie_art_served_locally_and_cached(art,library,client):
    (library/'Film.mp4').write_bytes(b'video');scan_library()
    movie=client.get('/api/movies').json()[0]
    poster=asset(art,'poster');landscape=asset(art,'landscape');backdrop=asset(art,'backdrop')
    (art/'index.json').write_text(json.dumps({str(movie['id']):dict(poster=poster,landscape=landscape,backdrop=backdrop,source_url='https://example.com/title')}))
    updated=client.get('/api/movies').json()[0]
    for role in ['poster','landscape','backdrop']:
        response=client.get(updated[role+'_url'])
        assert response.status_code==200 and response.headers['content-type']=='image/jpeg'
        assert 'immutable' in response.headers['cache-control']
    assert updated['stream_url']==movie['stream_url']
    assert client.get('/api/library/browse').json()[0]['landscape_url']==updated['landscape_url']
    assert client.get('/artwork/index.json').status_code==404

def test_show_and_episode_inherit_correct_art(art,library,client):
    (library/'Show.S01E01.mp4').write_bytes(b'video');scan_library()
    show_id=artwork.show_id(episode_identity('Show.S01E01.mp4'))
    poster=asset(art,'poster')
    (art/'index.json').write_text(json.dumps({show_id:dict(poster=poster)}))
    show=client.get('/api/library/browse').json()[0]
    assert show['poster_url'].endswith(poster)
    assert show['seasons'][0]['episodes'][0]['poster_url']==show['poster_url']

def test_bad_paths_missing_images_and_atomic_reload(art):
    (art/'index.json').write_text(json.dumps({'1':dict(poster='../secret',backdrop='f'*24+'-backdrop.jpg')}))
    assert 'poster_url' not in artwork.decorate({'id':1},'http://server')
    assert 'backdrop_url' not in artwork.decorate({'id':1},'http://server')
    name=asset(art,'poster')
    temp=art/'new.json';temp.write_text(json.dumps({'1':dict(poster=name)}));temp.replace(art/'index.json')
    assert artwork.decorate({'id':1},'http://server')['poster_url'].endswith(name)
    (art/'index.json').write_text('broken')
    assert artwork.decorate({'id':1},'http://server')['poster_url'].endswith(name)

def test_symlink_outside_artwork_rejected(art,client,tmp_path):
    outside=tmp_path/'secret';outside.write_bytes(b'secret')
    name='b'*24+'-poster.jpg';(art/name).symlink_to(outside)
    assert client.get('/artwork/'+name).status_code==404
