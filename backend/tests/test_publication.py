"""Publication safeguards must reject private files even when force-added to Git."""
import importlib.util
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('publication', ROOT / 'scripts/audit-publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


def test_forced_runtime_files_are_rejected(tmp_path):
    for name in ['.env', 'data/library.db', 'config/artwork-matches.json', 'dist/channel.zip']:
        path = Path(name)
        issues = publication.audit(tmp_path, [path])
        assert issues == [(name, 0, 'private/runtime file is selected for publication')]


def test_allowlist_excludes_library_and_dependencies(tmp_path):
    for name in ['README.md', '.env.example', '.env', 'media/Movies/private.mp4',
                 'data/library.db', 'config/show-aliases.json', 'config/show-aliases.example.json',
                 'backend/app/main.py', 'backend/__pycache__/main.pyc']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('example')
    assert set(map(str, publication.source_paths(tmp_path))) == {
        'README.md', '.env.example', 'config/show-aliases.example.json', 'backend/app/main.py'}


def test_exact_secret_matches_are_redacted(tmp_path):
    secret = b'sensitive' + b'-example-value'
    (tmp_path / 'README.md').write_bytes(secret)
    issues = publication.audit(tmp_path, [Path('README.md')], [secret])
    assert issues == [('README.md', 0, 'matches a private credential value')]
    assert secret.decode() not in str(issues)


def test_provider_tokens_and_credential_urls_are_rejected(tmp_path):
    payload = 'ghp_' + 'A' * 36 + '\nhttp://' + 'someone:credential' + '@example.invalid/'
    (tmp_path / 'README.md').write_text(payload)
    reasons = {issue[2] for issue in publication.audit(tmp_path, [Path('README.md')])}
    assert reasons == {'provider credential', 'credential in URL'}


def test_symlinks_are_rejected(tmp_path):
    (tmp_path / 'README.md').symlink_to(tmp_path / 'elsewhere')
    assert publication.audit(tmp_path, [Path('README.md')])[0][2] == 'symlink is not publishable'


def test_png_metadata_is_rejected(tmp_path):
    payload = b'Comment\x00personal metadata'
    kind = b'tEXt'
    png = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', len(payload)) + kind + payload
    png += struct.pack('>I', zlib.crc32(kind + payload))
    (tmp_path / 'art.png').write_bytes(png)
    assert publication.audit(tmp_path, [Path('art.png')])[0][2] == 'PNG metadata needs review'


def test_documentation_addresses_are_allowed(tmp_path):
    (tmp_path / 'README.md').write_text('http://192.0.2.10:8080 and /home/example/gravyflix/')
    assert publication.audit(tmp_path, [Path('README.md')]) == []
