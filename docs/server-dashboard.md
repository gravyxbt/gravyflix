# Gravyflix server dashboard

Open `http://YOUR_SERVER_LAN_IP:8080/manage` on a phone or computer on your home network.
The gear link on the watch page opens the same dashboard. No Roku update is required.

- **Overview:** media counts, storage, playback cache, media-tool checks, and library service status.
- **Media library:** search grouped movies and shows; open a title for episodes, paths, codecs, and subtitle/intro information. **Scan library** discovers files without waiting for the next automatic pass.
- **Artwork review:** choose from the public-source matches reported by the existing matcher. The choice is persisted in `config/artwork-matches.json` and the selected artwork is fetched in the background. **Find missing artwork** respects the importer's existing retry interval.
- **Subtitles:** see ready tracks and discovery notes, including missing matches, provider quota, or configuration requirements. **Check for subtitles** respects the existing download budget and retry policy; it does not force downloads of already processed files.
- **Skip intros:** review status, enter start/end times in seconds, or disable skipping for an individual file. Manual timing persists through background analysis and takes effect on the next playback.
- **Movie credits:** see automatic chapter/visual detection progress or correct an HH:MM:SS start for earlier movie Up next prompts. Episodes retain their final-30-second timing. See [Movie credits](movie-credits.md).
- **Server settings:** configure an existing media folder, scan interval, TV address, background services, subtitle languages/budget, and playback cache/encoder. Changes are saved to `.env`; they require a server restart. API keys are write-only; leaving the field blank preserves the existing key. Process environment variables take precedence over `.env`.
- **Setup & devices:** media naming guide, server instructions, Cast setup, and a downloadable Roku package. Open this page at a LAN-reachable address before downloading: the ZIP is configured for that browser address without changing the source files or existing packaged ZIP.

## Applying settings

The dashboard does not interrupt playback or restart services automatically. After saving,
restart when nobody is watching:

```bash
systemctl --user restart roku-media-server.service
```

If running in the foreground, stop with Ctrl-C and run `./scripts/start.sh` again.
If your service uses another name, restart your own service. Scan the library after changing
the media folder. Folder changes do not move or delete files; missing old paths are hidden
by the next scan. A folder must exist and be readable before it can be selected.

## Background actions and safety

Management actions run one at a time, outside HTTP/UI threads. Progress is a visible
queued/running/done/error state, not a per-file percentage. The last 20 management jobs
are kept in memory; they reset when the server restarts. Restarting ends in-flight management work; retry unfinished actions after startup. Existing automatic workers
continue using their own scheduling and locking. Errors are logged in the server journal:

```bash
journalctl --user -u roku-media-server.service -n 100 --no-pager
```

Like the existing watch-and-cast controls, this dashboard is for a trusted LAN and does
not provide user accounts. Management APIs require a custom same-origin header and reject
foreign origins; `.env` and stored API keys are never served. Do not publish this server
on the Internet. The dashboard does not install system packages, alter router settings,
rename media, or delete originals. Initial Python/FFmpeg installation still follows the
README; the dashboard is available after the backend is running.

## Validation

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_management.py -q
# In one terminal (localhost-only UI test server; no background workers):
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8081 --lifespan off
# In another terminal, from the project directory:
node scripts/test-dashboard.cjs
```

Browser tests mock management and TV operations. They verify desktop/phone layouts,
library details, artwork approvals, intro editing, settings saves, and setup feedback.
Screenshots are saved in `dist/dashboard-test-*.png`. Stop the temporary test server
with Ctrl-C when finished.
