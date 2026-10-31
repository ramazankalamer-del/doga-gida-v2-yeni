from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from test_api import client
from test_orders import payload as order_payload
import main

def customer(client):
    return next(row for row in client.get('/api/customers').json() if row['id']==1)

def product(client):
    return next(row for row in client.get('/api/products').json() if row['id']==1)

def update_payload(row,**changes):
    return {**row,'expected_version':row['version'],**changes}

def test_customer_edit_persistence_and_related_records(client):
    original=customer(client)
    before=client.get('/api/customer-balances').json()
    data=update_payload(original,name='  Örnek Düzenlenen Market  ',contact='Örnek Yetkili',phone='0000000000',district='Örnek Bölge')
    result=client.post('/api/customers/1',json=data)
    assert result.status_code==200
    assert result.json()['name']=='Örnek Düzenlenen Market'
    assert result.json()['version']==original['version']+1
    assert result.json()['phone']=='0000000000'
    assert client.get('/api/dashboard').json()['customers']==4
    main.initialize()
    assert customer(client)==result.json()
    after=client.get('/api/customer-balances').json()
    assert [(b['id'],b['balance_cents']) for b in after]==[(b['id'],b['balance_cents']) for b in before]
    assert client.get('/api/orders').json()[-1]['customer']=='Örnek Düzenlenen Market'

def test_stale_customer_edit_cannot_overwrite(client):
    old=customer(client)
    assert client.post('/api/customers/1',json=update_payload(old,name='Örnek Birinci')).status_code==200
    assert client.post('/api/customers/1',json=update_payload(old,name='Örnek İkinci')).status_code==409
    assert customer(client)['name']=='Örnek Birinci'

def test_product_edit_preserves_old_order_snapshot_and_changes_future_price(client):
    old_order=client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':1}])).json()
    current=product(client)
    result=client.post('/api/products/1',json=update_payload(current,name='Örnek Yeni Yağ',sku=' new-001 ',category='Örnek Kategori',price='99.95',stock=100,min_stock=110))
    assert result.status_code==200
    edited=result.json()
    assert edited['sku']=='NEW-001' and edited['price']==99.95 and edited['stock']==100
    assert edited['version']==current['version']+1
    saved=next(o for o in client.get('/api/orders').json() if o['id']==old_order['id'])
    assert saved['items']==old_order['items']
    new_order=client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':1}])).json()
    assert new_order['amount']==99.95
    assert new_order['items'][0]['name']=='Örnek Yeni Yağ'
    assert any(p['id']==1 for p in client.get('/api/dashboard').json()['low_stock'])

def test_order_and_cancellation_invalidate_stale_product_forms(client):
    old=product(client)
    order=client.post('/api/orders',json=order_payload(items=[{'product_id':1,'quantity':2}])).json()
    assert client.post('/api/products/1',json=update_payload(old,stock=100)).status_code==409
    assert product(client)['stock']==82
    after_sale=product(client)
    assert client.post(f"/api/orders/{order['id']}/cancel",json={'reason':'Örnek iptal'}).status_code==200
    assert client.post('/api/products/1',json=update_payload(after_sale,stock=100)).status_code==409
    assert product(client)['stock']==84
    assert product(client)['version']==old['version']+2

def test_duplicate_sku_does_not_partially_update(client):
    old=product(client)
    assert client.post('/api/products/1',json=update_payload(old,sku='dg-002',stock=100)).status_code==409
    assert product(client)==old

@pytest.mark.parametrize('role',['staff','viewer'])
def test_editing_roles(client,role):
    c,p=customer(client),product(client)
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    expected=200 if role=='staff' else 403
    assert client.post('/api/customers/1',json=update_payload(c)).status_code==expected
    assert client.post('/api/products/1',json=update_payload(p)).status_code==expected

def test_csrf_anonymous_missing_records(client):
    c,p=customer(client),product(client)
    for path,data in [('/api/customers',update_payload(c)),('/api/products',update_payload(p))]:
        assert client.post(path+'/999',json=data).status_code==404
        assert client.post(path+'/1',json=data,headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.post('/api/customers/1',json=update_payload(c)).status_code==401
    assert client.post('/api/products/1',json=update_payload(p)).status_code==401

@pytest.mark.parametrize('change',[{'price':'1.234'},{'stock':-1},{'min_stock':-1},{'expected_version':-1},{'expected_version':'0'},{'name':' '}])
def test_invalid_product_edits(client,change):
    old=product(client)
    assert client.post('/api/products/1',json=update_payload(old,**change)).status_code==422
    assert product(client)==old

def test_two_editors_cannot_overwrite_each_other(client):
    old=product(client)
    def edit(name):
        try:
            main.update_product(1,main.ProductUpdate(**update_payload(old,name=name)),{'id':1})
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit,['Örnek Bir','Örnek İki']))==[200,409]
    assert product(client)['version']==old['version']+1

def test_revoked_writer_rechecked_in_transaction(client):
    c,p=customer(client),product(client)
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    for call in [lambda:main.update_customer(1,main.CustomerUpdate(**update_payload(c)),{'id':1}),lambda:main.update_product(1,main.ProductUpdate(**update_payload(p)),{'id':1})]:
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code==403
