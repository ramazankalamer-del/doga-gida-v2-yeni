import pytest
from test_api import client
import main

def test_summary_balance_matches_statement_and_empty_visits(client):
    data=client.get('/api/customers/1/summary').json()
    assert data['balance_cents']==client.get('/api/customers/1/statement').json()['current_balance_cents']
    assert data['balance_cents']==1280000
    assert data['last_visit_record'] is None and data['last_successful_visit_date'] is None
    assert data['customer']['id']==1

def test_latest_date_attempt_successful_and_customer_isolation(client):
    with main.database() as db:
        for customer,day,visited,stamp,note,reason in [(1,'2020-01-01',1,'2022-01-01T12:00:00+03:00','Başarılı not',''),(1,'2020-02-01',0,'2020-02-01T12:00:00+03:00','Son not','Kapalıydı'),(2,'2020-03-01',1,'2020-03-01T12:00:00+03:00','Başka müşteri','')]:
            db.execute('INSERT INTO customer_visits(customer_id,visit_date,visited,version,updated_by,updated_at,note,reason) VALUES(?,?,?,1,1,?,?,?)',(customer,day,visited,stamp,note,reason))
    data=client.get('/api/customers/1/summary').json()
    assert data['last_visit_record']['visit_date']=='2020-02-01'
    assert data['last_visit_record']['reason']=='Kapalıydı'
    assert data['last_successful_visit_date']=='2020-01-01'
    assert data['last_visit_record']['updated_username']=='tester'
    assert client.post('/api/customers/1/visit',json={'visit_date':'2020-02-01','visited':True,'note':'Düzeltildi','expected_version':1}).status_code==200
    data=client.get('/api/customers/1/summary').json()
    assert data['last_successful_visit_date']=='2020-02-01' and data['last_visit_record']['note']=='Düzeltildi'

def test_credit_balance_and_cancelled_collection(client):
    with main.database() as db:
        cid=db.execute("INSERT INTO collections(customer_id,amount_cents,date) VALUES(1,1280001,'2020-01-01')").lastrowid
    assert client.get('/api/customers/1/summary').json()['balance_cents']==-1
    with main.database() as db:
        db.execute("INSERT INTO collection_cancellations VALUES(?,1,'Test iptal','2020-01-02T12:00:00+03:00')",(cid,))
    assert client.get('/api/customers/1/summary').json()['balance_cents']==1280000

def test_future_legacy_visit_not_reported(client,monkeypatch):
    monkeypatch.setattr(main,'today',lambda:'2020-01-01')
    with main.database() as db:
        db.execute("INSERT INTO customer_visits(customer_id,visit_date,visited,version,updated_by,updated_at) VALUES(1,'2020-01-02',1,1,1,'2020-01-02T12:00:00+03:00')")
    data=client.get('/api/customers/1/summary').json()
    assert data['last_successful_visit_date'] is None and data['last_visit_record'] is None

def test_summary_roles_missing_anonymous_and_no_mutation(client):
    with main.database() as db:
        before=[tuple(r) for r in db.execute('SELECT * FROM customers')]
        db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/customers/1/summary').status_code==200
    assert client.get('/api/customers/999/summary').status_code==404
    with main.database() as db: assert [tuple(r) for r in db.execute('SELECT * FROM customers')]==before
    client.cookies.clear()
    assert client.get('/api/customers/1/summary').status_code==401
