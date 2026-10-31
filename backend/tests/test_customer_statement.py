import pytest
from test_api import client
from test_collections import balance, payload as collection_payload
from test_orders import payload as order_payload
import main


def new_customer(client):
    return client.post('/api/customers',json={'name':'Örnek Ekstre','contact':'Test Yetkili','district':'Test'}).json()


def statement(client,customer_id=1,query=''):
    response=client.get(f'/api/customers/{customer_id}/statement{query}')
    assert response.status_code==200
    data=response.json()
    running=data['opening_balance_cents']
    for row in data['movements']:
        running+=row['debit_cents']-row['credit_cents']
        assert row['balance_cents']==running
    assert running==data['closing_balance_cents']
    assert running==data['opening_balance_cents']+data['debit_cents']-data['credit_cents']
    assert data['current_balance_cents']==balance(client,customer_id)['balance_cents']
    assert response.headers['cache-control']=='no-store'
    return data


def test_statement_is_scoped_and_excludes_unassigned_legacy_collections(client):
    data=statement(client)
    assert data['customer']['id']==1
    assert data['debit_cents']==1280000 and data['credit_cents']==0
    assert len(data['movements'])==1
    assert data['movements'][0]['reference']=='DG-0001'
    assert data['current_balance_cents']==1280000


def test_empty_account_and_future_period(client):
    customer=new_customer(client)
    data=statement(client,customer['id'])
    assert data['movements']==[] and data['current_balance_cents']==0
    data=statement(client,1,'?start_date=2099-01-01')
    assert data['movements']==[] and data['opening_balance_cents']==1280000


def test_cancellations_are_reversals_in_their_own_period(client):
    customer=new_customer(client)
    with main.database() as db:
        first=db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,10000,'İptal edildi','2026-10-01')",(customer['id'],)).lastrowid
        db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,2000,'Bekliyor','2026-10-04')",(customer['id'],))
        cash=db.execute("INSERT INTO collections(customer_id,amount_cents,date,method,note) VALUES(?,4000,'2026-10-03','cash','Örnek ödeme')",(customer['id'],)).lastrowid
        db.execute('INSERT INTO order_cancellations VALUES(?,?,?,?)',(first,1,'Örnek iptal','2026-10-05T12:00:00+03:00'))
        db.execute('INSERT INTO collection_cancellations VALUES(?,?,?,?)',(cash,1,'Örnek tahsilat iptali','2026-10-06T12:00:00+03:00'))
    data=statement(client,customer['id'])
    assert [row['kind'] for row in data['movements']]==['order','collection','order','order_cancel','collection_cancel']
    assert data['closing_balance_cents']==2000
    period=statement(client,customer['id'],'?start_date=2026-10-03&end_date=2026-10-05')
    assert period['opening_balance_cents']==10000
    assert period['debit_cents']==2000 and period['credit_cents']==14000
    assert period['closing_balance_cents']==-2000
    assert period['current_balance_cents']==2000
    assert [row['date'] for row in period['movements']]==['2026-10-03','2026-10-04','2026-10-05']
    before_cancel=statement(client,customer['id'],'?end_date=2026-10-02')
    assert before_cancel['closing_balance_cents']==10000


def test_real_api_transactions_and_retries_do_not_duplicate_statement(client):
    customer=new_customer(client)
    order=order_payload(customer_id=customer['id'],items=[{'product_id':1,'quantity':1}])
    result=client.post('/api/orders',json=order).json()
    assert client.post('/api/orders',json=order).json()==result
    payment=collection_payload(customer_id=customer['id'],amount='400.01')
    paid=client.post('/api/collections',json=payment).json()
    client.post('/api/collections',json=payment)
    data=statement(client,customer['id'])
    assert len(data['movements'])==2 and data['closing_balance_cents']==-7501
    client.post(f"/api/orders/{result['id']}/cancel",json={'reason':'Test sipariş iptali'})
    client.post(f"/api/collections/{paid['id']}/cancel",json={'reason':'Test tahsilat iptali'})
    data=statement(client,customer['id'])
    assert len(data['movements'])==4 and data['closing_balance_cents']==0


def test_legacy_cancellation_without_date_does_not_invent_a_reversal_date(client):
    with main.database() as db:
        db.execute("UPDATE orders SET status='İptal edildi' WHERE id=1")
    data=statement(client)
    assert data['closing_balance_cents']==0
    assert len(data['movements'])==1 and data['movements'][0]['debit_cents']==0
    assert 'İptal tarihi olmayan' in data['movements'][0]['note']


def test_cancellation_date_uses_istanbul_day(client):
    customer=new_customer(client)
    with main.database() as db:
        order=db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,1,'İptal edildi','2026-10-01')",(customer['id'],)).lastrowid
        db.execute('INSERT INTO order_cancellations VALUES(?,?,?,?)',(order,1,'Örnek iptal','2026-10-01T22:30:00+00:00'))
    data=statement(client,customer['id'],'?end_date=2026-10-01')
    assert data['closing_balance_cents']==1 and data['current_balance_cents']==0
    assert statement(client,customer['id'])['movements'][-1]['date']=='2026-10-02'


@pytest.mark.parametrize('query',['?start_date=2026-11-01&end_date=2026-10-01','?start_date=yanlis','?end_date=2026-02-30'])
def test_invalid_period(client,query):
    assert client.get('/api/customers/1/statement'+query).status_code==422


@pytest.mark.parametrize('role',['admin','staff','viewer'])
def test_statement_read_permissions(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert statement(client)['current_balance_cents']==1280000
    assert client.get('/api/customers/999/statement').status_code==404
    client.cookies.clear()
    assert client.get('/api/customers/1/statement').status_code==401
