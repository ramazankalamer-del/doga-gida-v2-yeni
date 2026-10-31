import pytest
from fastapi.testclient import TestClient
import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'test.db'))
    with TestClient(main.app) as client:
        yield client

def test_seed_idempotent_and_summary(client):
    assert client.get('/api/health').json() == {'status':'ok'}
    before=client.get('/api/dashboard').json()
    main.initialize()
    assert client.get('/api/dashboard').json()==before
    assert before['customers']==4
    assert before['sales']==31075
    assert before['collections']==18500
    assert before['orders']==4
    assert before['stock']==334
    assert len(before['low_stock'])==2

def test_customer_persistence(client):
    payload={'name':'  Örnek Test Market  ','contact':'Demo Kişi','district':'İzmir','phone':''}
    result=client.post('/api/customers',json=payload)
    assert result.status_code==201
    assert result.json()['name']=='Örnek Test Market'
    assert client.get('/api/customers').json()[0]['id']==result.json()['id']
    assert client.get('/api/dashboard').json()['customers']==5

def test_product_validation_duplicate_and_summary(client):
    payload={'name':'Örnek Ürün','sku':'test-1','category':'Gıda','price':'12.35','stock':5,'min_stock':10}
    result=client.post('/api/products',json=payload)
    assert result.status_code==201
    assert result.json()['price']==12.35
    assert result.json()['sku']=='TEST-1'
    assert client.post('/api/products',json=payload).status_code==409
    assert client.get('/api/dashboard').json()['stock']==339
    assert len(client.get('/api/dashboard').json()['low_stock'])==3
    for invalid in [{'price':-1},{'stock':-1},{'stock':1.2},{'name':'  '},{'price':'1.234'}]:
        assert client.post('/api/products',json={**payload,**invalid}).status_code==422

def test_invalid_customer(client):
    assert client.post('/api/customers',json={'name':' ','contact':'AB','district':'CD'}).status_code==422

def test_daily_summary_excludes_older_orders(client):
    with main.database() as db:
        db.execute("INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(1,50000,'Bekliyor','2000-01-01')")
    assert client.get('/api/dashboard').json()['sales']==31075
    assert client.get('/api/dashboard').json()['orders']==4
