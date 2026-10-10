# Security and privacy

Gravyflix runs on a trusted LAN. It has no user authentication; same-origin checks
and client headers are not passwords. Never forward port 8080 to the Internet.
Restrict server access to household devices and keep dependencies updated.

Store credentials only in local `.env` or your process environment. Runtime
metadata, downloads, cache files and diagnostics can reveal personal library and
watching information. Keep them out of Git; see docs/publishing.md.

Use GitHub's private vulnerability reporting if the repository owner enables it.
Do not post real API keys, passwords or private logs in public issues. If a
credential is exposed, revoke/rotate it and inspect the repository history.
