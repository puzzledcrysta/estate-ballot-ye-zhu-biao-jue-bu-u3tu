"""M8 产权更正：同一议案两份互斥更正的双路复算、对账与复核。"""
import pytest
from app.settings import KEY, UNIT

BOOK = f'{KEY},外部记录值({UNIT})\nP1,100\nP2,60\n'


def form(key, kind, estate, ballot, note=''):
    return {'key': key, 'kind': kind, 'estate': estate, 'ballot': ballot, 'note': note}


@pytest.fixture
def flip_payload():
    # 原票双门槛通过；更正一只改票（人数翻盘），更正二调产权结构但结论不变。
    return {
        'key': 'P1',
        'original': form('P1', '一般', 'A:50:甲=100;B:50:乙=100', '甲:赞成;乙:赞成'),
        'correction_a': form('P1', '一般', 'A:50:甲=100;B:50:乙=100', '甲:赞成;乙:反对'),
        'correction_b': form('P1', '一般', 'A:60:甲=100;B:40:乙=100', '甲:赞成;乙:赞成'),
    }


@pytest.fixture
def stable_payload():
    # 两份更正面积与人数结论都与原票一致（均通过），且金额均与外部账匹配。
    return {
        'key': 'P2',
        'original': form('P2', '一般', 'A:40:甲=100;B:20:乙=100', '甲:赞成;乙:赞成'),
        'correction_a': form('P2', '一般', 'A:30:甲=100;B:30:乙=100', '甲:赞成;乙:赞成'),
        'correction_b': form('P2', '一般', 'A:20:甲=100;B:40:乙=100', '甲:赞成;乙:赞成'),
    }


def submit(client, payload, book=BOOK):
    return client.post('/api/corrections', json={**payload, 'book': book})


def test_flip_is_held_for_verification(client, flip_payload):
    report = submit(client, flip_payload).json()
    assert report['status'] == '待核实' and report['stable'] is False
    assert report['reason'] == 'CORRECTION_FLIP'
    labels = {item['label']: item for item in report['variants']}
    assert labels['原票']['passed'] is True
    assert labels['产权更正一']['passed'] is False
    assert labels['产权更正二']['passed'] is True
    flip, = report['flips']
    assert flip['to'] == 'correction_a' and '由通过变为未通过' in flip['detail']


def test_each_variant_recalculates_area_and_headcount(client, flip_payload):
    variants = {item['slot']: item for item in submit(client, flip_payload).json()['variants']}
    metrics = variants['correction_a']['metrics']
    assert (metrics['产权面积'], metrics['参与人数'], metrics['赞成人数']) == ('100', '2', '1')
    assert metrics['双门槛'] == '未通过'
    assert variants['original']['metrics']['赞成面积'] == '100'
    assert variants['correction_b']['metrics']['产权面积'] == '100'


def test_each_variant_reconciles_with_book_separately(client, flip_payload):
    variants = {item['label']: item for item in submit(client, flip_payload).json()['variants']}
    assert variants['原票']['book'] == {'code': 'MATCH', 'reference': '100', 'delta': '0',
                                        'book_line': 2}
    assert variants['产权更正一']['book']['code'] == 'AMOUNT_DELTA'
    assert variants['产权更正一']['book']['delta'] == '-50'
    # 汇总账保留三路各自的单边/差额痕迹。
    rows = submit(client, flip_payload).json()['book']['rows']
    assert {row['key'] for row in rows} >= {'P1#original', 'P1#correction_a', 'P1#correction_b'}


def test_confirm_blocked_when_conclusions_conflict(client, flip_payload):
    cid = submit(client, flip_payload).json()['manifest']['correction_id']
    blocked = client.post(f'/api/corrections/{cid}/reviews',
                          json={'version': 0, 'decision': '确认', 'note': ''})
    assert (blocked.status_code, blocked.json()['code']) == (422, 'CORRECTION_FLIP')
    held = client.post(f'/api/corrections/{cid}/reviews',
                       json={'version': 0, 'decision': '留待核实', 'note': '产权归属待不动产登记核实'})
    assert held.status_code == 200 and held.json()['decision'] == '留待核实'


def test_stable_pack_can_be_confirmed(client, stable_payload):
    report = submit(client, stable_payload).json()
    assert report['status'] == '结论不变' and report['stable'] is True
    cid = report['manifest']['correction_id']
    ok = client.post(f'/api/corrections/{cid}/reviews',
                     json={'version': 0, 'decision': '确认', 'note': ''})
    assert ok.status_code == 200 and ok.json()['version'] == 1
    assert client.get(f'/api/corrections/{cid}/reviews').json()[0]['decision'] == '确认'


def test_original_and_both_corrections_are_evidence(client, stable_payload):
    cid = submit(client, stable_payload).json()['manifest']['correction_id']
    exported = client.get(f'/api/corrections/{cid}/export').json()
    assert [item['label'] for item in exported['variants']] == ['原票', '产权更正一', '产权更正二']
    for item in exported['variants']:
        assert item['raw'] and item['proof'] and item['fields']


def test_rerun_same_pack_is_idempotent(client, flip_payload):
    first = submit(client, flip_payload).json()
    cid = first['manifest']['correction_id']
    # 等价载荷（键序不同）仍指向同一内容寻址批次。
    reordered = {'book': BOOK, **flip_payload}
    second = client.post('/api/corrections', json=reordered).json()
    assert second['manifest']['correction_id'] == cid
    assert len(client.get('/api/corrections').json()) == 1


def test_signed_pack_grows_no_new_confirmation_on_rerun(client, stable_payload):
    cid = submit(client, stable_payload).json()['manifest']['correction_id']
    client.post(f'/api/corrections/{cid}/reviews',
                json={'version': 0, 'decision': '确认', 'note': '结论不变'})
    client.post(f'/api/corrections/{cid}/replay')
    submit(client, stable_payload)
    timeline = client.get(f'/api/corrections/{cid}/reviews').json()
    assert [item['version'] for item in timeline] == [1]
    assert timeline[0]['decision'] == '确认'


def test_quarantined_correction_is_held(client):
    payload = {
        'key': 'P3',
        'original': form('P3', '一般', 'A:40:甲=100;B:20:乙=100', '甲:赞成;乙:赞成'),
        'correction_a': form('P3', '一般', 'A:80:甲=50+乙=40', '甲:赞成'),
        'correction_b': form('P3', '一般', 'A:20:甲=100;B:40:乙=100', '甲:赞成;乙:赞成'),
    }
    report = submit(client, payload).json()
    assert report['status'] == '待核实' and report['reason'] == 'CORRECTION_QUARANTINE'
    assert report['quarantine'][0]['code'] == 'ESTATE_SHARE'
    cid = report['manifest']['correction_id']
    blocked = client.post(f'/api/corrections/{cid}/reviews',
                          json={'version': 0, 'decision': '确认', 'note': 'x'})
    assert blocked.json()['code'] == 'CORRECTION_QUARANTINE'


def test_identical_corrections_rejected(client, flip_payload):
    payload = {**flip_payload, 'correction_b': dict(flip_payload['correction_a'])}
    response = client.post('/api/corrections', json={**payload, 'book': BOOK})
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_SAME')


def test_corrections_must_share_one_key(client, flip_payload):
    payload = {**flip_payload,
               'correction_b': {**flip_payload['correction_b'], 'key': 'OTHER'}}
    response = client.post('/api/corrections', json={**payload, 'book': BOOK})
    assert (response.status_code, response.json()['code']) == (422, 'CORRECTION_KEY')


def test_stale_review_version_rejected(client, stable_payload):
    cid = submit(client, stable_payload).json()['manifest']['correction_id']
    client.post(f'/api/corrections/{cid}/reviews',
                json={'version': 0, 'decision': '确认', 'note': 'ok'})
    stale = client.post(f'/api/corrections/{cid}/reviews',
                        json={'version': 0, 'decision': '确认', 'note': 'again'})
    assert (stale.status_code, stale.json()['code']) == (409, 'STALE')


def test_hold_requires_note_on_conflict(client, flip_payload):
    cid = submit(client, flip_payload).json()['manifest']['correction_id']
    response = client.post(f'/api/corrections/{cid}/reviews',
                           json={'version': 0, 'decision': '留待核实', 'note': '   '})
    assert (response.status_code, response.json()['code']) == (422, 'REVIEW_NOTE')


def test_unknown_correction_404(client):
    response = client.get('/api/corrections/nope')
    assert (response.status_code, response.json()['code']) == (404, 'RUN_UNKNOWN')


def test_replay_restores_same_result(client, stable_payload):
    first = submit(client, stable_payload).json()
    cid = first['manifest']['correction_id']
    assert client.post(f'/api/corrections/{cid}/replay').json() == first
