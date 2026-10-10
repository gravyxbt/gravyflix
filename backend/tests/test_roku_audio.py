import json
import subprocess
import time
from pathlib import Path
import pytest
from test_library import library, client
from app import config, playback_api
from app.database import initialize, connection
from app.main import get_movie
from app.media_tools import binary, inspect_media, select_tracks, probe_fields
from app.roku_audio import AudioCache, Job, fingerprint, LEASE_TTL
from app.scanner import scan_library

@pytest.fixture
def audio_cache(tmp_path, monkeypatch, library):
    monkeypatch.setattr(config, 'ROKU_CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(config, 'ROKU_CACHE_MAX_BYTES', 512 * 1024**2)
    monkeypatch.setattr(config, 'ROKU_AUDIO_MODE', 'auto')
    cache = AudioCache()
    monkeypatch.setattr(playback_api, 'cache', cache)
    yield cache
    cache.close()

def terminal(cache, token):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = cache.status(token)
        if result['state'] in {'ready', 'failed', 'cancelled'}:
            return result
        time.sleep(.05)
    pytest.fail('Audio worker did not finish')

def generate(path, codec='ac3', channels=2):
    ffmpeg = binary('ffmpeg')
    if not ffmpeg or not binary('ffprobe'):
        pytest.skip('Install FFmpeg/ffprobe for actual codec integration tests')
    subprocess.run([ffmpeg, '-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24',
                    '-f','lavfi','-i','sine=frequency=800:sample_rate=48000',
                    '-t','2','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
                    '-c:a',codec,'-ac',str(channels),str(path)],check=True,timeout=20)

def video_frames(path):
    result = subprocess.run([binary('ffmpeg'),'-v','error','-i',str(path),'-map','0:v:0',
                             '-f','framemd5','-'],capture_output=True,text=True,check=True,timeout=20)
    return [line.rsplit(',',1)[-1].strip() for line in result.stdout.splitlines() if not line.startswith('#')]

@pytest.mark.parametrize('codec,channels', [('ac3',2),('eac3',6),('aac',6)])
def test_real_conversion_range_reuse_and_original(library, client, audio_cache, codec, channels):
    source=library/'Sound.mkv'
    generate(source,codec,channels)
    before=source.read_bytes()
    scan_library()
    movie=client.get('/api/movies').json()[0]
    assert movie['audio_codec']==codec and movie['audio_channels']==channels
    assert movie['audio_tracks'][0]['channels']==channels
    body={'movie_id':movie['id']}
    assert client.post('/api/playback/roku',json=body).status_code==403
    response=client.post('/api/playback/roku',json=body,headers={'X-Media-Client':'roku'})
    assert response.status_code==200
    token=response.json()['token']
    status=terminal(audio_cache,token)
    assert status['state']=='ready',status
    output,_=audio_cache.paths(status['key'])
    data=output.read_bytes()
    video,audio,_=select_tracks(inspect_media(output))
    assert video['codec_name']=='h264'
    assert (audio['codec_name'],audio['profile'],audio['channels'])==('aac','LC',2)
    assert video_frames(source)==video_frames(output)
    decoded=subprocess.run([binary('ffmpeg'),'-v','error','-i',str(output),'-map','0:a:0',
                            '-f','s16le','-'],capture_output=True,check=True,timeout=20).stdout
    assert len(decoded)>10000 and any(decoded)
    plan=client.get(f'/api/playback/roku/status/{token}').json()
    url=plan['stream_url']
    assert plan['delivery']=='audio_convert'
    assert client.head(url).headers['content-length']==str(len(data))
    for value,expected in [('bytes=0-999',data[:1000]),('bytes=-100',data[-100:]),('bytes=1000-',data[1000:])]:
        response=client.get(url,headers={'Range':value})
        assert response.status_code==206
        assert response.content==expected
        assert response.headers['content-type']=='video/mp4'
    assert client.get(url,headers={'Range':f'bytes={len(data)}-'}).status_code==416
    assert len(audio_cache.leases)==1  # Transfer leases released, playback lease retained.
    mtime=output.stat().st_mtime_ns
    from app.playback_policy import decide
    second=audio_cache.prepare(get_movie(movie['id']),plan=decide(get_movie(movie['id'])))
    assert audio_cache.leases[token][0] is audio_cache.leases[second][0]
    assert output.stat().st_mtime_ns==mtime
    audio_cache.release(second)
    original=client.post('/api/playback/roku',json={**body,'mode':'original'},headers={'X-Media-Client':'roku'}).json()
    assert original['delivery']=='direct'
    assert client.get(original['stream_url']).content==before
    assert source.read_bytes()==before
    assert not list(config.ROKU_CACHE_DIR.glob('*.part'))
    client.delete(f'/api/playback/roku/status/{token}',headers={'X-Media-Client':'roku'})
    assert client.get(f'/api/playback/roku/status/{token}').status_code==404
    # Reopen a new manager as after server restart: valid on-disk cache remains usable.
    fresh=AudioCache()
    try:
        token2=fresh.prepare(get_movie(movie['id']),plan=decide(get_movie(movie['id'])))
        assert fresh.status(token2)['state']=='ready'
        assert fresh.executor is None
    finally:
        fresh.close()
    source.write_bytes(before+b'changed')
    assert client.get(url).status_code==409

def test_mp4_stays_direct(library,client,audio_cache):
    (library/'Movie.mp4').write_bytes(b'movie')
    scan_library()
    movie=client.get('/api/movies').json()[0]
    response=client.post('/api/playback/roku',json={'movie_id':movie['id']},headers={'X-Media-Client':'roku'})
    assert response.json()['delivery']=='direct'
    assert audio_cache.executor is None
    assert not audio_cache.jobs

def test_failed_conversion_is_visible(library,client,audio_cache):
    if not binary('ffmpeg') or not binary('ffprobe'):
        pytest.skip('FFmpeg required')
    (library/'Bad.mkv').write_bytes(b'not a movie')
    scan_library()
    row=get_movie(client.get('/api/movies').json()[0]['id'])
    token=audio_cache.prepare(row)
    status=terminal(audio_cache,token)
    assert status['state']=='failed'
    assert not list(config.ROKU_CACHE_DIR.glob('*.mp4'))

def test_cancel_only_after_last_client_and_expiry(audio_cache):
    job=Job('test',{})
    audio_cache.jobs[job.key]=job
    now=time.monotonic()
    audio_cache.leases={'a':(job,now),'b':(job,now)}
    audio_cache.release('a')
    assert not job.cancel.is_set()
    audio_cache.release('b')
    assert job.cancel.is_set()
    ready=Job('ready',{},state='ready')
    audio_cache.jobs[ready.key]=ready
    audio_cache.leases={'expired':(ready,now-LEASE_TTL-1),'transfer':(ready,None)}
    audio_cache.expire()
    assert 'expired' not in audio_cache.leases
    assert 'transfer' in audio_cache.leases
    assert ready.key in audio_cache.jobs

def test_eviction_protects_active_files(audio_cache,monkeypatch):
    monkeypatch.setattr(config,'ROKU_CACHE_MAX_BYTES',100)
    root=audio_cache.root()
    old=root / ('a'*64+'.mp4')
    active=root / ('b'*64+'.mp4')
    unrelated=root/'personal.mp4'
    unrelated.write_bytes(b'never evict me')
    old.write_bytes(b'a'*40)
    active.write_bytes(b'b'*40)
    job=Job('b'*64,{},state='ready')
    audio_cache.leases['playing']=(job,time.monotonic())
    audio_cache.reserve(50)
    assert unrelated.exists()
    assert not old.exists()
    assert active.exists()
    with pytest.raises(ValueError,match='cache is full'):
        audio_cache.reserve(70)

def test_default_audio_and_attached_art_selection():
    info={'streams':[
        {'index':0,'codec_type':'video','disposition':{'attached_pic':1}},
        {'index':1,'codec_type':'video','codec_name':'h264'},
        {'index':2,'codec_type':'audio','codec_name':'ac3','channels':6},
        {'index':3,'codec_type':'audio','codec_name':'aac','channels':2,'disposition':{'default':1}}]}
    v,a,tracks=select_tracks(info)
    assert v['index']==1 and a['index']==3 and len(tracks)==2
    assert probe_fields(info)['audio_channels']==2

def test_source_escape_rejected(library,audio_cache,tmp_path):
    outside=tmp_path/'private.mkv';outside.write_bytes(b'secret')
    link=library/'escape.mkv';link.symlink_to(outside)
    with pytest.raises(ValueError):
        audio_cache.prepare({'id':1,'file_path':str(link)})

def test_additive_migration_preserves_id(library):
    initialize()
    (library/'Existing.mp4').write_bytes(b'video')
    scan_library()
    with connection() as db:
        before=dict(db.execute('SELECT * FROM movies').fetchone())
        for name in ['audio_channels','audio_profile','audio_tracks','probe_version']:
            db.execute(f'ALTER TABLE movies DROP COLUMN {name}')
    initialize()
    with connection() as db:
        after=dict(db.execute('SELECT * FROM movies').fetchone())
    assert after['id']==before['id'] and after['date_added']==before['date_added']
    assert after['probe_version']==0

@pytest.mark.parametrize('video_codec', ['mpeg4','libx264'])
def test_avi_conversion_and_folder_catalog(library,client,audio_cache,monkeypatch,video_codec):
    if not binary('ffmpeg') or not binary('ffprobe'):
        pytest.skip('FFmpeg required')
    folder=library/'Eastbound & Down'/'Season 1'
    folder.mkdir(parents=True)
    source=folder/'Chapter 1.AVI'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24',
                    '-f','lavfi','-i','sine=frequency=700:sample_rate=48000','-t','2',
                    '-c:v',video_codec,'-c:a','libmp3lame',str(source)],check=True,timeout=20)
    before=source.read_bytes()
    scan_library()
    movie=client.get('/api/movies').json()[0]
    assert movie['stream_format']=='avi'
    show=client.get('/api/library/browse').json()[0]
    assert show['kind']=='show' and show['title']=='Eastbound & Down'
    assert show['seasons'][0]['number']==1
    assert show['seasons'][0]['episodes'][0]['id']==movie['id']
    # The old audio-only disable setting cannot accidentally send raw AVI to Roku.
    monkeypatch.setattr(config,'ROKU_AUDIO_MODE','original')
    response=client.post('/api/playback/roku',json={'movie_id':movie['id']},headers={'X-Media-Client':'roku'})
    assert response.status_code==200
    token=response.json()['token']
    status=terminal(audio_cache,token)
    assert status['state']=='ready',status
    plan=client.get(f'/api/playback/roku/status/{token}').json()
    assert plan['delivery']==('video_convert' if video_codec=='mpeg4' else 'audio_convert')
    output,_=audio_cache.paths(status['key'])
    video,audio,_=select_tracks(inspect_media(output))
    assert video['codec_name']=='h264' and video['pix_fmt']=='yuv420p'
    assert video['level']==31 if video_codec=='mpeg4' else video['level']<=41
    assert audio['codec_name']=='aac' and audio['channels']==2
    assert client.get(plan['stream_url'],headers={'Range':'bytes=0-999'}).content==output.read_bytes()[:1000]
    assert source.read_bytes()==before
    assert client.head(movie['stream_url']).headers['content-type']=='video/x-msvideo'

def test_hevc_command_transcodes_and_h264_command_copies():
    from app.roku_audio import conversion_command
    audio={'index':1,'codec_name':'aac'}
    hevc=conversion_command('ffmpeg',Path('Film.mkv'),Path('out'),Path('progress'),
                            {'index':0,'codec_name':'hevc','pix_fmt':'yuv420p'},audio)
    assert hevc[hevc.index('-c:v')+1]=='libx264'
    assert 'hvc1' not in hevc
    assert hevc[hevc.index('-profile:v')+1]=='high'
    h264=conversion_command('ffmpeg',Path('Film.mkv'),Path('out'),Path('progress'),
                            {'index':0,'codec_name':'h264','pix_fmt':'yuv420p'},audio)
    assert h264[h264.index('-c:v')+1]=='copy'


def test_hevc_mkv_is_prepared_as_h264(library,client,audio_cache):
    if not binary('ffmpeg') or not binary('ffprobe'):pytest.skip('FFmpeg required')
    source=library/'HEVC (2026).mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24',
        '-f','lavfi','-i','sine=frequency=800:sample_rate=48000','-t','2',
        '-c:v','libx265','-preset','ultrafast','-x265-params','pools=1:frame-threads=1:log-level=error',
        '-c:a','aac',str(source)],check=True,timeout=20)
    before=source.read_bytes();scan_library()
    movie=client.get('/api/movies').json()[0]
    response=client.post('/api/playback/roku',json={'movie_id':movie['id']},headers={'X-Media-Client':'roku'})
    token=response.json()['token'];status=terminal(audio_cache,token)
    assert status['state']=='ready' and status['delivery']=='video_convert'
    output,_=audio_cache.paths(status['key'])
    video,audio,_=select_tracks(inspect_media(output))
    assert video['codec_name']=='h264' and video['pix_fmt']=='yuv420p'
    assert audio['codec_name']=='aac' and audio['channels']==2
    assert source.read_bytes()==before
    url=client.get('/api/playback/roku/status/'+token).json()['stream_url']
    result=client.get(url,headers={'Range':'bytes=0-99'})
    assert result.status_code==206 and len(result.content)==100

def test_nvenc_command_uses_h264_options(monkeypatch):
    from app.roku_audio import conversion_command
    monkeypatch.setattr(config,'ROKU_VIDEO_ENCODER','h264_nvenc')
    command=conversion_command('ffmpeg',Path('Film.mkv'),Path('out'),Path('progress'),
        {'index':0,'codec_name':'hevc'},{'index':1,'codec_name':'aac'})
    assert command[command.index('-c:v')+1]=='h264_nvenc'
    assert '-crf' not in command and command[command.index('-cq')+1]=='20'
    assert '-maxrate' in command and '-vf' in command

def test_hevc_invalidates_video_copy_cache_but_preserves_h264_keys(library):
    import hashlib
    source=library/'Film.mkv';source.write_bytes(b'video')
    stat=source.stat()
    row=dict(id=7,file_path=str(source),video_codec='h264')
    legacy=hashlib.sha256(json.dumps(['aac-lc-stereo-mp4-v1',7,str(source),stat.st_size,stat.st_mtime_ns]).encode()).hexdigest()
    assert fingerprint(row)==legacy
    row['video_codec']='hevc'
    assert fingerprint(row)!=legacy
