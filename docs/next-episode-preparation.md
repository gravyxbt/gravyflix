# Prepare the next episode while watching

Roku build **00018** starts preparing the next series episode as soon as the current
Video enters playing. It uses the same episode order as Up Next/autoplay: across
seasons, skipping duplicate encodes and covered combined episodes. Only one next
episode is held per Roku app session. MKV and AVI targets use the existing compatible
playback pipeline; direct MP4 targets need no preparation. Movie recommendations,
extras/specials with no regular next episode, Original audio mode and cancelled
autoplay do not trigger lookahead.

The original video is never modified. H.264 MKVs keep their video and convert audio
to AAC stereo in the cached MP4, as before. AVI and other incompatible video codecs
still use the existing video conversion settings. No second FFmpeg worker, GPU
change or new external service is introduced.

## What to expect

The first uncached episode still needs normal preparation. Later episodes can start
from an already-ready cached copy. If you jump to the next episode very early or a
conversion takes longer than the current episode, Play waits only for the remaining
work; it shares the running job instead of starting over. Cache-full, decode or network
failures during speculation are logged, do not interrupt the current episode, and
normal Play remains the fallback.

The preparation Task polls every 15 seconds, including when the current video is paused,
to keep the next cache entry protected from eviction. No networking runs on Roku's UI
thread. While handing off to the next episode, the old lookahead lease remains alive
until the new foreground playback lease has been acquired and playback is ready.
This prevents cancellation and wasted re-conversion during Up Next transitions.

Back/Stop, manual title selection and Cancel next release unwanted background work.
Completed cached copies remain eligible for later reuse under the existing cache
size/eviction policy. If the Roku disconnects, its unrenewed lease expires after
120 seconds when the cache next processes leases. Preparation errors expire/release
normally; originals are untouched.

## Foreground priority and multiple Rokus

The playback API accepts an optional `purpose` field:

```json
{"movie_id": 123, "purpose": "prefetch"}
```

Omitting it means foreground playback. The existing single FFmpeg worker is retained.
A new uncached foreground title cancels queued/running conversions held exclusively
by background leases, freeing the worker once cancellation cleanup finishes. A job
with any foreground viewer remains protected. Foreground loading of the same prefetched
file adds a foreground lease to the existing job and reuses the same result. Cache
capacity and free-disk-space checks still apply, including reservations for jobs that
are shutting down. A ready stream/cache hit does not cancel background work merely
because a player requests another video byte range.

Several Rokus can share a conversion/cache entry using independent leases. One client
canceling its lookahead cannot cancel an episode another client is actively preparing.
This feature concerns Roku preparation; Vizio continues to stream original files.

## Installation and troubleshooting

The backend must run the updated code, and the Roku needs the new ZIP. Refreshing
its catalog alone does not install the Task/controller change.

```bash
cd ~/roku-media-server
BACKEND_URL=http://192.0.2.10:8080 ./scripts/package-roku.sh
# With your existing ROKU_DEV_TARGET and DEVPASSWORD set:
./scripts/install-roku.sh
```

Or upload `dist/my-media.zip` through the Roku Developer Application Installer,
username `rokudev`, with your developer password. Build 00018 also includes Skip Intro.

Watch a regular MKV episode long enough for the next one to finish preparing, then
select Up Next or let autoplay proceed. Logs should show:

- Roku: `PREFETCH: preparing next`, then `ready for next playback`.
- Backend: existing `ROKU AUDIO` preparation logs; a new manual load may log
  `PREFETCH: yielding ... to foreground playback`.
- Next foreground request: `state: ready` with the same generated cache file.

Use `journalctl --user -u roku-media-server.service -f` for server logs and
`nc ROKU_IP 8085` for Roku console logs. Cache files remain under `ROKU_CACHE_DIR`
(default `data/roku-cache`); `ROKU_CACHE_MAX_GB` retains its existing default of 50.

## Files and verification

`PrefetchTask.xml/.brs` perform the async request/heartbeat/cleanup.
`PrefetchController.brs`, `AutoplayController.brs` and `MainScene.brs/.xml` control
selection and safe handoff. `playback_api.py` labels requests and `roku_audio.py`
tracks background-only leases for foreground priority. Tests cover actual FFmpeg
conversion/cache reuse and range delivery, incomplete-job promotion, priority,
multi-client protection, expiry, eligibility, cancellation and autoplay handoff.

```bash
./scripts/test.sh
./scripts/test-roku-ui.sh
```

Physical Roku verification is still needed for real playback-to-prefetch timing,
Back/Stop cleanup, the still-watching prompt, and the next episode's startup delay.
No TV playback was started during implementation tests.
