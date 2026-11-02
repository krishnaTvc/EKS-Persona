#!/usr/bin/env python3
"""Exercise the full stack through Nginx; Python standard library only."""
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080').rstrip('/')


def request(path, body=None):
    headers = {'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
        return response.status, response.read(), response.headers


status, html, _ = request('/')
assert status == 200 and b'Wildly You' in html
print('PASS frontend')
status, data, _ = request('/api/registrations', {'name': 'WSL Explorer', 'age': 30})
assert status == 201
created = json.loads(data)
assert created['name'] == 'WSL Explorer' and created['persona']['animal']
print('PASS registration and persona selection')
_, data, _ = request('/api/registrations/' + created['registration_id'])
assert json.loads(data) == created
print('PASS saved result and stable assignment')
_, image, headers = request(created['image_url'])
assert b'<svg' in image and headers.get_content_type() == 'image/svg+xml'
print('PASS media image')
try:
    request('/api/registrations', {'name': ' ', 'age': 0})
except HTTPError as error:
    assert error.code == 422
else:
    raise AssertionError('Invalid input was accepted')
print('PASS input validation')
print('All smoke checks passed. Saved ID:', created['registration_id'])
