import json
from app.errors import DataError
from app.store import connection


def lookup(db, correction_id):
    row = db.execute('SELECT * FROM corrections WHERE id=?', (correction_id,)).fetchone()
    if row is None:
        raise DataError('RUN_UNKNOWN', '没有此更正批次', 404)
    return row


def fetch(correction_id):
    with connection() as db:
        return lookup(db, correction_id)


def persist(correction_id, package, book, result, created):
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO corrections VALUES (?,?,?,?,?)',
                   (correction_id, package, book, json.dumps(result, ensure_ascii=False), created))
        return lookup(db, correction_id)


def history():
    with connection() as db:
        return [dict(row) for row in
                db.execute('SELECT id,created FROM corrections ORDER BY created DESC,id DESC LIMIT 50')]
