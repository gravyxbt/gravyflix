#!/usr/bin/env python3
"""Project CLI: PYTHONPATH=backend .venv/bin/python scripts/subtitles.py status|process|sync."""
import argparse
import json
from app import config, subtitles
from app.database import connection, initialize
from app.subtitle_sync import synchronize
parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['status','process','sync'])
parser.add_argument('--movie-id',type=int)
parser.add_argument('--track-id')
args=parser.parse_args()
initialize();subtitles.initialize()
if args.command=='process':
    subtitles.SubtitleWorker().run_once()
elif args.command=='status':
    with connection() as db:
        rows=[dict(r) for r in db.execute('SELECT m.title,s.movie_id,s.state,s.note,s.retry_at,s.tracks FROM subtitle_jobs s JOIN movies m ON m.id=s.movie_id')]
    for row in rows: row['tracks']=json.loads(row['tracks'])
    print(json.dumps(rows,indent=2))
else:
    with connection() as db:
        row=db.execute('SELECT * FROM movies WHERE id=? AND available=1',(args.movie_id,)).fetchone()
    old=subtitles.saved(args.movie_id)
    if not row or not old: parser.error('Movie/subtitles unavailable')
    tracks=json.loads(old['tracks'])
    selected=next((t for t in tracks if t['id']==args.track_id),None)
    if not selected: parser.error('Track does not belong to this movie')
    video=subtitles.checked_path(row)
    if old['signature']!=subtitles.signature(video,subtitles.sidecars(video)): parser.error('Source changed; refresh first')
    path=subtitles.root()/(selected['id']+'.srt')
    data=synchronize(video,selected['id'],path.read_bytes())
    new_id=__import__('hashlib').sha256(data+selected['id'].encode()).hexdigest()
    subtitles.publish(new_id,data)
    selected['id']=new_id
    selected['sync']='ffsubsync'
    subtitles.store(row['id'],old['signature'],tracks,old['state'],old['note'],old['retry_at'])
    print('Synchronized captions saved. Restart this title to load the updated track.')
