from uuid import uuid4
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
import main
from test_api import client
from test_business_modules import supplier,buy,pay
from test_finance import account


def customer(client):
    return client.post('/api/customers',json={'name':'İade Market','contact':'Yetkili','district':'İstanbul'}).json()['id']


def sell(client,cid=1,qty=3):
    return client.post('/api/orders',json={'customer_id':cid,'request_id':str(uuid4()),'items':[{'product_id':1,'quantity':qty}]}).json()['id']


def ret(client,kind,sid,qty=1,**changes):
    return client.post('/api/returns',json={'kind':kind,'source_id':sid,'warehouse':'IADE' if kind=='sale' else 'MERKEZ',
        'note':'Örnek ticari iade','request_id':str(uuid4()),'items':[{'product_id':1,'quantity':qty}],**changes})


def product(client): return next(p for p in client.get('/api/products').json() if p['id']==1)
def balance(client,cid): return next(c for c in client.get('/api/customer-balances').json() if c['id']==cid)


def test_sales_return_stock_balance_statement_due_profit_and_cancel(client):
    cid=customer(client);sid=supplier(client)
    buy(client,sid,items=[{'product_id':1,'quantity':10,'unit_cost':'12.35'}])
    original=product(client);oid=sell(client,cid)
    payload_id=str(uuid4());r=ret(client,'sale',oid,request_id=payload_id).json()
    assert r['amount_cents']==32500 and r['warehouse']=='IADE'
    assert product(client)['stock']==original['stock']-3 and product(client)['return_stock']==1
    assert ret(client,'sale',oid,request_id=payload_id).json()==r
    assert product(client)['return_stock']==1
    assert balance(client,cid)['returns_cents']==32500 and balance(client,cid)['balance_cents']==65000
    statement=client.get(f'/api/customers/{cid}/statement').json()
    assert statement['current_balance_cents']==65000 and statement['movements'][-1]['kind']=='sales_return'
    assert client.get(f'/api/customers/{cid}/summary').json()['balance_cents']==65000
    assert client.get(f'/api/receivables?customer_id={cid}').json()['remaining_cents']==65000
    report=client.get('/api/profit-report?product_id=1').json()
    assert report['sales_cents']==65000 and report['estimated_cost_cents']==2470 and report['profit_cents']==62530
    assert client.post(f'/api/orders/{oid}/cancel',json={'reason':'Asıl kaydı iptal'}).status_code==409
    order=next(o for o in client.get('/api/orders').json() if o['id']==oid)
    assert order['has_returns'] and not order['can_cancel']
    source=client.get(f'/api/returns/sources?kind=sale&party_id={cid}').json()['rows'][0]
    assert source['items'][0]['remaining_quantity']==2
    assert ret(client,'sale',oid,qty=3).status_code==409
    assert ret(client,'sale',oid,request_id=payload_id,qty=2).status_code==409
    result=client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'Yanlış iade kaydı'})
    assert result.status_code==200 and product(client)['return_stock']==0
    assert client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'Tekrar iptal'}).status_code==200
    assert balance(client,cid)['balance_cents']==97500
    assert client.get(f'/api/customers/{cid}/statement').json()['current_balance_cents']==97500
    assert client.post(f'/api/orders/{oid}/cancel',json={'reason':'Satış iptali'}).status_code==200
    assert product(client)['stock']==original['stock']
    assert ret(client,'sale',oid).status_code==409


def test_purchase_return_stock_supplier_statement_due_and_cost_source(client):
    sid=supplier(client);aid=account(client).json()['id'];before=product(client)['stock']
    pid=buy(client,sid,items=[{'product_id':1,'quantity':3,'unit_cost':'12.35'}]).json()['id'];pay(client,sid,aid)
    r=ret(client,'purchase',pid).json()
    assert product(client)['stock']==before+2
    assert client.get('/api/suppliers').json()[0]['balance_cents']==1469
    assert client.get(f'/api/suppliers/{sid}/statement').json()['current_cents']==1469
    assert client.get(f'/api/payables?supplier_id={sid}').json()['remaining_cents']==1469
    assert client.post(f'/api/purchases/{pid}/cancel',json={'reason':'Alış iptali'}).status_code==409
    assert client.get('/api/purchases').json()['rows'][0]['has_returns']
    assert ret(client,'purchase',pid,warehouse='IADE').status_code==409
    assert ret(client,'purchase',pid,qty=3).status_code==409
    assert ret(client,'purchase',pid,qty=2).status_code==201
    assert client.get('/api/payables').json()['advance_cents']==1001
    assert client.get('/api/suppliers').json()[0]['balance_cents']==-1001
    assert client.get('/api/stock-needs').status_code==200
    oid=sell(client,qty=1)
    with main.database() as db:
        assert db.execute('''SELECT unit_cost_cents FROM sale_cost_snapshots s JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=?''',(oid,)).fetchone()[0] is None
    assert client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'Alış iade iptali'}).status_code==200
    assert product(client)['stock']==before


def test_return_credit_after_collection_no_finance_movement(client):
    cid=customer(client);oid=sell(client,cid,1)
    client.post('/api/collections',json={'customer_id':cid,'amount':'325','method':'cash','note':'Tam tahsilat','request_id':str(uuid4())})
    finance=client.get('/api/finance').json()
    assert ret(client,'sale',oid).status_code==201
    assert balance(client,cid)['balance_cents']==-32500
    assert client.get('/api/receivables').json()['remaining_cents']>=0
    assert client.get('/api/finance').json()==finance


def test_atomic_multiline_failure_and_cancel_stock_checks(client):
    oid=client.post('/api/orders',json={'customer_id':1,'request_id':str(uuid4()),'items':[{'product_id':1,'quantity':2},{'product_id':2,'quantity':2}]}).json()['id']
    with main.database() as db: db.execute('UPDATE products SET return_stock=10000000 WHERE id=2')
    before=product(client)
    assert ret(client,'sale',oid,items=[{'product_id':1,'quantity':1},{'product_id':2,'quantity':1}]).status_code==409
    assert product(client)==before and client.get('/api/returns?kind=sale').json()['total']==0
    with main.database() as db: db.execute('UPDATE products SET return_stock=0 WHERE id=2')
    r=ret(client,'sale',oid).json()
    with main.database() as db: db.execute('UPDATE products SET return_stock=0 WHERE id=1')
    assert client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'Stok tükenmiş'}).status_code==409
    assert client.get('/api/returns?kind=sale').json()['rows'][0]['cancellation'] is None


def test_return_insert_failure_rolls_back_stock_and_ledger(client):
    oid=sell(client);before=product(client)
    with main.database() as db:
        db.execute("CREATE TRIGGER broken_return BEFORE INSERT ON stock_movements WHEN NEW.kind='sales_return_in' BEGIN SELECT RAISE(ABORT,'fail'); END")
    with pytest.raises(sqlite3.IntegrityError):ret(client,'sale',oid)
    assert product(client)==before and client.get('/api/returns?kind=sale').json()['total']==0


def test_concurrent_returns_cannot_exceed_source_quantity(client):
    oid=sell(client,qty=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:ret(client,'sale',oid).status_code,range(2)))
    assert sorted(results)==[201,409]
    assert product(client)['return_stock']==1


@pytest.mark.parametrize('items',[[],[{'product_id':1,'quantity':0}],[{'product_id':1,'quantity':True}],[{'product_id':1,'quantity':1.5}],[{'product_id':1,'quantity':1},{'product_id':1,'quantity':1}]])
def test_return_validation(client,items):
    oid=sell(client)
    assert ret(client,'sale',oid,items=items).status_code==422
    assert ret(client,'sale',oid,warehouse='MERKEZ').status_code==422
    assert ret(client,'sale',oid,note='   ').status_code==422


def test_return_permissions_and_legacy_source(client):
    assert ret(client,'sale',1).status_code==409
    oid=sell(client)
    r=ret(client,'sale',oid).json()
    with main.database() as db: db.execute("UPDATE users SET role='staff'")
    assert client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'Yetkisiz iptal'}).status_code==403
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert ret(client,'sale',oid).status_code==403
    for path in ['returns?kind=sale','returns/sources?kind=purchase','stock-needs']:
        assert client.get('/api/'+path).status_code==200
    client.cookies.clear();assert client.get('/api/returns?kind=sale').status_code==401


def test_return_periods_and_prior_period_profit_reversal(client,monkeypatch):
    cid=customer(client);sid=supplier(client)
    buy(client,sid,items=[{'product_id':1,'quantity':2,'unit_cost':'10.01'}])
    monkeypatch.setattr(main,'today',lambda:'2026-01-01');oid=sell(client,cid,1)
    # The purchase helper uses 2020, so its cost is available at sale time.
    monkeypatch.setattr(main,'today',lambda:'2026-02-01');r=ret(client,'sale',oid).json()
    report=client.get('/api/profit-report?start_date=2026-02-01&product_id=1').json()
    assert report['sales_cents']==-32500 and report['estimated_cost_cents']==-1001 and report['profit_cents']==-31499
    old=client.get(f'/api/customers/{cid}/statement?end_date=2026-01-31').json()
    assert old['closing_balance_cents']==32500 and old['current_balance_cents']==0
    client.post(f"/api/returns/{r['id']}/cancel",json={'reason':'İade iptali'})
    with main.database() as db:
        db.execute("UPDATE commercial_return_cancellations SET cancelled_at='2026-03-01T12:00:00+03:00'")
    middle=client.get(f'/api/customers/{cid}/statement?end_date=2026-02-28').json()
    assert middle['closing_balance_cents']==0 and middle['current_balance_cents']==32500


def test_stock_needs_estimates_filters_and_migration_backup(client):
    sid=supplier(client)
    pid=buy(client,sid,items=[{'product_id':1,'quantity':1,'unit_cost':'1.01'}]).json()['id']
    with main.database() as db:
        db.execute('UPDATE products SET stock=0,min_stock=5,return_stock=100 WHERE id=1')
    data=client.get('/api/stock-needs?status=out').json()
    row=next(r for r in data['rows'] if r['id']==1)
    assert row['needed_quantity']==6 and row['estimated_cents']==606 and row['return_stock']==100
    assert not any(r['id']==1 for r in client.get('/api/stock-needs?status=low').json()['rows'])
    assert ret(client,'purchase',pid,warehouse='IADE').status_code==201
    row=next(r for r in client.get('/api/stock-needs?status=out').json()['rows'] if r['id']==1)
    assert row['unit_cost_cents'] is None and row['estimated_cents'] is None
    assert client.get('/api/stock-needs?status=bad').status_code==422
    with main.database() as db: db.execute('DROP TABLE commercial_return_cancellations')
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1


def test_return_sources_history_and_needs_pagination_totals(client):
    with main.database() as db:
        for i in range(51):
            oid=db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(1,202,'Bekliyor','2020-01-01')").lastrowid
            db.execute("INSERT INTO order_items(order_id,product_id,name,sku,quantity,price_cents) VALUES(?,1,'Ürün','X',2,101)",(oid,))
            rid=db.execute("""INSERT INTO commercial_returns(kind,order_id,warehouse,date,amount_cents,note,request_id,payload,created_by,created_at)
                VALUES('sale',?,'IADE','2020-01-02',101,'test',?,'{}',1,'2020-01-02')""",(oid,str(uuid4()))).lastrowid
            db.execute("INSERT INTO commercial_return_items VALUES(?,1,'Ürün','X',1,101,NULL)",(rid,))
            db.execute("INSERT INTO products(name,sku,category,price_cents,stock,min_stock) VALUES(?,?,'Test',101,0,1)",(f'Azalan {i}',f'LOW-{i}'))
    for path in ['returns?kind=sale','returns/sources?kind=sale']:
        data=client.get('/api/'+path+'&offset=50').json()
        assert data['total']==51 and len(data['rows'])==1
    needs=client.get('/api/stock-needs?status=out&offset=50').json()
    assert needs['total']==51 and len(needs['rows'])==1 and needs['needed_quantity']==102


def test_daily_dashboard_and_route_subtract_return_on_its_own_date(client):
    oid=sell(client,cid=1,qty=1)
    before=client.get('/api/dashboard').json()['sales']
    ret(client,'sale',oid)
    assert client.get('/api/dashboard').json()['sales']==before-325
    data=client.get('/api/daily-route-summary?unassigned=true&visit_date='+main.today()).json()
    assert data['returns_cents']==32500
    assert data['sales_cents']==int((before-325)*100)
