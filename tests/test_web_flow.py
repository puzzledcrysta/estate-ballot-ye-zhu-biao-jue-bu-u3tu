from app.settings import TITLE


def test_page_and_stages(client):
    page = client.get('/')
    assert page.status_code == 200 and TITLE in page.text
    for route,field in [('intake','encoding'),('contract','accepted'),('quality','ready'),('domain','accepted'),('reconcile','balanced')]:
        response = client.post(f'/api/{route}',json={})
        assert response.status_code == 200 and field in response.json()


def test_malformed_sample_can_retry(client):
    invalid = client.post('/api/runs',json={'data':'"ab'})
    assert invalid.json()['code']=='CSV'
    assert client.post('/api/runs',json={}).json()['counts']['accepted']==26


def test_accepted_single_source_has_external_diff(client):
    report = client.post('/api/reconcile',json={}).json()
    assert report['balanced'] and report['book']['mismatched']==3


def test_correction_workbench_roundtrip(client):
    page = client.get('/')
    assert page.status_code == 200 and 'correction-desk' in page.text
    payload = {
        'key': 'P1',
        'book': '表决议案,外部记录值(平方米)\nP1,100\n',
        'original': {'key': 'P1', 'kind': '一般', 'estate': 'A:50:甲=100;B:50:乙=100',
                     'ballot': '甲:赞成;乙:赞成'},
        'correction_a': {'key': 'P1', 'kind': '一般', 'estate': 'A:50:甲=100;B:50:乙=100',
                         'ballot': '甲:赞成;乙:反对'},
        'correction_b': {'key': 'P1', 'kind': '一般', 'estate': 'A:60:甲=100;B:40:乙=100',
                         'ballot': '甲:赞成;乙:赞成'},
    }
    report = client.post('/api/corrections', json=payload).json()
    assert report['status'] == '待核实'
    cid = report['manifest']['correction_id']
    assert client.get(f'/api/corrections/{cid}/export').status_code == 200
    assert client.post(f'/api/corrections/{cid}/reviews',
                       json={'version': 0, 'decision': '留待核实', 'note': '待登记核实'}).status_code == 200
    # 同样两份更正重跑：已登记的复核记录不新增。
    client.post(f'/api/corrections/{cid}/replay')
    assert len(client.get(f'/api/corrections/{cid}/reviews').json()) == 1
