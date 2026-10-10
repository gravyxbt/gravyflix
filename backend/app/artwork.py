"""Local-only artwork lookup. The importer owns network access and image decoding."""
import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from . import config

router = APIRouter()
NAME = re.compile(r'[0-9a-f]{24}-(poster|backdrop|landscape)\.jpg')
_lock = threading.Lock()
_stamp = None
_index = {}

def root():
    return config.ROOT / 'data/artwork'

def entries():
    global _stamp, _index
    path = root() / 'index.json'
    try:
        stat = path.stat()
        stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}
    with _lock:
        if stamp != _stamp:
            try:
                value = json.loads(path.read_text())
                if not isinstance(value, dict):
                    raise ValueError('Artwork index must be an object')
                _index, _stamp = value, stamp
            except (OSError, ValueError):
                logging.getLogger('media').exception('ART: Invalid artwork index; retaining last good index')
        return _index

def decorate(item, base, parent_id=None):
    index = entries()
    entry = index.get(str(item['id'])) or index.get(parent_id)
    from .genres import genres_for
    item['genres'] = genres_for(item['id'], parent_id, entry)
    if not isinstance(entry, dict):
        return item
    for role in ('poster', 'backdrop', 'landscape'):
        name = entry.get(role, '')
        if isinstance(name, str) and NAME.fullmatch(name) and (root()/name).is_file():
            item[role + '_url'] = f'{base}/artwork/{name}'
    item['artwork_source'] = entry.get('source_url')
    return item

def show_id(series):
    return 'show-' + hashlib.sha256(series['show_key'].encode()).hexdigest() if series else None

@router.get('/artwork/{name}')
def image(name: str):
    if not NAME.fullmatch(name):
        raise HTTPException(404, 'Artwork not found')
    path = (root()/name).resolve()
    if not path.is_relative_to(root().resolve()) or not path.is_file():
        raise HTTPException(404, 'Artwork not found')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control':'public, max-age=31536000, immutable'})

@router.get('/artwork-credits', include_in_schema=False)
def credits():
    path = config.ROOT / 'data/artwork-reports/sources.html'
    if not path.is_file():
        raise HTTPException(404, 'Artwork source report not generated')
    return FileResponse(path, media_type='text/html', headers={'Cache-Control':'no-cache'})
