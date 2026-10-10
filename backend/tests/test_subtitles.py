import json
import threading
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app import config, subtitles, opensubtitles
from app.main import app
from app.scanner import scan_library
from app.database import connection

SRT=b'1\n00:00:01,000 --> 00:00:03,000\nHello world\n'

@pytest.fixture
def media(tmp_path,monkeypatch):
    root=tmp_path/'Movies';root.mkdir()
    monkeypatch.setattr(config,'ROOT',tmp_path)
    monkeypatch.setattr(config,'MOVIES_DIR',root)
    monkeypatch.setattr(config,'DATABASE_PATH',tmp_path/'db.sqlite3')
    monkeypatch.setattr(subtitles,'inspect_media',lambda p:{'streams':[]})
    with TestClient(app) as client:
        yield root,client

def get_row():
    with connection() as db: return dict(db.execute('SELECT * FROM movies WHERE available=1').fetchone())

def test_local_caption_discovery_and_endpoints(media):
    root,client=media
    movie=root/'Film.mp4';movie.write_bytes(b'test')
    (root/'Film.en.srt').write_bytes(SRT)
    (root/'Film.en.forced.srt').write_bytes(SRT)
    (root/'Film Two.en.srt').write_bytes(SRT)
    scan_library()
    worker=subtitles.SubtitleWorker();worker.run_once()
    row=get_row();data=client.get(f'/api/movies/{row["id"]}/subtitles').json()
    assert data['state']=='ready'
    assert len(data['tracks'])==2
    assert {t['kind'] for t in data['tracks']}=={'regular','forced'}
    url=data['tracks'][0]['url']
    assert client.get(url).content==SRT
    assert client.head(url).status_code==200
    vtt=url[:-4]+'.vtt'
    response=client.get(vtt)
    assert response.status_code==200 and response.text.startswith('WEBVTT\n\n')
    assert '00:00:01.000 --> 00:00:03.000' in response.text
    assert response.headers['access-control-allow-origin']=='*'
    assert client.head(vtt).status_code==200
    assert client.get('/subtitles/not-an-id.srt').status_code==404
    movie.write_bytes(b'replaced media')
    assert client.get(url).status_code==404
    assert client.get(vtt).status_code==404
    assert client.get(f'/api/movies/{row["id"]}/subtitles').json()['state']=='pending'
    worker.run_once()
    assert client.get(f'/api/movies/{row["id"]}/subtitles').json()['tracks'][0]['id']!=data['tracks'][0]['id']

def test_sidecar_change_and_symlink_outside(media,tmp_path):
    root,client=media
    movie=root/'Film.mp4';movie.write_bytes(b'test')
    other=tmp_path/'other.srt';other.write_bytes(SRT)
    (root/'Film.en.srt').symlink_to(other)
    scan_library()
    assert subtitles.sidecars(movie)==[]
    (root/'Film.en.srt').unlink()
    (root/'Film.en.srt').write_bytes(SRT)
    worker=subtitles.SubtitleWorker();worker.run_once()
    row=get_row();before=subtitles.saved(row['id'])
    (root/'Film.en.srt').write_bytes(SRT.replace(b'Hello world',b'Changed text'))
    worker.run_once()
    assert before['signature']!=subtitles.saved(row['id'])['signature']

def test_embedded_tracks_and_forced_does_not_block_download(media,monkeypatch):
    root,_=media;(root/'Film.mkv').write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda p:{'streams':[
        {'index':2,'codec_type':'subtitle','codec_name':'subrip','tags':{'language':'eng'},'disposition':{'forced':1}},
        {'index':3,'codec_type':'subtitle','codec_name':'hdmv_pgs_subtitle'}]})
    monkeypatch.setattr(subtitles,'convert',lambda *a:SRT)
    subtitles.SubtitleWorker().run_once()
    old=subtitles.saved(get_row()['id']);tracks=json.loads(old['tracks'])
    assert len(tracks)==1 and tracks[0]['kind']=='forced'
    assert old['state']=='configuration_required'
    assert (root/'Film.mkv').read_bytes()==b'test'

@pytest.mark.parametrize('data',[b'',b'not subtitles',b'<html>error</html>',b'1\n00:00:01,000 --> 00:00:03,000\n\xff'])
def test_invalid_download_rejected(data):
    with pytest.raises((ValueError,UnicodeError)): subtitles.validate_srt(data)

def test_hash_small_and_known_contents(tmp_path):
    path=tmp_path/'video';path.write_bytes(b'\0'*131072)
    assert opensubtitles.movie_hash(path)=='0000000000020000'
    path.write_bytes(b'\0'*4096)
    assert opensubtitles.movie_hash(path) is None

def test_provider_selection_is_exact_language_full_dialogue(monkeypatch):
    monkeypatch.setattr(config,'SUBTITLE_PREFER_SDH',False)
    attrs={'moviehash_match':True,'language':'en','files':[{'file_id':1}]}
    result=lambda **kw:{'attributes':{**attrs,**kw}}
    assert opensubtitles.choose([result(moviehash_match=False),result(foreign_parts_only=True)],'en') is None
    assert opensubtitles.choose([result(language='es'),result(ai_translated=True)],'en') is None
    assert opensubtitles.choose([result(hearing_impaired=True),result(files=[{'file_id':2}])],'en')[5]==2

def test_anonymous_budget_persists_and_blocks(media):
    for i in range(5): assert opensubtitles.budget(reserve=True)[0]
    allowed,until=opensubtitles.budget()
    assert not allowed and until>0
    assert not opensubtitles.budget()[0]

def test_download_is_cached_and_not_repeated(media,monkeypatch):
    root,_=media;movie=root/'Film.mp4';movie.write_bytes(b'\0'*131072);scan_library()
    monkeypatch.setattr(config,'OPENSUBTITLES_API_KEY','test-key-not-real')
    search={'data':[{'attributes':{'moviehash_match':True,'language':'en','files':[{'file_id':123}]}}]}
    calls=[]
    def api(path,body=None):
        calls.append(path)
        return search if path.startswith('/subtitles?') else {'link':'https://dl.opensubtitles.com/file','remaining':4}
    monkeypatch.setattr(opensubtitles,'api',api)
    monkeypatch.setattr(opensubtitles,'fetch_file',lambda url:SRT)
    worker=subtitles.SubtitleWorker();worker.run_once();worker.run_once()
    old=subtitles.saved(get_row()['id'])
    assert old['state']=='ready'
    assert json.loads(old['tracks'])[0]['provider_file_id']==123
    assert sum(p=='/download' for p in calls)==1

def test_uncertain_match_does_not_spend_download(media,monkeypatch):
    root,_=media;(root/'Film.mp4').write_bytes(b'\0'*131072);scan_library()
    monkeypatch.setattr(config,'OPENSUBTITLES_API_KEY','test-key-not-real')
    api=Mock(return_value={'data':[{'attributes':{'language':'en','moviehash_match':False}}]})
    monkeypatch.setattr(opensubtitles,'api',api)
    subtitles.SubtitleWorker().run_once()
    assert subtitles.saved(get_row()['id'])['state']=='needs_review'
    assert api.call_count==1
    assert opensubtitles.budget()[0]

def test_provider_outage_preserves_forced_track(media,monkeypatch):
    root,_=media;movie=root/'Film.mp4';movie.write_bytes(b'\0'*131072)
    (root/'Film.en.forced.srt').write_bytes(SRT);scan_library()
    monkeypatch.setattr(config,'OPENSUBTITLES_API_KEY','test-key-not-real')
    def fail(*a): raise opensubtitles.ProviderError('rate_wait',60)
    monkeypatch.setattr(opensubtitles,'api',fail)
    subtitles.SubtitleWorker().run_once()
    old=subtitles.saved(get_row()['id'])
    assert old['state']=='rate_wait' and len(json.loads(old['tracks']))==1
    assert not opensubtitles.budget()[0]


def test_real_ffmpeg_embedded_extraction(media):
    import subprocess
    from app.media_tools import binary
    root,client=media
    executable=binary('ffmpeg')
    if not executable: pytest.skip('FFmpeg unavailable')
    source=root/'input.srt';source.write_bytes(SRT)
    movie=root/'Embedded.mkv'
    subprocess.run([executable,'-v','error','-y','-f','lavfi','-i','color=c=black:s=160x90:r=10:d=4',
        '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-i',str(source),'-map','0:v','-map','1:a','-map','2:s',
        '-t','4','-c:v','libx264','-c:a','aac','-c:s','srt','-metadata:s:s:0','language=eng',str(movie)],
        check=True,capture_output=True,timeout=30)
    scan_library()
    # Undo the fixture's fake probe only for this real extraction exercise.
    from app.media_tools import inspect_media
    old=subtitles.inspect_media
    subtitles.inspect_media=inspect_media
    try: subtitles.SubtitleWorker().run_once()
    finally: subtitles.inspect_media=old
    data=client.get(f'/api/movies/{get_row()["id"]}/subtitles').json()
    assert len(data['tracks'])==1 and data['tracks'][0]['source']=='embedded'
    assert b'Hello world' in client.get(data['tracks'][0]['url']).content


def test_release_fallback_and_hash_priority(monkeypatch):
    monkeypatch.setattr(config,'SUBTITLE_PREFER_SDH',False)
    def result(hash_match,release,file_id):
        return {'attributes':{'language':'en','moviehash_match':hash_match,'release':release,'files':[{'file_id':file_id}]}}
    path=Path('Show.S01E02.1080p.WEB-GROUP.mkv')
    assert opensubtitles.choose([result(False,'Different Cut',1)],'en',path) is None
    assert opensubtitles.choose([result(False,'Show.S01E02.1080p.WEB-GROUP',1)],'en',path)[0] is False
    assert opensubtitles.choose([result(False,path.stem,1),result(True,'Other release',2)],'en',path)[5]==2


def test_sync_quality_failure_is_not_published(media,monkeypatch):
    root,_=media;movie=root/'Film.mp4';movie.write_bytes(b'\0'*131072);scan_library()
    monkeypatch.setattr(config,'OPENSUBTITLES_API_KEY','test-key-not-real')
    def api(path,body=None):
        if path.startswith('/subtitles?'):
            return {'data':[{'attributes':{'language':'en','release':'Film','files':[{'file_id':5}]}}]}
        return {'link':'https://dl.opensubtitles.com/test'}
    monkeypatch.setattr(opensubtitles,'api',api)
    monkeypatch.setattr(opensubtitles,'fetch_file',lambda url:SRT)
    from app import subtitle_sync
    def fail(*a): raise RuntimeError('Low quality')
    monkeypatch.setattr(subtitle_sync,'synchronize',fail)
    subtitles.SubtitleWorker().run_once()
    old=subtitles.saved(get_row()['id'])
    assert old['state']=='needs_review' and json.loads(old['tracks'])==[]


def test_real_sync_corrects_offset_without_losing_dialogue(media):
    import random
    import srt
    from datetime import timedelta
    from app.subtitle_sync import synchronize
    root,_=media
    randomizer=random.Random(17)
    cues=[];now=10
    for index in range(100):
        now+=randomizer.uniform(1,5);end=now+randomizer.uniform(.5,3)
        cues.append(srt.Subtitle(index+1,timedelta(seconds=now),timedelta(seconds=end),'This is spoken dialogue.'))
        now=end
    reference=root/'reference.srt';reference.write_text(srt.compose(cues))
    shifted=srt.compose([srt.Subtitle(c.index,c.start+timedelta(seconds=2),c.end+timedelta(seconds=2),c.content) for c in cues])
    output=synchronize(reference,'sync-fixture',shifted.encode())
    result=list(srt.parse(output.decode()))
    assert len(result)==100
    assert abs((result[0].start-cues[0].start).total_seconds())<.02
    assert abs((result[-1].start-cues[-1].start).total_seconds())<.02
    assert (subtitles.root()/'sync-fixture.original.srt').is_file()


def test_sync_rejects_excessive_cue_loss(media,monkeypatch):
    from app import subtitle_sync
    original=SRT+b'\n2\n00:00:05,000 --> 00:00:07,000\nAnother line\n'
    def fake_run(command,**kwargs):
        output=Path(command[command.index('-o')+1]);output.write_bytes(SRT)
        return Mock(stdout='{"sync_was_successful":true}')
    monkeypatch.setattr(subtitle_sync.subprocess,'run',fake_run)
    with pytest.raises(RuntimeError,match='discarded'):
        subtitle_sync.synchronize(media[0]/'video','loss-check',original)


def test_browse_indicator_counts_only_ready_captions(media):
    root,client=media
    (root/'Show.S01E01.mp4').write_bytes(b'test')
    (root/'Show.S01E02.mp4').write_bytes(b'test')
    (root/'Show.S01E01.en.srt').write_bytes(SRT)
    (root/'Show.S01E02.en.forced.srt').write_bytes(SRT)
    (root/'Movie.mp4').write_bytes(b'test')
    scan_library();subtitles.SubtitleWorker().run_once()
    catalog=client.get('/api/library/browse').json()
    show=next(i for i in catalog if i['kind']=='show')
    assert show['subtitle_summary']=={'episode_total':2,'episodes_available':2,'episodes_full':1,'episodes_forced_only':1,'episodes_converting':0,'episodes_with_embedded_images':0}
    first,second=show['seasons'][0]['episodes']
    assert first['subtitle_summary']['has_full']
    assert second['subtitle_summary']['has_forced'] and not second['subtitle_summary']['has_full']
    movie=next(i for i in catalog if i['kind']=='movie')
    assert movie['subtitle_summary']['count']==0
    assert movie['subtitle_summary']['state']=='configuration_required'
    # A missing managed asset must never advertise available subtitles.
    old=subtitles.saved(first['id'])
    (subtitles.root()/(json.loads(old['tracks'])[0]['id']+'.srt')).unlink()
    show=next(i for i in client.get('/api/library/browse').json() if i['kind']=='show')
    assert show['subtitle_summary']['episodes_full']==0
    assert show['subtitle_summary']['episodes_available']==1


def test_indicator_prefers_full_dialogue_languages_over_forced():
    from app.subtitle_summary import summarize
    summary=summarize([{'kind':'forced','language':'eng'},{'kind':'regular','language':'spa'}],'quota_wait')
    assert summary['languages']==['spa']
    assert summary['has_full'] and summary['has_forced']
