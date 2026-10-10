import pytest
from test_library import library, client
from app.catalog import episode_identity, build_catalog
from app.scanner import scan_library

@pytest.mark.parametrize('filename,title,season,episode',[
    ('Eastbound.And.Down.S02E01.720p.HDTV.x264.mkv','Eastbound And Down',2,1),
    ('Letterkenny S01-E02 - Super Soft Birthday.mp4','Letterkenny',1,2),
    ('Rick and Morty - S02E10 The Wedding Squanchers.mkv','Rick and Morty',2,10),
    ('Sample.Show.2x03.Title.mkv','Sample Show',2,3),
    ('Sample.Show.S00E01.Special.mkv','Sample Show',0,1),
])
def test_episode_names(filename,title,season,episode):
    result=episode_identity(filename)
    assert (result['show_title'],result['season_number'],result['episode_number'])==(title,season,episode)

@pytest.mark.parametrize('filename',['Iron Man 2.mp4','1-3 Iron Man 2.mp4','2001 A Space Odyssey (1968).mp4','S02E01.mkv','._Show.S01E01.mp4'])
def test_do_not_guess(filename):
    assert episode_identity(filename) is None

def movie(id,name,added='2026-01-01'):
    return dict(id=id,filename=name,title=name,date_added=added,stream_url=f'/stream/{id}',stream_format='mkv')

def test_group_variants_sort_and_preserve_identity():
    data=[movie(1,'Example.and.Show.S04E10.mkv'),movie(2,'Example & Show S02E03.mkv'),
          movie(3,'example.and.show.S02E01.mkv','2026-02-01'),movie(4,'Movie.mp4'),
          movie(5,'._Example.and.Show.S04E10.mkv')]
    result=build_catalog(data)
    assert len(result)==2
    show=next(x for x in result if x['kind']=='show')
    assert show['episode_count']==3 and show['season_count']==2
    assert [s['number'] for s in show['seasons']]==[2,4]
    episodes=show['seasons'][0]['episodes']
    assert [e['episode_number'] for e in episodes]==[1,3]
    assert episodes[0]['id']==3 and episodes[0]['stream_url']=='/stream/3'
    assert show['date_added']=='2026-02-01'
    assert 'stream_url' not in show
    assert build_catalog(data[:1])[0]['id']==show['id']
    assert data[0]['title']==data[0]['filename'] # Input not mutated.

def test_episode_titles_and_combined_file():
    result=episode_identity('Letterkenny S01-E02 - Super Soft Birthday.mp4')
    assert result['episode_title']=='Episode 2 · Super Soft Birthday'
    result=episode_identity('Rick and Morty - S01E01 - Pilot HDTV-1080p.mkv')
    assert result['episode_title']=='Episode 1 · Pilot'
    result=episode_identity('Show.S01E01E02.Double.Pilot.720p.mkv')
    assert result['episode_end']==2 and result['episode_title']=='Episodes 1–2 · Double Pilot'
    assert len(build_catalog([movie(1,'Show (2005).S01E01.mkv'),movie(2,'Show (2020).S01E01.mkv')]))==2

def test_browse_and_flat_api_coexist(library,client):
    for name in ['Show.S02E10.mkv','Show.S02E02.mkv','Movie.mp4']:
        (library/name).write_bytes(b'test')
    scan_library()
    flat=client.get('/api/movies').json()
    response=client.get('/api/library/browse')
    assert response.status_code==200
    browse=response.json()
    assert len(flat)==3 and len(browse)==2
    show=next(x for x in browse if x['kind']=='show')
    episode=show['seasons'][0]['episodes'][0]
    original=next(x for x in flat if x['filename']=='Show.S02E02.mkv')
    assert episode['id']==original['id']
    assert episode['stream_url']==original['stream_url']
    assert client.get(episode['stream_url']).content==b'test'
    assert client.get(f"/api/movies/{episode['id']}").json()==original
    (library/'Show.S02E02.mkv').unlink()
    scan_library()
    remaining=next(x for x in client.get('/api/library/browse').json() if x['kind']=='show')
    assert remaining['id']==show['id'] and remaining['episode_count']==1

@pytest.mark.parametrize('filename,folders,expected',[
    ('Chapter 6.avi',('Example & Show','Season 1'),(1,6)),
    ('Episode 2.avi',('Show','Season 03'),(3,2)),
    ('Chapter 1.avi',('Show','Extras'),None),
    ('Chapter 1.avi',(),None),
    ('Outtakes.avi',('Show','Season 1'),None),
])
def test_explicit_folder_episode_names(filename,folders,expected):
    result=episode_identity(filename,folders)
    if expected is None:
        assert result is None
    else:
        assert (result['season_number'],result['episode_number'])==expected

@pytest.mark.parametrize('name',[
    'example.show.s02e08.tvrip.xvid-tvgeeks.avi',
    'examples.show.s02e09.tvrip.xvid-fqm.avi',
    'releasegroup-examples.show.s02.e01.xvid.avi',
    "Example's Show S01E01.avi",
])
def test_configured_show_aliases(name):
    identity=episode_identity(name)
    assert identity['show_title']=="Example's Show"
    assert identity['show_key']=='examples show'

def test_typo_filename_uses_verified_episode_folder():
    result=episode_identity('example.show.e02e10.tvrips.xvid-tvgeeks.avi',
        ('Examples.Show.DVDRip','Season.02','Examples.Show.S02E10.TVRIP.XVID-TVGEEKS'))
    assert result['show_title']=="Example's Show"
    assert (result['season_number'],result['episode_number'])==(2,10)
    assert episode_identity('unknown.avi',('Show','Season 1','Show.S02E10')) is None
    assert episode_identity('unknown.avi',('Show','Extras','Show.S02E10')) is None

def test_aliases_do_not_merge_other_titles_or_remakes():
    assert episode_identity('Another Show S01E01.avi')['show_key']=='another show'
    assert episode_identity('Examples Show (2020) S01E01.avi')['show_key']!='examples show'
    rows=build_catalog([movie(1,'example.show.S01E01.avi'),movie(2,'releasegroup-examples.show.S02E01.avi')])
    assert len(rows)==1 and rows[0]['episode_count']==2

from app.catalog import grouping_hint

def hinted(id,name,folders=()):
    return {**movie(id,name),'grouping_hint':grouping_hint(name,folders)}

def test_multipart_folder_evidence_and_numeric_order():
    data=[hinted(n,f'Example.Documentary.Part{n}.avi',('Documentaries','Example.Documentary')) for n in [10,2,1]]
    show=build_catalog(data)[0]
    assert show['title']=='Example Documentary' and show['episode_count']==3
    assert show['seasons'][0]['title']=='Parts'
    assert [e['episode_number'] for e in show['seasons'][0]['episodes']]==[1,2,10]
    assert len(build_catalog([movie(1,'Movie.Part1.avi'),movie(2,'Movie.Part2.avi')]))==2
    assert build_catalog([hinted(1,'Movie.Part1.avi',('Movie',))])[0]['kind']=='movie'

def test_explicit_loose_disc_series():
    show=build_catalog([movie(1,'Example.Training.Disk2.H264.avi'),movie(2,'Example.Training.Disk1.H264.avi')])[0]
    assert show['title']=='Example Training'
    assert show['seasons'][0]['title']=='Discs'
    assert [e['episode_title'] for e in show['seasons'][0]['episodes']]==['Disc 1','Disc 2']

def test_extras_attach_only_to_known_show_and_sort_last():
    data=[movie(1,'Example.and.Show.S01E01.mkv'),hinted(2,'Highlights.avi',('Example & Show','Extras'))]
    result=build_catalog(data)
    assert len(result)==1
    show=result[0]
    assert show['episode_count']==1 and show['extra_count']==1 and show['season_count']==1
    assert [s['title'] for s in show['seasons']]==['Season 1','Extras']
    extra=show['seasons'][-1]['episodes'][0]
    assert extra['title']=='Highlights' and extra['id']==2 and extra['stream_url']=='/stream/2'
    assert build_catalog(data[1:])[0]['kind']=='movie'
    # Specials and extras remain separate.
    show=build_catalog(data+[movie(3,'Example.and.Show.S00E01.mkv')])[0]
    assert [s['title'] for s in show['seasons']]==['Specials','Season 1','Extras']

@pytest.fixture(autouse=True)
def explicit_grouping_rules(tmp_path, monkeypatch):
    import json
    from app import config
    from app.catalog import show_aliases, multipart_series
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/show-aliases.json').write_text(json.dumps({
        'Example Show': "Example's Show", 'Examples Show': "Example's Show",
        'releasegroup-Examples Show': "Example's Show",
    }))
    (tmp_path / 'config/library-rules.json').write_text(json.dumps({'multipart_series':['Example Training']}))
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    show_aliases.cache_clear(); multipart_series.cache_clear()
    yield
    show_aliases.cache_clear(); multipart_series.cache_clear()
