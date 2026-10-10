"""Anonymous OpenSubtitles REST client; conservative exact-file matching only."""
import hashlib
import json
import struct
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from . import config
from .database import connection

BASE = 'https://api.opensubtitles.com/api/v1'

class ProviderError(Exception):
    def __init__(self, state, delay=3600):
        self.state, self.delay = state, delay

def movie_hash(path):
    size = path.stat().st_size
    if size < 131072: return None
    with path.open('rb') as file:
        head = file.read(65536)
        file.seek(-65536,2)
        tail = file.read(65536)
    value = (size + sum(struct.unpack('<8192Q',head)) + sum(struct.unpack('<8192Q',tail))) & 0xffffffffffffffff
    return f'{value:016x}'

def api(path, body=None):
    request = Request(BASE+path, data=json.dumps(body).encode() if body is not None else None,
        headers={'Api-Key':config.OPENSUBTITLES_API_KEY,'User-Agent':'GRAVYFLIX v0.2.15',
                 'Accept':'application/json','Content-Type':'application/json'})
    try:
        with urlopen(request, timeout=25) as response:
            data = response.read(2*1024*1024+1)
            if len(data)>2*1024*1024: raise ProviderError('failed')
            return json.loads(data)
    except HTTPError as exc:
        if exc.code == 429:
            try: delay = max(60,int(exc.headers.get('Retry-After','3600')))
            except ValueError: delay = 3600
            raise ProviderError('rate_wait',delay) from None
        if exc.code in {402,406}: raise ProviderError('quota_wait',86400) from None
        if exc.code in {401,403}: raise ProviderError('configuration_required',86400) from None
        raise ProviderError('failed') from None
    except (URLError,TimeoutError,ValueError,OSError): raise ProviderError('failed') from None

def budget(reserve=False, retry=None):
    day = datetime.now(timezone.utc).date().isoformat()
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO subtitle_provider_budget(day) VALUES(?)',(day,))
        # Respect cooldowns even across UTC midnight and restarts.
        until = db.execute('SELECT MAX(retry_at) FROM subtitle_provider_budget').fetchone()[0] or 0
        row = db.execute('SELECT attempts FROM subtitle_provider_budget WHERE day=?',(day,)).fetchone()
        if retry is not None:
            db.execute('UPDATE subtitle_provider_budget SET retry_at=? WHERE day=?',(retry,day))
        if until > time.time(): return False,until
        if row['attempts'] >= config.SUBTITLE_DAILY_DOWNLOAD_LIMIT:
            midnight = (int(time.time())//86400+1)*86400
            return False,midnight
        if reserve: db.execute('UPDATE subtitle_provider_budget SET attempts=attempts+1 WHERE day=?',(day,))
        return True,0

def normalized_release(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())

def choose(results, language, filename=None):
    candidates=[]
    for result in results:
        a=result.get('attributes',{})
        if a.get('language') != language: continue
        exact_hash = bool(a.get('moviehash_match'))
        exact_release = bool(filename and normalized_release(a.get('release','')) == normalized_release(filename.stem))
        if not exact_hash and not exact_release: continue
        if a.get('foreign_parts_only') or a.get('machine_translated') or a.get('ai_translated'): continue
        for f in a.get('files',[]):
            if isinstance(f.get('file_id'),int):
                candidates.append((exact_hash, bool(a.get('hearing_impaired')) == config.SUBTITLE_PREFER_SDH,
                    bool(a.get('from_trusted')),float(a.get('ratings') or 0),int(a.get('download_count') or 0),f['file_id'],a))
    return max(candidates,key=lambda x:x[:6]) if candidates else None

def fetch_file(url):
    # Provider redirects must remain on its own HTTPS domains; never attach the API key here.
    from .subtitles import MAX_SIZE
    def allowed(value):
        parsed=urlparse(value)
        return parsed.scheme=='https' and (parsed.hostname or '').endswith('.opensubtitles.com') and not parsed.username
    if not allowed(url): raise ProviderError('failed')
    from urllib.request import HTTPRedirectHandler, build_opener
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not allowed(newurl): raise ProviderError('failed')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    with build_opener(Redirects()).open(Request(url,headers={'User-Agent':'GRAVYFLIX v0.2.15'}),timeout=25) as response:
        data=response.read(MAX_SIZE+1)
    if len(data)>MAX_SIZE: raise ProviderError('failed')
    return data

def enrich(row,path,sig,tracks,stop):
    from .subtitles import LANGUAGES, publish, track
    languages=config.SUBTITLE_LANGUAGES
    missing=[lang for lang in languages if not any(t['language']==LANGUAGES.get(lang,lang) and t['kind']!='forced' for t in tracks)]
    if not missing: return tracks,'ready','',0
    if not config.OPENSUBTITLES_API_KEY:
        return tracks,'configuration_required','Local captions available; OpenSubtitles API key is not configured.',time.time()+3600
    allowed,retry=budget()
    if not allowed: return tracks,'quota_wait','Waiting for download allowance or provider cooldown.',retry
    value=movie_hash(path)
    if not value: return tracks,'no_match','File too small for provider hash matching.',time.time()+86400
    for language in missing:
        if stop.is_set(): return tracks,'pending','',time.time()+60
        allowed,retry=budget()
        if not allowed: return tracks,'quota_wait','Waiting for download allowance.',retry
        try:
            if stop.wait(1): return tracks,'pending','',time.time()+60
            params={'languages':language,'moviehash':value,'query':path.name}
            result=api('/subtitles?'+urlencode(sorted(params.items())))
            selected=choose(result.get('data',[]),language,path)
            if selected is None:
                return tracks,'needs_review' if result.get('data') else 'no_match','No verified exact-file subtitle match; nothing downloaded.',time.time()+86400
            budget(reserve=True) # Persist before the quota-consuming request; failures count conservatively.
            response=api('/download',{'file_id':selected[5],'sub_format':'srt'})
            data=fetch_file(response['link'])
            key=hashlib.sha256(f'{row["id"]}:{sig}:opensubtitles:{selected[5]}'.encode()).hexdigest()
            if not selected[0]:
                from .subtitle_sync import synchronize
                try: data = synchronize(path,key,data)
                except (RuntimeError, OSError):
                    return tracks,'needs_review','Release matched, but automatic synchronization was not trustworthy.',time.time()+86400
            publish(key,data)
            t=track(key,language,False,bool(selected[6].get('hearing_impaired')),'opensubtitles')
            t.update(provider_file_id=selected[5],match='file_hash' if selected[0] else 'release_synced')
            tracks.append(t)
            if response.get('remaining') == 0:
                try: until=datetime.fromisoformat(response['reset_time_utc'].replace('Z','+00:00')).timestamp()
                except (KeyError,ValueError): until=time.time()+86400
                budget(retry=until)
        except ProviderError as exc:
            until=time.time()+exc.delay
            if exc.state in {'quota_wait','rate_wait','configuration_required'}: budget(retry=until)
            return tracks,exc.state,'Provider request deferred; check configuration or quota.',until
        except (KeyError,ValueError,UnicodeError,OSError,URLError):
            return tracks,'failed','Downloaded subtitle could not be validated.',time.time()+3600
    return tracks,'ready','',0
