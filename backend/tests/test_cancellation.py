from concurrent.futures import ThreadPoolExecutor
import pytest
from test_api import client
from test_orders import payload
import main

def create(client):
    response=client.post('/api/orders',json=payload())
    assert response.status_code==201
    return response.json()

def test_cancel_restores_stock_summary_and_persists_reason(client):
    before=client.get('/api/dashboard').json()
    order=create(client)
    assert order['can_cancel']
    response=client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'  Müşteri vazgeçti  '})
    assert response.status_code==200
    cancelled=response.json()
    assert cancelled['status']=='İptal edildi'
    assert not cancelled['can_cancel']
    assert cancelled['cancellation']['reason']=='Müşteri vazgeçti'
    assert cancelled['cancellation']['cancelled_at'].endswith('+03:00')
    assert cancelled['amount']==order['amount']
    after=client.get('/api/dashboard').json()
    for key in ('sales','orders','stock','customers','collections'):
        assert after[key]==before[key]
    assert after['recent_orders'][0]['status']=='İptal edildi'
    main.initialize()
    assert client.get('/api/orders').json()[0]==cancelled
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Tekrar deneme'}).json()==cancelled
    assert client.get('/api/dashboard').json()==after
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM order_cancellations').fetchone()[0]==1
        assert db.execute('SELECT user_id FROM order_cancellations').fetchone()[0]==1

def test_concurrent_cancellation_only_restores_once(client):
    order=create(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:main.cancel_order(order['id'],main.CancellationInput(reason='Örnek iptal'),{'id':1}),range(2)))
    assert results[0]==results[1]
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==84
        assert db.execute('SELECT stock FROM products WHERE id=2').fetchone()[0]==156
        assert db.execute('SELECT COUNT(*) FROM order_cancellations').fetchone()[0]==1

@pytest.mark.parametrize('status',['Hazırlanıyor','Dağıtımda','Teslim edildi','İptal edildi'])
def test_non_pending_orders_cannot_cancel(client,status):
    order=create(client)
    with main.database() as db:
        db.execute('UPDATE orders SET status=? WHERE id=?',(status,order['id']))
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==409
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==82
        assert not db.execute('SELECT 1 FROM order_cancellations').fetchone()

def test_legacy_order_and_missing_order(client):
    assert client.post('/api/orders/4/cancel',json={'reason':'Örnek iptal'}).status_code==409
    assert client.post('/api/orders/999/cancel',json={'reason':'Örnek iptal'}).status_code==404
    assert all(not o['can_cancel'] for o in client.get('/api/orders').json())

@pytest.mark.parametrize('reason',['','  ','AB','x'*501])
def test_reason_validation(client,reason):
    order=create(client)
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':reason}).status_code==422
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM order_cancellations').fetchone()

@pytest.mark.parametrize('role',['staff','viewer'])
def test_cancellation_roles(client,role):
    order=create(client)
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==(200 if role=='staff' else 403)

def test_csrf_and_anonymous_denied(client):
    order=create(client)
    path=f"/api/orders/{order['id']}/cancel"
    assert client.post(path,json={'reason':'Örnek iptal'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.post(path,json={'reason':'Örnek iptal'}).status_code==401

def test_stock_limit_failure_is_atomic(client):
    order=create(client)
    with main.database() as db:
        db.execute('UPDATE products SET stock=10000000 WHERE id=2')
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==409
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==82
        assert db.execute('SELECT stock FROM products WHERE id=2').fetchone()[0]==10000000
        assert db.execute('SELECT status FROM orders WHERE id=?',(order['id'],)).fetchone()[0]=='Bekliyor'
        assert not db.execute('SELECT 1 FROM order_cancellations').fetchone()

def test_retry_creating_cancelled_order_never_sells_again(client):
    item=payload()
    order=client.post('/api/orders',json=item).json()
    cancelled=client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).json()
    assert client.post('/api/orders',json=item).json()==cancelled
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==84
