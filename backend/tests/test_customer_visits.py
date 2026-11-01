import pytest
from test_api import client
import main

def save(client,day='2020-01-01',visited=True,version=0,customer=1):
    return client.post(f'/api/customers/{customer}/visit',json={'visit_date':day,'visited':visited,'expected_version':version})

def test_dates_persistence_reversal_and_audit(client):
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()==[]
    before=client.get('/api/dashboard').json()
    assert save(client).json()['version']==1
    assert save(client,day='2020-01-02').status_code==200
    assert save(client,visited=False,version=1).json()['visited']==0
    main.initialize()
    rows=client.get('/api/customer-visits?visit_date=2020-01-01').json()
    assert len(rows)==1 and rows[0]['visited']==0 and rows[0]['version']==2
    assert client.get('/api/customer-visits?visit_date=2020-01-02').json()[0]['visited']==1
    assert client.get('/api/dashboard').json()==before
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM customer_visit_events').fetchone()[0]==3

def test_conflict_does_not_overwrite_and_customer_independence(client):
    assert save(client).status_code==200
    assert save(client,visited=False).status_code==409
    assert save(client,customer=2).status_code==200
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM customer_visit_events').fetchone()[0]==2

@pytest.mark.parametrize('change',[{'visit_date':'9999-01-01'},{'visit_date':'2026-02-30'},{'visited':'true'},{'expected_version':True},{'expected_version':-1}])
def test_invalid_no_writes(client,change):
    data={'visit_date':'2020-01-01','visited':True,'expected_version':0,**change}
    assert client.post('/api/customers/1/visit',json=data).status_code==422
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()==[]

def test_permissions_and_missing_customer(client):
    assert save(client,customer=999).status_code==404
    assert client.post('/api/customers/1/visit',json={'visit_date':'2020-01-01','visited':True,'expected_version':0},headers={'X-CSRF-Token':'bad'}).status_code==403
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert save(client).status_code==403
    assert client.get('/api/customer-visits?visit_date=2020-01-01').status_code==200
    with pytest.raises(main.HTTPException) as e:
        main.save_customer_visit(1,main.VisitInput(visit_date='2020-01-01',visited=True,expected_version=0),{'id':1})
    assert e.value.status_code==403
    client.cookies.clear()
    assert save(client).status_code==401
    assert client.get('/api/customer-visits?visit_date=2020-01-01').status_code==401

def test_migration_backup_keeps_prior_data(client):
    from pathlib import Path
    with main.database() as db:
        db.execute('DROP TABLE customer_visit_events');db.execute('DROP TABLE customer_visits')
    main.initialize()
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
    assert len(client.get('/api/customers').json())==4

def test_audit_failure_rolls_back_visit(client):
    import sqlite3
    with main.database() as db:
        db.execute("CREATE TRIGGER fail_visit BEFORE INSERT ON customer_visit_events BEGIN SELECT RAISE(ABORT,'audit failed'); END")
    with pytest.raises(sqlite3.IntegrityError):
        main.save_customer_visit(1,main.VisitInput(visit_date='2020-01-01',visited=True,expected_version=0),{'id':1})
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()==[]

def test_staff_and_today_boundary(client,monkeypatch):
    monkeypatch.setattr(main,'today',lambda:'2026-01-02')
    with main.database() as db: db.execute("UPDATE users SET role='staff'")
    assert save(client,day='2026-01-02').status_code==200
    assert save(client,day='2026-01-03').status_code==422
