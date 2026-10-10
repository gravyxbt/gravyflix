from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_library import library, client
from app import cast_api, casting, config
from app.scanner import scan_library

HEADERS = {"X-Media-Control": "1"}

def test_web_and_stream_cors(client, library):
    assert client.get("/").status_code == 200
    assert "GRAVYFLIX" in client.get("/").text
    assert client.get("/web/app.js").status_code == 200
    assert "<video" not in client.get("/").text
    response = client.options("/stream/1", headers={"Origin":"https://receiver.example"})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "*"

def test_cast_routes(client, library, monkeypatch):
    fake = Mock()
    fake.snapshot.return_value = {"state":"IDLE", "connected":True}
    fake.play_movie.return_value = {"state":"PLAYING"}
    fake.command.return_value = {"state":"PAUSED"}
    monkeypatch.setattr(cast_api, "manager", fake)
    assert client.get("/api/cast/status").json()["connected"]
    (library/"Test.mp4").write_bytes(b"video")
    scan_library()
    movie_id=client.get("/api/movies").json()[0]["id"]
    assert client.post("/api/cast/play",json={"movie_id":movie_id}).status_code == 403
    assert client.post("/api/cast/play",json={"movie_id":movie_id},headers=HEADERS).json()["state"] == "PLAYING"
    assert fake.play_movie.call_args.args[0]["id"] == movie_id
    assert client.post("/api/cast/play",json={"movie_id":9999},headers=HEADERS).status_code == 404
    assert client.post("/api/cast/control",json={"action":"pause"},headers=HEADERS).status_code == 200
    for body in [{"action":"seek"},{"action":"seek","position":-1},{"action":"launch"}]:
        assert client.post("/api/cast/control",json=body,headers=HEADERS).status_code == 422
    fake.snapshot.side_effect=RuntimeError("TV offline")
    response=client.get("/api/cast/status")
    assert response.status_code==503 and "TV offline" in response.json()["detail"]
    assert "access-control-allow-origin" not in response.headers

def test_other_apps_are_not_controlled(monkeypatch):
    manager=casting.CastManager()
    status=SimpleNamespace(content_id="https://other.example/movie",player_state="PLAYING")
    cast=SimpleNamespace(media_controller=SimpleNamespace(status=status),name="Living Room")
    monkeypatch.setattr(manager,"connect",lambda:cast)
    monkeypatch.setattr(manager,"stream_base",lambda:"http://192.0.2.10:8080")
    assert not manager.snapshot()["active"]
    with pytest.raises(RuntimeError,match="No GRAVYFLIX"):
        manager.command("stop")

def test_play_uses_server_url(monkeypatch, library, client):
    manager=casting.CastManager()
    path=library/"Test.mp4"
    path.write_bytes(b"video")
    url="http://192.0.2.10:8080/stream/42"
    status=SimpleNamespace(content_id=url,player_state="PLAYING",title="Test",duration=12,
                           adjusted_current_time=1,idle_reason=None)
    controller=Mock(status=status)
    cast=SimpleNamespace(media_controller=controller,name="Living Room")
    monkeypatch.setattr(manager,"connect",lambda:cast)
    monkeypatch.setattr(manager,"stream_base",lambda:"http://192.0.2.10:8080")
    monkeypatch.setattr(manager.features,"loaded",lambda:None)
    from app import subtitles
    monkeypatch.setattr(subtitles,"available",lambda row,base:{"tracks":[]})
    result=manager.play_movie({"file_path":str(path),"id":42,"title":"Test"})
    assert result["active"]
    controller.play_media.assert_called_once_with(url,"video/mp4",title="Test",stream_type="BUFFERED")
    manager.command("seek",100)
    controller.seek.assert_called_once_with(11.9,timeout=5)
