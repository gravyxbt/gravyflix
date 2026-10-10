#!/usr/bin/env python3
"""Background/CLI import from public title pages; browsing remains local-only."""
import argparse,hashlib,io,json,re,time,unicodedata,urllib.parse,urllib.request
import fcntl
import html
from contextlib import contextmanager
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image,ImageOps
from app import config
from app.database import connection
from app.models import movie_response
from app.catalog import build_catalog
from app.genres import parse_genres, GENRE_VERSION
ROOT=config.ROOT
SOURCES=ROOT/'data/artwork-source';ART=ROOT/'data/artwork'
INDEX=ROOT/'data/artwork/index.json';REPORT=ROOT/'data/artwork-reports/matching.json'
STATE=ROOT/'data/artwork-reports/attempts.json'
MATCH_VERSION=2
ERROR_RETRY_SECONDS=300
ERROR_RETRY_MAX_SECONDS=3600

@contextmanager
def import_lock():
    for p in [SOURCES,ART,REPORT.parent]:p.mkdir(parents=True,exist_ok=True)
    with (ART/'import.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def write_json(path, value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2))
    temporary.replace(path)

def complete(entry):
    roles=[entry.get(role) for role in ('poster','landscape','backdrop')]
    return any(roles) and all(not name or (ART/name).is_file() for name in roles)

def fetch(url):
    target=SOURCES/hashlib.sha256(url.encode()).hexdigest()
    is_page=urllib.parse.urlparse(url).hostname=='www.themoviedb.org'
    if target.exists() and (not is_page or time.time()-target.stat().st_mtime < config.ARTWORK_RETRY_SECONDS):return target.read_bytes()
    req=urllib.request.Request(url,headers={'User-Agent':'MyMediaPersonalLibrary/1.0'})
    with urllib.request.urlopen(req,timeout=25) as response:
        data=response.read(16*1024*1024+1)
    if len(data)>16*1024*1024:raise ValueError('Download exceeds image/page budget')
    target.write_bytes(data)
    time.sleep(.35)
    return data

def norm(value):
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower().replace('&','and')
    return re.sub(r'[^a-z0-9]','',value)

def artwork_query(title):
    """Strip trailing release editions, keeping meaningful title words and sequel numbers."""
    query=re.sub(r'^\d{1,3}-\d{1,3}\s+', '', title)
    query=re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', query).strip()
    edition=r"(?:unrated|un[ -]?cut|extended(?:[ -]+(?:cut|edition))?|director['’]?s[ -]+cut|theatrical[ -]+cut|remastered|special[ -]+edition|collector['’]?s[ -]+edition)"
    while True:
        cleaned=re.sub(r'(?i)\s+[\[(]?'+edition+r'[\])]?\s*$', '', query).strip()
        if cleaned==query or not cleaned or norm(cleaned) in {'the','a','an'}: return query
        query=cleaned

def search_queries(query,year,kind):
    queries=[query]
    # Some release collections label the first film "I"; only use this fallback
    # with a known movie year, and still require an exact title/year match.
    if kind=='movie' and year is not None and re.search(r'\s+I$',query):
        queries.append(re.sub(r'\s+I$', '', query))
    return queries

def retry_at(prior):
    report=prior.get('report',{})
    default=ERROR_RETRY_SECONDS if report.get('status')=='error' else config.ARTWORK_RETRY_SECONDS
    return prior.get('next_retry_at',prior.get('time',0)+default)

def search(query,kind):
    soup=BeautifulSoup(fetch('https://www.themoviedb.org/search/'+kind+'?'+urllib.parse.urlencode({'query':query})), 'html.parser')
    found=[]
    container=soup.find(id=kind+'_results')
    if not container:return found
    for card in container.select('[data-object-id]'):
        heading=card.find('h2');date=card.select_one('.release_date')
        if not heading:continue
        a=heading.find_parent('a');href=a.get('href','')
        if not re.match('/'+kind+r'/\d+',href):continue
        years=re.findall(r'\b(?:19|20)\d{2}\b',date.get_text() if date else '')
        found.append({'title':heading.get_text(' ',strip=True),'year':int(years[-1]) if years else None,'url':'https://www.themoviedb.org'+href})
    return found

def image_file(url,role):
    data=fetch(url)
    with Image.open(io.BytesIO(data)) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        # Avoid publishing placeholder assets or stretching portrait art as a backdrop.
        if min(im.size)<100:raise ValueError('Image too small')
        if role!='poster' and im.width/im.height<1.3:raise ValueError('Not landscape artwork')
        bounds={'poster':(300,450),'backdrop':(960,540),'landscape':(480,270)}[role]
        im.thumbnail(bounds,Image.Resampling.LANCZOS)
        out=io.BytesIO();im.save(out,'JPEG',quality=88,optimize=True);result=out.getvalue()
    name=hashlib.sha256(result).hexdigest()[:24]+'-'+role+'.jpg'
    temporary=ART/(name+'.tmp');temporary.write_bytes(result);temporary.replace(ART/name)
    return name

def download(match):
    if not re.fullmatch(r'https://www\.themoviedb\.org/(?:movie|tv)/\d+[^?#]*',match['url']):raise ValueError('Override must be a public TMDB movie/TV URL')
    soup=BeautifulSoup(fetch(match['url']),'html.parser')
    title=soup.select_one('meta[property="og:title"]')
    if not title or norm(title['content'])!=norm(match['title']):raise ValueError('Detail title disagrees with search match')
    images=[x.get('content','') for x in soup.select('meta[property="og:image"]')]
    poster=next((u for u in images if '/w500/' in u),None)
    backdrop=next((u for u in images if '/w780/' in u),None)
    entry={'matched_title':match['title'],'matched_year':match['year'],'source_url':match['url'],'provider':'TMDB public title page',
           'genres':parse_genres(soup),'genre_version':GENRE_VERSION}
    if poster:entry['poster']=image_file(poster,'poster')
    if backdrop:
        entry['backdrop']=image_file(backdrop.replace('/w780/','/w1280/'),'backdrop')
        entry['landscape']=image_file(backdrop,'landscape')
    if not entry.get('poster') and not entry.get('backdrop'):raise ValueError('No artwork on title page')
    return entry

def enrich_genres(index, items):
    errors=[]
    for item in items:
        key=str(item['id']);entry=index.get(key,{})
        url=entry.get('source_url','')
        if not re.fullmatch(r'https://www\.themoviedb\.org/(?:movie|tv)/\d+[^?#]*',url):continue
        if entry.get('genre_version')==GENRE_VERSION:continue
        if time.time()-entry.get('genres_attempted_at',0)<config.ARTWORK_RETRY_SECONDS:continue
        entry['genres_attempted_at']=time.time()
        try:
            soup=BeautifulSoup(fetch(url),'html.parser')
            title=soup.select_one('meta[property="og:title"]')
            if not title or norm(title.get('content',''))!=norm(entry.get('matched_title','')):
                raise ValueError('Genre title page disagrees with verified artwork match')
            entry['genres']=parse_genres(soup)
            entry['genre_version']=GENRE_VERSION
            entry.pop('genres_error',None)
            print('GENRES',key,item['title'],'->',entry['genres'],flush=True)
        except Exception as exc:
            entry['genres_error']=str(exc)
            print('GENRES ERROR',key,str(exc),flush=True)
        index[key]=entry
        write_json(INDEX,index)
    for key,entry in index.items():
        if entry.get('genres_error'):errors.append({'id':key,'error':entry['genres_error']})
    write_json(REPORT.parent/'genres.json',errors)

def run(refresh=()):
    with import_lock():
        return _run(refresh)

def _run(refresh=()):
    with connection() as db:rows=db.execute('SELECT * FROM movies WHERE available=1').fetchall()
    items=build_catalog([movie_response(r,'http://localhost:8080').model_dump() for r in rows])
    override_path=ROOT/'config/artwork-matches.json'
    overrides=json.loads(override_path.read_text()) if override_path.exists() else {}
    index=json.loads(INDEX.read_text()) if INDEX.exists() else {}
    attempts=json.loads(STATE.read_text()) if STATE.exists() else {}
    report=[]
    for item in items:
        key=str(item['id'])
        if key in index and key not in refresh and complete(index[key]):continue
        if item['title'] in {'ETRG','RARBG COM','My Media Test'}:
            report.append({'id':key,'title':item['title'],'status':'local_clip'});continue
        override=overrides.get(key,{})
        query=override.get('query') or artwork_query(item['title'])
        show_year=re.search(r'\(((?:19|20)\d{2})\)\s*$',item['title']) if item['kind']=='show' else None
        year=override.get('year',int(show_year[1]) if show_year else item.get('year'))
        kind=override.get('kind','tv' if item['kind']=='show' else 'movie')
        signature=json.dumps([MATCH_VERSION,query,year,kind,override],sort_keys=True)
        prior=attempts.get(key,{})
        if key not in refresh and prior.get('signature')==signature and time.time()<retry_at(prior):
            if prior.get('report'):report.append(prior['report'])
            continue
        attempts[key]={'signature':signature,'time':time.time()}
        try:
            candidates=[];exact=[]
            if not override.get('url'):
                for search_query in search_queries(query,year,kind):
                    found=search(search_query,kind)
                    for match in found:
                        if match['url'] not in {m['url'] for m in candidates}:candidates.append(match)
                    exact=[m for m in found if norm(m['title'])==norm(search_query) and (year is None or m['year']==year)]
                    if exact:break
            if override.get('url'):
                match={'url':override['url'],'title':override.get('matched_title',query),'year':year}
            elif len(exact)==1:match=exact[0]
            else:
                report.append({'id':key,'title':item['title'],'query':query,'year':year,'status':'needs_review','candidates':candidates})
                attempts[key]['report']=report[-1]
                attempts[key]['next_retry_at']=attempts[key]['time']+config.ARTWORK_RETRY_SECONDS
                write_json(STATE,attempts)
                print('REVIEW',key,query,[(m['title'],m['year']) for m in candidates[:4]],flush=True);continue
            index[key]=download(match)
            write_json(INDEX,index)
            attempts.pop(key,None)
            print('MATCH',key,query,'->',match['title'],match['year'],flush=True)
        except Exception as exc:
            failures=prior.get('failures',0)+1 if prior.get('signature')==signature else 1
            delay=min(ERROR_RETRY_MAX_SECONDS,ERROR_RETRY_SECONDS*2**min(failures-1,4))
            attempts[key].update(failures=failures,next_retry_at=time.time()+delay)
            report.append({'id':key,'title':item['title'],'status':'error','error':str(exc),
                           'next_retry_at':attempts[key]['next_retry_at']})
            print('ERROR',key,query,str(exc),flush=True)
        if report and report[-1]['id']==key:attempts[key]['report']=report[-1]
        write_json(STATE,attempts)
        write_json(REPORT,report)
    write_json(REPORT,report)
    enrich_genres(index, items)
    credits=['<!doctype html><html><meta charset="utf-8"><title>GRAVYFLIX artwork sources</title><h1>Artwork sources</h1><p>Public TMDB title pages and locally generated frames. This project is not endorsed by TMDB.</p><ul>']
    for key,entry in sorted(index.items()):
        title=html.escape(entry.get('matched_title',key))
        url=entry.get('source_url','')
        if url.startswith('https://www.themoviedb.org/'):
            credits.append('<li>'+title+' — <a href="'+html.escape(url,quote=True)+'">TMDB public title page</a></li>')
        else:
            credits.append('<li>'+title+' — local media frame</li>')
    credits.append('</ul></html>')
    target=REPORT.parent/'sources.html';temporary=target.with_suffix('.tmp')
    temporary.write_text('\n'.join(credits));temporary.replace(target)
    print('TOTAL',len(index),'cached entries;',len(report),'review items',flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-id',action='append',default=[],help='Re-match an existing movie/show ID after editing config/artwork-matches.json')
    args=parser.parse_args()
    run(args.refresh_id)
