"""Pure, conservative playback choices. Extensions are containers, not codecs."""
from pathlib import Path
import subprocess
VERSION=1

def decide(row,client='roku',mode='auto',capabilities=None):
    r=dict(row);caps=capabilities or {};suffix=Path(r.get('filename','')).suffix.lower()
    def plan(delivery,reason):return {'delivery':delivery,'reason':reason,'policy_version':VERSION,'client':client,'video_codec':r.get('video_codec'),'audio_codec':r.get('audio_codec')}
    if mode=='original':return plan('direct','original_override')
    video=r.get('video_codec');audio=r.get('audio_codec')
    if not video or r.get('probe_error'):return plan('direct','probe_unavailable_attempt_original')
    hdr=r.get('color_transfer') in {'smpte2084','arib-std-b67'}
    pix=r.get('pixel_format') or 'yuv420p'
    video_ok=video=='h264' and pix in {'yuv420p','yuvj420p'} and (r.get('video_level') or 0)<=41 and (r.get('width') or 0)<=1920 and (r.get('height') or 0)<=1080 and (r.get('frame_rate') or 0)<=30
    # A positive decoder response is for this specific source, not an unrestricted codec promise.
    if client=='roku' and isinstance(caps.get('source_video_supported'),bool) and not hdr:
        video_ok=caps['source_video_supported'] and pix in {'yuv420p','yuvj420p'} and video in {'h264','hevc'} and (r.get('width') or 0)<=1920 and (r.get('height') or 0)<=1080 and (r.get('frame_rate') or 0)<=30
    if mode=='compatible':video_ok=False
    if hdr and not video_ok:return plan('unsupported','hdr_requires_verified_tone_mapping')
    if not video_ok:return plan('video_convert','video_exceeds_receiver_profile')
    audio_ok=not audio or (audio=='aac' and r.get('audio_channels') in {1,2} and (r.get('audio_profile') in {None,'LC'}))
    if not audio_ok:return plan('audio_convert','audio_requires_aac_stereo')
    if suffix not in {'.mp4','.m4v'}:return plan('remux','container_requires_mp4')
    return plan('direct','source_matches_receiver_profile')

def media_row(row):
    """Upgrade probe fields for the selected file, not all movies inside a request."""
    r=dict(row)
    if r.get('video_profile') is not None or r.get('probe_error'):return r
    from .media_tools import inspect_media,probe_fields
    from .roku_audio import source_path
    from .database import connection
    try:
        values=probe_fields(inspect_media(source_path(r)))
        with connection() as db:db.execute('UPDATE movies SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),r['id']))
        r.update(values)
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError):pass
    return r
