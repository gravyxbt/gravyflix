# Automatic subtitles

Gravyflix discovers captions after library scanning. No manual extraction is needed.
It uses matching sidecar files and embedded text tracks first. When a selected
subtitle language exists only as an embedded DVD bitmap track (`dvd_subtitle`),
it automatically converts that track to timed SRT text with local OCR. Roku uses
SRT; the web/Cast interface serves the same cues as WebVTT. Caption controls remain
available during playback.

Conversion runs in the background, one track at a time, using the bundled OCR model.
Video is not re-encoded and original files are unchanged. Select subtitle languages
in the dashboard or `SUBTITLE_LANGUAGES`; English is the default. An already-ready
full text track avoids unnecessary conversion. If local tracks do not cover the
selected language, existing OpenSubtitles discovery remains the fallback and
respects its daily allowance. Local OCR does not use that allowance.

New rips enter the queue automatically after the next library scan. Existing files
are reconsidered once when this feature is installed. The initial library pass can
take hours, depending on subtitle count and CPU speed; tracks become available
individually as they finish. Refresh the library after conversion to update badges.

The dashboard distinguishes queued/converting embedded tracks from ready captions.
Browse badges count only usable text tracks. Ready captions are cached under
`data/subtitles`; conversion is repeated if the source changes, a cached output
is missing, the selected languages change, or the converter version changes.
A restart cancels the active subprocess; unfinished work resumes on the next pass.

The decoder retains the source's subtitle timestamps, with no speech-alignment
pass needed. OCR can still misread words or punctuation. Conversions with missing
cues or too many low-confidence cues are rejected rather than published as complete.
Local `.ocr.json` reports contain timing, quality statistics and a few recognized
lines for troubleshooting. These are private runtime files, not public source.

This first converter handles embedded four-color DVD/VobSub tracks in video files.
Blu-ray PGS/DVB image subtitles and external `.idx`/`.sub` pairs need a separate
conversion path and are not converted by this implementation. Embedded text tracks
and `.srt`, `.vtt`, `.ass`, `.ssa` sidecars continue to work as before.
