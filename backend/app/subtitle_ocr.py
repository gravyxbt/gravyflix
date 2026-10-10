"""Offline DVD bitmap-to-SRT conversion in an isolated, bounded background process."""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

VERSION = 1
MAX_CUES = 20000
MAX_PIXELS = 4096 * 2160


def line_crops(indices):
    """Read complete lines, testing palette indices without unsafe palette pointers."""
    import cv2
    import numpy as np
    if indices.ndim != 2 or not indices.size or indices.size > MAX_PIXELS:
        raise ValueError('Invalid subtitle bitmap dimensions')
    border = np.concatenate([indices[0], indices[-1], indices[:, 0], indices[:, -1]])
    background = int(np.bincount(border).argmax())
    active = np.where((indices != background).sum(axis=1) > 2)[0]
    if not len(active): return [], 0
    groups = np.split(active, np.where(np.diff(active) > 3)[0] + 1)
    groups = [g for g in groups if len(g) >= 3]
    if len(groups) > 12: raise ValueError('Too many subtitle lines')
    colors = [int(v) for v in np.unique(indices) if v != background]
    if len(colors) > 3: raise ValueError('Expected a four-color DVD subtitle')
    crops = []
    for color in colors:
        for group in groups:
            image = np.where(indices[group[0]:group[-1]+1] == color, 0, 255).astype(np.uint8)
            image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
            image = cv2.copyMakeBorder(image, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
            crops.append(np.repeat(image[:, :, None], 3, axis=2))
    return crops, len(groups)


class Reader:
    def __init__(self):
        from .credit_detection import Analyzer
        # Reuse the pinned bundled recognition model and single-thread ONNX setup.
        self.engine = Analyzer(Path('.'), 1200).engine
        self.cache = {}

    def read(self, rectangle):
        import numpy as np
        from rapidocr.ch_ppocr_rec import TextRecInput
        if rectangle.type != b'bitmap' or rectangle.width <= 0 or rectangle.height <= 0:
            return '', 0.0
        if rectangle.width * rectangle.height > MAX_PIXELS:
            raise ValueError('Subtitle bitmap exceeds size limit')
        raw = bytes(rectangle.planes[0])
        if len(raw) != rectangle.width * rectangle.height:
            raise ValueError('Unexpected subtitle bitmap layout')
        key = hashlib.sha256(raw + str((rectangle.width, rectangle.height)).encode()).digest()
        if key in self.cache: return self.cache[key]
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(rectangle.height, rectangle.width)
        crops, lines = line_crops(pixels)
        if not lines: return '', 0.0
        result = self.engine.text_rec(TextRecInput(img=crops))
        texts, scores = result.txts or (), result.scores or ()
        if len(texts) != len(crops): raise ValueError('OCR returned incomplete results')
        chosen = []
        for line in range(lines):
            candidates = [(float(scores[i]), texts[i].strip()) for i in range(line, len(crops), lines)]
            score, text = max(candidates)
            if not text or not math.isfinite(score): return '', 0.0
            chosen.append((score, html.escape(text, quote=False)))
        value = ('\n'.join(t for _, t in chosen), min(s for s, _ in chosen))
        if len(self.cache) < MAX_CUES: self.cache[key] = value
        return value


def timing(subset, packet, origin=0.0):
    """AVSubtitle pts is microseconds; display offsets are milliseconds."""
    base = subset.pts / 1000000 if subset.pts is not None and subset.pts > -(2**62) else float(packet.pts * packet.time_base)
    start = base + subset.start_display_time / 1000 - origin
    end = base + subset.end_display_time / 1000 - origin
    if end <= start and packet.duration:
        end = base + float(packet.duration * packet.time_base) - origin
    if not all(map(math.isfinite, (start, end))) or start < -0.1 or not 0 < end - start <= 120:
        raise ValueError('Invalid embedded subtitle timing')
    return max(0, start), end


def convert_file(path, stream_index, output, report, timeout=1200):
    import av
    import cv2
    cv2.setNumThreads(1)
    import srt
    from datetime import timedelta
    try: os.nice(10)
    except OSError: pass
    started = time.monotonic()
    deadline = started + timeout
    reader = Reader()
    cues = []; total = 0; weak = 0; first = []; original = Path(path).stat()
    with av.open(str(path)) as container:
        stream = container.streams[stream_index]
        if stream.type != 'subtitle' or stream.codec_context.name != 'dvdsub':
            raise ValueError('Only embedded DVD bitmap subtitles are supported')
        origin = (container.start_time or 0) / av.time_base
        for packet in container.demux(stream):
            if time.monotonic() > deadline: raise TimeoutError('Subtitle conversion time budget exceeded')
            if not packet.size: continue
            subset = stream.codec_context.decode2(packet)
            if not subset or not len(subset): continue
            total += 1
            if total > MAX_CUES: raise ValueError('Subtitle cue budget exceeded')
            start, end = timing(subset, packet, origin)
            parts = [reader.read(rect) for rect in sorted(subset, key=lambda r: (r.y, r.x))]
            text = '\n'.join(t for t, _ in parts if t)
            confidence = min((score for _, score in parts), default=0.0)
            if not text or confidence < .75: weak += 1
            if not text: continue
            cues.append(srt.Subtitle(len(cues)+1, timedelta(seconds=start), timedelta(seconds=end), text))
            if len(first) < 5: first.append(dict(start=round(start,3), end=round(end,3), text=text, confidence=round(confidence,4)))
            if total % 50 == 0:
                print(json.dumps({'cues':total,'low_confidence':weak}), flush=True)
    after = Path(path).stat()
    if (original.st_size, original.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Media changed during subtitle conversion')
    quality = dict(version=VERSION, elapsed_seconds=round(time.monotonic()-started,2), cues=total, recognized=len(cues), low_confidence=weak,
                   low_confidence_fraction=weak / max(1,total), first_cues=first)
    Path(report).write_text(json.dumps(quality,indent=2)+'\n')
    if not total or len(cues) != total or weak > max(1, total * .08):
        raise ValueError('Subtitle OCR needs review; conversion was not published')
    payload = srt.compose(cues).encode('utf-8')
    from .subtitles import validate_srt
    validate_srt(payload)
    Path(output).write_bytes(payload)
    print(json.dumps({'complete':True, 'cues':total,'low_confidence':weak}),flush=True)


def convert(path, stream, output, report, stop=None):
    """Cancel on shutdown; hard timeout contains decoder/OCR failures."""
    process = subprocess.Popen([sys.executable, '-m', 'app.subtitle_ocr', str(path), str(stream), str(output), str(report)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 1230
    try:
        while process.poll() is None:
            if stop and stop.is_set(): raise InterruptedError('Subtitle conversion cancelled')
            if time.monotonic() > deadline: raise TimeoutError('Subtitle conversion timed out')
            time.sleep(.2)
        _, errors = process.communicate()
        if process.returncode:
            raise RuntimeError('Embedded subtitle OCR failed; see local conversion report')
        return Path(output).read_bytes()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        if process.stderr: process.stderr.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path');parser.add_argument('stream',type=int);parser.add_argument('output');parser.add_argument('report')
    args=parser.parse_args()
    convert_file(args.path,args.stream,args.output,args.report)
