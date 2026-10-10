from app import credits, config
from app.database import connection
from app.main import get_movie
from test_credits import movies, client, library


def result(start=6500):
    return dict(start=start,confidence=.94,samples=20,note='Recognized credits',evidence={'roles':['directed by','music by']})


def test_legacy_no_match_upgraded_and_visual_result_cached(client,movies,monkeypatch):
    movie_id=movies['A Movie (2020).mkv'];row=get_movie(movie_id)
    credits.save(row,None,'chapter','No chapter')
    monkeypatch.setattr(config,'AUTO_VISUAL_CREDITS',True)
    worker=credits.CreditWorker();seen=[]
    monkeypatch.setattr(worker,'chapters',lambda path:[])
    monkeypatch.setattr(worker,'visual',lambda path,duration:seen.append(path.name) or result())
    assert worker.run_once()=={'checked':1,'found':1}
    marker=credits.available(row)
    assert marker['start']==6500 and marker['method']=='visual'
    assert marker['analysis_version']==credits.VISUAL_VERSION
    assert worker.run_once()=={'checked':0,'found':0}
    assert len(seen)==1


def test_visual_failure_backoff_and_negative_cache(client,movies,monkeypatch):
    row=get_movie(movies['A Movie (2020).mkv'])
    monkeypatch.setattr(config,'AUTO_VISUAL_CREDITS',True)
    worker=credits.CreditWorker();monkeypatch.setattr(worker,'chapters',lambda path:[])
    def fail(*args):raise RuntimeError('failed')
    monkeypatch.setattr(worker,'visual',fail)
    worker.run_once();marker=credits.available(row)
    assert marker['state']=='error' and marker['retry_at']>0
    assert worker.run_once()=={'checked':0,'found':0}
    with connection() as db:db.execute('UPDATE credit_markers SET retry_at=0')
    monkeypatch.setattr(worker,'visual',lambda *args:result(None))
    worker.run_once()
    assert credits.available(row)['state']=='no_match'
    assert worker.run_once()=={'checked':0,'found':0}


def test_manual_edit_while_visual_job_is_running_wins(client,movies,monkeypatch):
    row=get_movie(movies['A Movie (2020).mkv'])
    monkeypatch.setattr(config,'AUTO_VISUAL_CREDITS',True)
    worker=credits.CreditWorker();monkeypatch.setattr(worker,'chapters',lambda path:[])
    def visual(*args):
        credits.manual(row,6400)
        return result()
    monkeypatch.setattr(worker,'visual',visual)
    worker.run_once()
    assert credits.available(row)['start']==6400
    assert credits.available(row)['method']=='manual'


def test_conversion_priority_prevents_ocr_job(client,movies,monkeypatch):
    from app.roku_audio import cache
    from types import SimpleNamespace
    monkeypatch.setattr(config,'AUTO_VISUAL_CREDITS',True)
    previous=cache.jobs
    cache.jobs={'foreground':SimpleNamespace(state='preparing')}
    worker=credits.CreditWorker();monkeypatch.setattr(worker,'chapters',lambda path:[])
    monkeypatch.setattr(worker,'visual',lambda *args:(_ for _ in ()).throw(AssertionError('Must not start')))
    assert worker.run_once()=={'checked':0,'found':0}
    cache.jobs=previous
