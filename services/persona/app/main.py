import pymysql
from fastapi import FastAPI, HTTPException

from .db import connection

app = FastAPI(title='Persona API', version='1.0.0')
FIELDS = 'id, animal, slug, description, image_key'


def query_one(sql, params=()):
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    except (pymysql.MySQLError, OSError, KeyError):
        raise HTTPException(503, 'Persona database is unavailable') from None


@app.get('/healthz')
def health():
    return {'status': 'ok', 'service': 'persona'}


@app.get('/readyz')
def ready():
    if not query_one('SELECT id FROM persona LIMIT 1'):
        raise HTTPException(503, 'Persona catalogue has not been seeded')
    return {'status': 'ready'}


# Keep /random before /{persona_id}, so it cannot be interpreted as an integer ID.
@app.get('/personas/random')
def random_persona():
    # Eight seeded rows: RAND() is deliberately simple for this tiny catalogue.
    row = query_one(f'SELECT {FIELDS} FROM persona ORDER BY RAND() LIMIT 1')
    if row is None:
        raise HTTPException(503, 'No personas available')
    return row


@app.get('/personas/{persona_id}')
def read_persona(persona_id: int):
    row = query_one(f'SELECT {FIELDS} FROM persona WHERE id = %s', (persona_id,))
    if row is None:
        raise HTTPException(404, 'Persona not found')
    return row
