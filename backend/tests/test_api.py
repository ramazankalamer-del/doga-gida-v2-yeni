import pytest
from fastapi.testclient import TestClient
import main
import auth
from manage_user import create_user

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setenv('COOKIE_SECURE', '0')
    with TestClient(main.app) as client:
        create_user('tester', 'Test-only-password-42', 'admin')
        result = client.post('/api/auth/login', json={'username':'tester','password':'Test-only-password-42'}, headers={'X-Requested-With':'doga'})
        client.headers['X-CSRF-Token'] = result.json()['csrf']
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

@pytest.mark.parametrize('path',['dashboard','customers','products','auth/me'])
def test_anonymous_denied(client,path):
    client.cookies.clear()
    assert client.get('/api/'+path).status_code==401

@pytest.mark.parametrize('role',['admin','staff','viewer'])
def test_roles_and_csrf(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/customers').status_code==200
    assert client.get('/api/products').status_code==200
    assert client.get('/api/dashboard').status_code==200
    for path,payload in [('customers',{'name':'Demo Market','contact':'Demo Kişi','district':'Demo'}),
                         ('products',{'name':'Demo Ürün','sku':'ROLE-1','category':'Demo','price':10,'stock':1})]:
        assert client.post('/api/'+path,json=payload).status_code==(403 if role=='viewer' else 201)
        assert client.post('/api/'+path,json=payload,headers={'X-CSRF-Token':'wrong'}).status_code==403

def test_logout_expiry_and_storage(client):
    token=client.cookies.get(auth.COOKIE)
    with main.database() as db:
        row=db.execute('SELECT * FROM sessions').fetchone()
        assert row['token_hash']!=token
        assert db.execute('SELECT password_hash FROM users').fetchone()[0]!='Test-only-password-42'
    assert client.post('/api/auth/logout',json={}).status_code==200
    client.cookies.set(auth.COOKIE,token)
    assert client.get('/api/auth/me').status_code==401
    result=client.post('/api/auth/login',json={'username':'tester','password':'Test-only-password-42'},headers={'X-Requested-With':'doga'})
    assert result.status_code==200
    with main.database() as db:
        db.execute('UPDATE sessions SET expires=0')
    assert client.get('/api/customers').status_code==401

def test_login_errors_and_throttle(client):
    client.cookies.clear()
    payload={'username':'missing','password':'incorrect'}
    assert client.post('/api/auth/login',json=payload).status_code==403
    for _ in range(5):
        result=client.post('/api/auth/login',json=payload,headers={'X-Requested-With':'doga'})
        assert result.status_code==401
        assert result.json()['detail']=='Kullanıcı adı veya parola hatalı.'
    assert client.post('/api/auth/login',json=payload,headers={'X-Requested-With':'doga'}).status_code==429

def test_disabled_user_and_live_role_change(client):
    with main.database() as db:
        db.execute("UPDATE users SET role='viewer'")
    assert client.get('/api/auth/me').json()['role']=='viewer'
    with main.database() as db:
        db.execute('UPDATE users SET active=0')
    assert client.get('/api/auth/me').status_code==401

def test_cookie_flags_and_rotation(client,monkeypatch):
    old=client.cookies.get(auth.COOKIE)
    monkeypatch.setenv('COOKIE_SECURE','1')
    result=client.post('/api/auth/login',json={'username':'tester','password':'Test-only-password-42'},headers={'X-Requested-With':'doga'})
    cookie=result.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    assert 'max-age=28800' in cookie
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM sessions WHERE token_hash=?',(auth.token_hash(old),)).fetchone()

def test_anonymous_writes_and_forged_cookie(client):
    client.cookies.clear()
    client.cookies.set(auth.COOKIE,'forged-admin')
    assert client.post('/api/customers',json={'name':'Demo','contact':'Demo','district':'Demo'}).status_code==401
    assert client.post('/api/products',json={'name':'Demo','sku':'FAKE','category':'Demo','price':10,'stock':1}).status_code==401

def test_existing_data_survives_auth_migration(client):
    before=client.get('/api/customers').json()
    with main.database() as db:
        db.executescript('DROP TABLE sessions; DROP TABLE login_attempts; DROP TABLE users;')
    main.initialize()
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==len(before)

def test_password_salts_and_validation():
    from manage_user import create_user
    one=auth.password_hash('Synthetic-password-42')
    two=auth.password_hash('Synthetic-password-42')
    assert one!=two
    assert auth.verify('Synthetic-password-42',one)
    assert not auth.verify('wrong',one)
    with pytest.raises(ValueError):
        create_user('demo','short','admin')
