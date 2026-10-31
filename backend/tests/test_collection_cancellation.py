from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
import pytest
from test_api import client
from test_collections import payload, balance
from manage_user import create_user
import main

def create(client,**changes):
    response=client.post('/api/collections',json=payload(**changes))
    assert response.status_code==201
    return response.json()

def test_cancel_restores_balance_summary_and_retains_record(client):
    before=balance(client)
    summary=client.get('/api/dashboard').json()
    entry=create(client)
    response=client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'  Örnek hatalı kayıt  '})
    assert response.status_code==200
    cancelled=response.json()
    assert not cancelled['can_cancel']
    assert cancelled['cancellation']['reason']=='Örnek hatalı kayıt'
    assert cancelled['cancellation']['cancelled_at'].endswith('+03:00')
    for key in ('amount_cents','customer_id','date','method','note'):
        assert cancelled[key]==entry[key]
    assert balance(client)==before
    assert client.get('/api/dashboard').json()==summary
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Tekrar iptal'}).json()==cancelled
    main.initialize()
    assert client.get('/api/collections').json()[0]==cancelled
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM collections').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM collection_cancellations').fetchone()[0]==1
        assert db.execute('SELECT user_id FROM collection_cancellations').fetchone()[0]==1

def test_concurrent_cancellation_only_records_once(client):
    entry=create(client)
    before=balance(client)['balance_cents']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:main.cancel_collection(entry['id'],main.CancellationInput(reason='Örnek iptal'),{'id':1}),range(2)))
    assert results[0]==results[1]
    assert balance(client)['balance_cents']==before+1235
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM collection_cancellations').fetchone()[0]==1

@pytest.mark.parametrize('role',['staff','viewer'])
def test_only_admin_can_cancel(client,role):
    entry=create(client)
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==403
    assert balance(client)['collected_cents']==1235

def test_legacy_missing_and_csrf_anonymous(client):
    assert client.post('/api/collections/1/cancel',json={'reason':'Örnek iptal'}).status_code==409
    assert not client.get('/api/collections').json()[0]['can_cancel']
    assert client.post('/api/collections/999/cancel',json={'reason':'Örnek iptal'}).status_code==404
    entry=create(client)
    path=f"/api/collections/{entry['id']}/cancel"
    assert client.post(path,json={'reason':'Örnek iptal'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.post(path,json={'reason':'Örnek iptal'}).status_code==401

@pytest.mark.parametrize('reason',['','  ','AB','x'*501])
def test_reason_required(client,reason):
    entry=create(client)
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':reason}).status_code==422
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM collection_cancellations').fetchone()

def test_cancel_historical_collection_does_not_change_today(client):
    entry=create(client)
    with main.database() as db:
        db.execute("UPDATE collections SET date='2000-01-01' WHERE id=?",(entry['id'],))
    today=client.get('/api/dashboard').json()['collections']
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    assert client.get('/api/dashboard').json()['collections']==today
    assert balance(client)['collected_cents']==0

def test_overpayment_credit_returns_to_zero(client):
    customer=client.post('/api/customers',json={'name':'Örnek Avans','contact':'Demo Kişi','district':'Örnek'}).json()
    entry=create(client,customer_id=customer['id'],amount='10.00')
    assert balance(client,customer['id'])['balance_cents']==-1000
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    assert balance(client,customer['id'])['balance_cents']==0

def test_retry_original_creation_does_not_reactivate(client):
    item=payload()
    entry=client.post('/api/collections',json=item).json()
    cancelled=client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Örnek iptal'}).json()
    assert client.post('/api/collections',json=item).json()==cancelled
    assert balance(client)['collected_cents']==0

def test_revoked_admin_cannot_mutate(client):
    entry=create(client)
    with main.database() as db:
        db.execute("UPDATE users SET role='staff'")
    with pytest.raises(HTTPException) as error:
        main.cancel_collection(entry['id'],main.CancellationInput(reason='Örnek iptal'),{'id':1})
    assert error.value.status_code==403
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM collection_cancellations').fetchone()

def test_admin_can_cancel_staff_collection(client):
    create_user('synthetic-staff','Synthetic-password-42','staff')
    entry=main.add_collection(main.CollectionInput(**payload()),{'id':2})
    assert client.post(f"/api/collections/{entry['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    with main.database() as db:
        assert db.execute('SELECT created_by FROM collections WHERE id=?',(entry['id'],)).fetchone()[0]==2
        assert db.execute('SELECT user_id FROM collection_cancellations').fetchone()[0]==1
