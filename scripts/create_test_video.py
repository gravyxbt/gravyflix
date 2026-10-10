import shutil
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.config import MOVIES_DIR
ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("Install FFmpeg, or project-local imageio-ffmpeg (see README).")
MOVIES_DIR.mkdir(parents=True, exist_ok=True)
output = MOVIES_DIR / "My Media Test (2026).mp4"
subprocess.run([ffmpeg, "-hide_banner", "-n", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24",
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
    "-t", "12", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-ac", "2", "-b:a", "128k", "-movflags", "+faststart", str(output)], check=True)
print(output)
