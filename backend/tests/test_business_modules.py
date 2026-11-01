from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pytest
from test_api import client
from test_finance import account
import main

def supplier(client):
    return client.post('/api/suppliers',json={'name':'Örnek Tedarikçi','contact':'Yetkili','request_id':str(uuid4())}).json()['id']
def buy(client,sid,rid=None,**changes):
    return client.post('/api/purchases',json={'supplier_id':sid,'date':'2020-01-01','due_date':'2020-01-10','note':'Örnek alış','request_id':rid or str(uuid4()),'items':[{'product_id':1,'quantity':2,'unit_cost':'12.35'}],**changes})
def pay(client,sid,aid,rid=None):
    return client.post('/api/supplier-payments',json={'supplier_id':sid,'account_id':aid,'date':'2020-01-02','amount':'10.01','note':'Örnek ödeme','request_id':rid or str(uuid4())})
def stock(client):return next(p['stock'] for p in client.get('/api/products').json() if p['id']==1)

def test_purchase_stock_debt_retry_cancel_and_payment(client):
    sid=supplier(client);before=stock(client);rid=str(uuid4());purchase=buy(client,sid,rid=rid).json()
    assert purchase['amount_cents']==2470 and stock(client)==before+2
    assert buy(client,sid,rid=rid).json()==purchase and stock(client)==before+2
    assert client.get('/api/suppliers').json()[0]['balance_cents']==2470
    aid=account(client).json()['id'];prid=str(uuid4());payment=pay(client,sid,aid,prid).json()
    assert pay(client,sid,aid,prid).json()==payment
    assert client.get('/api/suppliers').json()[0]['balance_cents']==1469
    assert client.get('/api/finance').json()['accounts'][0]['balance_cents']==8999
    assert client.post(f"/api/finance/entries/{payment['finance_entry_id']}/cancel",json={'reason':'Yanlış yer'}).status_code==409
    assert client.post(f"/api/supplier-payments/{payment['id']}/cancel",json={'reason':'Ödeme iptali'}).status_code==200
    assert client.get('/api/suppliers').json()[0]['balance_cents']==2470
    assert client.post(f"/api/purchases/{purchase['id']}/cancel",json={'reason':'Alış iptali'}).status_code==200
    assert stock(client)==before and client.get('/api/suppliers').json()[0]['balance_cents']==0
    ledger=client.get('/api/stock-ledger').json()
    row=next(p for p in ledger['products'] if p['id']==1)
    assert row['stock']==row['opening_stock']+row['net_change']

def test_purchase_validation_stock_rollback_and_supplier_version(client):
    sid=supplier(client);before=stock(client)
    assert buy(client,sid,items=[{'product_id':999,'quantity':1,'unit_cost':'1'}]).status_code==404
    assert buy(client,sid,items=[{'product_id':1,'quantity':10000000,'unit_cost':'1'}]).status_code==409
    assert stock(client)==before
    row=client.get('/api/suppliers').json()[0];payload={'name':'Yeni ad','expected_version':row['version']}
    assert client.post(f'/api/suppliers/{sid}',json=payload).status_code==200
    assert client.post(f'/api/suppliers/{sid}',json=payload).status_code==409
    p=buy(client,sid).json()
    with main.database() as db: db.execute('UPDATE products SET stock=0 WHERE id=1')
    assert client.post(f"/api/purchases/{p['id']}/cancel",json={'reason':'Stok yetersiz'}).status_code==409
    assert client.get('/api/suppliers').json()[0]['balance_cents']==2470

def test_supplier_payment_atomic_failure(client):
    sid=supplier(client);aid=account(client).json()['id']
    with main.database() as db: db.execute("CREATE TRIGGER fail_payment BEFORE INSERT ON supplier_payments BEGIN SELECT RAISE(ABORT,'fail'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError): pay(client,sid,aid)
    data=client.get('/api/finance').json()
    assert data['total']==0 and data['accounts'][0]['balance_cents']==10000

def test_purchasing_readonly_permissions(client):
    sid=supplier(client)
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert buy(client,sid).status_code==403
    assert client.get('/api/suppliers').status_code==200
    assert client.get('/api/purchases').status_code==200
    client.cookies.clear();assert client.get('/api/supplier-payments').status_code==401

def test_receivables_fifo_due_status_versions_and_no_mutation(client):
    # Use deterministic dates and two dated orders, one undated order first.
    with main.database() as db:
        db.execute("UPDATE orders SET date='2020-01-01',due_date=NULL")
        ids=[]
        for day,due,amount in [('2020-01-02','2020-01-03',1000),('2020-01-03','2020-01-10',2000)]:
            ids.append(db.execute("INSERT INTO orders(customer_id,amount_cents,status,date,due_date) VALUES(1,?,'Bekliyor',?,?)",(amount,day,due)).lastrowid)
        db.execute("INSERT INTO collections(customer_id,amount_cents,date) VALUES(1,1280500,'2020-01-04')")
    result=client.get('/api/receivables?customer_id=1').json()
    assert result['remaining_cents']==2500
    assert [r['remaining_cents'] for r in result['rows']]==[500,2000]
    assert all(r['state']=='overdue' for r in result['rows'])
    order=next(o for o in client.get('/api/orders').json() if o['id']==ids[0])
    payload={'due_date':main.today(),'expected_version':order['due_version']}
    assert client.post(f'/api/orders/{ids[0]}/due-date',json=payload).status_code==200
    assert client.post(f'/api/orders/{ids[0]}/due-date',json=payload).status_code==409
    assert client.get('/api/receivables?customer_id=1&status=today').json()['remaining_cents']==500
    assert client.post(f'/api/orders/{ids[1]}/due-date',json={'due_date':'2019-01-01','expected_version':0}).status_code==422

def test_receivables_no_due_credit_and_viewer(client):
    result=client.get('/api/receivables?status=undated').json()
    assert result['total']==4
    with main.database() as db:
        db.execute("INSERT INTO collections(customer_id,amount_cents,date) VALUES(1,9999999,'2000-01-01')")
        db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/receivables?customer_id=1').json()['total']==0
    assert client.post('/api/orders/1/due-date',json={'due_date':None,'expected_version':0}).status_code==403

def test_finance_export_all_rows_numeric_text_safety_and_print(client):
    aid=account(client).json()['id']
    with main.database() as db:
        for i in range(55):
            db.execute("INSERT INTO finance_entries(account_id,kind,amount_cents,date,category,note,request_id,created_by,created_at) VALUES(?,'income',101,'2020-01-01','','=SUM(A1) <script>',?,1,'2020-01-01T12:00:00+03:00')",(aid,str(uuid4())))
    assert len(client.get('/api/finance').json()['entries'])==50
    exported=client.get('/api/finance/export')
    assert exported.status_code==200 and 'spreadsheetml' in exported.headers['content-type']
    with ZipFile(BytesIO(exported.content)) as z:
        assert z.testzip() is None
        for name in z.namelist():
            if name.endswith('.xml') or name.endswith('.rels'): ET.fromstring(z.read(name))
        sheet=ET.fromstring(z.read('xl/worksheets/sheet4.xml'));ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert len(sheet.findall('x:sheetData/x:row',ns))==56
        assert sheet.find('.//x:f',ns) is None
        assert sheet.find('.//x:c[@r="D2"]/x:v',ns).text=='1.01'
    printed=client.get('/api/finance/print').text
    assert '&lt;script&gt;' in printed and '<script>' not in printed
    assert '1,01' in printed
    assert client.get('/api/finance/export?start_date=2021-01-01&end_date=2020-01-01').status_code==422
    client.cookies.clear();assert client.get('/api/finance/export').status_code==401

def test_new_schema_backup_preserves_customers(client):
    from pathlib import Path
    with main.database() as db: db.execute('DROP TABLE supplier_payments')
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    assert len(client.get('/api/customers').json())==4
