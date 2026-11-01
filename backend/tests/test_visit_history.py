import pytest
from test_api import client
import main

def seed():
    with main.database() as db:
        for customer,day,status,note,reason in [(1,'2020-01-01',1,'İlk not',''),(1,'2020-02-01',0,'Tekrar uğranacak','Kapalıydı'),(2,'2020-03-01',1,'Diğer müşteri','')]:
            db.execute('INSERT INTO customer_visits(customer_id,visit_date,visited,version,updated_by,updated_at,note,reason) VALUES(?,?,?,1,1,?,?,?)',(customer,day,status,'2020-03-01T12:00:00+03:00',note,reason))

def test_history_is_customer_scoped_ordered_and_paginated(client):
    seed()
    data=client.get('/api/customers/1/visits?limit=1').json()
    assert data['total']==2 and data['visited']==1 and data['not_visited']==1
    assert data['visits'][0]['visit_date']=='2020-02-01'
    assert data['visits'][0]['reason']=='Kapalıydı'
    second=client.get('/api/customers/1/visits?limit=1&offset=1').json()
    assert second['visits'][0]['note']=='İlk not'
    assert client.get('/api/customers/1/visits?offset=100').json()['visits']==[]
    assert client.get('/api/customers/3/visits').json()['total']==0

def test_date_range_inclusive_and_latest_state_only(client):
    seed()
    data=client.get('/api/customers/1/visits?start_date=2020-02-01&end_date=2020-02-01').json()
    assert data['total']==1 and data['not_visited']==1
    assert client.post('/api/customers/1/visit',json={'visit_date':'2020-02-01','visited':True,'expected_version':1,'note':'Güncel'}).status_code==200
    data=client.get('/api/customers/1/visits').json()
    assert data['total']==2 and data['visited']==2 and data['visits'][0]['note']=='Güncel'
    assert client.get('/api/customers/1/visits?end_date=2019-01-01').json()['total']==0

@pytest.mark.parametrize('query',['start_date=2020-02-01&end_date=2020-01-01','start_date=bad','limit=101','limit=0','offset=-1'])
def test_bad_history_query(client,query):
    assert client.get('/api/customers/1/visits?'+query).status_code==422

def test_read_permissions_missing_and_no_mutation(client):
    seed()
    with main.database() as db:
        before=[tuple(r) for r in db.execute('SELECT * FROM customer_visits')]
        db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/customers/1/visits').status_code==200
    assert client.get('/api/customers/999/visits').status_code==404
    with main.database() as db: assert [tuple(r) for r in db.execute('SELECT * FROM customer_visits')]==before
    client.cookies.clear()
    assert client.get('/api/customers/1/visits').status_code==401
