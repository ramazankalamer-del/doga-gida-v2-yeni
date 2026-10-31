from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from fastapi import HTTPException
from test_api import client
from test_orders import payload as order_payload
from test_editing import update_payload
import main

def payload(**changes):
    return {'product_id':1,'quantity':5,'note':'  Örnek teslimat  ','request_id':str(uuid4()),**changes}

def ledger(client):
    response=client.get('/api/stock-ledger')
    assert response.status_code==200
    data=response.json()
    for product in data['products']:
        assert product['opening_stock']+product['net_change']==product['stock']
    return data

def product(client,product_id=1):
    return next(row for row in client.get('/api/products').json() if row['id']==product_id)

def test_existing_stock_baseline_has_no_invented_history(client):
    data=ledger(client)
    assert len(data['products'])==5 and data['movements']==[]
    assert sum(p['opening_stock'] for p in data['products'])==334
    main.initialize()
    assert ledger(client)==data

def test_receipt_updates_stock_version_dashboard_and_history(client):
    before=product(client)
    summary=client.get('/api/dashboard').json()
    item=payload()
    result=client.post('/api/stock-receipts',json=item)
    assert result.status_code==201
    movement=result.json()
    assert movement['kind']=='receipt' and movement['quantity']==5
    assert movement['before_stock']==84 and movement['after_stock']==89
    assert movement['note']=='Örnek teslimat' and movement['username']=='tester'
    assert movement['created_at'].endswith('+03:00')
    assert product(client)['version']==before['version']+1
    assert client.get('/api/dashboard').json()['stock']==summary['stock']+5
    assert client.post('/api/stock-receipts',json=item).json()==movement
    assert product(client)['stock']==89
    assert len(ledger(client)['movements'])==1
    main.initialize()
    assert ledger(client)['movements'][0]==movement

def test_order_cancel_and_manual_correction_share_ledger(client):
    order=client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':2}])).json()
    assert ledger(client)['movements'][0]['quantity']==-2
    assert ledger(client)['movements'][0]['order_id']==order['id']
    assert client.post('/api/orders',json={**order_payload(),'request_id':str(uuid4()),'items':[{'product_id':2,'quantity':999999}]}).status_code==409
    assert len(ledger(client)['movements'])==1
    path=f"/api/orders/{order['id']}/cancel"
    assert client.post(path,json={'reason':'Örnek iptal'}).status_code==200
    assert client.post(path,json={'reason':'Tekrar iptal'}).status_code==200
    assert len(ledger(client)['movements'])==2
    assert ledger(client)['movements'][0]['kind']=='cancellation'
    current=product(client)
    assert client.post('/api/products/1',json=update_payload(current,stock=80,name='Örnek Yeni Ad')).status_code==200
    data=ledger(client)
    assert data['movements'][0]['kind']=='correction' and data['movements'][0]['quantity']==-4
    assert data['movements'][0]['name']=='Örnek Yeni Ad'
    assert data['movements'][-1]['name']=='Ayçiçek Yağı 5 L'
    current=product(client)
    assert client.post('/api/products/1',json=update_payload(current,price='99.95')).status_code==200
    assert len(ledger(client)['movements'])==3

def test_new_product_opening_stock_is_recorded(client):
    result=client.post('/api/products',json={'name':'Örnek Yeni Ürün','sku':'LEDGER-1','category':'Örnek','price':'10.00','stock':7,'min_stock':1})
    assert result.status_code==201
    data=ledger(client)
    entry=data['movements'][0]
    assert entry['kind']=='opening' and entry['quantity']==7
    overview=next(p for p in data['products'] if p['id']==result.json()['id'])
    assert overview['opening_stock']==0 and overview['stock']==7

def test_receipt_invalidates_stale_product_edit(client):
    old=product(client)
    assert client.post('/api/stock-receipts',json=payload()).status_code==201
    assert client.post('/api/products/1',json=update_payload(old,stock=100)).status_code==409
    assert product(client)['stock']==89
    assert len(ledger(client)['movements'])==1

@pytest.mark.parametrize('change',[{'quantity':0},{'quantity':-1},{'quantity':1.5},{'quantity':True},{'quantity':10000001},{'note':' '},{'request_id':'invalid'}])
def test_invalid_receipt(client,change):
    assert client.post('/api/stock-receipts',json=payload(**change)).status_code==422
    assert ledger(client)['movements']==[]

def test_missing_product_limit_and_idempotency_conflict(client):
    assert client.post('/api/stock-receipts',json=payload(product_id=999)).status_code==404
    assert client.post('/api/stock-receipts',json=payload(quantity=10000000)).status_code==409
    item=payload()
    assert client.post('/api/stock-receipts',json=item).status_code==201
    assert client.post('/api/stock-receipts',json={**item,'quantity':6}).status_code==409
    assert client.post('/api/stock-receipts',json={**item,'product_id':2}).status_code==409
    assert len(ledger(client)['movements'])==1

@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_receipts_compose_without_duplicates(client,same_request):
    item=payload()
    def save(_):
        return main.add_stock_receipt(main.StockReceiptInput(**(item if same_request else payload())),{'id':1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(save,range(2)))
    assert product(client)['stock']==(89 if same_request else 94)
    assert len(ledger(client)['movements'])==(1 if same_request else 2)
    if same_request:
        assert results[0]==results[1]

@pytest.mark.parametrize('role',['staff','viewer'])
def test_ledger_permissions(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/stock-ledger').status_code==200
    assert client.post('/api/stock-receipts',json=payload()).status_code==(201 if role=='staff' else 403)

def test_csrf_anonymous_and_revoked_writer(client):
    assert client.post('/api/stock-receipts',json=payload(),headers={'X-CSRF-Token':'wrong'}).status_code==403
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    with pytest.raises(HTTPException) as error:
        main.add_stock_receipt(main.StockReceiptInput(**payload()),{'id':1})
    assert error.value.status_code==403
    client.cookies.clear()
    assert client.get('/api/stock-ledger').status_code==401
    assert client.post('/api/stock-receipts',json=payload()).status_code==401

def test_movement_write_failure_rolls_back_stock(client):
    before=product(client)
    with main.database() as db:
        db.executescript("CREATE TRIGGER reject_receipt BEFORE INSERT ON stock_movements WHEN NEW.kind='receipt' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        main.add_stock_receipt(main.StockReceiptInput(**payload()),{'id':1})
    assert product(client)==before
    assert ledger(client)['movements']==[]
