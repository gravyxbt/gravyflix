#!/usr/bin/env python3
"""Read-only audit of embedded subtitle streams in the original media library."""
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from app import config
from app.media_tools import inspect_media
from app.scanner import EXTENSIONS

TEXT={'subrip','srt','ass','ssa','webvtt','mov_text','text','ttml','sami','microdvd','subviewer','subviewer1','vplayer','mpl2','jacosub','pjs','realtext','stl'}
IMAGE={'hdmv_pgs_subtitle','dvd_subtitle','dvb_subtitle','xsub'}

def audit():
    root=config.MOVIES_DIR.resolve()
    if not root.is_dir():raise SystemExit('Media folder is unavailable')
    with sqlite3.connect(f'file:{config.DATABASE_PATH}?mode=ro',uri=True) as db:
        titles={path:{'id':number,'title':title} for number,path,title in db.execute('SELECT id,file_path,title FROM movies')}
    rows=[];skipped=0
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():continue
        if path.name.startswith('._'):
            skipped+=1;continue
        resolved=path.resolve()
        if not resolved.is_relative_to(root):continue
        row={'path':str(path.relative_to(root)),**titles.get(str(resolved),{}),'tracks':[]}
        try:
            info=inspect_media(resolved)
            for stream in info.get('streams',[]):
                if stream.get('codec_type')!='subtitle':continue
                tags=stream.get('tags',{});disposition=stream.get('disposition',{})
                codec=stream.get('codec_name','unknown')
                row['tracks'].append({'index':stream['index'],'codec':codec,
                    'type':'text' if codec in TEXT else 'image' if codec in IMAGE else 'unknown',
                    'language':tags.get('language') or 'und','title':tags.get('title') or '',
                    'default':bool(disposition.get('default')),'forced':bool(disposition.get('forced')),
                    'hearing_impaired':bool(disposition.get('hearing_impaired'))})
        except Exception as exc:row['error']=str(exc)
        rows.append(row)
    tracks=[track for row in rows for track in row['tracks']]
    summary={'files_inspected':len(rows),'with_subtitles':sum(bool(row['tracks']) for row in rows),
        'without_subtitles':sum(not row['tracks'] and 'error' not in row for row in rows),
        'probe_errors':sum('error' in row for row in rows),'resource_forks_skipped':skipped,
        'subtitle_tracks':len(tracks),'files_with_text':sum(any(t['type']=='text' for t in row['tracks']) for row in rows),
        'files_with_image':sum(any(t['type']=='image' for t in row['tracks']) for row in rows),
        'codecs':dict(Counter(t['codec'] for t in tracks)), 'languages':dict(Counter(t['language'] for t in tracks))}
    out=config.ROOT/'data/subtitle-reports';out.mkdir(parents=True,exist_ok=True)
    (out/'embedded-subtitles.json').write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),
        'library':str(root),'summary':summary,'files':rows},indent=2,ensure_ascii=False)+'\n')
    lines=['# Embedded subtitle audit','',f"Inspected {len(rows)} original video files; {summary['with_subtitles']} have embedded subtitles.",
        f"{summary['files_with_text']} files have text tracks; {summary['files_with_image']} have image tracks (these counts can overlap).",'',
        'Text tracks are candidates for extraction/conversion. Image tracks need a separate rendering/OCR strategy.',
        'This audit detects streams; it does not verify synchronization or subtitle contents, and does not enable subtitles in Roku.',
        '`und` means the language is not identified in the file. macOS resource forks and playback-cache copies are excluded.','',
        '| Video (relative library path) | Embedded tracks |','| --- | --- |']
    escape=lambda value:str(value).replace('|','\\|').replace('\n',' ')
    for row in rows:
        if not row['tracks']:continue
        labels=[]
        for t in row['tracks']:
            flags=', '.join(k.replace('_',' ') for k in ['default','forced','hearing_impaired'] if t[k])
            labels.append(f"#{t['index']} {t['language']} · {t['codec']} ({t['type']})"+(f" · {t['title']}" if t['title'] else '')+(f" [{flags}]" if flags else ''))
        lines.append('| '+escape(row['path'])+' | '+escape('; '.join(labels))+' |')
    lines+=['','## Files without embedded subtitles','']
    lines+=['- '+escape(row['path']) for row in rows if not row['tracks'] and 'error' not in row]
    if summary['probe_errors']:
        lines+=['','## Probe errors','']+['- '+escape(row['path'])+': '+escape(row['error']) for row in rows if 'error' in row]
    (out/'embedded-subtitles.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))
    print('Reports:',out)

if __name__=='__main__':audit()
