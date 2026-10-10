#!/usr/bin/env python3
"""Offline runtime smoke check: real FFmpeg, ffprobe audio fingerprinting and bundled OCR inference."""
import json
import tempfile
import subprocess
from pathlib import Path
from app.media_tools import binary, inspect_media
from app.credit_detection import Analyzer
from app.intros import audio_fingerprint, IntroWorker


def main():
    ffmpeg=binary('ffmpeg')
    if not ffmpeg or not binary('ffprobe'):
        raise SystemExit('Install FFmpeg and ffprobe before checking media support.')
    with tempfile.TemporaryDirectory(prefix='gravyflix-media-check-') as folder:
        path=Path(folder)/'sample video.mp4'
        subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=24',
                        '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','8',
                        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,timeout=30)
        info=inspect_media(path)
        assert any(s.get('codec_name')=='h264' for s in info['streams'])
        assert len(audio_fingerprint(path, 8, IntroWorker().command)) > 0
        analyzer=Analyzer(path,60)
        result=analyzer.sample(0)
        assert isinstance(result,dict) and not result['positive']
    print('PASS: H.264/AAC encode, ffprobe, frame extraction audio fingerprinting and bundled OCR inference')

if __name__=='__main__':main()
