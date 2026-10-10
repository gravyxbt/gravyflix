import os
import re
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
target = os.environ["ROKU_DEV_TARGET"]
if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", target):
    raise SystemExit("ROKU_DEV_TARGET must be an IP or hostname, optionally :port (no URL scheme).")
with (root / "dist/my-media.zip").open("rb") as archive:
    try:
        response = httpx.post(
            f"http://{target}/plugin_install",
            auth=httpx.DigestAuth("rokudev", os.environ["DEVPASSWORD"]),
            data={"mysubmit": "Install"},
            files={"archive": ("my-media.zip", archive, "application/zip")},
            timeout=120, trust_env=False,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"Roku installer HTTP failure: {exc}") from exc
report = root / "dist/roku-install-response.html"
report.write_text(response.text)
# The installer can return HTTP 200 for installation failures.
if not re.search(r"install\s+success", response.text, re.I):
    raise SystemExit(f"Installation was not confirmed. Inspect {report} and Roku port 8085 logs. "
                     "An identical package may already be installed.")
print(f"Roku reports install success. Response: {report}")
