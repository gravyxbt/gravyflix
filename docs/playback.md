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
