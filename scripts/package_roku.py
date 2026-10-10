"""Package with manifest at ZIP root. Optionally override URL without editing source."""
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
source = root / "roku"
for xml in source.rglob("*.xml"):
    ET.parse(xml)
config = (source / "source/Config.brs").read_text()
url = os.getenv("BACKEND_URL", "").rstrip("/")
if url:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(c in url for c in '"\r\n'):
        raise SystemExit("BACKEND_URL must be an HTTP(S) base URL without credentials, query or fragment")
    config = re.sub(r'return "[^"]*"', 'return "' + url + '"', config)
else:
    url = re.search(r'return "([^"]*)"', config)[1]
destination = root / "dist/my-media.zip"
destination.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(source).parts):
            name = path.relative_to(source).as_posix()
            archive.writestr(name, config.encode() if name == "source/Config.brs" else path.read_bytes())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert "manifest" in archive.namelist()
print(f"Packaged: {destination}\nBackend: {url}")
if "192.0.2.10" in url:
    print("Reminder: this is the example address. Set BACKEND_URL or edit roku/source/Config.brs.")
