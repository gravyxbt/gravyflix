import uvicorn
from .config import HOST, PORT
uvicorn.run("app.main:app", host=HOST, port=PORT, proxy_headers=False)
