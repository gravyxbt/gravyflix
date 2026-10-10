# Publishing Gravyflix safely

Publish the clean source distribution. Do not upload a live installation,
Desktop backup, server logs, diagnostic downloads or a sideload ZIP configured
for your home. This copy contains no inherited Git history, database, user
configuration or personal media.

## Included

Application code, Roku UI/branding/fallback artwork, third-party font notices,
fictional configuration templates, tests, dependency lockfiles, user guides,
MIT license and a read-only GitHub Actions test workflow.

The workflow uses the official [checkout](https://github.com/actions/checkout),
[Python](https://github.com/actions/setup-python), and
[Node](https://github.com/actions/setup-node) actions. It runs on GitHub-hosted
runners, requests read-only repository permissions and does not need application
API secrets. Its first hosted run is still needed to verify runner integration.

## Excluded

- `.env` and other credential files, installed dependencies and caches.
- Library databases, watch history, title matching decisions and genre overrides.
- Original videos, generated test videos, downloaded posters/subtitles and stills.
- Roku packages, screenshots, FFmpeg outputs, diagnostic exports and backups.
- Home addresses, workstation paths, network identifiers and deployment notes.

Only `.env.example` and `config/*.example.json` are shared examples. Configure a
new installation locally after cloning. `.gitignore` prevents ordinary additions
of private/runtime files; it cannot stop force-adds or remove historical commits.

## Before uploading

```bash
python3 scripts/audit-publication.py
```

When Git is available, initialize a new repository inside this source tree, stage
it, and inspect tracked files before the first commit:

```bash
git init -b main
git add .
python3 scripts/audit-publication.py --tracked
git diff --cached --stat
```

Use your GitHub-provided no-reply address for the commit author if you want to
keep a personal email out of public commits. Configure that identity locally
before committing. Create a new empty GitHub repository, then use its displayed
remote URL; do not put a personal access token in the URL or a shell command.

```bash
git commit -m "Initial public Gravyflix source"
git remote add origin https://github.com/YOUR_ACCOUNT/gravyflix.git
git push -u origin main
```

Git was not installed on the preparation machine, so no local commit or remote
was created. The source ZIP is an alternative: extract it and upload the files
using GitHub's file uploader. Include `.github`, `.gitignore` and `.env.example`;
some file pickers hide dotfiles. Uploading a ZIP as one repository file does not
create a browsable source tree. Upload it separately as a release attachment if desired.

## What the audit checks

Selected source paths, accidentally tracked ignored files (with `--tracked`),
credential-like literals, common provider tokens, private-key blocks, credentials
in URLs, private LAN addresses, personal home paths and PNG text/EXIF metadata.
Reports print filenames, line numbers and reasons; never the matching values.
An optional `--private-env PATH` comparison checks exact sensitive values against
an existing private `.env` without copying it into the source tree. That option
uses the installed `python-dotenv` dependency. Do not upload the private input.

Build a new source release with `make source-package` (writes `../gravyflix-source.zip`)
or `python3 scripts/package-source.py --output /path/outside/project/gravyflix-source.zip`.

The release packager uses a source allowlist and fails the audit before writing
an archive. No ignored runtime content is selected. Its manifest and SHA-256
checksum identify the exact reviewed artifact. Inspect the archive contents if
adding new file types or directories.

This is a defense against known patterns, not proof that arbitrary future secrets
are impossible. It does not inspect old Git objects. Keep GitHub secret scanning/
push protection enabled where available and use a history-capable scanner for
repositories with previous commits. Rotate any credential that was ever published;
simply deleting it from the latest version is insufficient.

## Sharing diagnostics

Playback reports omit credentials and media paths, but still identify watched
titles and times. Raw server/Roku logs may reveal more. Share the minimum needed
for a bug report and redact library titles, addresses and personal paths first.
