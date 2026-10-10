"""Bounded local OCR analysis of movie endings. No cloud calls or runtime guesses."""
import argparse
import json
import logging
import math
import os
import re
import subprocess
import time
from pathlib import Path

VERSION = 1
WIDTH, HEIGHT = 960, 540
MAX_SAMPLES = 100
ROLES = (
    'directed by', 'written by', 'written and directed', 'produced by', 'executive producer',
    'screenplay', 'director of photography', 'production designer', 'costume designer',
    'edited by', 'editing by', 'casting by', 'music by', 'music composed', 'original score',
    'co producer', 'associate producer', 'visual effects', 'special effects',
    'sound editor', 'sound supervisor', 'sound mixer', 'post production', 'assistant editor',
    'unit production', 'production manager', 'production supervisor', 'production assistant',
    'art director', 'set decorator', 'set decoration', 'camera operator', 'gaffer',
    'key grip', 'best boy', 'transportation', 'script supervisor', 'stunt', 'foley',
    'composit', 'animation supervisor', 'special thanks', 'filmed on', 'filmed in',
    'costume supervisor', 'makeup', 'make up', 'hair stylist', 'wardrobe', 'colorist',
    'casting director', 'cast of characters', 'starring',
)


def normalize(text):
    return re.sub(r'[^\w]+', ' ', text.casefold()).strip()


def describe_frame(lines, dark=0.0):
    """Role text + layout; bottom-of-screen dialogue alone is never evidence."""
    good = [line for line in lines if line['confidence'] >= .70 and len(normalize(line['text'])) >= 3]
    if not good:
        return dict(positive=False, dense=False, roles=[], texts=[], lines=[])
    texts = [normalize(line['text']) for line in good]
    roles = sorted({role for role in ROLES if any(role.replace(' ', '') in text.replace(' ', '') for text in texts)})
    centers = [(line['y0'] + line['y1']) / 2 for line in good]
    span = max(line['y1'] for line in good) - min(line['y0'] for line in good)
    caption_only = len(good) <= 4 and min(centers) > .78
    name_count = sum(2 <= len(text.split()) <= 5 and sum(c.isalpha() for c in text)/max(len(text),1) > .75 for text in texts)
    dense = len(good) >= 12 and span >= .35 and dark >= .68 and name_count / len(good) >= .45
    heading = bool(roles) and len(good) >= 2 and not caption_only and (span >= .035 or len(good) >= 5)
    return dict(positive=heading, dense=dense, roles=roles, texts=texts[:32], lines=good)


def scrolling(a, b):
    """Confirm upwards movement of multiple recognized lines one second apart."""
    first = {normalize(line['text']): (line['y0']+line['y1'])/2 for line in a.get('lines', []) if len(normalize(line['text'])) >= 6}
    shifts = [(line['y0']+line['y1'])/2-first[normalize(line['text'])] for line in b.get('lines', []) if normalize(line['text']) in first]
    upwards = [shift for shift in shifts if -.3 < shift < -.003]
    if len(upwards) < 3: return False
    middle = sorted(upwards)[len(upwards)//2]
    return sum(abs(s-middle) < max(.015,abs(middle)*.4) for s in upwards) >= 3


def sequence_confirmed(samples):
    positives = [s for s in samples if s['positive']]
    roles = {role for s in positives for role in s['roles']}
    texts = {text for s in positives for text in s['texts']}
    return len(positives) >= 3 and (len(roles) >= 2 or all('verified scrolling credit text' in s['roles'] for s in positives)) and len(texts) >= 6


def detect(duration, sample):
    """Coarse search, independent temporal confirmation, then two-second refinement."""
    if not math.isfinite(duration) or duration < 600:
        return dict(start=None, confidence=0, samples=0, note='Not a full-length movie')
    low = max(duration*.75, duration-900)
    high = duration-12
    cache = {}
    def get(stamp):
        stamp = round(stamp, 2)
        if stamp not in cache:
            if len(cache) >= MAX_SAMPLES: raise RuntimeError('Credits frame budget exceeded')
            cache[stamp] = sample(stamp)
        return cache[stamp]
    t = low
    while t <= high-30:
        first = get(t)
        if first['dense'] and not first['positive']:
            second = get(t+1)
            if scrolling(first,second):
                first.update(positive=True, roles=['verified scrolling credit text'])
        if first['positive']:
            # Five frames span a minute: allow blank fades or an intervening scene.
            times = [t+i*15 for i in range(5) if t+i*15 <= high]
            frames = [get(stamp) for stamp in times]
            for stamp,frame in zip(times,frames):
                if frame['dense'] and not frame['positive'] and scrolling(frame,get(stamp+1)):
                    frame.update(positive=True, roles=['verified scrolling credit text'])
            if sequence_confirmed(frames):
                start = t
                # Coarse hits may be after the first card; refine the prior interval.
                for stamp in range(math.ceil(max(low,t-120)),math.ceil(t),2):
                    candidate=get(stamp)
                    if candidate['positive']:
                        # Don't trust an isolated credit-like subtitle before the confirmed run.
                        support=[get(min(stamp+i,high)) for i in (4,8,12)]
                        if sum(s['positive'] for s in support)>=1:
                            start=stamp
                            break
                return dict(start=round(start,2), confidence=.94, samples=len(cache),
                    note='Credit headings and sustained credit sequence recognized locally',
                    evidence=dict(roles=sorted({r for s in frames for r in s['roles']}),
                        opening_text=get(start)['texts'][:10], confirmed_at=times,
                        scan_start=round(low,2), detector_version=VERSION))
        t += 30
    return dict(start=None, confidence=0, samples=len(cache), note='No sufficiently confident visual credit sequence found',
        evidence=dict(detector_version=VERSION,scan_start=round(low,2)))


class Analyzer:
    def __init__(self, path, timeout=300):
        import numpy as np
        import onnxruntime as ort
        import rapidocr
        from rapidocr import RapidOCR
        ort.disable_telemetry_events()
        logging.getLogger('RapidOCR').setLevel(logging.ERROR)
        model_root = Path(rapidocr.__file__).parent / 'models'
        names = dict(Det='PP-OCRv6_det_small.onnx',Rec='PP-OCRv6_rec_small.onnx',Cls='ch_ppocr_mobile_v2.0_cls_mobile.onnx')
        if not all((model_root/name).is_file() for name in names.values()):
            raise RuntimeError('Bundled OCR models missing; reinstall the pinned rapidocr dependency')
        params = {'Global.log_level':'error','Global.use_cls':False,
            'EngineConfig.onnxruntime.intra_op_num_threads':1,
            'EngineConfig.onnxruntime.inter_op_num_threads':1}
        params.update({kind+'.model_path':str(model_root/name) for kind,name in names.items()})
        self.engine = RapidOCR(params=params)
        self.path = path
        self.deadline = time.monotonic()+timeout
        self.np = np

    def frame(self, stamp):
        from .media_tools import binary
        if time.monotonic() >= self.deadline: raise TimeoutError('Credits analysis time budget exceeded')
        executable=binary('ffmpeg')
        if not executable: raise RuntimeError('FFmpeg is unavailable')
        result=subprocess.run([executable,'-v','error','-nostdin','-threads','1','-ss',str(stamp),'-i',str(self.path),
            '-map','0:V:0','-frames:v','1','-vf',f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2',
            '-threads','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,timeout=20,check=True)
        if len(result.stdout)!=WIDTH*HEIGHT*3: raise RuntimeError('Unable to decode movie sample')
        return self.np.frombuffer(result.stdout,dtype=self.np.uint8).reshape(HEIGHT,WIDTH,3)

    def sample(self, stamp):
        from rapidocr.ch_ppocr_rec import TextRecInput
        import cv2
        image=self.frame(stamp)
        detected=self.engine(image,use_det=True,use_cls=False,use_rec=False)
        boxes=getattr(detected,'boxes',None)
        if (boxes is None or not len(boxes)) and float((image.mean(axis=2)<65).mean())>.8:
            # Colored outline titles on dark backgrounds can be near-invisible to OCR.
            gray=self.np.clip(image.max(axis=2).astype(self.np.float32)*2.5,0,255).astype(self.np.uint8)
            image=self.np.repeat(gray[:,:,None],3,axis=2)
            detected=self.engine(image,use_det=True,use_cls=False,use_rec=False)
            boxes=getattr(detected,'boxes',None)
        if boxes is None or not len(boxes): return describe_frame([])
        # Read at most 32 lines per frame: large rolls can contain hundreds.
        selected=list(boxes)
        if len(selected)>32:
            indexes=self.np.linspace(0,len(selected)-1,32,dtype=int)
            selected=[selected[i] for i in indexes]
        crops=[]; bounds=[]
        for box in selected:
            x0=max(0,int(box[:,0].min())-2);x1=min(WIDTH,int(box[:,0].max())+3)
            y0=max(0,int(box[:,1].min())-2);y1=min(HEIGHT,int(box[:,1].max())+3)
            if x1<=x0 or y1<=y0: continue
            # Rectify slanted animated titles before recognition.
            width=max(4,int(max(self.np.linalg.norm(box[0]-box[1]),self.np.linalg.norm(box[2]-box[3]))))
            height=max(4,int(max(self.np.linalg.norm(box[0]-box[3]),self.np.linalg.norm(box[1]-box[2]))))
            target=self.np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]],dtype=self.np.float32)
            matrix=cv2.getPerspectiveTransform(box.astype(self.np.float32),target)
            crops.append(cv2.warpPerspective(image,matrix,(width,height),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE))
            bounds.append((y0/HEIGHT,y1/HEIGHT))
        if not crops: return describe_frame([])
        read=self.engine.text_rec(TextRecInput(img=crops))
        lines=[dict(text=text,confidence=float(score),y0=bound[0],y1=bound[1]) for text,score,bound in zip(read.txts or (),read.scores or (),bounds)]
        dark=float((image.mean(axis=2)<65).mean())
        return describe_frame(lines,dark)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--path',required=True);parser.add_argument('--duration',type=float,required=True);parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args()
    try:
        os.nice(10)  # One low-priority CPU worker; preserve playback resources.
        analyzer=Analyzer(Path(args.path),args.timeout)
        result=detect(args.duration,analyzer.sample)
        print(json.dumps(result),flush=True)
    except Exception as exc:
        print(json.dumps(dict(error=type(exc).__name__,note='Visual credits analysis could not complete')),flush=True)
        raise SystemExit(1)

if __name__=='__main__': main()
