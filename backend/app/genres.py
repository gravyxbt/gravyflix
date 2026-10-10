"""Genre normalization from verified public title pages and local overrides."""
import json
import re
from functools import lru_cache
from . import config

GENRE_VERSION = 1
GENRES = {28:["Action"],12:["Adventure"],16:["Animation"],35:["Comedy"],80:["Crime"],
    99:["Documentary"],18:["Drama"],10751:["Family"],14:["Fantasy"],36:["History"],
    27:["Horror"],10402:["Music"],9648:["Mystery"],10749:["Romance"],878:["Science Fiction"],
    10770:["TV Movie"],53:["Thriller"],10752:["War"],37:["Western"],
    10759:["Action","Adventure"],10762:["Kids"],10763:["News"],10764:["Reality"],
    10765:["Science Fiction","Fantasy"],10766:["Soap"],10767:["Talk"],10768:["War & Politics"]}

def parse_genres(soup):
    genres=[]
    for link in soup.select('.genres a[href]'):
        match=re.fullmatch(r'/genre/(\d+)[^/]*/(?:movie|tv)',link['href'])
        if match:
            for name in GENRES.get(int(match[1]),[]):
                if name not in genres:genres.append(name)
    return genres

@lru_cache(maxsize=8)
def _overrides(path, stamp):
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or any(not isinstance(v,list) or any(not isinstance(g,str) or not g.strip() for g in v) for v in value.values()):
        raise ValueError('genre-overrides.json must map media/show IDs to lists of genre names')
    return {key:list(dict.fromkeys(g.strip() for g in genres)) for key,genres in value.items()}

def genres_for(item_id, parent_id, entry):
    genres=entry.get('genres',[]) if isinstance(entry,dict) else []
    genres=[g for g in genres if isinstance(g,str) and g.strip()] if isinstance(genres,list) else []
    path=config.ROOT/'config/genre-overrides.json'
    if path.exists():
        overrides=_overrides(path,path.stat().st_mtime_ns)
        genres=overrides.get(str(item_id),overrides.get(parent_id,genres))
    return genres
