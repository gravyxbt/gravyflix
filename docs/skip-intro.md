# Skip Intro on Roku

Install Roku build 00017 (`dist/my-media.zip`) to enable this feature. The lower-right
**Skip Intro · OK** button appears for up to ten seconds during a detected opening.
Press OK while it is visible to seek to the opening's end. Ignoring it never skips
automatically. The Video keeps focus throughout; after dismissal/expiry, OK returns
to pause/play. Play/Pause continues to control transport even when the button is up.
A visible native seek timeline always owns OK. Directional seeking and Options
hide the prompt; Back keeps the existing playback-exit behavior. The prompt appears
once per playback session; replaying the intro does not repeatedly interrupt you.

## Automatic detection

Ubuntu analyzes regular series episodes locally in a background thread, independently
of artwork and subtitles. It reads explicit Intro/Opening/Title Sequence chapter labels
when available. Otherwise it fingerprints only the first ten minutes (or 40% of a
shorter episode) of audio with FFmpeg's Chromaprint muxer. It aligns repeated audio
within a season, even when different-length cold opens move the theme. Audio detection
requires three distinct episode identities; duplicate encodes count as one episode.
Matching passages must last 15–100 seconds, have changing fingerprints, and agree
in position and duration across at least two other episodes. Multiple plausible
repeated passages are left unmatched. At most eight independent reference episodes
per season are used to bound comparison work.

This is a conservative repeated-audio detector, not semantic understanding of every
TV opening. Changed themes, very short intros, alternate audio mixes, long cold opens,
recaps, or seasons with fewer than three episodes can remain unmatched. Shared studio
logos contiguous with a theme may be part of the detected opening. Timing is approximate
and chooses a conservative endpoint; it can leave a little of the theme instead of
intentionally seeking beyond the matching passage. It is not a promise of exact edits
for every show. Reviewed markers can correct or disable a detection.

Episodes without a confident marker play normally with no skip button. Movies,
extras and specials are not automatically compared. Text chapter markers do not need
multiple episodes. Original videos are never changed and no content is uploaded.
No new external account or download quota is required. FFmpeg must include Chromaprint;
the project-local FFmpeg installed on this server does.

## Scanning and storage

`AUTO_INTROS=true` is the default; set false in `.env` and restart the backend to stop
automatic analysis. A pass starts ten seconds after startup, then runs on the configured
library interval (normally five minutes after the preceding pass). A manual scan through
`POST /api/library/scan` also wakes it. Analysis time depends on episode count/audio codecs;
the first pass takes longer. Fingerprints and marker/no-match results are cached in
SQLite `intro_fingerprints` and `intro_markers`. Adding episodes changes the comparison
scope and revisits previous unmatched files. File size/mtime changes invalidate markers.

API: `GET /api/movies/{id}/intro` returns `{state, intro, note}`; ready markers include
`start`, `end` (seconds), `method`, `confidence`, and `evidence`. Playback Tasks fetch
this metadata before starting Video. An unavailable detector/endpoint never blocks
playback. Background work stays off Roku's render thread and HTTP playback handlers.
The feature currently adds a Roku overlay; it does not add a custom Vizio TV overlay.

```bash
cd ~/roku-media-server
PYTHONPATH=backend .venv/bin/python scripts/intros.py status
PYTHONPATH=backend .venv/bin/python scripts/intros.py scan --show "The Office"
# Or analyze every series:
PYTHONPATH=backend .venv/bin/python scripts/intros.py scan
# Review a single episode; seconds measured in its ORIGINAL video:
PYTHONPATH=backend .venv/bin/python scripts/intros.py set --movie-id 123 --start 45 --end 76
PYTHONPATH=backend .venv/bin/python scripts/intros.py disable --movie-id 123
```

Manual settings survive subsequent analysis until the media source changes. Restart
the title to fetch newly reviewed markers. Removing a `disabled` setting currently
requires setting a reviewed interval with `set`; automatic scanning deliberately
preserves reviewed disable decisions.

## Validation and installing

```bash
./scripts/test.sh
./scripts/test-roku-ui.sh
BACKEND_URL=http://192.0.2.10:8080 ./scripts/package-roku.sh
# Set your existing ROKU_DEV_TARGET and DEVPASSWORD first:
./scripts/install-roku.sh
```

Alternatively upload `dist/my-media.zip` through the Roku Developer Application
Installer, username `rokudev`, using your developer password. This feature changes
Roku code, so refreshing the library alone is insufficient; install the new package.

Tests cover shifted repeated audio (including real FFmpeg extraction), unrelated audio,
constant fingerprints, short logos, duplicate encodes, consensus ambiguity, chapters,
manual overrides and source invalidation. BrightScript tests cover the ten-second
window/expiry, skip seeking, held OK, pause/play restoration and native seek priority.
Physical Roku verification is still necessary for button placement, real Timer events,
seek precision on the specific device, caption synchronization after skipping, and
continued Up Next/Back behavior. Before testing, make sure the chosen episode's API
has a ready marker. A missing prompt on an unmatched episode is expected.

References: [Roku Video node](https://developer.roku.com/dev/docs/video),
[FFmpeg Chromaprint muxer](https://ffmpeg.org/ffmpeg-formats.html#chromaprint-1),
[Chromaprint timing configuration](https://github.com/acoustid/chromaprint/blob/master/src/fingerprinter_configuration.h).
