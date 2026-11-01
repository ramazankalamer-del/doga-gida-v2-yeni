import pytest
from test_api import client
import main

def seed():
    with main.database() as db:
        db.executemany('INSERT INTO customer_route_days VALUES(?,?)',[(1,1),(2,1),(3,1),(1,4),(2,4)])

def save(client,scope,ids,version=0):
    return client.post(f'/api/route-order/{scope}',json={'customer_ids':ids,'expected_version':version})

def test_persistent_order_is_per_weekday_and_unassigned_scope(client):
    seed()
    assert client.get('/api/route-order/1').json()['customer_ids']==[1,2,3]
    assert save(client,1,[3,1,2]).json()['version']==1
    assert save(client,4,[2,1]).status_code==200
    assert save(client,0,[4]).status_code==200
    main.initialize()
    assert client.get('/api/route-order/1').json()['customer_ids']==[3,1,2]
    assert client.get('/api/route-order/4').json()['customer_ids']==[2,1]
    assert client.get('/api/route-order/0').json()['customer_ids']==[4]

def test_membership_changes_append_new_skip_removed_and_reject_old_form(client):
    seed();assert save(client,1,[3,1,2]).status_code==200
    with main.database() as db:
        db.execute('DELETE FROM customer_route_days WHERE customer_id=1 AND weekday=1')
        db.execute('INSERT INTO customer_route_days VALUES(4,1)')
    assert client.get('/api/route-order/1').json()['customer_ids']==[3,2,4]
    assert save(client,1,[3,1,2],1).status_code==409
    assert save(client,1,[4,3,2],1).status_code==200

def test_stale_version_cannot_overwrite_and_no_customer_visit_or_money_changes(client):
    seed();before=client.get('/api/customers').json();money=client.get('/api/dashboard').json()
    assert save(client,1,[2,3,1]).status_code==200
    assert save(client,1,[1,2,3]).status_code==409
    assert client.get('/api/customers').json()==before
    assert client.get('/api/dashboard').json()==money
    assert client.get('/api/customer-visits?visit_date=2026-10-26').json()==[]

@pytest.mark.parametrize('ids,status',[([1,1,2],422),([1,2],409),([1,2,3,4],409),([True,2,3],422),(['1',2,3],422),([1,2,999],409)])
def test_invalid_partial_or_outside_scope_order_is_rejected(client,ids,status):
    seed();assert save(client,1,ids).status_code==status
    assert client.get('/api/route-order/1').json()['version']==0

def test_scope_validation_permissions_and_csrf(client):
    seed()
    assert client.get('/api/route-order/8').status_code==422
    assert save(client,-1,[]).status_code==422
    assert client.post('/api/route-order/1',json={'customer_ids':[3,2,1],'expected_version':0},headers={'X-CSRF-Token':'bad'}).status_code==403
    with main.database() as db: db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/route-order/1').status_code==200
    assert save(client,1,[3,2,1]).status_code==403
    with pytest.raises(main.HTTPException) as e:
        main.save_route_order(1,main.RouteOrderInput(customer_ids=[3,2,1],expected_version=0),{'id':1})
    assert e.value.status_code==403
    client.cookies.clear()
    assert client.get('/api/route-order/1').status_code==401

def test_failed_position_write_rolls_back_order_and_version(client):
    import sqlite3
    seed();assert save(client,1,[3,2,1]).status_code==200
    with main.database() as db:
        db.execute("CREATE TRIGGER reject_position BEFORE INSERT ON route_order_positions BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        main.save_route_order(1,main.RouteOrderInput(customer_ids=[1,2,3],expected_version=1),{'id':1})
    assert client.get('/api/route-order/1').json()=={'scope_id':1,'version':1,'customer_ids':[3,2,1]}

def test_schema_upgrade_backs_up_once(client):
    from pathlib import Path
    with main.database() as db:
        db.execute('DROP TABLE route_order_positions');db.execute('DROP TABLE route_order_versions')
    main.initialize()
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
