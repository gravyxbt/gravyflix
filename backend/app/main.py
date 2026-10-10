import logging
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from . import config
from .database import connection, initialize
from .models import Movie, movie_response
from .scanner import scan_library

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("media")

def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # Route lookup only; sends no packet.
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"

@asynccontextmanager
async def lifespan(app):
    initialize()
    from .cast_features import initialize as initialize_cast
    initialize_cast()
    from .watch_history import initialize as initialize_history
    initialize_history()
    from .intros import initialize as initialize_intros, IntroWorker
    initialize_intros()
    from .credits import initialize as initialize_credits, CreditWorker
    initialize_credits()
    try:
        result = scan_library()
        count = result["found"]
    except OSError:
        log.exception("SCAN: Library unavailable")
        count = "unavailable"
    log.info("Media server running\nLocal API: http://%s:%s\nMovie library: %s\nMovies found: %s",
             lan_ip(), config.PORT, config.MOVIES_DIR, count)
    from .artwork_worker import ArtworkWorker
    worker = ArtworkWorker()
    app.state.artwork_worker = worker
    worker.start()
    from .subtitles import initialize as initialize_subtitles, SubtitleWorker
    initialize_subtitles()
    subtitle_worker = SubtitleWorker()
    app.state.subtitle_worker = subtitle_worker
    subtitle_worker.start()
    intro_worker = IntroWorker()
    app.state.intro_worker = intro_worker
    intro_worker.start()
    credit_worker = CreditWorker()
    app.state.credit_worker = credit_worker
    credit_worker.start()
    try:
        yield
    finally:
        credit_worker.close()
        intro_worker.close()
        subtitle_worker.close()
        worker.close()
    from .casting import manager
    manager.shutdown()
    from .roku_audio import cache
    cache.close()

app = FastAPI(title="My Media", lifespan=lifespan)

@app.middleware("http")
async def request_log(request, call_next):
    response = await call_next(request)
    log.info("HTTP: %s %s %s -> %d", request.client.host if request.client else "?",
             request.method, request.url.path, response.status_code)
    return response

@app.get("/health")
def health():
    return {"status": "ok"}

def base_url(request):
    return config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")

def get_movie(movie_id):
    with connection() as db:
        row = db.execute("SELECT * FROM movies WHERE id=? AND available=1", (movie_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Movie not found; rescan the library")
    return row

@app.get("/api/movies", response_model=list[Movie])
def movies(request: Request):
    with connection() as db:
        rows = db.execute("SELECT * FROM movies WHERE available=1 ORDER BY title COLLATE NOCASE, id").fetchall()
    return [movie_response(row, base_url(request)) for row in rows]

@app.get("/api/movies/{movie_id}", response_model=Movie)
def movie(movie_id: int, request: Request):
    return movie_response(get_movie(movie_id), base_url(request))

@app.post("/api/library/scan")
def scan(request: Request):
    try:
        result = scan_library()
        worker = getattr(request.app.state, "artwork_worker", None)
        if worker:
            worker.request()
        subtitle_worker = getattr(request.app.state, "subtitle_worker", None)
        if subtitle_worker:
            subtitle_worker.request()
        intro_worker = getattr(request.app.state, "intro_worker", None)
        if intro_worker:
            intro_worker.request()
        credit_worker = getattr(request.app.state, "credit_worker", None)
        if credit_worker:
            credit_worker.request()
        return result
    except OSError as exc:
        log.exception("SCAN: Failed")
        raise HTTPException(503, "Movie directory unavailable; check server logs") from exc

@app.api_route("/stream/{movie_id}", methods=["GET", "HEAD"])
def stream(movie_id: int, request: Request):
    from .streaming import stream_movie
    return stream_movie(get_movie(movie_id), request)

# Receiver requests originate from its hosted Cast application; allow CORS only
# for read-only media. TV controls remain same-origin.
@app.middleware("http")
async def media_cors(request, call_next):
    from starlette.responses import Response
    is_stream = request.url.path.startswith(("/stream/", "/subtitles/", "/api/playback/roku/media/"))
    if is_stream and request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    if is_stream:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Range, Content-Type"
        response.headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Range, Accept-Ranges"
    return response

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .cast_api import router as cast_router
app.include_router(cast_router)
app.mount("/web", StaticFiles(directory=config.ROOT / "backend/app/web"), name="web")

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(config.ROOT / "backend/app/web/index.html", headers={"Cache-Control": "no-cache"})

from .playback_api import router as playback_router
app.include_router(playback_router)

@app.get("/api/library/browse")
def browse(request: Request):
    from .catalog import build_catalog
    from .artwork import decorate
    catalog = build_catalog([movie.model_dump() for movie in movies(request)])
    for item in catalog:
        decorate(item, base_url(request))
        if item['kind'] == 'show':
            for season in item['seasons']:
                for episode in season['episodes']:
                    decorate(episode, base_url(request), str(item['id']))
    from .subtitle_summary import decorate_catalog, library_summaries
    from .watch_history import decorate as decorate_history
    return decorate_history(decorate_catalog(catalog, library_summaries()))

from .artwork import router as artwork_router
app.include_router(artwork_router)

from .subtitle_api import router as subtitle_router
app.include_router(subtitle_router)

from .intro_api import router as intro_router
app.include_router(intro_router)

# Browser administration stays separate from the watch-and-cast interface.
from .management import router as management_router
app.include_router(management_router)

@app.get('/manage', include_in_schema=False)
def management_home():
    return FileResponse(config.ROOT / 'backend/app/web/manage.html', headers={'Cache-Control': 'no-store'})

@app.get('/manage/guide/{name}', include_in_schema=False)
def management_guide(name: str):
    guides = {'media': config.ROOT / 'docs/organizing-your-media.md', 'setup': config.ROOT / 'README.md'}
    if name not in guides:
        raise HTTPException(404, 'Guide not found')
    return FileResponse(guides[name], media_type='text/plain; charset=utf-8', headers={'Cache-Control': 'no-cache'})

@app.get('/api/movies/{movie_id}/credits')
def movie_credits(movie_id: int):
    from .credits import available
    return available(get_movie(movie_id))

from .playback_sessions import router as session_router
app.include_router(session_router)
