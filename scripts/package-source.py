#!/usr/bin/env python3
"""Build an audited public source ZIP; never package the live installation wholesale."""
import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', ROOT / 'scripts/audit-publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='ZIP destination outside this source directory')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.is_relative_to(ROOT):
        parser.error('Write release artifacts outside the source directory.')
    if destination.exists():
        parser.error('Destination already exists; choose a new name.')
    paths = sorted(publication.source_paths(ROOT))
    problems = publication.audit(ROOT, paths)
    if problems:
        for path, line, reason in problems:
            print(f'{path}:{line}: {reason}')
        raise SystemExit('Publication audit failed; no archive written.')
    # Snapshot bytes so the manifest and ZIP always describe the same reviewed files.
    files = {str(path): (ROOT / path).read_bytes() for path in paths}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo('gravyflix/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if (ROOT / name).stat().st_mode & 0o111 else 0o644
            info.external_attr = (0o100000 | mode) << 16
            archive.writestr(info, data)
    manifest = {'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    destination.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256').write_text(f'{checksum}  {destination.name}\n')
    print(f'Packaged {len(files)} audited source files: {destination.name}')

if __name__ == '__main__':
    main()
