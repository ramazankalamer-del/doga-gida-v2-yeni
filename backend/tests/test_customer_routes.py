from pathlib import Path
import sqlite3
import pytest
from fastapi import HTTPException
from test_api import client
from test_editing import customer,update_payload
import main


def test_multiple_days_save_sort_persist_and_clear_without_changing_gps(client):
    before=customer(client)
    assert before['route_days']==[]
    result=client.post('/api/customers/1/route-days',json={'route_days':[5,1,3],'expected_version':before['version']})
    assert result.status_code==200
    updated=result.json()
    assert updated['route_days']==[1,3,5] and updated['version']==before['version']+1
    assert updated['name']==before['name'] and updated['latitude']==before['latitude']
    main.initialize()
    assert customer(client)==updated
    cleared=client.post('/api/customers/1/route-days',json={'route_days':[],'expected_version':updated['version']})
    assert cleared.status_code==200 and customer(client)['route_days']==[]
    assert len(client.get('/api/customers').json())==4


def test_create_route_days_and_legacy_customer_edit_preserve_days(client):
    created=client.post('/api/customers',json={'name':'Örnek Rota','contact':'Test Yetkili','district':'Test','route_days':[7,2]}).json()
    assert created['route_days']==[2,7]
    data={k:v for k,v in update_payload(created,name='Rota yeni adı').items() if k!='route_days'}
    assert client.post(f"/api/customers/{created['id']}",json=data).status_code==200
    current=next(c for c in client.get('/api/customers').json() if c['id']==created['id'])
    assert current['route_days']==[2,7]


def test_stale_route_and_customer_edits_do_not_overwrite(client):
    before=customer(client)
    first=client.post('/api/customers/1/route-days',json={'route_days':[1,4],'expected_version':before['version']})
    assert first.status_code==200
    assert client.post('/api/customers/1/route-days',json={'route_days':[2],'expected_version':before['version']}).status_code==409
    assert client.post('/api/customers/1',json=update_payload(before,name='Eski kart')).status_code==409
    assert customer(client)==first.json()


@pytest.mark.parametrize('days',[[0],[8],[True],['1'],[1,1],list(range(1,9)),None,{}])
def test_invalid_route_days_do_not_write(client,days):
    before=customer(client)
    assert client.post('/api/customers/1/route-days',json={'route_days':days,'expected_version':before['version']}).status_code==422
    assert customer(client)==before


def test_route_days_permissions_csrf_and_locked_writer_check(client):
    data={'route_days':[1,4],'expected_version':customer(client)['version']}
    assert client.post('/api/customers/1/route-days',json={'expected_version':data['expected_version']}).status_code==422
    assert client.post('/api/customers/1/route-days',json=data,headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/api/customers/999/route-days',json=data).status_code==404
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    assert client.post('/api/customers/1/route-days',json=data).status_code==403
    assert customer(client)['route_days']==[]
    with pytest.raises(HTTPException) as error:
        main.update_route_days(1,main.RouteDaysUpdate(**data),{'id':1})
    assert error.value.status_code==403
    client.cookies.clear()
    assert client.post('/api/customers/1/route-days',json=data).status_code==401


def test_route_migration_backs_up_and_preserves_accounts(client):
    with main.database() as db:
        before=[tuple(row) for row in db.execute('SELECT * FROM users')]
        db.execute('DROP TABLE customer_route_days')
    main.initialize()
    assert customer(client)['route_days']==[]
    with main.database() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM users')]==before
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT 1 FROM sqlite_master WHERE name='customer_route_days'").fetchone() is None
