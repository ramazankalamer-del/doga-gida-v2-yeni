import pytest
from test_api import client
import main

def seed():
    with main.database() as db:
        db.executemany('INSERT INTO customer_route_days VALUES(?,?)',[(1,1),(1,4),(2,1),(3,4)])
        for customer,amount,status,day in [(1,1001,'Bekliyor','2026-10-26'),(2,2002,'Teslim edildi','2026-10-26'),(3,9000,'Bekliyor','2026-10-26'),(4,4000,'Bekliyor','2026-10-26'),(1,10000,'İptal edildi','2026-10-26'),(1,9999,'Bekliyor','2026-10-27')]:
            db.execute('INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,?,?,?)',(customer,amount,status,day))
        oid=db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(2,8000,'Bekliyor','2026-10-26')").lastrowid
        db.execute("INSERT INTO order_cancellations VALUES(?,1,'test','2026-10-27T12:00:00+03:00')",(oid,))
        for customer,amount in [(1,501),(2,1000),(3,4000),(4,600),(None,9000)]:
            db.execute("INSERT INTO collections(customer_id,amount_cents,date) VALUES(?,?,'2026-10-26')",(customer,amount))
        cid=db.execute("INSERT INTO collections(customer_id,amount_cents,date) VALUES(1,3000,'2026-10-26')").lastrowid
        db.execute("INSERT INTO collection_cancellations VALUES(?,1,'test','2026-10-27T12:00:00+03:00')",(cid,))
        for customer,visited in [(1,1),(2,0),(3,1)]:
            db.execute("INSERT INTO customer_visits(customer_id,visit_date,visited,version,updated_by,updated_at) VALUES(?,'2026-10-26',?,1,1,'2026-10-26T12:00:00+03:00')",(customer,visited))

def test_daily_summary_scope_date_cents_cancellations_and_no_duplicates(client):
    seed()
    data=client.get('/api/daily-route-summary?visit_date=2026-10-26').json()
    assert data=={'date':'2026-10-26','unassigned':False,'customers':2,'visited':1,'remaining':1,'order_count':2,'sales_cents':3003,'returns_cents':0,'collection_count':2,'collections_cents':1501}
    other=client.get('/api/daily-route-summary?visit_date=2026-11-02').json()
    assert other['customers']==2 and other['visited']==other['sales_cents']==other['collections_cents']==0
    assert other['remaining']==2

def test_unassigned_and_empty_day_do_not_leak_other_customers(client):
    seed()
    data=client.get('/api/daily-route-summary?visit_date=2026-10-26&unassigned=true').json()
    assert data['customers']==1 and data['remaining']==1 and data['sales_cents']==4000 and data['collections_cents']==600
    empty=client.get('/api/daily-route-summary?visit_date=2026-10-28').json()
    assert all(empty[k]==0 for k in ['customers','visited','remaining','order_count','sales_cents','collection_count','collections_cents'])

def test_current_route_edits_and_visit_changes_reflect_without_financial_writes(client):
    seed()
    with main.database() as db:
        before=[tuple(r) for r in db.execute('SELECT * FROM orders')]
        db.execute('DELETE FROM customer_route_days WHERE customer_id=2')
    data=client.get('/api/daily-route-summary?visit_date=2026-10-26').json()
    assert data['customers']==data['visited']==1 and data['remaining']==0 and data['sales_cents']==1001
    assert client.post('/api/customers/1/visit',json={'visit_date':'2026-10-26','visited':False,'expected_version':1}).status_code==200
    assert client.get('/api/daily-route-summary?visit_date=2026-10-26').json()['remaining']==1
    with main.database() as db: assert [tuple(r) for r in db.execute('SELECT * FROM orders')]==before

@pytest.mark.parametrize('query',['','visit_date=bad','visit_date=2026-02-30','visit_date=2026-10-26&unassigned=bad'])
def test_summary_input_validation(client,query):
    assert client.get('/api/daily-route-summary?'+query).status_code==422

def test_summary_read_permissions(client):
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/daily-route-summary?visit_date=2026-10-26').status_code==200
    client.cookies.clear()
    assert client.get('/api/daily-route-summary?visit_date=2026-10-26').status_code==401
