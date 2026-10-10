"""Background intro analysis, persistent per-file markers and manual corrections."""
import hashlib
import json
import logging
import math
from pathlib import Path
import struct
import subprocess
import threading
import time
from . import config
from .database import connection
from .media_tools import binary
from .intro_detection import VERSION, chapter_marker, pair_match, consensus
log = logging.getLogger('media')


def initialize():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS intro_markers (
            movie_id INTEGER PRIMARY KEY, signature TEXT NOT NULL, scope TEXT NOT NULL,
            state TEXT NOT NULL, marker TEXT, note TEXT NOT NULL, updated_at REAL NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS intro_fingerprints (
            signature TEXT PRIMARY KEY, data BLOB NOT NULL)''')


def checked(row):
    path = Path(row['file_path']).resolve()
    if not path.is_relative_to(config.MOVIES_DIR.resolve()) or not path.is_file():
        raise ValueError('Media file unavailable')
    stat = path.stat()
    if stat.st_size != row['file_size'] or stat.st_mtime_ns != row['modification_time']:
        raise ValueError('Media changed; rescan the library')
    return path


def signature(row):
    checked(row)
    return hashlib.sha256(f"{VERSION}:{row['file_path']}:{row['file_size']}:{row['modification_time']}".encode()).hexdigest()


def available(row):
    try: sig = signature(row)
    except (ValueError, OSError): return {'state':'pending', 'intro':None, 'note':'Media changed or unavailable'}
    with connection() as db: item = db.execute('SELECT * FROM intro_markers WHERE movie_id=?', (row['id'],)).fetchone()
    if not item or item['signature'] != sig:
        return {'state':'pending', 'intro':None, 'note':'Intro has not been analyzed yet'}
    return {'state':item['state'], 'intro':json.loads(item['marker']) if item['marker'] else None, 'note':item['note']}


def store(row, sig, scope, marker=None, state='no_match', note='No confident repeated opening found'):
    with connection() as db:
        db.execute('''INSERT INTO intro_markers VALUES(?,?,?,?,?,?,?) ON CONFLICT(movie_id) DO UPDATE SET
            signature=excluded.signature,scope=excluded.scope,state=excluded.state,marker=excluded.marker,
            note=excluded.note,updated_at=excluded.updated_at
            WHERE intro_markers.scope != 'manual' OR intro_markers.signature != excluded.signature OR excluded.scope = 'manual'
            ''',
            (row['id'],sig,scope,'ready' if marker else state,json.dumps(marker) if marker else None,note,time.time()))


def manual(row, start=None, end=None):
    sig = signature(row)
    marker = None
    if start is not None:
        duration = row['duration'] or 0
        if not all(map(math.isfinite,[start,end])) or not 0 <= start < end < duration:
            raise ValueError('Require 0 <= start < end < episode duration')
        marker = dict(start=start,end=end,confidence=1.0,method='manual',evidence=1)
    store(row,sig,'manual',marker,'disabled','User reviewed intro' if marker else 'Intro skipping disabled for this file')


class IntroWorker:
    def __init__(self):
        self.stop = threading.Event(); self.wake = threading.Event()
        self.thread = None; self.process = None; self.lock = threading.Lock()
    def start(self):
        if not config.AUTO_INTROS: return
        self.thread = threading.Thread(target=self.loop,name='intro-worker',daemon=True);self.thread.start()
    def request(self): self.wake.set()
    def close(self):
        self.stop.set();self.wake.set()
        with self.lock:
            if self.process and self.process.poll() is None: self.process.terminate()
        if self.thread:self.thread.join(timeout=5)
    def command(self,args):
        with self.lock:
            if self.stop.is_set():raise InterruptedError('Intro scan cancelled')
            self.process = subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            out,err = self.process.communicate(timeout=90)
            if self.process.returncode:raise RuntimeError(err.decode(errors='replace')[-400:])
            return out
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.communicate();raise RuntimeError('Intro audio extraction timed out')
        finally:
            with self.lock:self.process=None
    def fingerprint(self,row,sig):
        with connection() as db: cached=db.execute('SELECT data FROM intro_fingerprints WHERE signature=?',(sig,)).fetchone()
        if cached:return list(struct.unpack('<'+'I'*(len(cached['data'])//4),cached['data']))
        executable=binary('ffmpeg')
        if not executable:raise RuntimeError('FFmpeg unavailable')
        out=self.command([executable,'-v','error','-nostdin','-threads','1','-i',str(checked(row)),
            '-t',str(min(600,(row['duration'] or 1500)*.4)),'-map','0:a:0','-vn','-ac','1','-ar','11025',
            '-f','chromaprint','-algorithm','1','-fp_format','raw','pipe:1'])
        if len(out)%4 or len(out)>100000:raise ValueError('Invalid audio fingerprint')
        with connection() as db:db.execute('INSERT OR REPLACE INTO intro_fingerprints VALUES(?,?)',(sig,out))
        return list(struct.unpack('<'+'I'*(len(out)//4),out))
    def chapters(self,row):
        executable=binary('ffprobe')
        if not executable:return None
        result=self.command([executable,'-v','error','-show_chapters','-of','json',str(checked(row))])
        return chapter_marker(json.loads(result).get('chapters',[]),row['duration'] or 0)
    def run_once(self, show=None):
        from .models import movie_response
        from .catalog import build_catalog
        initialize()
        with connection() as db:rows=[dict(r) for r in db.execute('SELECT * FROM movies WHERE available=1')]
        by_id={r['id']:r for r in rows}
        catalog=build_catalog([movie_response(r,'http://localhost').model_dump() for r in rows])
        counts={'ready':0,'no_match':0,'pending':0,'errors':0}
        for series in catalog:
            if series['kind']!='show' or (show and series['title'].casefold()!=show.casefold()):continue
            for season in series['seasons']:
                if season['number']<=0:continue
                episodes=[e for e in season['episodes'] if e.get('duration') and e['duration']>=120]
                valid=[]
                for episode in episodes:
                    row=by_id[episode['id']]
                    try:valid.append((episode,row,signature(row)))
                    except (ValueError,OSError):continue
                scope=hashlib.sha256(json.dumps([(e['episode_number'],e.get('episode_end'),sig) for e,r,sig in valid]).encode()).hexdigest()
                identities={}; fingerprints={}
                for e,r,sig in valid:
                    identities.setdefault((e['episode_number'],e.get('episode_end')),(e,r,sig))
                refs=list(identities.values())[:8]
                for ep,row,sig in valid:
                    if self.stop.is_set():return counts
                    with connection() as db:old=db.execute('SELECT * FROM intro_markers WHERE movie_id=?',(row['id'],)).fetchone()
                    if old and old['signature']==sig and (old['scope']=='manual' or (old['scope']==scope and old['state']!='error')):continue
                    try:
                        marker=self.chapters(row)
                        if not marker and len(identities)>=3:
                            if sig not in fingerprints:fingerprints[sig]=self.fingerprint(row,sig)
                            matches=[]
                            for other,other_row,other_sig in refs:
                                identity=(other['episode_number'],other.get('episode_end'))
                                if identity==(ep['episode_number'],ep.get('episode_end')):continue
                                if other_sig not in fingerprints:fingerprints[other_sig]=self.fingerprint(other_row,other_sig)
                                matches.append((identity,pair_match(fingerprints[sig],fingerprints[other_sig])))
                            marker=consensus(matches)
                        # Do not publish a marker for a source changed during extraction.
                        if signature(row)!=sig:continue
                        state='pending' if len(identities)<3 and not marker else 'no_match'
                        note='Intro detected' if marker else 'Need three distinct episodes in this season' if state=='pending' else 'No confident repeated opening found'
                        store(row,sig,scope,marker,state,note)
                        counts['ready' if marker else state]+=1
                        log.info('INTRO: %s / %s: %s %s',series['title'],ep['title'],note,marker or '')
                    except InterruptedError:return counts
                    except Exception as exc:
                        counts['errors']+=1;store(row,sig,scope,state='error',note=str(exc)[:400]);log.warning('INTRO: %s: %s',row['filename'],exc)
        return counts
    def loop(self):
        # Keep initial startup/API responsiveness ahead of media analysis.
        if self.stop.wait(10):return
        while not self.stop.is_set():
            try:self.run_once()
            except Exception:log.exception('INTRO: Analysis pass failed')
            self.wake.wait(config.AUTO_LIBRARY_SCAN_SECONDS);self.wake.clear()
