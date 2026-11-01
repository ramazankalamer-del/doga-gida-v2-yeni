import pytest
from uuid import uuid4
from test_api import client
import main

def account(client,name='Ana kasa',kind='cash',opening='100.00',request_id=None):
    return client.post('/api/finance/accounts',json={'name':name,'kind':kind,'opening':opening,'request_id':request_id or str(uuid4())})

def entry(client,account_id,kind='expense',amount='12.35',request_id=None,**changes):
    return client.post('/api/finance/entries',json={'account_id':account_id,'kind':kind,'amount':amount,'date':'2020-01-02','category':'Yakıt' if kind=='expense' else '','note':'Örnek işlem','request_id':request_id or str(uuid4()),**changes})

def test_account_cents_entries_period_totals_and_cancel(client):
    aid=account(client).json()['id']
    expense=entry(client,aid).json()
    assert entry(client,aid,'income','20.01').status_code==200
    assert entry(client,aid,'withdrawal','1.02').status_code==200
    data=client.get('/api/finance').json()
    assert data['accounts'][0]['balance_cents']==10664
    assert (data['income_cents'],data['expense_cents'],data['withdrawal_cents'])==(2001,1235,102)
    assert client.post(f"/api/finance/entries/{expense['id']}/cancel",json={'reason':'Yanlış gider'}).status_code==200
    assert client.post(f"/api/finance/entries/{expense['id']}/cancel",json={'reason':'Tekrar iptal'}).status_code==200
    data=client.get('/api/finance').json()
    assert data['expense_cents']==0 and data['accounts'][0]['balance_cents']==11899
    assert len(data['entries'])==3 and any(e['cancellation'] for e in data['entries'])

def test_idempotency_and_conflicting_retry(client):
    rid=str(uuid4());first=account(client,request_id=rid)
    assert account(client,request_id=rid).json()==first.json()
    assert account(client,name='Başka',request_id=rid).status_code==409
    eid=str(uuid4());aid=first.json()['id'];one=entry(client,aid,request_id=eid)
    assert entry(client,aid,request_id=eid).json()==one.json()
    assert entry(client,aid,amount='1.00',request_id=eid).status_code==409
    assert client.get('/api/finance').json()['total']==1

def test_cash_insufficient_cancel_and_bank_negative(client):
    aid=account(client,opening='0').json()['id']
    assert entry(client,aid).status_code==409
    incoming=entry(client,aid,'income','10').json()
    expense=entry(client,aid,amount='5').json()
    assert client.post(f"/api/finance/entries/{incoming['id']}/cancel",json={'reason':'İptal denemesi'}).status_code==409
    assert client.post(f"/api/finance/entries/{expense['id']}/cancel",json={'reason':'Gider iptali'}).status_code==200
    assert client.post(f"/api/finance/entries/{incoming['id']}/cancel",json={'reason':'Giriş iptali'}).status_code==200
    bank=account(client,name='Banka',kind='bank',opening='0').json()['id']
    assert entry(client,bank,amount='1').status_code==200
    assert client.get('/api/finance').json()['accounts'][1]['balance_cents']==-100

def test_filters_isolation_and_legacy_not_imported(client):
    before=client.get('/api/customer-balances').json()
    a=account(client).json()['id'];b=account(client,name='İkinci').json()['id']
    entry(client,a,'income','2.01');entry(client,b,'income','9')
    assert client.get(f'/api/finance?account_id={a}&start_date=2020-01-02&end_date=2020-01-02').json()['income_cents']==201
    data=client.get('/api/finance?end_date=2019-01-01').json()
    assert data['total']==data['income_cents']==0 and data['accounts'][0]['balance_cents']==10201
    assert client.get('/api/customer-balances').json()==before
    assert client.get('/api/finance?account_id=999').status_code==404

@pytest.mark.parametrize('changes',[{'amount':'0'},{'amount':'1.001'},{'date':'9999-01-01'},{'category':''},{'note':'  '},{'date':'2020-02-30'}])
def test_invalid_entry_no_write(client,changes):
    aid=account(client).json()['id']
    assert entry(client,aid,**changes).status_code in (422,404)
    assert client.get('/api/finance').json()['total']==0

def test_roles_csrf_locked_role_recheck_and_anonymous(client):
    aid=account(client).json()['id']
    with main.database() as db: db.execute("UPDATE users SET role='staff'")
    assert account(client,name='Reddedilir').status_code==403
    eid=entry(client,aid).json()['id']
    assert client.post(f'/api/finance/entries/{eid}/cancel',json={'reason':'Yetkisiz iptal'}).status_code==403
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert entry(client,aid).status_code==403
    assert client.get('/api/finance').status_code==200
    with pytest.raises(main.HTTPException) as e:
        main.create_finance_entry(main.FinanceEntryInput(account_id=aid,kind='income',amount='1',date='2020-01-01',note='Test',request_id=uuid4()),{'id':1})
    assert e.value.status_code==403
    client.cookies.clear()
    assert client.get('/api/finance').status_code==401

def test_account_validation_migration_and_persistence(client):
    from pathlib import Path
    assert account(client,opening='-1').status_code==422
    assert account(client,name='  ').status_code==422
    assert account(client).status_code==200
    assert account(client,name='ANA KASA').status_code==409
    main.initialize()
    assert len(client.get('/api/finance').json()['accounts'])==1
    with main.database() as db:
        db.execute('DROP TABLE finance_cancellations');db.execute('DROP TABLE finance_entries');db.execute('DROP TABLE finance_accounts')
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    assert client.get('/api/finance').json()['accounts']==[]

def test_concurrent_cash_outflows_cannot_overdraw(client):
    from concurrent.futures import ThreadPoolExecutor
    aid=account(client,opening='10').json()['id']
    def withdraw(_):
        try:
            main.create_finance_entry(main.FinanceEntryInput(account_id=aid,kind='withdrawal',amount='7',date='2020-01-01',note='Eşzamanlı çıkış',request_id=uuid4()),{'id':1})
            return 200
        except main.HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(withdraw,range(2)))==[200,409]
    assert client.get('/api/finance').json()['accounts'][0]['balance_cents']==300

def test_finance_csrf_missing_account_and_invalid_range(client):
    aid=account(client).json()['id']
    payload={'account_id':aid,'kind':'income','amount':'1','date':'2020-01-01','note':'Test giriş','request_id':str(uuid4())}
    assert client.post('/api/finance/entries',json=payload,headers={'X-CSRF-Token':'bad'}).status_code==403
    assert entry(client,999).status_code==404
    assert client.get('/api/finance?start_date=2020-02-01&end_date=2020-01-01').status_code==422
