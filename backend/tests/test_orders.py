from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from test_api import client
import main

def payload(**changes):
    return {'customer_id':1,'request_id':str(uuid4()),'items':[{'product_id':1,'quantity':2},{'product_id':2,'quantity':3}],**changes}

def test_create_server_prices_stock_dashboard_and_retry(client):
    before=client.get('/api/dashboard').json()
    item=payload(amount=1)
    result=client.post('/api/orders',json=item)
    assert result.status_code==201
    order=result.json()
    assert order['amount']==905
    assert len(order['items'])==2
    assert order['items'][0]['price_cents']==32500
    assert client.post('/api/orders',json=item).json()==order
    summary=client.get('/api/dashboard').json()
    assert summary['sales']==before['sales']+905
    assert summary['orders']==before['orders']+1
    assert summary['stock']==before['stock']-5
    assert client.get('/api/orders').json()[0]==order
    main.initialize()
    assert client.get('/api/orders').json()[0]==order
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==82

def test_all_or_nothing_and_unknown_records(client):
    before=client.get('/api/dashboard').json()
    item=payload(items=[{'product_id':1,'quantity':1},{'product_id':2,'quantity':999}])
    assert client.post('/api/orders',json=item).status_code==409
    assert client.get('/api/dashboard').json()==before
    assert client.post('/api/orders',json=payload(customer_id=999)).status_code==404
    assert client.post('/api/orders',json=payload(items=[{'product_id':999,'quantity':1}])).status_code==404
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==0
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==84

@pytest.mark.parametrize('items',[[],[{'product_id':1,'quantity':0}],[{'product_id':1,'quantity':-1}],[{'product_id':1,'quantity':1.5}],[{'product_id':1,'quantity':True}],[{'product_id':1,'quantity':1},{'product_id':1,'quantity':2}]])
def test_invalid_order(client,items):
    assert client.post('/api/orders',json=payload(items=items)).status_code==422

def test_request_key_conflict_and_csrf(client):
    item=payload()
    assert client.post('/api/orders',json=item).status_code==201
    assert client.post('/api/orders',json={**item,'customer_id':2}).status_code==409
    assert client.post('/api/orders',json={**item,'items':[{'product_id':1,'quantity':1}]}).status_code==409
    assert client.post('/api/orders',json=payload(),headers={'X-CSRF-Token':'wrong'}).status_code==403

@pytest.mark.parametrize('role',['staff','viewer'])
def test_order_roles(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/orders').status_code==200
    assert client.post('/api/orders',json=payload()).status_code==(403 if role=='viewer' else 201)

def test_anonymous_order_denied(client):
    client.cookies.clear()
    assert client.get('/api/orders').status_code==401
    assert client.post('/api/orders',json=payload()).status_code==401

def test_concurrent_orders_cannot_oversell(client):
    with main.database() as db:
        db.execute('UPDATE products SET stock=1 WHERE id=1')
    def save(_):
        try:
            main.add_order(main.OrderInput(**payload(items=[{'product_id':1,'quantity':1}])),{'id':1})
            return 201
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save,range(2)))==[201,409]
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==1

def test_concurrent_retries_only_decrement_once(client):
    item=main.OrderInput(**payload(items=[{'product_id':1,'quantity':1}]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        orders=list(pool.map(lambda _:main.add_order(item,{'id':1}),range(2)))
    assert orders[0]==orders[1]
    with main.database() as db:
        assert db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==83
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==1
