import os
from contextlib import contextmanager
from pathlib import Path

import pymysql


@contextmanager
def connection():
    db = pymysql.connect(
        host=os.getenv('DB_HOST', 'mysql'),
        user=os.getenv('DB_USER', 'registration'),
        password=Path(os.environ['DB_PASSWORD_FILE']).read_text().strip(),
        database=os.getenv('DB_NAME', 'animal_persona'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
    )
    try:
        yield db
    finally:
        db.close()
