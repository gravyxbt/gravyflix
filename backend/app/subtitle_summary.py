"""Ready-caption summaries for browsing: one database read, no extraction/network."""
import json
from . import config, subtitles
from .database import connection

def summarize(tracks, state='pending', embedded=()):
    return dict(embedded_image_count=sum(bool(e.get('image_based')) for e in embedded),
        conversion_pending=state in {'processing','queued'} and any(e.get('convertible') for e in embedded), state=state,count=len(tracks),has_full=any(t.get('kind')!='forced' for t in tracks),
        has_forced=any(t.get('kind')=='forced' for t in tracks),
        has_sdh=any(t.get('kind')=='sdh' for t in tracks),
        languages=sorted({t.get('language','und') for t in tracks if t.get('kind')!='forced'}
                         or {t.get('language','und') for t in tracks}))

def library_summaries():
    with connection() as db:
        rows=db.execute('''SELECT m.*,s.signature,s.tracks,s.state,s.embedded FROM movies m
            LEFT JOIN subtitle_jobs s ON s.movie_id=m.id WHERE m.available=1''').fetchall()
    output={}
    assets=config.ROOT/'data/subtitles'
    for row in rows:
        tracks=[];state=row['state'] or 'pending'
        if row['signature']:
            try:
                path=subtitles.checked_path(row)
                if row['signature']==subtitles.signature(path,subtitles.sidecars(path)):
                    tracks=[t for t in json.loads(row['tracks']) if (assets/(t['id']+'.srt')).is_file()]
                else: state='pending'
            except (OSError,ValueError): state='unavailable'
        output[row['id']]=summarize(tracks,state,json.loads(row['embedded'] or '[]'))
    return output

def decorate_catalog(catalog,summaries):
    for item in catalog:
        if item['kind']!='show':
            item['subtitle_summary']=summaries.get(item['id'],summarize([]))
            continue
        regular=[]
        for season in item['seasons']:
            for episode in season['episodes']:
                summary=summaries.get(episode['id'],summarize([]))
                episode['subtitle_summary']=summary
                if season['number']>=0: regular.append(summary)
        item['subtitle_summary']=dict(episode_total=len(regular),
            episodes_available=sum(s['count']>0 for s in regular),
            episodes_converting=sum(s.get('conversion_pending',False) for s in regular),
            episodes_with_embedded_images=sum(s.get('embedded_image_count',0)>0 for s in regular),
            episodes_full=sum(s['has_full'] for s in regular),
            episodes_forced_only=sum(s['count']>0 and not s['has_full'] for s in regular))
    return catalog
