import logging
import os
from uuid import UUID, uuid4

import httpx
import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from .db import connection

app = FastAPI(title='Registration API', version='1.0.0')
log = logging.getLogger('uvicorn.error')
PERSONA_URL = os.getenv('PERSONA_URL', 'http://persona:8000').rstrip('/')
MEDIA_URL = os.getenv('MEDIA_URL', 'http://media:8000').rstrip('/')


class RegistrationInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    age: int = Field(strict=True, ge=1, le=120)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(value.split())
        if not value:
            raise ValueError('Please enter your name.')
        if any(ord(char) < 32 for char in value):
            raise ValueError('Name contains unsupported characters.')
        return value


def downstream_json(url):
    try:
        response = httpx.get(url, timeout=4.0, trust_env=False)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        log.warning('A downstream API is unavailable')
        raise HTTPException(503, 'A supporting service is unavailable. Please try again.') from None


def result(row, persona):
    media = downstream_json(f"{MEDIA_URL}/images/{persona['image_key']}")
    return {
        'registration_id': row['id'],
        'name': row['name'],
        'age': row['age'],
        'persona': persona,
        'image_url': media['url'],
    }


@app.get('/healthz')
def health():
    return {'status': 'ok', 'service': 'registration'}


@app.get('/readyz')
def ready():
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT 1')
    except (pymysql.MySQLError, OSError, KeyError):
        raise HTTPException(503, 'Database is unavailable') from None
    downstream_json(f'{PERSONA_URL}/readyz')
    downstream_json(f'{MEDIA_URL}/readyz')
    return {'status': 'ready'}


@app.post('/api/registrations', status_code=201)
def register(body: RegistrationInput):
    persona = downstream_json(f'{PERSONA_URL}/personas/random')
    row = {'id': str(uuid4()), 'name': body.name, 'age': body.age}
    # Resolve dependencies before inserting: a media outage must not create a hidden row.
    response = result(row, persona)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO registrations (id, name, age, persona_id) VALUES (%s, %s, %s, %s)',
                (row['id'], body.name, body.age, persona['id']),
            )
            db.commit()
    except (pymysql.MySQLError, OSError, KeyError):
        log.warning('Registration database write failed')
        raise HTTPException(503, 'Could not save your registration. Please try again.') from None
    return response


@app.get('/api/registrations/{registration_id}')
def read_registration(registration_id: UUID):
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                'SELECT id, name, age, persona_id FROM registrations WHERE id = %s',
                (str(registration_id),),
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, OSError, KeyError):
        raise HTTPException(503, 'Database is unavailable. Please try again.') from None
    if row is None:
        raise HTTPException(404, 'Registration not found')
    persona = downstream_json(f"{PERSONA_URL}/personas/{row['persona_id']}")
    return result(row, persona)
