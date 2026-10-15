"""Household progress with session ordering; clients never supply wall-clock authority."""
import json, math, secrets, time, hashlib
from datetime import datetime, timezone
from .database import connection

TERMINAL = {'finished','stopped','error','cancelled','next'}

def signature(row):
    r=dict(row)
    return hashlib.sha256(f"{r.get('file_path')}:{r.get('file_size')}:{r.get('modification_time')}".encode()).hexdigest()

def initialize():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS history_migrations (name TEXT PRIMARY KEY)')
        db.execute('''CREATE TABLE IF NOT EXISTS watch_history (
            movie_id INTEGER PRIMARY KEY, position REAL NOT NULL, duration REAL NOT NULL,
            completed INTEGER NOT NULL, updated_at TEXT NOT NULL, signature TEXT NOT NULL,
            owner_version INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS playback_sessions (
            version INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            movie_id INTEGER NOT NULL, client_id TEXT NOT NULL, client_type TEXT NOT NULL,
            intent TEXT NOT NULL, signature TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'requested',
            sequence INTEGER NOT NULL DEFAULT -1, position REAL NOT NULL DEFAULT 0,
            duration REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL,
            ended INTEGER NOT NULL DEFAULT 0, delivery TEXT, reason TEXT,
            preparation_seconds REAL, first_play_seconds REAL, buffering_seconds REAL NOT NULL DEFAULT 0,
            buffering_since REAL, activated INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS playback_events (
            session_id TEXT NOT NULL, sequence INTEGER NOT NULL, event TEXT NOT NULL,
            received_at REAL NOT NULL, position REAL NOT NULL, PRIMARY KEY(session_id,sequence))''')
        if not db.execute("SELECT 1 FROM history_migrations WHERE name='cast-v1'").fetchone():
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='cast_history'").fetchone():
                for r in db.execute('SELECT h.*,m.file_path,m.file_size,m.modification_time FROM cast_history h JOIN movies m ON m.id=h.movie_id').fetchall():
                    db.execute('INSERT OR IGNORE INTO watch_history VALUES(?,?,?,?,?,?,0)',(r['movie_id'],r['position'],r['duration'],r['completed'],r['updated_at'],signature(r)))
            db.execute("INSERT INTO history_migrations VALUES('cast-v1')")

def history():
    with connection() as db:
        rows=db.execute('SELECT h.*,m.file_path,m.file_size,m.modification_time FROM watch_history h JOIN movies m ON m.id=h.movie_id WHERE m.available=1 ORDER BY h.updated_at DESC').fetchall()
    result=[]
    for r in rows:
        item={k:r[k] for k in ('movie_id','position','duration','completed','updated_at')}
        item['resume_valid']=r['signature']==signature(r)
        if not item['resume_valid']:item['position']=0
        result.append(item)
    return result

def create(row, client_id, client_type, intent='resume'):
    r=dict(row);now=time.time();sig=signature(r);sid=secrets.token_hex(16)
    with connection() as db:
        h=db.execute('SELECT * FROM watch_history WHERE movie_id=?',(r['id'],)).fetchone()
        resume=float(h['position']) if h and h['signature']==sig and not h['completed'] and intent=='resume' and h['position']>15 and h['position']<h['duration']-30 else 0
        db.execute('INSERT INTO playback_sessions(id,movie_id,client_id,client_type,intent,signature,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(sid,r['id'],client_id,client_type,intent,sig,now,now))
    prune()
    return {'session_id':sid,'resume_position':resume}

def ending_start(row, duration, credits_start=None):
    """Use the same movie credits / episode ending windows as the next-title UI."""
    from pathlib import Path
    from . import config
    from .catalog import episode_identity, grouping_hint
    path = Path(row['file_path'])
    try: folders = path.parent.relative_to(config.MOVIES_DIR).parts
    except ValueError: folders = ()
    episode = episode_identity(path.name, folders) or grouping_hint(path.name, folders)
    if not episode and credits_start is not None and math.isfinite(credits_start) and 0 < credits_start < duration:
        return credits_start
    return duration - 30 if duration > 30 else None

def record(sid, sequence, position, duration, state, event=None, *, credits_start=None):
    if not all(math.isfinite(x) and x>=0 for x in (position,duration)):raise ValueError('Invalid progress')
    now=time.time();event=event or state
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        s=db.execute('SELECT * FROM playback_sessions WHERE id=?',(sid,)).fetchone()
        if not s:raise KeyError('Session expired')
        if s['ended'] or sequence<=s['sequence']:return {'accepted':False}
        if now-s['updated_at']>86400:return {'accepted':False}
        row=db.execute('SELECT * FROM movies WHERE id=? AND available=1',(s['movie_id'],)).fetchone()
        if not row or signature(row)!=s['signature']:return {'accepted':False}
        duration=min(duration,float(row['duration'] or duration))
        position=min(position,duration) if duration else 0
        activated=bool(s['activated']) or state in {'playing','paused'}
        buffering_since=s['buffering_since'];buffering=s['buffering_seconds']
        if state=='buffering' and buffering_since is None:buffering_since=now
        elif state!='buffering' and buffering_since is not None:buffering+=now-buffering_since;buffering_since=None
        first=s['first_play_seconds']
        if state=='playing' and first is None:first=now-s['created_at']
        ended=state in TERMINAL
        db.execute('UPDATE playback_sessions SET sequence=?,position=?,duration=?,state=?,updated_at=?,ended=?,activated=?,first_play_seconds=?,buffering_since=?,buffering_seconds=? WHERE id=?',(sequence,position,duration,state,now,int(ended),int(activated),first,buffering_since,buffering,sid))
        db.execute('INSERT INTO playback_events VALUES(?,?,?,?,?)',(sid,sequence,event,now,position))
        db.execute('DELETE FROM playback_events WHERE session_id=? AND sequence NOT IN (SELECT sequence FROM playback_events WHERE session_id=? ORDER BY sequence DESC LIMIT 200)',(sid,sid))
        completed=False
        written=False
        if activated and duration>0:
            ending=ending_start(row,duration,credits_start)
            completed=state=='finished' or (state in {'stopped','next'} and ending is not None and position>=ending)
            if completed:position=duration
            # Every newer registered session that has actually started wins over an older one.
            latest=db.execute('SELECT MAX(version) FROM playback_sessions WHERE movie_id=? AND activated=1',(s['movie_id'],)).fetchone()[0]
            if latest==s['version']:
                written=True
                db.execute('''INSERT INTO watch_history VALUES(?,?,?,?,?,?,?) ON CONFLICT(movie_id) DO UPDATE SET
                    position=excluded.position,duration=excluded.duration,completed=excluded.completed,
                    updated_at=excluded.updated_at,signature=excluded.signature,owner_version=excluded.owner_version
                    WHERE excluded.owner_version>=watch_history.owner_version''',(s['movie_id'],position,duration,int(completed),datetime.now(timezone.utc).isoformat(),s['signature'],s['version']))
    return {'accepted':True,'completed':bool(completed and written)}

def delivery(sid, plan, preparation_seconds=None):
    with connection() as db:
        db.execute('UPDATE playback_sessions SET delivery=?,reason=?,preparation_seconds=? WHERE id=?',(plan['delivery'],plan['reason'],preparation_seconds,sid))

def prune():
    with connection() as db:
        db.execute("UPDATE playback_sessions SET ended=1,state='expired' WHERE ended=0 AND updated_at<?",(time.time()-86400,))
        db.execute('DELETE FROM playback_sessions WHERE ended=1 AND (updated_at<? OR id NOT IN (SELECT id FROM playback_sessions ORDER BY updated_at DESC LIMIT 1000))',(time.time()-7*86400,))
        db.execute('DELETE FROM playback_events WHERE session_id NOT IN (SELECT id FROM playback_sessions)')

def decorate(catalog):
    h={r['movie_id']:r for r in history()}
    for item in catalog:
        children=[e for s in item.get('seasons',[]) for e in s['episodes']] if item.get('kind')=='show' else [item]
        for e in children:
            r=h.get(e['id'],{})
            e.update(resume_position=r.get('position',0) if not r.get('completed') else 0,completed=bool(r.get('completed') and r.get('resume_valid')),history_updated_at=r.get('updated_at',''))
        if item.get('kind')=='show':
            episodes=sorted((e for e in children if e.get('season_number',0)>0),
                key=lambda e:(e['season_number'],e.get('episode_number',0),e['id']))
            watched=[e for e in episodes if h.get(e['id'],{}).get('resume_valid')
                and (e['completed'] or e['resume_position']>15)]
            if watched:
                latest=max(watched,key=lambda e:e['history_updated_at'])
                target=None
                if not latest['completed']:
                    target=latest
                else:
                    following=episodes[episodes.index(latest)+1:]
                    target=next((e for e in following if not e['completed']),None)
                    # Revisit gaps only after reaching the end of the available series.
                    if target is None:
                        target=next((e for e in episodes if not e['completed']),None)
                if target is not None:
                    item.update(resume_episode=target,resume_position=target['resume_position'],
                        duration=target.get('duration'),history_updated_at=latest['history_updated_at'],
                        continue_watching=True)
    return catalog
