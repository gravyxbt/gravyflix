import json
import subprocess
import sys
import srt
from pathlib import Path
from .media_tools import binary
from .subtitles import root, validate_srt

def synchronize(video, key, data):
    original=root()/(key+'.original.srt')
    original.write_text(validate_srt(data),encoding='utf-8')
    output=root()/(key+'.synced.srt')
    executable=binary('ffmpeg')
    if not executable: raise RuntimeError('FFmpeg unavailable')
    command=[sys.executable,'-m','app.subtitle_sync_runner',str(video),'-i',str(original),'-o',str(output),
        '--reference-stream','0:a:0','--vad','webrtc','--skip-sync-on-low-quality',
        '--quality-max-offset-seconds','30','--max-framerate-deviation','0.05',
        '--ffmpeg-path',str(Path(executable).parent)]
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=600,check=True)
        report=json.loads(result.stdout.strip().splitlines()[-1])
        if not report.get('sync_was_successful'): raise RuntimeError('Alignment rejected')
        payload=output.read_bytes()
        validate_srt(payload)
        before=list(srt.parse(validate_srt(data)))
        after=list(srt.parse(payload.decode('utf-8-sig')))
        if len(after) < max(1,len(before)*0.95):
            raise RuntimeError('Alignment discarded too many dialogue cues')
        (root()/(key+'.sync.json')).write_text(json.dumps(report),encoding='utf-8')
        return payload
    except (ValueError,IndexError,subprocess.SubprocessError) as exc:
        raise RuntimeError('Subtitle synchronization failed') from exc
    finally:
        output.unlink(missing_ok=True)
