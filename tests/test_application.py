"""Real FastAPI handlers with in-process HTTP routing and a SQLite DB adapter.

These checks cover application behavior, not MySQL/Docker compatibility.
Run scripts/cloud/smoke.sh and the cloud persistence test for deployment checks.
"""
import importlib
from pathlib import Path
import re
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import httpx
import pymysql
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services'))
registration = importlib.import_module('registration.app.main')
persona = importlib.import_module('persona.app.main')
media = importlib.import_module('media.app.main')


class Cursor:
    def __init__(self, db):
        self.cursor = db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()

    def execute(self, sql, params=()):
        self.cursor.execute(sql.replace('%s', '?').replace('RAND()', 'RANDOM()'), params)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None


class Connection:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return Cursor(self.db)

    def commit(self):
        self.db.commit()


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript('''
            CREATE TABLE persona (id INTEGER PRIMARY KEY AUTOINCREMENT, animal TEXT,
                slug TEXT, description TEXT, image_key TEXT);
            CREATE TABLE registrations (id TEXT PRIMARY KEY, name TEXT, age INTEGER,
                persona_id INTEGER REFERENCES persona(id));
        ''')
        sql = (ROOT / 'database/init/01-schema.sql').read_text()
        self.db.executescript(sql[sql.index('INSERT INTO persona'):])

        @contextmanager
        def connection():
            yield Connection(self.db)

        self.patches = [
            patch.object(registration, 'connection', connection),
            patch.object(persona, 'connection', connection),
        ]
        for item in self.patches:
            item.start()
        self.persona = TestClient(persona.app)
        self.media = TestClient(media.app)
        self.registration = TestClient(registration.app)

        def get(url, **_):
            if url.startswith(registration.PERSONA_URL + '/'):
                return self.persona.get(url[len(registration.PERSONA_URL):])
            if url.startswith(registration.MEDIA_URL + '/'):
                return self.media.get(url[len(registration.MEDIA_URL):])
            raise AssertionError('Unexpected outgoing HTTP request: ' + url)

        self.http_patch = patch.object(registration.httpx, 'get', side_effect=get)
        self.http_patch.start()

    def tearDown(self):
        self.http_patch.stop()
        for client in [self.persona, self.media, self.registration]:
            client.close()
        for item in reversed(self.patches):
            item.stop()
        self.db.close()

    def create(self, name='Krishna', age=30):
        return self.registration.post('/api/registrations', json={'name': name, 'age': age})

    def test_create_then_reload_preserves_assignment(self):
        response = self.create('  Krishna   T  ', 30)
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        self.assertEqual(data['name'], 'Krishna T')
        self.assertEqual(data['age'], 30)
        with TestClient(registration.app) as new_client:
            reloaded = new_client.get('/api/registrations/' + data['registration_id'])
        self.assertEqual(reloaded.json(), data)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registrations').fetchone()[0], 1)

    def test_duplicate_names_get_independent_records(self):
        first, second = self.create().json(), self.create().json()
        self.assertNotEqual(first['registration_id'], second['registration_id'])

    def test_invalid_input_does_not_insert(self):
        for body in [
            {'name': ' ', 'age': 30}, {'name': 'K', 'age': 0},
            {'name': 'K', 'age': 121}, {'name': 'K', 'age': 20.5},
            {'name': 'K', 'age': True}, {'name': 'K', 'age': '30'},
            {'name': 'x' * 81, 'age': 30}, {'name': 'K'},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.registration.post('/api/registrations', json=body).status_code, 422)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registrations').fetchone()[0], 0)

    def test_name_is_parameterized_and_unicode_survives(self):
        name = "కృష్ణ'); DROP TABLE registrations; --"
        data = self.create(name).json()
        saved = self.registration.get('/api/registrations/' + data['registration_id']).json()
        self.assertEqual(saved['name'], name)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registrations').fetchone()[0], 1)

    def test_missing_and_invalid_registration_ids(self):
        self.assertEqual(self.registration.get('/api/registrations/' + str(uuid4())).status_code, 404)
        self.assertEqual(self.registration.get('/api/registrations/not-a-uuid').status_code, 422)

    def test_catalogue_and_every_image_work(self):
        rows = self.db.execute('SELECT * FROM persona').fetchall()
        self.assertEqual(len(rows), 8)
        for row in rows:
            with self.subTest(animal=row['animal']):
                self.assertEqual(self.persona.get('/personas/' + str(row['id'])).json()['animal'], row['animal'])
                url = self.media.get('/images/' + row['image_key']).json()['url']
                image = self.media.get(url)
                self.assertEqual(image.status_code, 200)
                self.assertIn('image/svg+xml', image.headers['content-type'])
                self.assertIn('<svg', image.text)

    def test_random_route_is_not_treated_as_an_integer_id(self):
        self.assertEqual(self.persona.get('/personas/random').status_code, 200)
        self.assertEqual(self.persona.get('/personas/999').status_code, 404)

    def test_unknown_images_and_traversal_are_rejected(self):
        for key in ['missing.svg', '..%2Fapp%2Fmain.py', '%2e%2e', 'panda.svg.exe']:
            self.assertIn(self.media.get('/images/' + key).status_code, [404, 422])

    def test_all_readiness_endpoints(self):
        for client in [self.persona, self.media, self.registration]:
            self.assertEqual(client.get('/readyz').status_code, 200)

    def test_media_outage_does_not_create_a_hidden_registration(self):
        # Replace only media calls; persona still exercises the real API handler.
        def failed_media(url, **kwargs):
            if url.startswith(registration.MEDIA_URL):
                raise httpx.ConnectError('simulated outage')
            return self.persona.get(url[len(registration.PERSONA_URL):])
        with patch.object(registration.httpx, 'get', side_effect=failed_media):
            self.assertEqual(self.create().status_code, 503)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM registrations').fetchone()[0], 0)

    def test_database_outage_returns_actionable_error(self):
        with patch.object(registration, 'connection', side_effect=pymysql.OperationalError(2003, 'simulated')):
            self.assertEqual(self.create().status_code, 503)
            self.assertEqual(self.registration.get('/readyz').status_code, 503)

    def test_missing_catalogue_is_not_ready(self):
        self.db.execute('DELETE FROM persona')
        self.assertEqual(self.persona.get('/readyz').status_code, 503)
        self.assertEqual(self.create().status_code, 503)


class PackageTests(unittest.TestCase):
    def test_static_gallery_matches_seeded_catalogue(self):
        script = (ROOT / 'services/frontend/static/app.js').read_text()
        slugs = set(re.findall(r"\['([a-z]+)', '[A-Z]", script))
        self.assertEqual(slugs, {path.stem for path in (ROOT / 'services/media/assets').glob('*.svg')})


if __name__ == '__main__':
    unittest.main(verbosity=2)
