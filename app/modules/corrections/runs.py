import json
from .repository import fetch, persist
from .schema import CorrectionPack
from .service import build


def run(pack: CorrectionPack, book: bytes):
    correction_id, raw, result, created = build(pack, book)
    stored = persist(correction_id, raw, book, result, created)
    return json.loads(stored['result'])


def replay(correction_id):
    old = fetch(correction_id)
    pack = CorrectionPack.model_validate(json.loads(old['package']))
    return run(pack, old['book'])


def get(correction_id):
    return json.loads(fetch(correction_id)['result'])
