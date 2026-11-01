from uuid import uuid4
import sqlite3
import pytest
from test_api import client
from test_finance import account,entry
import main

def collect(client,aid,amount='12.35',rid=None):
    return client.post('/api/collections',json={'customer_id':1,'account_id':aid,'amount':amount,'method':'cash','note':'Bağlı tahsilat','request_id':rid or str(uuid4())})

def transfer(client,source,target,amount='10.01',rid=None):
    return client.post('/api/finance/transfers',json={'source_account_id':source,'target_account_id':target,'amount':amount,'date':'2020-01-02','note':'Kasa banka aktarımı','request_id':rid or str(uuid4())})

def test_linked_receipt_is_atomic_idempotent_and_cancelled_together(client):
    aid=account(client).json()['id'];rid=str(uuid4())
    before=client.get('/api/customers/1/summary').json()['balance_cents']
    receipt=collect(client,aid,rid=rid).json()
    assert receipt['account_id']==aid and receipt['account_name']=='Ana kasa'
    assert collect(client,aid,rid=rid).json()==receipt
    data=client.get('/api/finance').json();movement=data['entries'][0]
    assert data['total']==1 and movement['collection_id']==receipt['id']
    assert data['accounts'][0]['balance_cents']==11235
    assert client.get('/api/customers/1/summary').json()['balance_cents']==before-1235
    assert client.post(f"/api/finance/entries/{movement['id']}/cancel",json={'reason':'Yanlış yerden iptal'}).status_code==409
    assert client.post(f"/api/collections/{receipt['id']}/cancel",json={'reason':'Tahsilat iptali'}).status_code==200
    assert client.get('/api/finance').json()['accounts'][0]['balance_cents']==10000
    assert client.get('/api/customers/1/summary').json()['balance_cents']==before

def test_linked_cancel_cannot_overdraw_cash_and_missing_account_does_not_write(client):
    aid=account(client,opening='0').json()['id']
    receipt=collect(client,aid,amount='10').json()
    entry(client,aid,amount='9')
    assert client.post(f"/api/collections/{receipt['id']}/cancel",json={'reason':'Yetersiz kasa'}).status_code==409
    assert not next(r for r in client.get('/api/collections').json() if r['id']==receipt['id'])['cancellation']
    assert client.get('/api/finance').json()['accounts'][0]['balance_cents']==100
    count=len(client.get('/api/collections').json())
    assert collect(client,999).status_code==404
    assert len(client.get('/api/collections').json())==count

def test_receipt_rollback_if_finance_write_fails(client):
    aid=account(client).json()['id'];before=len(client.get('/api/collections').json())
    with main.database() as db: db.execute("CREATE TRIGGER fail_finance BEFORE INSERT ON finance_entries BEGIN SELECT RAISE(ABORT,'test fail'); END")
    with pytest.raises(sqlite3.IntegrityError):
        main.add_collection(main.CollectionInput(customer_id=1,account_id=aid,amount='2',method='cash',request_id=uuid4()),{'id':1})
    assert len(client.get('/api/collections').json())==before

def test_transfer_two_legs_retries_and_report_exclusion(client):
    a=account(client).json()['id'];b=account(client,name='Banka',kind='bank',opening='20').json()['id'];rid=str(uuid4())
    row=transfer(client,a,b,rid=rid).json()
    assert transfer(client,a,b,rid=rid).json()==row
    assert transfer(client,a,b,amount='11',rid=rid).status_code==409
    data=client.get('/api/finance').json()
    assert [x['balance_cents'] for x in data['accounts']]==[8999,3001]
    assert data['income_cents']==data['withdrawal_cents']==data['expense_cents']==0
    assert data['transfer_in_cents']==data['transfer_out_cents']==1001
    assert client.post(f"/api/finance/entries/{row['source_entry_id']}/cancel",json={'reason':'Tek ayak'}).status_code==409
    assert client.post(f"/api/finance/transfers/{row['id']}/cancel",json={'reason':'Aktarım iptal'}).status_code==200
    assert client.post(f"/api/finance/transfers/{row['id']}/cancel",json={'reason':'Tekrar iptal'}).status_code==200
    assert [x['balance_cents'] for x in client.get('/api/finance').json()['accounts']]==[10000,2000]

def test_transfer_validation_and_atomic_second_leg_failure(client):
    a=account(client).json()['id'];b=account(client,name='İkinci').json()['id']
    assert transfer(client,a,a).status_code==422
    assert transfer(client,a,999).status_code==404
    assert transfer(client,a,b,amount='101').status_code==409
    with main.database() as db: db.execute("CREATE TRIGGER fail_target BEFORE INSERT ON finance_entries WHEN NEW.kind='income' BEGIN SELECT RAISE(ABORT,'fail target'); END")
    with pytest.raises(sqlite3.IntegrityError):
        main.create_finance_transfer(main.FinanceTransferInput(source_account_id=a,target_account_id=b,amount='5',date='2020-01-01',note='Test aktarım',request_id=uuid4()),{'id':1})
    assert client.get('/api/finance').json()['total']==0

def test_transfer_cancel_rollback_when_destination_cash_spent(client):
    a=account(client,kind='bank').json()['id'];b=account(client,name='Kasa',opening='0').json()['id']
    row=transfer(client,a,b,amount='10').json();entry(client,b,amount='9')
    assert client.post(f"/api/finance/transfers/{row['id']}/cancel",json={'reason':'Para harcandı'}).status_code==409
    data=client.get('/api/finance').json()
    assert [x['balance_cents'] for x in data['accounts']]==[9000,100]
    assert not any(x['cancellation'] for x in data['entries'])

def test_expense_categories_use_all_filtered_active_records(client):
    a=account(client).json()['id'];b=account(client,name='İkinci').json()['id']
    entry(client,a,amount='1.01');entry(client,a,amount='2.02');removed=entry(client,a,amount='3.03').json()
    entry(client,b,amount='4.04',category='Kira')
    client.post(f"/api/finance/entries/{removed['id']}/cancel",json={'reason':'İptal gider'})
    report=client.get('/api/finance').json()
    assert report['expense_categories']==[{'category':'Kira','count':1,'amount_cents':404},{'category':'Yakıt','count':2,'amount_cents':303}]
    assert sum(r['amount_cents'] for r in report['expense_categories'])==report['expense_cents']==707
    assert client.get(f'/api/finance?account_id={a}').json()['expense_categories']==[{'category':'Yakıt','count':2,'amount_cents':303}]
    assert client.get('/api/finance?end_date=2019-01-01').json()['expense_categories']==[]

def test_new_tables_backup_and_permissions(client):
    from pathlib import Path
    a=account(client).json()['id'];b=account(client,name='İkinci').json()['id']
    with main.database() as db:
        db.execute('DROP TABLE collection_finance_links');db.execute('DROP TABLE finance_transfers')
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert transfer(client,a,b).status_code==403
    assert client.get('/api/finance').status_code==200
    client.cookies.clear()
    assert transfer(client,a,b).status_code==401
