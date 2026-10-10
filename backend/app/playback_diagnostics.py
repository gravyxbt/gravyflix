"""Bounded, local playback evidence. Never export credentials or media paths."""
import time
from .database import connection
from .watch_history import prune
from .roku_audio import cache

def report():
    prune()
    with connection() as db:
        rows=db.execute('''SELECT s.id,s.client_type,s.movie_id,s.state,s.position,s.duration,
            s.created_at,s.updated_at,s.ended,s.delivery,s.reason,s.preparation_seconds,
            s.first_play_seconds,s.buffering_seconds,s.buffering_since,m.title,
            m.video_codec,m.audio_codec,m.width,m.height
            FROM playback_sessions s LEFT JOIN movies m ON m.id=s.movie_id
            ORDER BY s.updated_at DESC LIMIT 1000''').fetchall()
        events=db.execute('''SELECT e.session_id,e.sequence,e.event,e.received_at,e.position
            FROM playback_events e JOIN playback_sessions s ON s.id=e.session_id
            ORDER BY e.received_at DESC LIMIT 2000''').fetchall()
    sessions=[dict(r) for r in rows]
    now=time.time()
    for s in sessions:
        if s['buffering_since'] is not None:s['buffering_seconds']+=max(0,now-s['buffering_since'])
        s.pop('buffering_since')
    with cache.lock:
        jobs=[dict(state=j.state,delivery=j.delivery,progress=j.progress) for j in cache.jobs.values() if j.state in {'queued','preparing'}]
        reserved=sum(j.reserved for j in cache.jobs.values() if j.state in {'queued','preparing'})
        leases=len(cache.leases)
    return dict(generated_at=now,retention_days=7,session_limit=1000,event_limit_per_session=200,
                sessions=sessions,events=[dict(r) for r in events],cache=dict(active_jobs=jobs,reserved_bytes=reserved,leases=leases),
                observation_limits='Reported player states and timestamps only. Video-frame freezes, Wi-Fi signal, and receiver decoder health are not measurable here.')
