import json
import pytest
from bs4 import BeautifulSoup
from app import title_metadata as metadata, public_artwork as importer, artwork
from test_artwork import art
from test_library import library, client
from app.scanner import scan_library

URL = 'https://www.themoviedb.org/tv/100-example-show'
TITLE = '''<meta property="og:title" content="Example Show"><div class="overview"><p>A funny <b>family</b> story.</p></div>
<ol class="people"><li class="profile"><p><a href="/person/1">Director</a></p></li></ol>
<ol class="people scroller"><li class="card"><p><a href="/person/2">Lead One</a></p><p class="character">Character</p></li>
<li class="card"><p><a href="/person/3">Lead Two</a></p></li></ol>'''


def soup(value):
    return BeautifulSoup(value, 'html.parser')


def season_page(number=1, title='Pilot', episode=1, show=100):
    return f'''<div class="episode"><div class="episode_title"><h3><a href="/tv/{show}-example-show/season/{number}/episode/{episode}"
    data-season-number="{number}" data-episode-number="{episode}">{title}</a></h3></div>
    <div class="overview"><p>A particular episode story.</p><a>Read More</a></div></div>'''


def test_title_parsing_excludes_crew_and_bounds_cast():
    fields = metadata.title_fields(soup(TITLE))
    assert fields['description'] == 'A funny family story.'
    assert fields['cast'] == ['Lead One', 'Lead Two']
    extra = ''.join(f'<li class="card"><p><a href="/person/{n}">Actor {n}</a></p></li>' for n in range(10))
    assert len(metadata.title_fields(soup('<ol class="people">'+extra+'</ol>'))['cast']) == 5
    assert metadata.plain('<script>bad()</script><p>Hello &amp; goodbye</p>') == 'Hello & goodbye'
    assert len(metadata.plain('a'*2000)) == 1200


def test_season_validation_and_read_more_exclusion():
    fields = metadata.season_fields(soup(season_page()), URL, 1)
    assert fields['1']['description'] == 'A particular episode story.'
    assert fields['1']['title'] == 'Pilot'
    with pytest.raises(ValueError):
        metadata.season_fields(soup(season_page(show=999)), URL, 1)
    with pytest.raises(ValueError):
        metadata.season_fields(soup(season_page(number=2)), URL, 1)
    with pytest.raises(ValueError):
        metadata.season_fields(soup('<p>unavailable</p>'), URL, 1)


def test_dvd_numbering_uses_unique_episode_title_and_avoids_wrong_summaries():
    entry = {'episode_metadata': {'5': {'23': {'title':'Company Picnic','description':'Correct story'},
                                       '28': {'title':'Wrong Episode','description':'Incorrect story'}}}}
    identity = {'season_number':5,'episode_number':28,'episode_end':28,'episode_title':'Episode 28 · Company Picnic'}
    assert metadata.episode_fields(entry, identity)['description'] == 'Correct story'
    identity['episode_title'] = 'Episode 28 · Unknown DVD title'
    assert metadata.episode_fields(entry, identity) is None
    identity['episode_title'] = 'Episode 28'
    assert metadata.episode_fields(entry, identity)['description'] == 'Incorrect story'
    identity['episode_end'] = 29
    assert metadata.episode_fields(entry, identity) is None
    identity.update(season_number=-1, episode_end=28)
    assert metadata.episode_fields(entry, identity) is None


def test_backfill_retains_art_caches_and_retries_new_episode(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, 'INDEX', tmp_path/'index.json')
    calls = []
    def fetch(url):
        calls.append(url)
        return (season_page() if '/season/' in url else TITLE).encode()
    monkeypatch.setattr(importer, 'fetch', fetch)
    index = {'show-1':{'matched_title':'Example Show','source_url':URL,'poster':'keep.jpg'}}
    items = [{'id':'show-1','title':'Example Show','kind':'show','seasons':[{'number':1,'episodes':[{'episode_number':1}]}]}]
    importer.enrich_metadata(index, items)
    assert index['show-1']['description'] == 'A funny family story.'
    assert index['show-1']['poster'] == 'keep.jpg'
    importer.enrich_metadata(index, items)
    assert len(calls) == 2
    items[0]['seasons'][0]['episodes'].append({'episode_number':2})
    importer.enrich_metadata(index, items)
    assert len(calls) == 3 and calls[-1].endswith('/season/1')


def test_wrong_page_and_network_failure_preserve_previous_good_data(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, 'INDEX', tmp_path/'index.json')
    index = {'1':{'matched_title':'Verified','source_url':'https://www.themoviedb.org/movie/1',
                  'description':'Keep this summary','cast':['Known Star'],'poster':'keep.jpg'}}
    monkeypatch.setattr(importer, 'fetch', lambda _: TITLE.encode())
    items = [{'id':1,'title':'Verified','kind':'movie'}]
    importer.enrich_metadata(index, items)
    assert index['1']['description'] == 'Keep this summary'
    assert index['1']['cast'] == ['Known Star']
    assert 'metadata_error' in index['1'] and 'metadata_version' not in index['1']
    monkeypatch.setattr(importer, 'fetch', lambda _: pytest.fail('Error should be backed off'))
    importer.enrich_metadata(index, items)


def test_api_movie_series_episode_metadata_and_clear_fallback(art, library, client):
    (library/'Film.mp4').write_bytes(b'video')
    (library/'Example Show.S01E01.Pilot.mp4').write_bytes(b'video')
    (library/'Example Show.S01E02.Unknown.mp4').write_bytes(b'video')
    scan_library()
    initial = client.get('/api/library/browse').json()
    show = next(i for i in initial if i['kind']=='show')
    movie = next(i for i in initial if i['kind']=='movie')
    entries = {str(movie['id']):{'description':'Movie story','cast':['Movie Star'],'source_url':'https://www.themoviedb.org/movie/2'},
               show['id']:{'description':'Series story','cast':['TV Star'],'source_url':URL,
                           'episode_metadata':{'1':{'1':{'title':'Pilot','description':'Pilot story','source_url':URL+'/season/1/episode/1'}}}}}
    (art/'index.json').write_text(json.dumps(entries))
    catalog = client.get('/api/library/browse').json()
    show = next(i for i in catalog if i['kind']=='show')
    movie = next(i for i in catalog if i['kind']=='movie')
    assert movie['description']=='Movie story' and movie['cast']==['Movie Star']
    assert show['description']=='Series story' and show['cast']==['TV Star']
    first, second = show['seasons'][0]['episodes']
    assert first['description']=='Pilot story' and first['description_scope']=='episode'
    assert first['cast']==['TV Star'] and first['cast_scope']=='series'
    assert second['description']=='Series story' and second['description_scope']=='series'
    assert client.get(f"/api/movies/{first['id']}").json()['description']=='Pilot story'


def test_malformed_cached_metadata_is_safe():
    item = metadata.decorate_metadata({'id':1}, {'source_url':None,'description':None,'cast':'bad'})
    assert item['cast'] == [] and 'description' not in item
    assert metadata.episode_fields({'episode_metadata':[]}, {'season_number':1,'episode_number':1}) is None
    assert metadata.episode_fields({'episode_metadata':{'1':{'1':None}}}, {'season_number':1,'episode_number':1}) is None
