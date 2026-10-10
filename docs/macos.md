# Apple Silicon macOS setup

Gravyflix can run on a native ARM Mac (M1 and newer). This setup targets **macOS 14
or newer and Python 3.13**. Linux remains supported. Intel Macs, Rosetta Python and
Windows are outside this release's target. ONNX Runtime's pinned Apple Silicon
wheel requires macOS 14+, and the supplied setup checks this before installing.

The backend, Roku app, web remote and media formats are the same as on Linux.
CPU conversion uses `libx264`. Keep that default on Macs; NVIDIA NVENC is not a Mac
encoder. Apple hardware encoding is a separate future enhancement.

## Install and start

Install [Homebrew](https://brew.sh/) using its official instructions if needed.
Use a native Terminal session, then install Python and both media tools:

```bash
brew install python@3.13 ffmpeg
python3.13 -c 'import platform; print(platform.machine())'
# Must print arm64.
```

[Homebrew's FFmpeg package](https://formulae.brew.sh/formula/ffmpeg) includes
`ffmpeg` and `ffprobe`. If you prefer project-local media tools, the existing
`./scripts/setup-media-tools.sh` supports native ARM Mac binaries as an alternative.

Clone or extract the source to `~/gravyflix`:

```bash
cd ~/gravyflix
./scripts/setup-macos.sh
./scripts/start.sh
```

Setup creates a local virtual environment and a private `.env` from the example
only if none exists. It preserves existing settings. If a virtual environment was
copied from Linux or created using Rosetta, use a fresh checkout or rename `.venv`
and rerun setup; virtual environments cannot be moved between operating systems.

The server runs in the foreground. Leave Terminal open and use Ctrl-C to stop it.
In another Terminal:

```bash
cd ~/gravyflix
curl http://localhost:8080/health
```

Use the LAN URL printed at startup to open the dashboard on a phone/computer.
Copy videos into `~/gravyflix/media/Movies`, or set `MOVIES_DIR` in `.env` to another
readable folder. Absolute external-drive paths such as `/Volumes/Media/Movies`
work. Keep the drive mounted; disconnected files are hidden by library scanning
until the drive returns and the next scan runs. No originals are deleted.

```bash
./scripts/scan.sh
```

## Roku and Vizio

Use the dashboard's Setup & devices page at the **Mac's LAN URL** to download a
Roku package configured for that Mac. Sideload through Roku's Development
Application Installer. The existing Roku UI and playback behavior are unchanged.
For shell packaging:

```bash
BACKEND_URL=http://YOUR_MAC_LAN_IP:8080 make roku-package
```

For Vizio/Google Cast, configure `CAST_HOST` in `.env` or the dashboard, then
restart. The phone, TV and Mac need access to the same home LAN. On macOS, allow
Python's incoming network connections if the firewall prompts; allow local-network
access for the process hosting Gravyflix if macOS requests it. VPN LAN access must
also be enabled. Do not disable the firewall or forward the server port online.

A sleeping Mac cannot serve video. Configure the Mac's power settings appropriately
if using it as an always-available server; closing a laptop lid can put it to sleep.

## Optional login service

After foreground playback works, stop it with Ctrl-C. From the project folder:

```bash
.venv/bin/python scripts/macos-service.py install
.venv/bin/python scripts/macos-service.py status
```

This creates only `~/Library/LaunchAgents/org.gravyflix.server.plist` and logs under
`~/Library/Logs/Gravyflix/`, then loads the service for your logged-in user. It uses
absolute paths and includes `/opt/homebrew/bin` so Homebrew FFmpeg is found without
interactive shell configuration. It does not copy API keys into the service file;
Gravyflix loads its existing private `.env`.

This is a login service, not a system daemon: it starts at login and requires your
user session. Apple documents per-user agents in its [launchd guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).
Run these commands from the same project folder:

```bash
.venv/bin/python scripts/macos-service.py restart
.venv/bin/python scripts/macos-service.py stop
.venv/bin/python scripts/macos-service.py start
.venv/bin/python scripts/macos-service.py uninstall
```

Restart only when nobody is watching. `stop` stops the current login session;
`uninstall` removes login startup. Uninstall retains the library, database,
configuration and media. Avoid running a foreground server at the same time.
If moving the project, uninstall from the old directory before installing from
its new location. The helper refuses to overwrite another installation's service.

View logs:

```bash
tail -n 100 ~/Library/Logs/Gravyflix/server.log
tail -n 100 ~/Library/Logs/Gravyflix/server-error.log
```

If the foreground server can read a folder but the login service cannot, check
macOS privacy permissions for that process, especially for protected user folders
or removable drives. Keep the project in your home folder rather than Desktop or
Documents for a simple initial setup. Review logs before sharing them: paths,
addresses and watched titles can be personal.

## Development verification

```bash
npm ci
make test
make roku-test-ui
PYTHONPATH=backend .venv/bin/python scripts/check-media-runtime.py
```

CI runs on Linux and an actual Apple Silicon macOS runner. Checks include real
FFmpeg encode/probe/frame extraction, bundled OCR inference, the backend suite,
Roku syntax/UI logic and launch-agent plist validation. Browser checks exercise
macOS restart guidance. Physical LAN playback, Cast discovery, privacy/firewall
permissions, sleep behavior and login/logout service lifecycle still need a real
home Mac test; hosted CI cannot prove those device/network behaviors.
