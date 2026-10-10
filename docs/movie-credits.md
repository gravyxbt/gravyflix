# Automatic movie credits and Up next

Gravyflix analyzes movies in the background and saves a credits-start marker. Roku build
**00019** and the web remote show Up next at that marker; episodes keep the final-30-second
window. OK / Play next uses the existing playback flow and three-autoplay confirmation.
Automatic playback still waits until the actual file ends, so you decide whether to skip
credits or continue watching. Rewinding before the marker hides the prompt.

## How automatic recognition works

1. Prefer a named end-credits chapter when the file includes one.
2. Otherwise examine small frames from the movie's last 15 minutes (or last quarter for
   shorter movies).
3. Read text locally with bundled RapidOCR models. Look for cast/crew headings, credit
   layouts, and sustained sequences; verify upward movement for unlabeled rolling text.
4. Confirm across several frames, then sample the boundary more closely to find the start.
5. Save confident results in SQLite. Cache both successful and inconclusive analysis so
   unchanged movies are not repeatedly decoded.

This runs **before playback**, not live on your Roku. Each movie usually takes a few
minutes to analyze. An existing large library can take hours on its first pass; newly
added movies receive priority between batches of three. Dashboard → **Movie credits**
shows pending/analyzing/ready/no-match/error states and the source of a detected marker.
Results apply when the movie is next started.

Movies are sampled one at a time at lower CPU priority, with one inference thread,
960×540 frames, at most 100 samples, and a five-minute analysis deadline by default.
Audio is not decoded or changed. Original files remain untouched. New visual analysis
is deferred while Roku-compatible playback preparation is queued/running. Already-running
analysis remains at low priority. A cross-process lock prevents duplicate dashboard and
automatic scans. Shutdown terminates the analyzer and its FFmpeg process group.

## Accuracy and review

Recognition is conservative, not guaranteed or frame-perfect. Dark animated cards,
credits over scenes, unusual languages/layouts, or movies with very long closing sequences
can be missed or marked slightly late. Runtime percentages alone never create a marker.
Uncertain files keep the original final-30-second fallback.

Manual timing remains an optional correction, not the normal workflow:

1. Open `/manage#credits` and search for the movie.
2. Enter HH:MM:SS (for example `01:41:32`) or seconds, then save.
3. Start playback again to use the updated marker.

**Use final 30 seconds** disables earlier prompts for that file. Reviewed choices take
priority even if made while an automatic analysis is running. Source replacement/modification
invalidates old markers. Series episodes and extras are excluded from movie analysis.

## Setup and controls

Install `backend/requirements.txt` or run the normal setup script. Python **3.11+** is
required by the CPU OCR runtime. Models are included in the pinned `rapidocr` wheel;
there are no model downloads during analysis and no movie frames sent to cloud services.
No system OCR package, GPU, or provider account is needed.

- `AUTO_CREDITS=true`: enable the background credits worker.
- `AUTO_VISUAL_CREDITS=true`: use local visual analysis when chapter metadata is absent.
- `CREDIT_ANALYSIS_TIMEOUT=300`: per-movie time budget, capped at 900 seconds.

The first two settings are available in the dashboard; save/restart to change them.
**Analyze movie endings** requests one batch of up to three unprocessed movies. The
automatic worker continues the queue. Transient failures retry after one hour; results
that have no confident match are retried only after the file or detector version changes.

## API and implementation

- `GET /api/movies/{id}/credits`: state, start, method, note, analysis version and score.
- Movies/catalog items include `credits_start` (seconds or null).
- Cast status includes `up_next_visible`; `remaining` still means time to the file end.
- Same-origin management: `PUT /api/manage/credits/{id}` with `{ "start": 6092 }` or
  `{ "disabled": true }`, and `POST /api/manage/credits/process`.

`credit_markers` is migrated additively with detector version, evidence, retry time, and
heuristic confidence. The score is an internal rule score, not a calibrated probability.
The file signature remains compatible with existing chapter/manual markers.

Detector: `backend/app/credit_detection.py`; worker and persistence: `backend/app/credits.py`.
Tests cover real local OCR on rendered credit cards, temporal confirmation, captions and
black-frame rejection, moving text, chapters, negative caching, retry state, manual-edit
races, and playback-preparation priority. Real movie boundary frames are also inspected.

References: [RapidOCR usage](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/),
[FFmpeg seeking and stream selection](https://www.ffmpeg.org/ffmpeg.html).
