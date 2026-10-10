"""Automatic local OCR, language selection, migration and source-timing regressions."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app import config, subtitles, subtitle_ocr
from app.database import connection
from app.scanner import scan_library
from test_subtitles import media, get_row, SRT


def dvd(index=2, language='eng', forced=False):
    return dict(index=index,codec_type='subtitle',codec_name='dvd_subtitle',
                tags={'language':language},disposition={'forced':forced})


def test_automatic_dvd_conversion_bypasses_quota_and_is_cached(media,monkeypatch):
    folder,client=media;path=folder/'Series.S01E01.mkv';path.write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd(),dvd(3,'spa')]})
    conversion=Mock(return_value=SRT);monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    monkeypatch.setattr(config,'SUBTITLE_LANGUAGES',['en'])
    worker=subtitles.SubtitleWorker();worker.run_once();worker.run_once()
    row=get_row();saved=subtitles.saved(row['id'])
    assert saved['state']=='ready' and conversion.call_count==1
    assert saved['local_revision']==subtitles.local_revision()
    assert len(json.loads(saved['embedded']))==2
    data=client.get(f'/api/movies/{row["id"]}/subtitles').json()
    assert data['tracks'][0]['source']=='embedded_ocr'
    assert client.get(data['tracks'][0]['url']).content==SRT
    assert client.get(data['tracks'][0]['url'][:-4]+'.vtt').status_code==200
    with connection() as db:assert db.execute('SELECT count(*) FROM subtitle_provider_budget').fetchone()[0]==0
    assert path.read_bytes()==b'test'


def test_existing_text_track_is_retained_without_ocr(media,monkeypatch):
    folder,_=media;(folder/'Film.mkv').write_bytes(b'test');(folder/'Film.en.srt').write_bytes(SRT);scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd()]})
    conversion=Mock();monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    subtitles.SubtitleWorker().run_once()
    assert subtitles.saved(get_row()['id'])['state']=='ready'
    conversion.assert_not_called()


def test_old_quota_wait_jobs_convert_after_feature_upgrade(media,monkeypatch):
    folder,_=media;path=folder/'Film.mkv';path.write_bytes(b'test');scan_library();row=get_row()
    subtitles.store(row['id'],subtitles.signature(path,[]),[],'quota_wait','quota',9999999999)
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd()]})
    conversion=Mock(return_value=SRT);monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    subtitles.SubtitleWorker().run_once()
    assert subtitles.saved(row['id'])['state']=='ready' and conversion.call_count==1


def test_language_change_adds_track_without_reconverting_english(media,monkeypatch):
    folder,_=media;(folder/'Film.mkv').write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd(),dvd(3,'spa')]})
    conversion=Mock(return_value=SRT);monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    monkeypatch.setattr(config,'SUBTITLE_LANGUAGES',['en']);worker=subtitles.SubtitleWorker();worker.run_once()
    monkeypatch.setattr(config,'SUBTITLE_LANGUAGES',['en','es']);worker.run_once()
    assert conversion.call_count==2
    assert {t['language'] for t in json.loads(subtitles.saved(get_row()['id'])['tracks'])}=={'eng','spa'}


def test_shutdown_does_not_publish_incomplete_conversion(media,monkeypatch):
    folder,_=media;(folder/'Film.mkv').write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd()]})
    monkeypatch.setattr(subtitle_ocr,'convert',Mock(side_effect=InterruptedError('cancelled')))
    subtitles.SubtitleWorker().run_once()
    old=subtitles.saved(get_row()['id'])
    assert json.loads(old['tracks'])==[] and old['local_revision']==''


def test_missing_ocr_asset_is_rebuilt(media,monkeypatch):
    folder,_=media;(folder/'Film.mkv').write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd()]})
    conversion=Mock(return_value=SRT);monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    worker=subtitles.SubtitleWorker();worker.run_once()
    track=json.loads(subtitles.saved(get_row()['id'])['tracks'])[0]
    (subtitles.root()/(track['id']+'.srt')).unlink();worker.run_once()
    assert conversion.call_count==2


def test_native_decoder_and_whole_line_ocr(tmp_path):
    import av
    import numpy as np
    from PIL import Image,ImageDraw,ImageFont
    assert av.CodecContext.create('dvdsub','r')
    image=Image.new('L',(480,50));draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(str(Path(__file__).resolve().parents[2]/'roku/fonts/DejaVuSans.ttf'),26)
    draw.text((8,5),'Hello from Gravyflix',font=font,fill=2,stroke_width=1,stroke_fill=1)
    pixels=np.asarray(image);rectangle=SimpleNamespace(type=b'bitmap',width=480,height=50,planes=[pixels.tobytes()])
    text,score=subtitle_ocr.Reader().read(rectangle)
    assert 'Hello' in text and 'Gravyflix' in text and score>.75


def test_source_timing_uses_microseconds_and_display_offsets():
    from fractions import Fraction
    packet=SimpleNamespace(pts=59059,time_base=Fraction(1,1000),duration=2526)
    subset=SimpleNamespace(pts=59059000,start_display_time=20,end_display_time=2525)
    assert subtitle_ocr.timing(subset,packet)==pytest.approx((59.079,61.584))
    subset.end_display_time=20
    assert subtitle_ocr.timing(subset,packet)==pytest.approx((59.079,61.585))
    subset.pts=-(2**63)
    assert subtitle_ocr.timing(subset,packet,origin=.1)==pytest.approx((58.979,61.485))


def test_invalid_timing_and_bitmap_bounds_rejected():
    import numpy as np
    packet=SimpleNamespace(pts=1,time_base=1,duration=0)
    with pytest.raises(ValueError):subtitle_ocr.timing(SimpleNamespace(pts=0,start_display_time=0,end_display_time=0),packet)
    with pytest.raises(ValueError):subtitle_ocr.line_crops(np.zeros((2,2,2),dtype=np.uint8))


def test_additive_migration_preserves_old_jobs(tmp_path,monkeypatch):
    import sqlite3
    monkeypatch.setattr(config,'DATABASE_PATH',tmp_path/'old.db')
    with sqlite3.connect(config.DATABASE_PATH) as db:
        db.execute("CREATE TABLE subtitle_jobs (movie_id INTEGER PRIMARY KEY,signature TEXT,tracks TEXT,state TEXT,note TEXT,retry_at REAL)")
        db.execute("INSERT INTO subtitle_jobs VALUES(1,'same','[]','quota_wait','waiting',0)")
    subtitles.initialize()
    old=subtitles.saved(1)
    assert old['signature']=='same' and old['state']=='quota_wait' and old['local_revision']==''


@pytest.mark.parametrize('confidence,accepted', [(0.99,True),(0.4,False)])
def test_conversion_quality_gate_preserves_timing_and_rejects_bad_output(tmp_path,monkeypatch,confidence,accepted):
    import av
    from fractions import Fraction
    path=tmp_path/'source.mkv';path.write_bytes(b'unchanged original')
    class Subset(list):
        pts=1000000;start_display_time=100;end_display_time=2200
    subset=Subset([SimpleNamespace(y=0,x=0)])
    codec=SimpleNamespace(name='dvdsub',decode2=lambda packet:subset)
    packet=SimpleNamespace(pts=1000,time_base=Fraction(1,1000),duration=2200,size=50)
    class Container:
        start_time=0;streams=[SimpleNamespace(type='subtitle',codec_context=codec)]
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def demux(self,stream):return iter([packet,packet])
    monkeypatch.setattr(av,'open',lambda path:Container())
    monkeypatch.setattr(subtitle_ocr,'Reader',lambda:SimpleNamespace(read=lambda r:('Hello from local subtitles',confidence)))
    monkeypatch.setattr(subtitle_ocr.os,'nice',lambda value:None)
    output=tmp_path/'result.srt';report=tmp_path/'report.json'
    if accepted:
        subtitle_ocr.convert_file(path,0,output,report)
        assert '00:00:01,100 --> 00:00:03,200' in output.read_text()
    else:
        with pytest.raises(ValueError,match='needs review'):subtitle_ocr.convert_file(path,0,output,report)
        assert not output.exists()
    assert json.loads(report.read_text())['cues']==2
    assert path.read_bytes()==b'unchanged original'


def test_converter_upgrade_refreshes_only_generated_ocr_tracks(media,monkeypatch):
    folder,_=media;(folder/'Film.mkv').write_bytes(b'test');scan_library()
    monkeypatch.setattr(subtitles,'inspect_media',lambda path:{'streams':[dvd()]})
    conversion=Mock(return_value=SRT);monkeypatch.setattr(subtitle_ocr,'convert',conversion)
    worker=subtitles.SubtitleWorker();worker.run_once()
    old=json.loads(subtitles.saved(get_row()['id'])['tracks'])[0]['id']
    monkeypatch.setattr(subtitles,'LOCAL_VERSION',2);worker.run_once()
    new=json.loads(subtitles.saved(get_row()['id'])['tracks'])[0]['id']
    assert conversion.call_count==2 and old != new
