import json
from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection
from .repository import lookup

DECISIONS = {'确认', '留待核实'}


def timeline(correction_id):
    with connection() as db:
        lookup(db, correction_id)
        return list(map(dict, db.execute(
            'SELECT version,decision,note,changed FROM correction_reviews '
            'WHERE correction_id=? ORDER BY version DESC', (correction_id,))))


def decide(correction_id, version, decision, note):
    note = note.strip()
    if decision not in DECISIONS:
        raise DataError('CORRECTION_REVIEW', '复核结论须为确认或留待核实')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = json.loads(lookup(db, correction_id)['result'])
        current = db.execute(
            'SELECT COALESCE(MAX(version),0) FROM correction_reviews WHERE correction_id=?',
            (correction_id,)).fetchone()[0]
        if current != version:
            raise DataError('STALE', '复核版本已过期，请刷新', 409)
        has_findings = bool(run['quarantine']) or any(
            variant['book'] is not None and variant['book']['code'] != 'MATCH'
            for variant in run['variants'])
        if decision == '确认' and not run['stable']:
            raise DataError(run['reason'], '结论打架的议案只能留待核实')
        if (has_findings or not run['stable'] or decision == '留待核实') and not note:
            raise DataError('REVIEW_NOTE', '有差异或结论待核实须填写复核意见')
        record = {'version': current + 1, 'decision': decision, 'note': note,
                  'changed': datetime.now(timezone.utc).isoformat()}
        db.execute('INSERT INTO correction_reviews VALUES (?,?,?,?,?)',
                   (correction_id, *record.values()))
        return record
