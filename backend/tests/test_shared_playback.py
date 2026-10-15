import json
import time
import pytest
from test_library import library, client
from test_roku_audio import audio_cache, generate, terminal, video_frames
from app import watch_history as history, config
from app.database import connection
from app.main import get_movie
from app.scanner import scan_library
from app.playback_policy import decide
from app.media_tools import inspect_media, select_tracks

HEADERS={'X-Media-Client':'roku'}
MANAGE={'X-Gravyflix-Manage':'1'}

def movie(library):
    (library/'Movie.mp4').write_bytes(b'fake')
    scan_library()
    with connection() as db:db.execute('UPDATE movies SET duration=1200')
    return get_movie(1)

def session(row,intent='resume'):
    return history.create(row,'test-device','roku',intent)['session_id']

def test_ordering_seek_and_failed_load(client,library):
    row=movie(library);a=session(row)
    assert history.record(a,1,200,1200,'playing')['accepted']
    b=session(row) # A not-yet-playing session never takes ownership.
    history.record(a,2,250,1200,'playing')
    assert history.history()[0]['position']==250
    history.record(b,1,400,1200,'playing')
    history.record(a,3,600,1200,'playing')
    assert history.history()[0]['position']==400
    assert not history.record(b,1,700,1200,'playing')['accepted']
    history.record(b,2,100,1200,'paused') # Backwards seek wins by sequence, not position.
    assert history.history()[0]['position']==100
    assert history.create(row,'other','roku','resume')['resume_position']==100
    assert history.create(row,'other','roku','restart')['resume_position']==0
    assert history.create(row,'other','roku','autoplay')['resume_position']==0
    history.record(b,3,100,1200,'stopped')
    assert not history.record(b,4,900,1200,'playing')['accepted']

def test_completion_and_changed_source(client,library):
    row=movie(library);sid=session(row)
    history.record(sid,1,700,1200,'playing')
    history.record(sid,2,710,1200,'next',credits_start=1000)
    assert not history.history()[0]['completed']
    sid=session(row);history.record(sid,1,1001,1200,'playing')
    history.record(sid,2,1001,1200,'next',credits_start=1000)
    assert history.history()[0]['completed']
    assert history.create(row,'other','roku')['resume_position']==0
    with connection() as db:db.execute('UPDATE movies SET file_size=file_size+1')
    assert not history.history()[0]['resume_valid']
    assert history.history()[0]['completed']

def test_migration_idempotent_and_removed_hidden(client,library):
    row=movie(library)
    with connection() as db:
        db.execute("DELETE FROM history_migrations WHERE name='cast-v1'")
        db.execute("INSERT INTO cast_history VALUES(1,90,1200,0,'2026-01-01T00:00:00+00:00')")
    history.initialize()
    assert history.history()[0]['position']==90
    sid=session(row);history.record(sid,1,120,1200,'playing')
    history.initialize()
    assert history.history()[0]['position']==120
    with connection() as db:db.execute('UPDATE movies SET available=0')
    assert history.history()==[]

def test_sessions_api_and_export_redaction(client,library):
    movie(library)
    body=dict(movie_id=1,client_id='test-roku',intent='resume')
    assert client.post('/api/playback/sessions',json=body).status_code==403
    assert client.post('/api/playback/sessions',json={**body,'client_type':'cast'},headers=HEADERS).status_code==403
    start=client.post('/api/playback/sessions',json=body,headers=HEADERS).json()
    sid=start['session_id']
    data=dict(sequence=1,position=50,duration=1200,state='playing')
    assert client.post('/api/playback/sessions/'+sid+'/progress',json=data,headers=HEADERS).json()['accepted']
    assert client.post('/api/playback/sessions/'+sid+'/progress',json={**data,'position':-1},headers=HEADERS).status_code==422
    assert client.get('/api/history').json()==client.get('/api/cast/history').json()
    assert client.get('/api/manage/playback').status_code==403
    export=client.get('/api/manage/playback/export',headers=MANAGE)
    assert export.status_code==200 and 'attachment' in export.headers['content-disposition']
    assert str(library) not in export.text and 'file_path' not in export.text and 'client_id' not in export.text
    assert export.json()['sessions'][0]['id']==sid

def test_history_show_resume_target(client,library):
    for name in ['Show.S01E01.mp4','Show.S01E02.mp4','Show.S00E01.mp4']:(library/name).write_bytes(b'fake')
    scan_library()
    with connection() as db:db.execute('UPDATE movies SET duration=1200')
    episodes=client.get('/api/movies').json()
    for ep in episodes:
        history.record(session(get_movie(ep['id'])),1,200,1200,'playing')
    show=client.get('/api/library/browse').json()[0]
    assert show['kind']=='show' and show['resume_episode']['episode_number']==2
    assert show['resume_episode']['season_number']==1

@pytest.mark.parametrize('fields,delivery',[
    ({},'direct'),({'filename':'Movie.mkv'},'remux'),
    ({'audio_codec':'ac3'},'audio_convert'),({'audio_channels':6},'audio_convert'),
    ({'video_codec':'hevc'},'video_convert'),({'frame_rate':60},'video_convert'),
    ({'width':3840,'height':2160},'video_convert'),
    ({'video_codec':'hevc','color_transfer':'smpte2084'},'unsupported'),
])
def test_policy(fields,delivery):
    row=dict(filename='Movie.mp4',video_codec='h264',pixel_format='yuv420p',video_level=41,width=1920,height=1080,frame_rate=24,audio_codec='aac',audio_channels=2,audio_profile='LC')
    row.update(fields)
    assert decide(row)['delivery']==delivery
    assert decide(row,'cast')['delivery']==delivery
    assert decide(row,mode='original')['delivery']=='direct'

def test_receiver_capability_and_hdr_guard():
    row=dict(filename='Movie.mp4',video_codec='h264',audio_codec='aac',audio_channels=2)
    assert decide(row,capabilities={'source_video_supported':False})['delivery']=='video_convert'
    row.update(video_codec='hevc',color_transfer='smpte2084')
    assert decide(row,capabilities={'source_video_supported':True})['delivery']=='unsupported'

def test_real_aac_remux_keeps_video_and_audio(client,library,audio_cache):
    source=library/'Copy.mkv';generate(source,'aac',2);before=source.read_bytes();scan_library()
    result=client.post('/api/playback/roku',json={'movie_id':1},headers=HEADERS).json()
    assert result['planned_delivery']=='remux'
    status=terminal(audio_cache,result['token']);assert status['state']=='ready'
    output,_=audio_cache.paths(status['key'])
    assert video_frames(output)==video_frames(source)
    assert select_tracks(inspect_media(output))[1]['codec_name']=='aac'
    assert client.options(result.get('stream_url') or client.get('/api/playback/roku/status/'+result['token']).json()['stream_url']).headers['access-control-allow-origin']=='*'
    assert source.read_bytes()==before

def test_retention_bounds_and_stale_updates(client,library):
    sid=session(movie(library))
    for i in range(210):history.record(sid,i,i,1200,'playing')
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM playback_events').fetchone()[0]==200
        db.execute('UPDATE playback_sessions SET updated_at=?',(time.time()-86401,))
    assert not history.record(sid,211,500,1200,'playing')['accepted']
    history.prune()
    with connection() as db:assert db.execute('SELECT state FROM playback_sessions').fetchone()[0]=='expired'

def test_capability_contract_and_session_mismatch(client,library):
    movie(library)
    body=dict(movie_id=1,capabilities={'source_video_supported':'yes'})
    assert client.post('/api/playback/roku',json=body,headers=HEADERS).status_code==422
    assert client.post('/api/playback/roku',json={'movie_id':1,'session_id':'0'*32},headers=HEADERS).status_code==409

def prepared_manager(monkeypatch):
    from app.casting import CastManager
    from app import cast_preparation
    from unittest.mock import Mock
    manager=CastManager()
    manager.stream_base=lambda:'http://192.0.2.10:8080'
    fake=Mock()
    fake.prepare.return_value='lease'
    fake.status.return_value={'state':'ready','key':'a'*64,'progress':100,'message':'Ready'}
    monkeypatch.setattr(cast_preparation,'cache',fake)
    return manager,fake

def test_cast_async_decision_resume_and_one_decoder_retry(client,library,monkeypatch):
    from app import cast_preparation
    row=movie(library)
    sid=session(row);history.record(sid,1,200,1200,'playing')
    row=dict(row,probe_error=None,video_codec='h264',audio_codec='aac',audio_channels=2,video_profile='High',video_level=41)
    monkeypatch.setattr(cast_preparation,'media_row',lambda r:row)
    manager,fake=prepared_manager(monkeypatch)
    calls=[]
    def load(row,position,manual,**kwargs):
        calls.append((position,kwargs))
        if len(calls)==1:raise RuntimeError('TV could not decode this file.')
        history.record(kwargs['session_id'],1,position,1200,'playing')
    manager._play_movie=load
    result=manager.play_movie(row,intent='resume')
    assert result['state']=='PREPARING'
    manager.preparation.thread.join(3)
    assert not manager.preparation.thread.is_alive()
    assert len(calls)==2 and calls[1][0]==200
    assert calls[0][1]['plan']['delivery']=='direct'
    assert calls[1][1]['plan']['delivery']=='video_convert'
    assert manager.features.prepared_token=='lease'
    assert fake.prepare.call_count==1
    manager.preparation.cancel()

def test_cast_network_failure_has_no_decoder_retry(client,library,monkeypatch):
    from app import cast_preparation
    from unittest.mock import Mock
    row=movie(library)
    monkeypatch.setattr(cast_preparation,'media_row',lambda r:dict(row))
    manager,fake=prepared_manager(monkeypatch)
    manager._play_movie=Mock(side_effect=RuntimeError('TV connection timed out'))
    manager.play_movie(row,intent='resume');manager.preparation.thread.join(3)
    assert manager._play_movie.call_count==1 and fake.prepare.call_count==0
    assert manager.snapshot()['state']=='ERROR'
    assert history.history()==[]

def test_cast_cancel_conversion_releases_lease(client,library,monkeypatch):
    import threading
    from app import cast_preparation
    from unittest.mock import Mock
    row=movie(library)
    monkeypatch.setattr(cast_preparation,'media_row',lambda r:dict(row,probe_error=None,video_codec='mpeg4'))
    manager,fake=prepared_manager(monkeypatch)
    entered=threading.Event()
    def waiting(token):
        entered.set()
        return dict(state='preparing',progress=10,message='Working')
    fake.status.side_effect=waiting
    manager._play_movie=Mock()
    manager.play_movie(row,intent='resume')
    assert entered.wait(2)
    result=manager.command('stop')
    assert result['state']=='IDLE'
    manager.preparation.thread.join(3)
    manager._play_movie.assert_not_called()
    fake.release.assert_called_once_with('lease')
    assert history.history()==[]

@pytest.mark.parametrize('state',['stopped','next'])
@pytest.mark.parametrize('position,completed',[(999,False),(1000,True),(1050,True)])
def test_movie_exit_or_next_at_credits(client,library,state,position,completed):
    from app.credits import save
    row=movie(library)
    save(row,1000,'manual','Test credits marker')
    sid=session(row)
    history.record(sid,1,position,1200,'playing')
    response=client.post(f'/api/playback/sessions/{sid}/end',headers=HEADERS,
        json=dict(sequence=2,position=position,duration=1200,state=state))
    assert response.status_code==200 and response.json()['completed']==completed
    entry=history.history()[0]
    assert bool(entry['completed'])==completed
    catalog=client.get('/api/library/browse').json()[0]
    assert catalog['completed']==completed
    assert catalog['resume_position']==(0 if completed else position)

@pytest.mark.parametrize('state',['stopped','next'])
def test_episode_completion_does_not_complete_unwatched_series(client,library,state):
    for name in ['Show.S01E01.mp4','Show.S01E02.mp4']:(library/name).write_bytes(b'fake')
    scan_library()
    with connection() as db:db.execute('UPDATE movies SET duration=1200')
    episodes=client.get('/api/movies').json()
    row=get_movie(episodes[0]['id']);sid=session(row)
    history.record(sid,1,1170,1200,'playing')
    result=history.record(sid,2,1170,1200,state)
    assert result['completed']
    show=client.get('/api/library/browse').json()[0]
    first,second=show['seasons'][0]['episodes']
    assert first['completed'] and not second['completed']
    assert show['resume_episode']['id']==second['id']
    assert show['continue_watching'] and show['resume_position']==0
    sid2=session(get_movie(second['id']))
    history.record(sid2,1,200,1200,'playing')
    show=client.get('/api/library/browse').json()[0]
    assert show['resume_episode']['id']==second['id']

@pytest.mark.parametrize('state',['playing','paused','error','cancelled'])
def test_credits_without_intentional_exit_stay_resumable(client,library,state):
    row=movie(library);sid=session(row)
    history.record(sid,1,1005,1200,'playing')
    result=history.record(sid,2,1005,1200,state,credits_start=1000)
    assert not result['completed'] and not history.history()[0]['completed']


def test_no_marker_uses_ending_window_not_a_guessed_long_credit_sequence(client,library):
    row=movie(library)
    for position,completed in [(1169,False),(1170,True)]:
        sid=session(row)
        history.record(sid,1,position,1200,'playing')
        assert history.record(sid,2,position,1200,'stopped')['completed']==completed


def test_series_continuation_across_seasons_and_restart(client,library):
    names=['Show.S01E01.mp4','Show.S01E02.mp4','Show.S02E01.mp4']
    for name in names:(library/name).write_bytes(b'fake')
    scan_library()
    with connection() as db:db.execute('UPDATE movies SET duration=1200')
    def browse():return client.get('/api/library/browse').json()[0]
    assert 'resume_episode' not in browse()
    episodes=[e for s in browse()['seasons'] for e in s['episodes']]
    def finish(e):
        sid=session(get_movie(e['id']))
        history.record(sid,1,1170,1200,'playing')
        history.record(sid,2,1170,1200,'stopped')
    finish(episodes[0]);finish(episodes[1])
    history.initialize() # Progress survives a new application initialization.
    assert browse()['resume_episode']['id']==episodes[2]['id']
    sid=session(get_movie(episodes[2]['id']))
    history.record(sid,1,345,1200,'playing')
    history.record(sid,2,345,1200,'stopped')
    assert browse()['resume_episode']['id']==episodes[2]['id']
    assert browse()['resume_position']==345
    finish(episodes[2])
    assert 'resume_episode' not in browse()
    (library/'Show.S02E02.mp4').write_bytes(b'fake')
    scan_library()
    assert browse()['resume_episode']['episode_number']==2
    assert browse()['resume_episode']['season_number']==2


def test_series_ignores_extras_and_changed_sources(client,library):
    for name in ['Show.S00E01.mp4','Show.S01E01.mp4','Show.S01E02.mp4']:
        (library/name).write_bytes(b'fake')
    scan_library()
    with connection() as db:db.execute('UPDATE movies SET duration=1200')
    show=client.get('/api/library/browse').json()[0]
    regular=next(e for s in show['seasons'] for e in s['episodes'] if e['season_number']==1)
    sid=session(get_movie(regular['id']))
    history.record(sid,1,300,1200,'playing')
    with connection() as db:db.execute('UPDATE movies SET file_size=file_size+1 WHERE id=?',(regular['id'],))
    assert 'resume_episode' not in client.get('/api/library/browse').json()[0]
