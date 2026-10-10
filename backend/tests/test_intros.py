import math
import random
import struct
import subprocess
import wave
from pathlib import Path
import pytest
from test_library import library, client
from app import intros
from app.intro_detection import pair_match, consensus, chapter_marker, STEP, DELAY
from app.database import connection
from app.scanner import scan_library
from app.media_tools import binary


def samples(seed,n=1600):
    r=random.Random(seed)
    return [r.getrandbits(32) for _ in range(n)]


def test_audio_alignment_with_shift_and_small_encoding_difference():
    a=samples(1);b=samples(2)
    b[350:650]=[x ^ 3 for x in a[100:400]]
    candidates=pair_match(a,b)
    assert len(candidates)==1
    assert abs(candidates[0]['start']-(100*STEP+DELAY/2))<1
    assert abs(candidates[0]['end']-(400*STEP+DELAY/2))<1
    assert candidates[0]['confidence']>.9


def test_unrelated_audio_silence_and_short_logos_rejected():
    assert pair_match(samples(1),samples(2))==[]
    assert pair_match([123]*1600,[123]*1600)==[]
    a=samples(3);b=samples(4);b[200:240]=a[50:90]
    assert pair_match(a,b)==[]


def test_consensus_requires_independent_episodes_and_rejects_ambiguous_passages():
    x={'start':35,'end':65,'confidence':.96}
    y={'start':35.5,'end':64.5,'confidence':.97}
    assert consensus([('ep1',[x])]) is None
    assert consensus([('ep1',[x]),('ep1',[y])]) is None
    marker=consensus([('ep1',[x]),('ep2',[y])])
    assert marker['evidence']==3 and marker['end']==64.5
    other={'start':100,'end':125,'confidence':.97}
    assert consensus([('ep1',[x,other]),('ep2',[y,other])]) is None


def test_chapter_labels_and_bad_bounds():
    chapter=lambda title,start,end:{'tags':{'title':title},'start_time':str(start),'end_time':str(end)}
    assert chapter_marker([chapter('Opening Credits',20,50)],100)['end']==50
    for c in [chapter('Chapter 1',20,50),chapter('Recap',0,40),chapter('Intro',20,120),chapter('Intro',math.nan,50),chapter('Intro',-1,20)]:
        assert chapter_marker([c],100) is None


def episode_row(library,filename='Show.S01E01.mp4'):
    path=library/filename;path.write_bytes(b'video');scan_library()
    with connection() as db:
        db.execute('UPDATE movies SET duration=300')
        return dict(db.execute('SELECT * FROM movies WHERE filename=?',(filename,)).fetchone())


def test_intro_api_manual_marker_and_source_invalidation(client,library):
    row=episode_row(library)
    assert client.get(f'/api/movies/{row["id"]}/intro').json()['intro'] is None
    intros.manual(row,20,50)
    result=client.get(f'/api/movies/{row["id"]}/intro').json()
    assert result['state']=='ready' and result['intro']['end']==50
    for start,end in [(-1,40),(50,20),(20,400),(math.nan,30)]:
        with pytest.raises(ValueError):intros.manual(row,start,end)
    Path(row['file_path']).write_bytes(b'replaced media')
    assert client.get(f'/api/movies/{row["id"]}/intro').json()['intro'] is None
    assert client.get('/api/movies/99999/intro').status_code==404


def test_worker_season_consensus_and_manual_preservation(client,library,monkeypatch):
    rows=[episode_row(library,f'Show.S01E0{i}.mp4') for i in range(1,4)]
    worker=intros.IntroWorker()
    monkeypatch.setattr(worker,'chapters',lambda row:None)
    theme=samples(8,250)
    def fake(row,sig):
        values=samples(row['id'],1600);offset=100+row['id']*40;values[offset:offset+250]=theme
        return values
    monkeypatch.setattr(worker,'fingerprint',fake)
    assert worker.run_once()['ready']==3
    assert all(intros.available(row)['intro']['evidence']==3 for row in rows)
    intros.manual(rows[0],5,30)
    worker.run_once()
    assert intros.available(rows[0])['intro']['method']=='manual'
    # An automatic scan already in flight must not overwrite a newer review.
    intros.store(rows[0],intros.signature(rows[0]),'auto',{'start':30,'end':80})
    assert intros.available(rows[0])['intro']['end']==30
    intros.manual(rows[1]);worker.run_once()
    assert intros.available(rows[1])['state']=='disabled'


def test_duplicate_encodes_do_not_count_as_three_episodes(client,library,monkeypatch):
    for name in ['Show.S01E01.mp4','Show.S01E01.other.mp4','Show.S01E02.mp4']:episode_row(library,name)
    worker=intros.IntroWorker();monkeypatch.setattr(worker,'chapters',lambda row:None)
    extract=__import__('unittest.mock',fromlist=['Mock']).Mock();monkeypatch.setattr(worker,'fingerprint',extract)
    assert worker.run_once()['pending']==3
    extract.assert_not_called()


def test_real_ffmpeg_fingerprints_find_theme_after_different_cold_opens(tmp_path,monkeypatch):
    executable=binary('ffmpeg')
    if not executable:pytest.skip('FFmpeg unavailable')
    np=pytest.importorskip('numpy')
    from app import config
    monkeypatch.setattr(config,'DATABASE_PATH',tmp_path/'db.sqlite3');monkeypatch.setattr(config,'MOVIES_DIR',tmp_path)
    intros.initialize();worker=intros.IntroWorker()
    rate=11025;n=rate*26;t=np.arange(n)/rate
    rng=np.random.default_rng(7)
    pitches=rng.choice([220,247,262,294,330,349,392,440,494,523,587],size=52)
    frequency=pitches[np.minimum((t*2).astype(int),51)]
    phase=np.cumsum(frequency)*2*np.pi/rate
    theme=.28*np.sin(phase)+.12*np.sin(phase*1.5)+.06*np.sin(phase*2)
    fingerprints=[]
    for index,prefix in enumerate([6,13,21]):
        def distinct_audio(length):
            time=np.arange(rate*length)/rate
            notes=rng.choice([165,185,208,233,277,311,370,415,466,554,622],size=length*3)
            phase=np.cumsum(notes[np.minimum((time*3).astype(int),len(notes)-1)])*2*np.pi/rate
            return .25*np.sin(phase)+.1*np.sin(phase*1.5)+rng.normal(0,.015,len(time))
        signal=np.concatenate([distinct_audio(prefix),theme,distinct_audio(12)])
        path=tmp_path/f'{index}.wav'
        with wave.open(str(path),'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes((signal*32767).astype('<i2').tobytes())
        stat=path.stat();row={'file_path':str(path),'file_size':stat.st_size,'modification_time':stat.st_mtime_ns,'duration':300}
        fingerprints.append(worker.fingerprint(row,intros.signature(row)))
    marker=consensus([('b',pair_match(fingerprints[0],fingerprints[1])),('c',pair_match(fingerprints[0],fingerprints[2]))])
    assert marker is not None
    assert abs(marker['start']-6)<4
    assert 29 <= marker['end'] <= 34
