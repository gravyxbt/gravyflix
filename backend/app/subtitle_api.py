from pathlib import Path
import json
import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from . import subtitles
from .database import connection
router=APIRouter()

@router.get('/api/movies/{movie_id}/subtitles')
def movie_subtitles(movie_id:int,request:Request):
    from .main import get_movie,base_url
    return subtitles.available(get_movie(movie_id),base_url(request))

@router.get('/api/subtitles/status')
def status():
    with connection() as db:
        rows=db.execute('SELECT movie_id,state,note,retry_at FROM subtitle_jobs').fetchall()
    return {'jobs':[dict(r) for r in rows]}

@router.api_route('/subtitles/{track_id}.srt',methods=['GET','HEAD'])
def serve(track_id:str):
    if not re.fullmatch('[a-f0-9]{64}',track_id): raise HTTPException(404,'Subtitle not found')
    with connection() as db:
        rows=db.execute('SELECT m.*,s.signature,s.tracks FROM movies m JOIN subtitle_jobs s ON s.movie_id=m.id WHERE m.available=1').fetchall()
    for row in rows:
        if any(t['id']==track_id for t in json.loads(row['tracks'])):
            try: path=subtitles.checked_path(row)
            except (ValueError,OSError): break
            if row['signature']!=subtitles.signature(path,subtitles.sidecars(path)): break
            file=subtitles.root()/(track_id+'.srt')
            if file.is_file(): return FileResponse(file,media_type='application/x-subrip',headers={'Cache-Control':'private, max-age=3600'})
    raise HTTPException(404,'Subtitle unavailable; refresh the library')

@router.api_route('/subtitles/{track_id}.vtt', methods=['GET', 'HEAD'])
def serve_vtt(track_id: str):
    """Use the same source/signature validation as Roku's SRT route."""
    import srt
    from fastapi.responses import Response
    response = serve(track_id)
    text = Path(response.path).read_text(encoding='utf-8-sig')
    cues = []
    for index, cue in enumerate(srt.parse(text), 1):
        timing = srt.timedelta_to_srt_timestamp(cue.start).replace(',', '.') + ' --> ' + srt.timedelta_to_srt_timestamp(cue.end).replace(',', '.')
        cues.append(f"{index}\n{timing}\n{cue.content}\n")
    return Response('WEBVTT\n\n' + '\n'.join(cues), media_type='text/vtt', headers={'Cache-Control': 'private, max-age=3600'})
