#!/usr/bin/env python3
"""Explicit fallback pass: stills only from each entry's own media file."""
import hashlib,io,json,subprocess,fcntl
from pathlib import Path
from PIL import Image,ImageOps
from app import config
from app.database import connection
from app.models import movie_response
from app.catalog import build_catalog
from app.media_tools import binary
root=config.ROOT/'data/artwork';index_path=root/'index.json'
root.mkdir(parents=True,exist_ok=True)
# Serialize with automatic/CLI public imports to avoid overwriting a newer index.
lock=(root/'import.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX)
index=json.loads(index_path.read_text()) if index_path.exists() else {}
with connection() as db:rows=[dict(r) for r in db.execute('SELECT * FROM movies WHERE available=1')]
by_id={r['id']:r for r in rows}
items=build_catalog([movie_response(r,'http://localhost:8080').model_dump() for r in rows])
for item in items:
    key=str(item['id']);entry=index.get(key,{})
    if all(entry.get(role) for role in ['poster','backdrop','landscape']):continue
    media_id=item['seasons'][0]['episodes'][0]['id'] if item['kind']=='show' else item['id']
    row=by_id[media_id]
    seconds=min(60,(row['duration'] or 10)*.2)
    result=subprocess.run([binary('ffmpeg'),'-v','error','-ss',str(seconds),'-i',row['file_path'],
        '-frames:v','1','-vf','scale=960:-2','-f','image2pipe','-vcodec','mjpeg','-'],capture_output=True,check=True,timeout=30)
    with Image.open(io.BytesIO(result.stdout)) as source:
        source=source.convert('RGB')
        for role,size in [('poster',(300,450)),('landscape',(480,270)),('backdrop',(960,540))]:
            if entry.get(role):continue
            im=ImageOps.pad(source,size,method=Image.Resampling.LANCZOS,color=(8,14,24))
            out=io.BytesIO();im.save(out,'JPEG',quality=88,optimize=True);data=out.getvalue()
            name=hashlib.sha256(data).hexdigest()[:24]+'-'+role+'.jpg'
            (root/name).write_bytes(data);entry[role]=name
            entry.setdefault('local_stills',[]).append(role)
    entry.setdefault('matched_title',item['title'])
    entry.setdefault('provider','Local video title frame/still')
    entry['still_source_media_id']=media_id;entry['still_timestamp']=seconds
    index[key]=entry
    print('STILL',key,item['title'],entry['local_stills'],flush=True)
temp=index_path.with_suffix('.tmp');temp.write_text(json.dumps(index,indent=2));temp.replace(index_path)
