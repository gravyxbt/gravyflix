#!/usr/bin/env python3
"""Scan/status or review an episode's intro marker. Never alters the video."""
import argparse,json,logging
from app import intros
from app.main import get_movie
from app.database import connection,initialize
p=argparse.ArgumentParser(description=__doc__)
s=p.add_subparsers(dest='command',required=True)
scan=s.add_parser('scan');scan.add_argument('--show')
s.add_parser('status')
set_parser=s.add_parser('set');set_parser.add_argument('--movie-id',type=int,required=True);set_parser.add_argument('--start',type=float,required=True);set_parser.add_argument('--end',type=float,required=True)
disable=s.add_parser('disable');disable.add_argument('--movie-id',type=int,required=True)
a=p.parse_args();initialize();intros.initialize();logging.basicConfig(level=logging.INFO)
if a.command=='scan':print(json.dumps(intros.IntroWorker().run_once(a.show),indent=2))
elif a.command=='status':
    with connection() as db:rows=db.execute('SELECT m.id,m.filename,i.state,i.marker,i.note FROM movies m JOIN intro_markers i ON i.movie_id=m.id WHERE m.available=1').fetchall()
    print(json.dumps([dict(r) for r in rows],indent=2))
else:intros.manual(get_movie(a.movie_id),a.start if a.command=='set' else None,a.end if a.command=='set' else None)
