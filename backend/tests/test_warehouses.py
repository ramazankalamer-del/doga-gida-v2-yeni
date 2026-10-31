from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from fastapi import HTTPException
from test_api import client
from test_orders import payload as order_payload
from test_editing import update_payload
import main


def payload(**changes):
    return {'product_id':1,'quantity':5,'note':'Örnek kontrol kaydı','request_id':str(uuid4()),**changes}


def transfer(**changes):
    return {**payload(), 'source':'IADE','target':'MERKEZ','inspection_confirmed':True, **changes}


def product(client):
    return next(p for p in client.get('/api/products').json() if p['id']==1)


def assert_balances(client):
    summary=client.get('/api/stock-ledger').json()
    rows=client.get('/api/warehouses').json()['products']
    for p in rows:
        central=next(row for row in summary['products'] if row['id']==p['id'])
        assert central['stock']==central['opening_stock']+central['net_change']==p['stock']
        assert p['return_stock']==sum(m['quantity'] for m in summary['movements'] if m['product_id']==p['id'] and m['warehouse']=='IADE')


def test_initial_warehouses_and_repeat_initialization(client):
    before=client.get('/api/warehouses').json()
    assert [(w['code'],w['stock'],w['sellable']) for w in before['warehouses']]==[('MERKEZ',334,True),('IADE',0,False)]
    main.initialize()
    assert client.get('/api/warehouses').json()==before
    assert client.get('/api/stock-ledger').json()['movements']==[]


def test_legacy_migration_preserves_records_and_backs_up(client):
    assert client.post('/api/stock-receipts',json=payload()).status_code==201
    with main.database() as db:
        before=[tuple(r) for r in db.execute('SELECT id,name,stock,version FROM products')]
        users=[tuple(r) for r in db.execute('SELECT * FROM users')]
        db.execute('ALTER TABLE stock_movements DROP COLUMN action_id')
        db.execute('ALTER TABLE stock_movements DROP COLUMN warehouse')
        db.execute('ALTER TABLE products DROP COLUMN return_stock')
        db.execute('DROP TABLE warehouse_actions')
    main.initialize()
    with main.database() as db:
        assert [tuple(r) for r in db.execute('SELECT id,name,stock,version FROM products')]==before
        assert [tuple(r) for r in db.execute('SELECT * FROM users')]==users
        assert db.execute('SELECT SUM(return_stock) FROM products').fetchone()[0]==0
        assert db.execute('SELECT warehouse FROM stock_movements').fetchone()[0]=='MERKEZ'
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as backup:
        assert 'return_stock' not in {r[1] for r in backup.execute('PRAGMA table_info(products)')}
        assert backup.execute('SELECT stock FROM products WHERE id=1').fetchone()[0]==89
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    assert_balances(client)


def test_return_does_not_increase_sellable_stock_or_customer_balance(client):
    before=product(client)
    balances=client.get('/api/customer-balances').json()
    action=payload()
    response=client.post('/api/warehouse-returns',json=action)
    assert response.status_code==201
    assert product(client)['stock']==before['stock']
    assert product(client)['return_stock']==5
    assert product(client)['version']==before['version']+1
    assert client.get('/api/customer-balances').json()==balances
    assert client.post('/api/warehouse-returns',json=action).json()==response.json()
    assert product(client)['return_stock']==5
    assert client.post('/api/warehouse-returns',json={**action,'quantity':6}).status_code==409
    assert_balances(client)


def test_transfer_preserves_total_and_records_both_legs(client):
    client.post('/api/warehouse-returns',json=payload())
    item=transfer(quantity=3)
    response=client.post('/api/warehouse-transfers',json=item)
    assert response.status_code==201
    assert product(client)['stock']==87 and product(client)['return_stock']==2
    legs=response.json()['movements']
    assert [(m['warehouse'],m['quantity']) for m in legs]==[('IADE',-3),('MERKEZ',3)]
    assert len({m['action_id'] for m in legs})==1
    assert client.post('/api/warehouse-transfers',json=item).json()==response.json()
    assert client.post('/api/warehouse-transfers',json={**item,'note':'Başka kontrol'}).status_code==409
    assert client.post('/api/warehouse-returns',json={k:v for k,v in item.items() if k not in ('source','target','inspection_confirmed')}).status_code==409
    assert_balances(client)


def test_quarantine_order_cancellation_and_product_edit_keep_returns_separate(client):
    assert client.post('/api/warehouse-transfers',json=transfer(source='MERKEZ',target='IADE',quantity=80)).status_code==201
    assert product(client)['stock']==4 and product(client)['return_stock']==80
    assert client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':5}])).status_code==409
    order=client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':2}])).json()
    assert product(client)['stock']==2
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    assert product(client)['stock']==4 and product(client)['return_stock']==80
    current=product(client)
    assert client.post('/api/products/1',json=update_payload(current,stock=7)).status_code==200
    assert product(client)['return_stock']==80
    assert_balances(client)


@pytest.mark.parametrize('change,status',[
    ({'source':'MERKEZ','target':'MERKEZ'},422),
    ({'source':'BASKA'},422),({'quantity':0},422),({'quantity':True},422),
    ({'inspection_confirmed':False},422),({'inspection_confirmed':'true'},422),
    ({'product_id':999},404),({},409)])
def test_rejected_transfers_leave_stock_unchanged(client,change,status):
    before=product(client)
    assert client.post('/api/warehouse-transfers',json=transfer(**change)).status_code==status
    assert product(client)==before
    assert client.get('/api/stock-ledger').json()['movements']==[]


def test_overflow_and_missing_return_are_rejected(client):
    assert client.post('/api/warehouse-returns',json=payload(product_id=999)).status_code==404
    assert client.post('/api/warehouse-returns',json=payload(quantity=10000000)).status_code==201
    assert client.post('/api/warehouse-returns',json=payload(quantity=1)).status_code==409
    assert client.post('/api/warehouse-transfers',json=transfer(source='MERKEZ',target='IADE',quantity=1)).status_code==409
    assert_balances(client)


@pytest.mark.parametrize('role',['staff','viewer'])
def test_permissions_and_csrf(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/warehouses').status_code==200
    assert client.post('/api/warehouse-returns',json=payload(),headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/api/warehouse-returns',json=payload()).status_code==(201 if role=='staff' else 403)
    assert client.post('/api/warehouse-transfers',json=transfer(quantity=1)).status_code==(201 if role=='staff' else 403)
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    with pytest.raises(HTTPException) as error:
        main.accept_return(main.StockReceiptInput(**payload()),{'id':1})
    assert error.value.status_code==403
    client.cookies.clear()
    assert client.get('/api/warehouses').status_code==401
    assert client.post('/api/warehouse-returns',json=payload()).status_code==401


@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_transfers_do_not_duplicate_or_oversell(client,same_request):
    client.post('/api/warehouse-returns',json=payload(quantity=5))
    item=transfer(quantity=5)
    def save(_):
        try:
            return main.transfer_stock(main.TransferInput(**(item if same_request else transfer(quantity=5))),{'id':1})
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(save,range(2)))
    if same_request:
        assert results[0]==results[1]
    else:
        assert sum(isinstance(r,dict) for r in results)==1 and 409 in results
    assert product(client)['stock']==89 and product(client)['return_stock']==0
    assert_balances(client)


def test_failed_second_leg_rolls_back_entire_transfer(client):
    client.post('/api/warehouse-returns',json=payload())
    before=product(client)
    with main.database() as db:
        db.executescript("CREATE TRIGGER reject_transfer BEFORE INSERT ON stock_movements WHEN NEW.kind='transfer_in' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        main.transfer_stock(main.TransferInput(**transfer()),{'id':1})
    assert product(client)==before
    assert len(client.get('/api/stock-ledger').json()['movements'])==1
    with main.database() as db:
        assert db.execute("SELECT COUNT(*) FROM warehouse_actions WHERE kind='transfer'").fetchone()[0]==0
