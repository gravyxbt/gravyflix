import pytest
from fastapi.testclient import TestClient
from app import config
from app.main import app
from app.scanner import parse_filename, scan_library

@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "Movies"
    root.mkdir()
    monkeypatch.setattr(config, "MOVIES_DIR", root)
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    return root

@pytest.fixture
def client(library):
    with TestClient(app) as client:
        yield client

@pytest.mark.parametrize("name,title,year", [
    ("The.Matrix.1999.1080p.mkv", "The Matrix", 1999),
    ("Arrival (2016).mp4", "Arrival", 2016),
    ("My_Movie.m4v", "My Movie", None),
    ("2001 A Space Odyssey (1968).mov", "2001 A Space Odyssey", 1968),
])
def test_names(name,title,year):
    assert parse_filename(name) == (title,year)

def test_scan_and_api(library, client):
    path = library / "Arrival (2016).mp4"
    path.write_bytes(b"test data")
    (library / "ignore.txt").write_text("ignore")
    assert client.post("/api/library/scan").json()["added"] == 1
    first = client.get("/api/movies").json()[0]
    assert first["title"] == "Arrival"
    assert first["stream_url"] == f"http://testserver/stream/{first['id']}"
    assert "file_path" not in first
    assert client.get(f"/api/movies/{first['id']}").json() == first
    assert scan_library()["added"] == 0
    path.write_bytes(b"changed")
    scan_library()
    again = client.get("/api/movies").json()[0]
    assert again["id"] == first["id"]
    assert again["date_added"] == first["date_added"]
    path.unlink()
    scan_library()
    assert client.get("/api/movies").json() == []
    assert client.get(f"/api/movies/{first['id']}").status_code == 404
    path.write_bytes(b"restored")
    scan_library()
    assert client.get("/api/movies").json()[0]["id"] == first["id"]

def test_symlink_outside_library(library, client, tmp_path):
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"secret")
    (library / "link.mp4").symlink_to(outside)
    scan_library()
    assert client.get("/api/movies").json() == []

def test_missing_directory_does_not_erase(library, client):
    (library / "movie.mkv").write_bytes(b"test")
    scan_library()
    library.rename(library.with_name("offline"))
    assert client.post("/api/library/scan").status_code == 503
    assert len(client.get("/api/movies").json()) == 1

@pytest.mark.parametrize('filename,title,year', [
    ('1-1 Iron Man.avi', 'Iron Man', None),
    ('2-7 New Film.mp4', 'New Film', None),
    ('1917 (2019).mp4', '1917', 2019),
    ('12 Angry Men (1957).mkv', '12 Angry Men', 1957),
    ('Iron Man 2.mp4', 'Iron Man 2', None),
    ('Film (Part 2).avi', 'Film (Part 2)', None),
    ('New.Film.DVDRip.XviD-GROUP.avi', 'New Film', None),
    ('[ www.Example.com ] - New Film 2001 WEBRip.avi', 'New Film', 2001),
    ('Show.S02E01.HDTV.x264.mkv', 'Show S02E01', None),
])
def test_clean_titles(filename, title, year):
    assert parse_filename(filename) == (title, year)


def test_rescan_retitles_unchanged_file_without_probe(library, monkeypatch):
    from app import scanner
    from app.database import connection
    path = library / '2-7 New Film.mp4'
    path.write_bytes(b'video')
    fields = dict(container='mp4', video_codec='h264', audio_codec='aac', width=16,
                  height=16, duration=1, audio_channels=2, audio_profile=None,
                  audio_tracks='[]', probe_version=scanner.PROBE_VERSION, probe_error=None)
    monkeypatch.setattr(scanner, 'probe', lambda p: fields)
    scan_library()
    with connection() as db:
        original = dict(db.execute('SELECT * FROM movies').fetchone())
        db.execute("UPDATE movies SET title='2-7 New Film'")
    def no_probe(p):
        pytest.fail('Unchanged video should not be reprobed')
    monkeypatch.setattr(scanner, 'probe', no_probe)
    assert scan_library()['updated'] == 1
    with connection() as db:
        current = dict(db.execute('SELECT * FROM movies').fetchone())
    assert current['title'] == 'New Film'
    for key in ('id', 'file_path', 'date_added', 'modification_time', 'file_size'):
        assert current[key] == original[key]
    assert scan_library()['updated'] == 0


def test_scan_discovers_new_season_before_browse(library, client):
    # An app catalog refresh alone is a DB read; POST scan must precede it.
    season = library / "Rick and Morty" / "Season 09"
    nested = season / "Rick.and.Morty.S09E02.1080p.x265-ELiTE"
    nested.mkdir(parents=True)
    (nested / "Rick.and.Morty.S09E02.1080p.x265-ELiTE.mkv").write_bytes(b"video")
    (season / "Rick.and.Morty.S09E03.1080p.WEB.h264.mkv").write_bytes(b"video")
    assert client.get("/api/library/browse").json() == []
    result = client.post("/api/library/scan")
    assert result.status_code == 200
    assert result.json()["added"] == 2
    shows = client.get("/api/library/browse").json()
    assert len(shows) == 1
    assert shows[0]["title"] == "Rick and Morty"
    assert shows[0]["seasons"][0]["number"] == 9
    assert [e["episode_number"] for e in shows[0]["seasons"][0]["episodes"]] == [2, 3]
    assert client.post("/api/library/scan").json()["added"] == 0
