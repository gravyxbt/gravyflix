"""Local Chromaprint alignment; no network or movie-specific timing guesses."""
from collections import Counter, defaultdict
import math
import statistics

# Chromaprint algorithm 1/Test2: 4096 frame, 2/3 overlap, 11025 Hz.
STEP = 1365 / 11025
DELAY = (19 * 1365 + 2731) / 11025
VERSION = 1
MIN_SECONDS = 15
MAX_SECONDS = 100


def chapter_marker(chapters, duration):
    for chapter in chapters:
        name = str(chapter.get('tags', {}).get('title', '')).strip().casefold()
        if name not in {'intro', 'opening', 'opening credits', 'title sequence', 'opening titles'}:
            continue
        try:
            start, end = float(chapter['start_time']), float(chapter['end_time'])
        except (KeyError, ValueError, TypeError):
            continue
        if all(map(math.isfinite, [start, end])) and 0 <= start < end < duration and start < 600 and 3 <= end-start <= 120:
            return {'start': start, 'end': end, 'confidence': 1.0, 'method': 'chapter', 'evidence': 1}
    return None


def pair_match(a, b):
    """Vote on audio alignment using non-constant 16-bit anchors, then verify bits."""
    if len(a) < 150 or len(b) < 150:
        return []
    positions = defaultdict(list)
    for j, value in enumerate(b):
        for shift in (0, 16):
            positions[(shift, (value >> shift) & 65535)].append(j)
    votes = Counter()
    for i, value in enumerate(a):
        for shift in (0, 16):
            hits = positions.get((shift, (value >> shift) & 65535), [])
            if len(hits) <= 12:  # Silence/constant tones must not dominate alignment.
                for j in hits:
                    votes[j-i] += 1
    intervals = []
    for offset, count in votes.most_common(20):
        if count < 20:
            continue
        first, last = max(0, -offset), min(len(a), len(b)-offset)
        good = [i for i in range(first, last) if (a[i] ^ b[i+offset]).bit_count() <= 6]
        if not good:
            continue
        runs = []; run = [good[0]]
        for i in good[1:]:
            if i-run[-1] <= 5:
                run.append(i)
            else:
                runs.append(run); run = [i]
        runs.append(run)
        for run in runs:
            span = run[-1]-run[0]+1
            if not MIN_SECONDS <= span*STEP <= MAX_SECONDS:
                continue
            if len(run)/span < .87 or len({a[i] for i in run}) < 30:
                continue
            errors = statistics.mean((a[i] ^ b[i+offset]).bit_count() for i in run)
            if errors > 3.5:
                continue
            # Fingerprints integrate multiple seconds. Keep the skip destination
            # conservative instead of adding the entire analysis delay to the end.
            start = max(0, run[0]*STEP + DELAY/2)
            end = (run[-1]+1)*STEP + DELAY/2
            candidate = {'start': start, 'end': end, 'confidence': round(1-errors/32, 3)}
            if not any(abs(start-x['start']) < 3 and abs(end-x['end']) < 3 for x in intervals):
                intervals.append(candidate)
    return intervals


def consensus(matches):
    """Require the same interval from two distinct other episode identities."""
    groups = []
    for identity, candidates in matches:
        for candidate in candidates:
            group = next((g for g in groups if abs(g[0][1]['start']-candidate['start']) <= 3
                          and abs(g[0][1]['end']-candidate['end']) <= 3), None)
            if group is None:
                groups.append([(identity, candidate)])
            elif identity not in {x[0] for x in group}:
                group.append((identity, candidate))
    verified = [g for g in groups if len(g) >= 2]
    if not verified:
        return None
    # Multiple repeated passages could be a recap or song, not a verified intro.
    if len(verified) != 1:
        return None
    group = verified[0]
    return dict(start=round(statistics.median(x[1]['start'] for x in group), 2),
                end=round(min(x[1]['end'] for x in group), 2),
                confidence=round(min(x[1]['confidence'] for x in group), 3),
                method='audio_consensus', evidence=len(group)+1)
