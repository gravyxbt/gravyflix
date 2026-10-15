# Playback and shared watch history

All clients use shared household history. Every media file keeps its own persistent
SQLite ID; series cards aggregate the most recently watched unfinished regular
episode. On Roku Home, Resume and Continue Watching start that episode directly.
TV Shows, Recently Added and genre cards retain the season/episode browser.

Progress saves about every 15 seconds and on playback state changes. A newer
successfully started session takes precedence over older sessions for that file.
Backward seeks are preserved. Failed preparation does not erase progress. After
power loss or Home-button exit, the last periodic save is the available resume point.
Start over and automatic next-title playback begin at zero. Replacing a file
invalidates old resume timing. Existing Cast-only history migrates once.

## Delivery choices

The backend inspects codecs rather than trusting the extension. Compatible MP4s
play directly. Other containers can be remuxed without changing the video/audio.
Incompatible audio becomes AAC stereo while compatible video is copied. Video
outside the receiving profile is prepared as H.264/AAC using FFmpeg. The original
file is never changed. Roku can submit source-specific decoder information; unknown
receivers use a conservative SDR/1080p/30fps baseline.

Use Options (*) on Roku's details page or the phone's Playback selector for
Automatic, Compatible H.264/AAC or Original file. HDR requiring unverified tone
mapping is rejected instead of silently producing incorrect SDR. Only a confirmed
decoder rejection triggers one automatic compatible retry; network timeouts do not
start conversion loops. The disk-budgeted cache supports cancellation, leases and
next-episode preparation. First playback can take time; later playback reuses it.

## Diagnostics

Open `/manage#playback`. Sessions show client type, state, progress, delivery reason,
preparation time, time to first Playing and reported buffering. Download diagnostics
exports bounded JSON without API keys, passwords, source URLs, device serials or
absolute media paths. Reports still contain title/history information: review them
before attaching to a public issue. Personal watch history remains in the ignored database.

Ended diagnostics expire after seven days; events are bounded to 200 per session.
Inactive sessions expire after 24 hours. The report includes at most 1,000 sessions
and the latest 2,000 events. Reported Playing does not prove that frames are being
rendered: decoder freezes, TV health and Wi-Fi signal cannot be measured here.

## Device checks

Watch briefly on Roku, exit, refresh the phone and resume on Cast. Seek backward,
stop and resume on Roku. Check Start over, direct MP4, MKV audio, AVI, captions,
Skip Intro and episode autoplay. Consult diagnostics for failures and preparation.

## Back during the next-title countdown

Back while the countdown is visible dismisses it and cancels autoplay for that
title. The next Back press exits playback to the title page, for movies and
episodes alike. The countdown is visually selected without taking keyboard focus from Video,
so cancelling it cannot trap pause/seek/Back in a hidden node. OK plays the next
title while the countdown is visible. The Video component sends an explicit exit command so native
player key handling cannot swallow that press after focus returns from the overlay.
Exiting saves progress, cancels background preparation and queued autoplay, then
stops playback. Late finished/stopped notifications cannot start another title.

## Completion when leaving credits

Leaving playback with Back, Stop or Next during a movie's verified credits marks
that movie completed in shared watch history. Without a credits marker, completion
uses the existing final-30-second ending window. Episodes use their current
final-30-second ending window too; only the episode you watched is completed, not
unwatched episodes or the whole series. Normal playback/pausing in the ending
window does not complete an item until you exit, skip or reach the end. Decoder
errors and cancelled preparation do not count as finishing.

Completed items are removed from Roku's cached Continue Watching shelf after the
history save is acknowledged, with your remaining browsing selection preserved.
A started series stays in that shelf while regular episodes remain unfinished,
pointing to the current episode or the next episode after completion.
The completion policy is shared by Roku and Cast; replaying a completed title
starts from the beginning and can create new unfinished progress.

### Continuing a series

Continue Watching remembers the most recently watched regular episode across Roku and casting. Stop partway through to resume that episode; finish it (or exit/advance in its final 30 seconds) to continue with the next unfinished episode, across seasons. The action says **Next Episode** when it starts at the beginning. Extras do not change the series position. A series you have not started stays out of this shelf; a fully completed series leaves it. If you reach the last available episode with earlier gaps, the first unfinished episode is offered. Newly added episodes make a previously finished series eligible again after the library scan. Progress is stored in SQLite and survives server and client restarts.

Roku refreshes Continue Watching after a saved playback session without rebuilding the other shelves or resetting your browsing position.
