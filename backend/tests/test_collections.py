from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
import pytest
from test_api import client
from test_orders import payload as order_payload
import main

def payload(**changes):
    return {'customer_id':1,'amount':'12.35','method':'cash','note':'  Örnek tahsilat  ','request_id':str(uuid4()),**changes}

def balance(client,customer_id=1):
    return next(b for b in client.get('/api/customer-balances').json() if b['id']==customer_id)

def test_collection_updates_balance_summary_and_persistence(client):
    before=balance(client)
    summary=client.get('/api/dashboard').json()
    item=payload()
    response=client.post('/api/collections',json=item)
    assert response.status_code==201
    entry=response.json()
    assert entry['amount_cents']==1235
    assert entry['customer_id']==1
    assert entry['note']=='Örnek tahsilat'
    assert entry['date']==main.today()
    assert balance(client)['balance_cents']==before['balance_cents']-1235
    assert balance(client)['collected_cents']==1235
    assert client.get('/api/dashboard').json()['collections']==summary['collections']+12.35
    assert client.get('/api/dashboard').json()['stock']==summary['stock']
    assert client.post('/api/collections',json=item).json()==entry
    main.initialize()
    assert client.get('/api/collections').json()[0]==entry
    assert balance(client)['collected_cents']==1235
    with main.database() as db:
        row=db.execute('SELECT created_by,created_at FROM collections WHERE id=?',(entry['id'],)).fetchone()
        assert row['created_by']==1 and row['created_at'].endswith('+03:00')

def test_unassigned_legacy_collection_is_never_allocated(client):
    assert balance(client)['sales_cents']==1280000
    assert balance(client)['collected_cents']==0
    assert balance(client)['balance_cents']==1280000
    old=client.get('/api/collections').json()[0]
    assert old['customer_id'] is None and old['customer'] is None
    assert old['amount_cents']==1850000
    main.initialize()
    assert client.get('/api/collections').json()==[old]

def test_overpayment_and_order_cancellation_leave_customer_credit(client):
    customer=client.post('/api/customers',json={'name':'Örnek Hesap','contact':'Demo Kişi','district':'Demo'}).json()
    assert balance(client,customer['id'])['balance_cents']==0
    order=client.post('/api/orders',json=order_payload(customer_id=customer['id'],items=[{'product_id':1,'quantity':1}])).json()
    assert client.post('/api/collections',json=payload(customer_id=customer['id'],amount='400.00')).status_code==201
    assert balance(client,customer['id'])['balance_cents']==-7500
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    result=balance(client,customer['id'])
    assert result['sales_cents']==0 and result['collected_cents']==40000 and result['balance_cents']==-40000

@pytest.mark.parametrize('change',[{'amount':'0'},{'amount':'-1'},{'amount':'1.234'},{'amount':'10000000.01'},{'method':'other'},{'customer_id':True},{'note':'x'*301},{'request_id':'invalid'}])
def test_invalid_collection(client,change):
    assert client.post('/api/collections',json=payload(**change)).status_code==422
    assert len(client.get('/api/collections').json())==1

def test_missing_customer_csrf_and_anonymous(client):
    assert client.post('/api/collections',json=payload(customer_id=999)).status_code==404
    assert client.post('/api/collections',json=payload(),headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.get('/api/collections').status_code==401
    assert client.get('/api/customer-balances').status_code==401
    assert client.post('/api/collections',json=payload()).status_code==401

@pytest.mark.parametrize('role',['staff','viewer'])
def test_collection_roles(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/collections').status_code==200
    assert client.get('/api/customer-balances').status_code==200
    assert client.post('/api/collections',json=payload()).status_code==(201 if role=='staff' else 403)

@pytest.mark.parametrize('change',[{'amount':'12.36'},{'customer_id':2},{'method':'transfer'},{'note':'Farklı kayıt'}])
def test_idempotency_conflicts(client,change):
    item=payload()
    assert client.post('/api/collections',json=item).status_code==201
    assert client.post('/api/collections',json={**item,**change}).status_code==409
    assert len(client.get('/api/collections').json())==2

def test_concurrent_repeat_is_recorded_once(client):
    item=main.CollectionInput(**payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:main.add_collection(item,{'id':1}),range(2)))
    assert results[0]==results[1]
    assert balance(client)['collected_cents']==1235

def test_totals_do_not_multiply_rows_and_include_history(client):
    for amount in ['0.10','0.20']:
        assert client.post('/api/collections',json=payload(amount=amount)).status_code==201
    for _ in range(2):
        assert client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':1}])).status_code==201
    with main.database() as db:
        db.execute("UPDATE collections SET date='2000-01-01' WHERE customer_id=1")
    result=balance(client)
    assert result['sales_cents']==1280000+65000
    assert result['collected_cents']==30
    assert result['balance_cents']==1344970
    assert client.get('/api/dashboard').json()['collections']==18500

def test_revoked_actor_is_rechecked_inside_transaction(client):
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    with pytest.raises(HTTPException) as error:
        main.add_collection(main.CollectionInput(**payload()),{'id':1})
    assert error.value.status_code==403
