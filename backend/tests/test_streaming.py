import pytest
from test_library import library, client
from app.scanner import scan_library

@pytest.fixture
def movie_file(library, client):
    data = bytes(range(256)) * 8192
    path = library / "Test.mp4"
    path.write_bytes(data)
    scan_library()
    movie_id = client.get("/api/movies").json()[0]["id"]
    return f"/stream/{movie_id}", data, path

def test_full_and_head(client, movie_file):
    url, data, _ = movie_file
    response = client.get(url)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert int(response.headers["content-length"]) == len(data)
    for headers in ({}, {"Range": "bytes=0-9"}):
        response = client.head(url, headers=headers)
        assert response.status_code == 200
        assert response.content == b""
        assert int(response.headers["content-length"]) == len(data)

@pytest.mark.parametrize("header,start,end", [
    ("bytes=0-999999", 0, 999999), ("bytes=10-19",10,19),
    ("bytes=2097140-",2097140,2097151), ("bytes=-10",2097142,2097151),
    ("bytes=2097150-9999999",2097150,2097151), ("bytes=-9999999",0,2097151),
    ("bytes=0-0",0,0),
])
def test_ranges(client, movie_file, header,start,end):
    url,data,_ = movie_file
    response = client.get(url, headers={"Range":header})
    assert response.status_code == 206
    assert response.content == data[start:end+1]
    assert response.headers["content-range"] == f"bytes {start}-{end}/{len(data)}"
    assert int(response.headers["content-length"]) == end-start+1

@pytest.mark.parametrize("header", ["bytes=99999999-", "bytes=20-10", "bytes=-0", "bytes=" + "9"*100 + "-"])
def test_unsatisfiable(client,movie_file,header):
    url,data,_ = movie_file
    response=client.get(url,headers={"Range":header})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(data)}"

@pytest.mark.parametrize("header", ["bytes=0-1,4-5", "bananas", "items=1-2", "bytes=-"])
def test_ignored_range(client,movie_file,header):
    url,data,_=movie_file
    response=client.get(url,headers={"Range":header})
    assert response.status_code==200
    assert response.content==data

def test_if_range(client,movie_file):
    url,data,_=movie_file
    etag=client.head(url).headers["etag"]
    assert client.get(url,headers={"Range":"bytes=0-2","If-Range":etag}).content==data[:3]
    assert client.get(url,headers={"Range":"bytes=0-2","If-Range":'"old"'}).status_code==200

def test_empty_deleted_and_replaced(client,movie_file,tmp_path):
    url,_,path=movie_file
    path.write_bytes(b"")
    assert client.get(url).content == b""
    assert client.get(url,headers={"Range":"bytes=0-"}).status_code==416
    path.unlink()
    assert client.get(url).status_code==404
    outside=tmp_path/"secret.mp4"
    outside.write_bytes(b"private")
    path.symlink_to(outside)
    assert client.get(url).status_code==404

@pytest.mark.parametrize("header", ["bytes=0-" + "9"*5000, "bytes=-" + "9"*5000, "bytes=" + "0"*5000 + "-99999999"])
def test_large_valid_ranges(client, movie_file, header):
    url,data,_ = movie_file
    response = client.get(url, headers={"Range":header})
    assert response.status_code == 206
    assert response.content == data
