from hashlib import sha256
import json
from datetime import datetime, timezone
from time import perf_counter
from app.errors import DataError
from app.settings import RULE_VERSION, UNIT
from app.modules.domain.rule import evaluate
from app.modules.reconcile.service import compare
from .schema import CorrectionPack, CorrectionForm

SLUGS = ('original', 'correction_a', 'correction_b')
TITLES = {'original': '原票', 'correction_a': '产权更正一', 'correction_b': '产权更正二'}


def cross_check(pack: CorrectionPack):
    forms = (pack.original, pack.correction_a, pack.correction_b)
    keys = {form.key for form in forms}
    if len(keys) != 1 or pack.key not in keys:
        raise DataError('CORRECTION_KEY', '原票与两份更正必须属于同一表决议案')
    if (pack.correction_a.model_dump(include={'kind', 'estate', 'ballot'})
            == pack.correction_b.model_dump(include={'kind', 'estate', 'ballot'})):
        raise DataError('CORRECTION_SAME', '两份产权更正内容完全相同，不构成互斥更正')


def evaluate_form(form: CorrectionForm, order: int):
    record = {'key': form.key, 'line': order, 'revision': None,
              'fields': form.as_fields(), 'raw': [form.key, form.kind, form.estate, form.ballot, form.note]}
    try:
        amount, proof = evaluate(record['fields'])
        metrics = {label: str(value) for label, value, _ in proof}
        passed = metrics['双门槛'] == '通过'
        return {'slot': None, 'label': '', 'key': form.key, 'note': form.note,
                'fields': record['fields'], 'raw': record['raw'], 'ok': True,
                'amount': format(amount, 'f'), 'unit': UNIT, 'passed': passed,
                'metrics': metrics,
                'proof': [{'metric': label, 'value': str(value), 'unit': unit} for label, value, unit in proof]}
    except DataError as error:
        return {'slot': None, 'label': '', 'key': form.key, 'note': form.note,
                'fields': record['fields'], 'raw': record['raw'], 'ok': False,
                'code': error.code, 'detail': str(error)}


def book_match(rows, key):
    line = next((row for row in rows if row['key'] == key), None)
    if line is None:
        return None
    return {'code': line['code'], 'reference': line['reference'], 'delta': line['delta'],
            'book_line': line['book_line']}


def evaluate_pack(pack: CorrectionPack, book: bytes):
    cross_check(pack)
    variants = []
    for order, slot in enumerate(SLUGS, start=1):
        form = getattr(pack, slot)
        outcome = evaluate_form(form, order)
        outcome['slot'] = slot
        outcome['label'] = TITLES[slot]
        if outcome['ok']:
            # 每路更正与外部账独立全外连接，同议案三路互不覆盖。
            report = compare([{'key': pack.key, 'line': order, 'amount': outcome['amount']}], book)
            outcome['book'] = book_match(report['rows'], pack.key)
        else:
            outcome['book'] = None
        variants.append(outcome)
    # 汇总账：三路复算值各自成行（键带槽位后缀），外部账逐笔列示，单边差异各自留痕。
    accepted_rows = [{'key': f'{pack.key}#{item["slot"]}', 'line': index,
                      'amount': item['amount']}
                     for index, item in enumerate((v for v in variants if v['ok']), start=1)]
    book_report = compare(accepted_rows, book)
    usable = [item for item in variants if item['ok']]
    quarantined = [{'slot': item['slot'], 'label': item['label'], 'key': item['key'],
                    'code': item['code'], 'detail': item['detail']}
                   for item in variants if not item['ok']]
    passes = {item['slot']: item['passed'] for item in usable}
    amounts = {item['slot']: item['amount'] for item in usable}
    flips = []
    original = next((item for item in variants if item['slot'] == 'original'), None)
    if original and original['ok']:
        for slot in ('correction_a', 'correction_b'):
            candidate = next(item for item in variants if item['slot'] == slot)
            if candidate['ok'] and candidate['passed'] != original['passed']:
                flips.append({'from': 'original', 'to': slot,
                              'detail': f"{TITLES[slot]}使结论由{'通过' if original['passed'] else '未通过'}"
                                        f"变为{'通过' if candidate['passed'] else '未通过'}"})
    stable = not quarantined and len(set(passes.values())) == 1 and not flips
    if quarantined:
        status, reason = '待核实', 'CORRECTION_QUARANTINE'
    elif flips:
        status, reason = '待核实', 'CORRECTION_FLIP'
    else:
        status, reason = '结论不变', 'MATCH'
    return {'key': pack.key, 'status': status, 'reason': reason, 'stable': stable,
            'flips': flips, 'quarantine': quarantined, 'passes': passes, 'amounts': amounts,
            'variants': variants, 'book': book_report}


def canonical(pack: CorrectionPack, book: bytes):
    raw = json.dumps(pack.model_dump(), ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    fingerprint = sha256(f'{RULE_VERSION}:correction:{sha256(raw).hexdigest()}:'
                         f'{sha256(book).hexdigest()}'.encode()).hexdigest()
    return fingerprint, raw


def build(pack: CorrectionPack, book: bytes):
    correction_id, raw = canonical(pack, book)
    started = perf_counter()
    result = evaluate_pack(pack, book)
    created = datetime.now(timezone.utc).isoformat()
    result['manifest'] = {'correction_id': correction_id, 'package_sha256': sha256(raw).hexdigest(),
                          'book_sha256': sha256(book).hexdigest(), 'version': RULE_VERSION,
                          'parameters': {'mode': '产权更正双路复算'},
                          'elapsed_ms': round((perf_counter() - started) * 100, 2), 'created': created}
    return correction_id, raw, result, created
