from base64 import b64encode
from fastapi import APIRouter, Response
from app.inputs import input_bytes
from app.settings import SAMPLE_ROOT
from .schema import CorrectionPack, CorrectionReview
from .runs import run, replay, get
from .repository import fetch, history
from .decisions import decide, timeline
from .bundle import bundle

router = APIRouter()


def book_bytes(pack: CorrectionPack):
    return input_bytes(pack.book, pack.book_base64, SAMPLE_ROOT / 'external.csv')


@router.post('/api/corrections')
def create(pack: CorrectionPack):
    return run(pack, book_bytes(pack))


@router.get('/api/corrections')
def list_corrections():
    return history()


@router.get('/api/corrections/{correction_id}')
def detail(correction_id: str):
    return get(correction_id)


@router.post('/api/corrections/{correction_id}/replay')
def again(correction_id: str):
    return replay(correction_id)


@router.get('/api/corrections/{correction_id}/source')
def source_inputs(correction_id: str):
    record = fetch(correction_id)
    return {'package_base64': b64encode(record['package']).decode(),
            'book_base64': b64encode(record['book']).decode()}


@router.get('/api/corrections/{correction_id}/reviews')
def reviews(correction_id: str):
    return timeline(correction_id)


@router.post('/api/corrections/{correction_id}/reviews')
def commit(correction_id: str, review: CorrectionReview):
    return decide(correction_id, review.version, review.decision, review.note)


@router.get('/api/corrections/{correction_id}/export')
def export(correction_id: str):
    return Response(bundle(correction_id), media_type='application/json',
                    headers={'Content-Disposition':
                             f'attachment; filename="correction-{correction_id}.json"'})
