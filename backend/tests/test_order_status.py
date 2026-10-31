from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from test_api import client
from test_orders import payload
import main

def create(client):
    response=client.post('/api/orders',json=payload(items=[{'product_id':1,'quantity':2}]))
    assert response.status_code==201
    return response.json()

def stage(expected='Bekliyor',target='Hazırlanıyor',**changes):
    return {'expected_status':expected,'status':target,'request_id':str(uuid4()),**changes}

def test_full_flow_history_and_no_extra_stock_or_money_change(client):
    order=create(client)
    products=client.get('/api/products').json()
    summary=client.get('/api/dashboard').json()
    balances=client.get('/api/customer-balances').json()
    for index,(old,new) in enumerate(main.ORDER_NEXT_STATUS.items(),1):
        result=client.post(f"/api/orders/{order['id']}/status",json=stage(old,new))
        assert result.status_code==200
        order=result.json()
        assert order['status']==new
        assert order['next_status']==main.ORDER_NEXT_STATUS.get(new)
        assert not order['can_cancel']
        assert len(order['status_history'])==index
        event=order['status_history'][-1]
        assert event['from_status']==old and event['to_status']==new
        assert event['username']=='tester' and event['changed_at'].endswith('+03:00')
    assert client.get('/api/products').json()==products
    assert client.get('/api/customer-balances').json()==balances
    after=client.get('/api/dashboard').json()
    for key in ('sales','orders','collections','stock'):
        assert after[key]==summary[key]
    assert after['recent_orders'][0]['status']=='Teslim edildi'
    main.initialize()
    assert client.get('/api/orders').json()[0]==order

@pytest.mark.parametrize('old,new',[('Bekliyor','Dağıtımda'),('Bekliyor','Teslim edildi'),('Hazırlanıyor','Hazırlanıyor'),('Dağıtımda','Hazırlanıyor'),('Teslim edildi','Dağıtımda')])
def test_skips_backwards_and_repeated_stage_rejected(client,old,new):
    order=create(client)
    with main.database() as db:
        db.execute('UPDATE orders SET status=? WHERE id=?',(old,order['id']))
    assert client.post(f"/api/orders/{order['id']}/status",json=stage(old,new)).status_code==409
    with main.database() as db:
        assert db.execute('SELECT status FROM orders WHERE id=?',(order['id'],)).fetchone()[0]==old
        assert not db.execute('SELECT 1 FROM order_status_events').fetchone()

def test_retry_stale_request_and_request_key_conflict(client):
    order=create(client)
    path=f"/api/orders/{order['id']}/status"
    item=stage()
    first=client.post(path,json=item).json()
    assert client.post(path,json=item).json()==first
    assert client.post(path,json=stage()).status_code==409
    assert client.post(path,json={**item,'status':'Dağıtımda'}).status_code==409
    assert client.post('/api/orders/1/status',json=item).status_code==409
    assert client.post(path,json=stage('Hazırlanıyor','Dağıtımda')).status_code==200
    assert client.post(path,json=item).json()['status']=='Dağıtımda'
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM order_status_events WHERE order_id=?',(order['id'],)).fetchone()[0]==2

@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_status_updates(client,same_request):
    order=create(client)
    item=stage()
    def advance(_):
        request=item if same_request else stage()
        try:
            result=main.update_order_status(order['id'],main.OrderStatusInput(**request),{'id':1})
            return 200,result
        except HTTPException as error:
            return error.status_code,None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(advance,range(2)))
    assert sorted(r[0] for r in results)==([200,200] if same_request else [200,409])
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM order_status_events').fetchone()[0]==1
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==82

def test_cancel_and_prepare_race_is_atomic(client):
    order=create(client)
    def save(action):
        try:
            if action=='cancel':
                main.cancel_order(order['id'],main.CancellationInput(reason='Örnek iptal'),{'id':1})
            else:
                main.update_order_status(order['id'],main.OrderStatusInput(**stage()),{'id':1})
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save,['cancel','prepare']))==[200,409]
    with main.database() as db:
        status=db.execute('SELECT status FROM orders WHERE id=?',(order['id'],)).fetchone()[0]
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==(84 if status=='İptal edildi' else 82)
        assert db.execute('SELECT COUNT(*) FROM order_status_events').fetchone()[0]==(0 if status=='İptal edildi' else 1)

def test_cancelled_order_cannot_advance_and_prepared_order_cannot_cancel(client):
    first=create(client)
    assert client.post(f"/api/orders/{first['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    assert client.post(f"/api/orders/{first['id']}/status",json=stage()).status_code==409
    second=create(client)
    assert client.post(f"/api/orders/{second['id']}/status",json=stage()).status_code==200
    assert client.post(f"/api/orders/{second['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==409

@pytest.mark.parametrize('role',['staff','viewer'])
def test_stage_permissions(client,role):
    order=create(client)
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.post(f"/api/orders/{order['id']}/status",json=stage()).status_code==(200 if role=='staff' else 403)

def test_csrf_anonymous_missing_and_validation(client):
    order=create(client)
    path=f"/api/orders/{order['id']}/status"
    assert client.post('/api/orders/999/status',json=stage()).status_code==404
    assert client.post(path,json=stage(status='unknown')).status_code==422
    assert client.post(path,json=stage(request_id='invalid')).status_code==422
    assert client.post(path,json=stage(),headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.post(path,json=stage()).status_code==401

def test_revoked_writer_and_legacy_history(client):
    products=client.get('/api/products').json()
    initial=next(o for o in client.get('/api/orders').json() if o['id']==1)
    assert initial['status_history']==[]
    assert client.post('/api/orders/1/status',json=stage('Hazırlanıyor','Dağıtımda')).status_code==200
    assert client.get('/api/products').json()==products
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    with pytest.raises(HTTPException) as error:
        main.update_order_status(1,main.OrderStatusInput(**stage('Dağıtımda','Teslim edildi')),{'id':1})
    assert error.value.status_code==403
