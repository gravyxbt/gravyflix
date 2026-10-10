import pytest
from app import config

@pytest.fixture(autouse=True)
def no_background_network(monkeypatch):
    # All automated tests use isolated libraries and mocked public-source requests.
    monkeypatch.setattr(config, "AUTO_INTROS", False)
    monkeypatch.setattr(config, "AUTO_CREDITS", False)
    monkeypatch.setattr(config, "AUTO_VISUAL_CREDITS", False)
    monkeypatch.setattr(config, "AUTO_ARTWORK", False)
    monkeypatch.setattr(config, "AUTO_SUBTITLES", False)
    monkeypatch.setattr(config, "OPENSUBTITLES_API_KEY", "")
    monkeypatch.setattr(config, "ROKU_VIDEO_ENCODER", "libx264")
