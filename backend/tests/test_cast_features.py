from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.cast_autoplay import next_item
from app.casting import CastManager
from app.cast_features import history
from test_library import library, client
from app.scanner import scan_library
from app.database import connection


def episode(id,season,number,end=None):
    return dict(id=id,kind='episode',show_key='show',season_number=season,episode_number=number,episode_end=end or number)

def test_next_episode_skips_combined_and_extras():
    current=episode(1,1,1,2)
    candidates=[episode(2,1,2),episode(3,1,3),episode(4,2,1),episode(5,-1,0)]
    catalog=[dict(kind='show',seasons=[dict(episodes=candidates)])]
    assert next_item(current,catalog,{1})['id']==3
    assert next_item(candidates[1],catalog,{1,3})['id']==4
    assert next_item(candidates[-1],catalog,set()) is None


def test_movie_recommendations_require_shared_genre_and_skip_short_and_visited():
    current=dict(id=1,kind='movie',genres=['Comedy','Action'])
    movies=[dict(id=i,kind='movie',title=title,genres=genres,duration=length)
        for i,title,genres,length in [(2,'A',['Comedy'],1000),(3,'B',['Comedy','Action'],1000),(4,'Short',['Comedy','Action'],20),(5,'Other',['Drama'],1000)]]
    assert next_item(current,movies,{1})['id']==3
    assert next_item(current,movies,{1,3})['id']==2
    assert next_item(current,movies,{1,2,3}) is None


def test_autoplay_requires_confirmation_after_three_and_never_controls_other_apps():
    manager=CastManager();features=manager.features
    status=SimpleNamespace(player_state='PLAYING',content_id='owned',idle_reason=None)
    controller=Mock(status=status)
    manager.cast=SimpleNamespace(media_controller=controller)
    manager.media_url='owned'
    manager.snapshot=Mock(return_value={'still_watching':True})
    features.next={'id':2};features.transitions=3;features.running=True
    features.advance()
    assert features.confirm
    controller.pause.assert_called_once_with(timeout=5)
    features.advance=Mock()
    status.content_id='another-app';features.tick()
    assert not features.running
    features.advance.assert_not_called()


def test_finish_and_confirmation_reset(client,library,monkeypatch):
    from app import main
    (library/'Test.mp4').write_bytes(b'video');scan_library()
    row=main.get_movie(1)
    manager=CastManager();features=manager.features
    status=SimpleNamespace(player_state='IDLE',idle_reason='FINISHED',content_id='owned',duration=100,adjusted_current_time=100)
    manager.cast=SimpleNamespace(media_controller=Mock(status=status));manager.media_url='owned'
    features.current={'id':row['id']};features.next={'id':row['id']};features.running=True;features.transitions=3
    manager.snapshot=Mock(return_value={'still_watching':features.confirm})
    features.tick()
    assert features.confirm and history()[0]['completed']==1
    manager.play_movie=Mock(return_value={'active':True})
    features.advance(confirm=True)
    assert features.transitions==1 and not features.confirm
    manager.play_movie.assert_called_once_with(row,manual=False,intent="autoplay")


def test_pause_does_not_advance_and_history_saved(client,library):
    (library/'Test.mp4').write_bytes(b'video');scan_library()
    manager=CastManager();features=manager.features
    status=SimpleNamespace(player_state='PAUSED',content_id='owned',duration=100,adjusted_current_time=25)
    manager.cast=SimpleNamespace(media_controller=Mock(status=status));manager.media_url='owned'
    features.current={'id':1};features.running=True;features.suspended=True;features.advance=Mock()
    features.tick()
    features.advance.assert_not_called()
    assert history()[0]['position']==25


def test_live_captions_reject_unknown_track():
    manager=CastManager();manager.snapshot=Mock(return_value={'active':True,'subtitle_tracks':[{'id':1}]})
    manager.cast=SimpleNamespace(media_controller=Mock())
    with pytest.raises(ValueError):manager.features.captions(2)
    manager.cast.media_controller.enable_subtitle.assert_not_called()
    manager.features.captions(1);manager.cast.media_controller.enable_subtitle.assert_called_once_with(1,timeout=5)
    manager.features.captions(None);manager.cast.media_controller.disable_subtitle.assert_called_once_with(timeout=5)


def test_feature_routes_enforce_control_header_and_pending_prompt(client, monkeypatch):
    from app import cast_api
    manager=Mock()
    manager.lock=__import__('threading').RLock()
    manager.snapshot.return_value={'active':True,'still_watching':False}
    monkeypatch.setattr(cast_api,'manager',manager)
    for path,body in [('captions',{'track_id':1}),('queue',{'action':'next'})]:
        assert client.post('/api/cast/'+path,json=body).status_code==403
    assert client.post('/api/cast/queue',json={'action':'confirm'},headers={'X-Media-Control':'1'}).status_code==409
    manager.features.advance.assert_not_called()
    manager.snapshot.return_value={'active':False,'still_watching':True}
    manager.features.advance.return_value={'active':True}
    assert client.post('/api/cast/queue',json={'action':'confirm'},headers={'X-Media-Control':'1'}).json()['active']
    manager.features.advance.assert_called_once_with(True)
    assert client.get('/api/cast/history').json()==[]
