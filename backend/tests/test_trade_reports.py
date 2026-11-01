from uuid import uuid4
from pathlib import Path
import sqlite3
import pytest
import main
from test_api import client
from test_finance import account
from test_business_modules import supplier,buy,pay


def sell(client,product=1,quantity=2,rid=None):
    return client.post('/api/orders',json={'customer_id':1,'request_id':rid or str(uuid4()),
        'items':[{'product_id':product,'quantity':quantity}]})


def test_sale_cost_snapshot_unknown_legacy_and_stable_estimate(client):
    sid=supplier(client)
    unknown=sell(client,quantity=1).json()
    purchase=buy(client,sid).json()
    rid=str(uuid4());sale=sell(client,rid=rid).json()
    assert sell(client,rid=rid).json()==sale
    report=client.get('/api/profit-report').json()
    row=next(r for r in report['rows'] if r['id']==1)
    assert row['sold_quantity']==3 and row['unknown_quantity']==1
    assert row['known_sales_cents']==65000 and row['estimated_cost_cents']==2470
    assert row['profit_cents']==62530 and row['purchased_cents']==2470
    assert report['unitemized_sales_cents']==3107500
    assert report['unknown_sales_cents']==3107500+32500
    buy(client,sid,items=[{'product_id':1,'quantity':2,'unit_cost':'20.00'}])
    assert client.post(f"/api/purchases/{purchase['id']}/cancel",json={'reason':'Alış iptali'}).status_code==200
    report=client.get('/api/profit-report?product_id=1').json()
    assert report['estimated_cost_cents']==2470 and report['profit_cents']==62530
    assert report['rows'][0]['last_cost_cents']==2000
    assert client.post(f"/api/orders/{sale['id']}/cancel",json={'reason':'Satış iptali'}).status_code==200
    report=client.get('/api/profit-report?product_id=1').json()
    assert report['known_sales_cents']==0 and report['unknown_sales_cents']==32500
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM sale_cost_snapshots').fetchone()[0]==2


def test_profit_last_valid_purchase_date_bounds_loss_and_rounding(client,monkeypatch):
    sid=supplier(client)
    buy(client,sid,date='2020-01-02',due_date=None,items=[{'product_id':1,'quantity':1,'unit_cost':'400.01'}])
    buy(client,sid,date='2020-01-01',due_date=None,items=[{'product_id':1,'quantity':1,'unit_cost':'1.01'}])
    # Later calendar purchase must not cost a backdated sale.
    monkeypatch.setattr(main,'today',lambda:'2020-01-02')
    sell(client,quantity=1)
    row=client.get('/api/profit-report?start_date=2020-01-02&end_date=2020-01-02&product_id=1').json()['rows'][0]
    assert row['last_cost_cents']==40001 and row['estimated_cost_cents']==40001
    assert row['profit_cents']==-7501 and row['purchased_quantity']==1
    assert client.get('/api/profit-report?end_date=2019-12-31').json()['sales_cents']==0
    assert client.get('/api/profit-report?start_date=2021-01-01&end_date=2020-01-01').status_code==422
    assert client.get('/api/profit-report?product_id=9999').status_code==404


def test_cost_snapshot_failure_rolls_back_sale_and_stock(client):
    before=client.get('/api/dashboard').json()
    with main.database() as db:
        db.execute("CREATE TRIGGER broken_cost BEFORE INSERT ON sale_cost_snapshots BEGIN SELECT RAISE(ABORT,'fail'); END")
    with pytest.raises(sqlite3.IntegrityError): sell(client)
    assert client.get('/api/dashboard').json()==before
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM order_items').fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM stock_movements WHERE kind='order'").fetchone()[0]==0


def test_payables_fifo_date_filters_cancellations_and_credit_isolation(client,monkeypatch):
    monkeypatch.setattr(main,'today',lambda:'2020-01-10')
    a=supplier(client);b=supplier(client);aid=account(client).json()['id']
    old=buy(client,a,date='2020-01-01',due_date=None).json()
    due=buy(client,a,date='2020-01-02',due_date='2020-01-10').json()
    buy(client,a,date='2020-01-03',due_date='2020-01-17')
    buy(client,b,date='2020-01-01',due_date='2020-01-09')
    payment=client.post('/api/supplier-payments',json={'supplier_id':a,'account_id':aid,'date':'2020-01-03',
        'amount':'30.00','note':'Test ödeme','request_id':str(uuid4())}).json()
    data=client.get(f'/api/payables?supplier_id={a}').json()
    assert [r['id'] for r in data['rows']]==[due['id'],3]
    assert data['remaining_cents']==4410 and data['rows'][0]['allocated_cents']==530
    assert client.get('/api/payables?status=overdue').json()['remaining_cents']==2470
    assert client.get(f'/api/payables?supplier_id={a}&status=week').json()['total']==2
    assert client.get(f'/api/payables?supplier_id={a}&status=today').json()['remaining_cents']==1940
    assert client.post(f"/api/purchases/{old['id']}/cancel",json={'reason':'Eski alış iptali'}).status_code==200
    assert client.get(f'/api/payables?supplier_id={a}').json()['remaining_cents']==1940
    assert client.post(f"/api/supplier-payments/{payment['id']}/cancel",json={'reason':'Ödeme iptali'}).status_code==200
    assert client.get(f'/api/payables?supplier_id={a}').json()['remaining_cents']==4940
    client.post('/api/supplier-payments',json={'supplier_id':a,'account_id':aid,'date':'2020-01-03',
        'amount':'60.00','note':'Test avans','request_id':str(uuid4())})
    data=client.get('/api/payables').json()
    assert data['advance_cents']==1060 and data['remaining_cents']==2470
    assert data['rows'][0]['supplier_id']==b
    assert client.get('/api/payables?supplier_id=9999').status_code==404
    assert client.get('/api/payables?status=wrong').status_code==422


def test_statement_cancellation_dates_opening_period_and_current_balance(client):
    sid=supplier(client);aid=account(client).json()['id']
    purchase=buy(client,sid).json();payment=pay(client,sid,aid).json()
    client.post(f"/api/purchases/{purchase['id']}/cancel",json={'reason':'Alış ters kayıt'})
    client.post(f"/api/supplier-payments/{payment['id']}/cancel",json={'reason':'Ödeme ters kayıt'})
    with main.database() as db:
        db.execute("UPDATE purchase_cancellations SET cancelled_at='2020-02-01T23:30:00+00:00'")
        db.execute("UPDATE finance_cancellations SET cancelled_at='2020-02-03T10:00:00+03:00'")
    data=client.get(f'/api/suppliers/{sid}/statement?start_date=2020-01-02&end_date=2020-01-31').json()
    assert data['opening_cents']==2470 and data['closing_cents']==1469 and data['current_cents']==0
    assert data['debit_cents']==0 and data['credit_cents']==1001 and data['total']==1
    full=client.get(f'/api/suppliers/{sid}/statement').json()
    assert [r['balance_cents'] for r in full['rows']]==[2470,1469,-1001,0]
    assert full['rows'][2]['date']=='2020-02-02'
    assert client.get(f'/api/suppliers/{sid}/statement?start_date=2020-02-01&end_date=2020-01-01').status_code==422
    assert client.get('/api/suppliers/9999/statement').status_code==404


def test_reports_pagination_totals_and_readonly_permissions(client):
    sid=supplier(client)
    with main.database() as db:
        for i in range(55):
            db.execute('''INSERT INTO purchases(supplier_id,date,due_date,amount_cents,note,request_id,payload,created_by,created_at)
                VALUES(?,'2020-01-01','2020-01-02',101,'test',?,'{}',1,'2020-01-01')''',(sid,str(uuid4())))
        db.execute("UPDATE users SET role='viewer'")
    for path in [f'suppliers/{sid}/statement','payables']:
        data=client.get('/api/'+path+'?offset=50').json()
        assert data['total']==55 and len(data['rows'])==5
        if path=='payables': assert data['remaining_cents']==5555
        else: assert data['closing_cents']==5555 and data['rows'][0]['balance_cents']==5151
    assert client.get('/api/profit-report').status_code==200
    client.cookies.clear()
    for path in [f'suppliers/{sid}/statement','payables','profit-report']:
        assert client.get('/api/'+path).status_code==401


def test_cost_migration_backup_and_no_guessed_legacy_costs(client):
    with main.database() as db: db.execute('DROP TABLE sale_cost_snapshots')
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM sale_cost_snapshots').fetchone()[0]==0
    assert client.get('/api/profit-report').json()['unknown_sales_cents']==3107500
