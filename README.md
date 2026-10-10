# Gravyflix

A private, self-hosted media library for your home network. A Linux or Apple Silicon Mac server stores
movies and TV episodes; a BrightScript/SceneGraph Roku app and an Android-friendly
web remote browse and play them. The phone controls a configured Google Cast/Vizio
receiver; movie bytes travel from the server to the TV.

## Features

- Cinematic Roku and web home screens with artwork, genre shelves and TV seasons.
- Shared household Continue Watching, Resume and Start over across Roku and Cast.
- HTTP byte-range streaming and codec-aware direct play, remuxing and conversion.
- Automatic public-source artwork matching with a review queue for ambiguous titles.
- Embedded/local subtitles, optional OpenSubtitles downloads and timing alignment.
- Intro skipping, movie credits detection, Up Next and bounded episode/movie autoplay.
- Next-episode preparation using a disk-budgeted conversion cache.
- Local management dashboard and playback diagnostics with downloadable reports.

This release uses FastAPI, SQLite and FFmpeg. It does not require TMDB credentials.
It is designed for a **trusted home LAN** and has no user login or Internet-facing
security boundary. Do not forward its port or expose its management dashboard publicly.

## Server setup

Requirements: Ubuntu/Linux with Python 3.11+, or Apple Silicon macOS 14+ with native
Python 3.13; FFmpeg and ffprobe on both. Node.js/npm are needed
for Roku compiler/browser development checks, not for running the Python backend.

Apple Silicon users: follow [macOS setup](docs/macos.md) for native Python, FFmpeg,
Mac network permissions and the optional login service. Windows and Intel Macs are
not supported by this setup yet.

On Linux, extract or clone the source into `~/gravyflix`, then:

```bash
cd ~/gravyflix
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
command -v ffmpeg ffprobe
```

If venv is unavailable, install Ubuntu's matching `python3-venv` package or use
`uv venv .venv`. If FFmpeg is unavailable, install your distribution's `ffmpeg`
package. An optional project-local download is available through
`./scripts/setup-media-tools.sh` after installing backend dependencies.

Edit `.env` for your setup:

```dotenv
MOVIES_DIR=media/Movies
HOST=0.0.0.0
PORT=8080
CAST_HOST=
OPENSUBTITLES_API_KEY=
```

Leave `CAST_HOST` blank if you only use Roku. For Vizio/Cast, set it to the TV's
LAN IPv4 address. API keys and developer passwords belong in local configuration
or environment variables; never commit them. `.env` is intentionally ignored.

```bash
./scripts/start.sh
# In another terminal, after copying videos into media/Movies:
./scripts/scan.sh
curl http://localhost:8080/health
curl http://localhost:8080/api/movies
```

The scanner recurses through the library every five minutes by default. Artwork
matching runs in the background; ambiguous matches appear in Artwork review.
Use the server's LAN address from another device, including `http://YOUR_SERVER_LAN_IP:8080/health`.
A DHCP reservation can keep this address stable. Allow LAN traffic through your
firewall/VPN if needed; do not configure Internet port forwarding.

For a disposable sample, `./scripts/create-test-video.sh` creates a 12-second
H.264/AAC MP4 locally. Test videos and personal media are not distributed here.

## Manage and organize

Open `http://YOUR_SERVER_LAN_IP:8080/manage` for scans, artwork review, subtitles,
intro/credits status, settings, Roku downloads and Playback diagnostics. Settings
changes require a backend restart. The watch-and-cast page is at `/`.

Read [Organizing your media](docs/organizing-your-media.md) before importing a
library. Example: `Example Show/Season 1/Example Show.S01E02 - Episode Title.mkv`.
Local corrections belong in `config/*.json`; fictional templates are included as
`config/*.example.json`. These runtime correction files are ignored because they
can reveal personal library contents. Copy a template to its corresponding name
only when you need an override; the backend works without any override files.

## Roku setup

1. On the Roku remote press Home three times, Up twice, Right, Left, Right, Left,
   Right to open Developer Settings. Enable the installer, accept the terms and
   set a developer password. Note the Roku's IP address.
2. Open `http://ROKU_IP` on a computer on the same network. Sign in as `rokudev`
   using the password you created.
3. Open Gravyflix's dashboard at the **LAN server URL**, choose Setup & devices,
   and download the Roku ZIP. It is configured for the address used by the browser.
4. Upload it to the Roku Development Application Installer and select Install
   or Replace. Replacing the package updates the development app.
5. Launch the development app from Roku Home. Use Options (*) on the home screen
   to scan/refresh. During playback, OK pauses/resumes or confirms a native seek;
   Options opens Roku's caption controls. A series' Resume action and its Continue
   Watching card resume the saved episode directly.

To package from the shell:

```bash
BACKEND_URL=http://YOUR_SERVER_LAN_IP:8080 make roku-package
```

`dist/my-media.zip` is the output. `roku/source/Config.brs` contains a documentation-only
address and must be overridden for a real installation. Generated packages can
contain your server address; they are ignored and should not be published.

Optional shell sideloading:

```bash
export ROKU_DEV_TARGET=YOUR_ROKU_IP
read -rsp 'Roku developer password: ' DEVPASSWORD; echo
export DEVPASSWORD
make roku-install
unset DEVPASSWORD
```

View Roku logs with `telnet ROKU_IP 8085` or `nc ROKU_IP 8085` on the LAN. Do not
share raw logs without reviewing titles, URLs and network information.

## Android and Vizio/Cast

Set `CAST_HOST` to the receiver's address, restart the backend, and open the server
URL in Android Chrome. Select a title and Play on TV. The phone acts as the remote;
its screen does not play the movie. The TV may need Internet access to launch
Google's hosted receiver even though media stays on the LAN. Only one configured
Cast receiver is supported initially; multiple Roku clients can use the server.

Shared history is household-wide. Progress saves about every 15 seconds and on
state changes. Continue Watching points to unfinished regular episodes, not extras.
See [Playback and history](docs/playback.md) for conversion and diagnostics limits.

## Optional background service

On macOS, use the optional [login service](docs/macos.md#optional-login-service).
The Linux user-level systemd unit assumes `~/gravyflix`; adjust its two paths if
installed elsewhere. Install it only after foreground playback works:

```bash
mkdir -p ~/.config/systemd/user
cp services/roku-media-server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now roku-media-server.service
journalctl --user -u roku-media-server.service -n 100 --no-pager
```

Stop the foreground server first so only one process binds port 8080. This user
service normally follows your login session; boot-before-login requires separate
systemd user-session configuration.

## Development and checks

```bash
./scripts/setup.sh                 # Includes test dependencies
npm ci                            # Optional Roku/browser tooling
make test
make roku-test-ui
make public-audit
```

Backend tests use isolated temporary libraries and mocked metadata providers;
FFmpeg integration tests exercise actual codecs and Range responses. Roku tests
cover syntax, XML/assets, resume routing, controls and autoplay policy. Physical
Roku/Vizio testing is still required for device-specific decoding and remote behavior.

For browser tests, install Playwright's Chromium (`npx playwright install chromium`),
run a localhost test server with `--lifespan off` as described in
[Server dashboard](docs/server-dashboard.md), then run the web/dashboard test scripts.

## Publishing this project

Use this clean source tree rather than an existing live-server folder or backup.
Read [Publishing safely](docs/publishing.md) and run the publication audit before
committing or uploading. Runtime data, video files, API keys, screenshots, Roku
ZIPs and old Git history are excluded from this distribution.

Third-party font notices are retained in `roku/fonts/LICENSE.txt`; see
[Third-party assets](THIRD_PARTY_NOTICES.md). Gravyflix is available under the [MIT license](LICENSE).
