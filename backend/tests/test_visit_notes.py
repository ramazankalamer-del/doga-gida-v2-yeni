import pytest
from test_api import client
import main

def write(client,**updates):
    return client.post('/api/customers/1/visit',json={'visit_date':'2020-01-01','visited':False,'expected_version':0,**updates})

def test_note_reason_roundtrip_clear_legacy_and_history(client):
    row=write(client,note='  Sipariş görüşülecek  ',reason='  Yetkili yoktu  ').json()
    assert row['note']=='Sipariş görüşülecek' and row['reason']=='Yetkili yoktu'
    # Old clients omit the fields: their status updates preserve notes.
    row=write(client,expected_version=1).json()
    assert row['note']=='Sipariş görüşülecek' and row['reason']=='Yetkili yoktu'
    row=write(client,expected_version=2,visited=True).json()
    assert row['note']=='Sipariş görüşülecek' and row['reason']==''
    row=write(client,expected_version=3,note='',reason='').json()
    assert row['note']==row['reason']==''
    main.initialize()
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()[0]==row
    with main.database() as db:
        events=db.execute('SELECT note,reason FROM customer_visit_events ORDER BY version').fetchall()
        assert tuple(events[0])==('Sipariş görüşülecek','Yetkili yoktu')
        assert tuple(events[-1])==('','')

@pytest.mark.parametrize('fields',[{'note':'x'*1001},{'reason':'x'*301},{'note':None},{'reason':25},{'visited':True,'reason':'Kapalı'}])
def test_invalid_notes_never_write(client,fields):
    assert write(client,**fields).status_code==422
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()==[]

def test_stale_note_edit_cannot_overwrite(client):
    assert write(client,note='İlk not').status_code==200
    assert write(client,note='Eski sürüm').status_code==409
    assert client.get('/api/customer-visits?visit_date=2020-01-01').json()[0]['note']=='İlk not'

def test_old_visit_schema_migration_preserves_rows_and_backup(client):
    from pathlib import Path
    import sqlite3
    assert write(client).status_code==200
    with main.database() as db:
        for table in ('customer_visits','customer_visit_events'):
            db.execute(f'ALTER TABLE {table} DROP COLUMN note')
            db.execute(f'ALTER TABLE {table} DROP COLUMN reason')
    main.initialize()
    row=client.get('/api/customer-visits?visit_date=2020-01-01').json()[0]
    assert row['version']==1 and row['note']==row['reason']==''
    backups=list((Path(main.DB_PATH).parent/'backups').glob('*.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as db:
        assert 'note' not in {r[1] for r in db.execute('PRAGMA table_info(customer_visits)')}
        assert db.execute('SELECT COUNT(*) FROM customer_visits').fetchone()[0]==1
    main.initialize()
    assert len(list((Path(main.DB_PATH).parent/'backups').glob('*.db')))==1
