import json
from .runs import get
from .decisions import timeline


def bundle(correction_id):
    result = get(correction_id)
    return json.dumps({'manifest': result['manifest'], 'key': result['key'],
                       'status': result['status'], 'stable': result['stable'],
                       'flips': result['flips'], 'quarantine': result['quarantine'],
                       'variants': result['variants'], 'book_summary': result['book'],
                       'reviews': timeline(correction_id)},
                      ensure_ascii=False, indent=2)
