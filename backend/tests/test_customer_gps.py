from pathlib import Path
import sqlite3
import pytest
from test_api import client
from test_editing import customer, update_payload
import main


def test_add_edit_clear_gps_and_persistence(client):
    row=customer(client)
    assert row['latitude'] is None and row['longitude'] is None
    added=client.post('/api/customers/1',json=update_payload(row,latitude=41.0082,longitude=28.9784))
    assert added.status_code==200
    assert added.json()['latitude']==41.0082 and added.json()['longitude']==28.9784
    main.initialize()
    assert customer(client)==added.json()
    edited=client.post('/api/customers/1',json=update_payload(added.json(),latitude=-33.9,longitude=151.2))
    assert edited.status_code==200 and edited.json()['latitude']==-33.9
    cleared=client.post('/api/customers/1',json=update_payload(edited.json(),latitude=None,longitude=None))
    assert cleared.status_code==200
    assert cleared.json()['latitude'] is None and cleared.json()['longitude'] is None
    assert cleared.json()['name']==row['name']
    assert cleared.json()['version']==row['version']+3
    main.initialize()
    assert customer(client)==cleared.json()


def test_create_with_zero_and_boundary_coordinates(client):
    row=customer(client)
    for latitude,longitude in [(0,0),(-90,-180),(90,180)]:
        result=client.post('/api/customers',json={**row,'latitude':latitude,'longitude':longitude})
        assert result.status_code==201
        assert result.json()['latitude']==latitude and result.json()['longitude']==longitude


@pytest.mark.parametrize('gps',[
    {'latitude':91,'longitude':0},{'latitude':0,'longitude':181},
    {'latitude':-91,'longitude':0},{'latitude':0,'longitude':-181},
    {'latitude':True,'longitude':0},{'latitude':'41.00','longitude':29},
    {'latitude':41,'longitude':None},{'latitude':None,'longitude':29},
    {'latitude':0},{'longitude':0},{'latitude':None},
    {'latitude':'NaN','longitude':29},{'latitude':{},'longitude':29}])
def test_invalid_gps_rejected_without_changes(client,gps):
    row=customer(client)
    old={k:v for k,v in row.items() if k not in ('latitude','longitude')}
    assert client.post('/api/customers/1',json={**update_payload(old),**gps}).status_code==422
    assert customer(client)==row
    before=len(client.get('/api/customers').json())
    assert client.post('/api/customers',json={**old,**gps}).status_code==422
    assert len(client.get('/api/customers').json())==before


def test_legacy_client_omitting_gps_preserves_it_and_stale_edit_fails(client):
    old=customer(client)
    added=client.post('/api/customers/1',json=update_payload(old,latitude=41,longitude=29)).json()
    legacy={k:v for k,v in added.items() if k not in ('latitude','longitude')}
    edited=client.post('/api/customers/1',json=update_payload(legacy,name='Yeni müşteri adı'))
    assert edited.status_code==200 and edited.json()['latitude']==41 and edited.json()['longitude']==29
    assert client.post('/api/customers/1',json=update_payload(added,latitude=None,longitude=None)).status_code==409
    assert customer(client)==edited.json()


def test_gps_migration_preserves_customer_and_account(client):
    with main.database() as db:
        customers=[tuple(r) for r in db.execute('SELECT id,name,version FROM customers')]
        users=[tuple(r) for r in db.execute('SELECT * FROM users')]
        db.execute('ALTER TABLE customers DROP COLUMN latitude')
        db.execute('ALTER TABLE customers DROP COLUMN longitude')
    main.initialize()
    with main.database() as db:
        assert [tuple(r) for r in db.execute('SELECT id,name,version FROM customers')]==customers
        assert [tuple(r) for r in db.execute('SELECT * FROM users')]==users
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as backup:
        assert 'latitude' not in {r[1] for r in backup.execute('PRAGMA table_info(customers)')}
    assert customer(client)['latitude'] is None


def test_gps_permissions_and_csrf(client):
    row=customer(client)
    data=update_payload(row,latitude=41,longitude=29)
    assert client.post('/api/customers/1',json=data,headers={'X-CSRF-Token':'wrong'}).status_code==403
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    assert client.post('/api/customers/1',json=data).status_code==403
    assert customer(client)==row
    client.cookies.clear()
    assert client.get('/api/customers').status_code==401
