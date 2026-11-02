from pathlib import Path
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title='Media API', version='1.0.0')
ASSETS = Path(__file__).resolve().parents[1] / 'assets'
KEY_PATTERN = re.compile(r'[a-z]{1,25}\.svg')


def asset_path(key):
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(404, 'Image not found')
    file = ASSETS / key
    if not file.is_file():
        raise HTTPException(404, 'Image not found')
    return file


@app.get('/healthz')
def health():
    return {'status': 'ok', 'service': 'media'}


@app.get('/readyz')
def ready():
    if len(list(ASSETS.glob('*.svg'))) != 8:
        raise HTTPException(503, 'Animal assets are incomplete')
    return {'status': 'ready'}


@app.get('/images/{key}')
def image_url(key: str):
    asset_path(key)
    # Browser-visible same-origin path. The browser cannot resolve Docker's 'media' hostname.
    # In the EKS/S3 phase this function can instead return an S3 presigned URL.
    return {'url': f'/media/{key}'}


@app.get('/media/{key}')
def image(key: str):
    file = asset_path(key)
    return FileResponse(
        file,
        media_type='image/svg+xml',
        headers={'Cache-Control': 'public, max-age=3600', 'X-Content-Type-Options': 'nosniff'},
    )
