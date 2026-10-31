import pytest
from test_api import client
import main
import auth
from manage_user import create_user

PAYLOAD = {'username':'  Demo-Personel  ','password':'Synthetic-only-password-42','role':'staff'}

def test_create_list_duplicate_and_no_secrets(client):
    result=client.post('/api/users',json=PAYLOAD)
    assert result.status_code==201
    assert result.json()=={'id':2,'username':'demo-personel','role':'staff','active':1}
    assert client.post('/api/users',json=PAYLOAD).status_code==409
    users=client.get('/api/users').json()
    assert len(users)==2
    assert all(set(u)=={'id','username','role','active'} for u in users)
    with main.database() as db:
        encoded=db.execute('SELECT password_hash FROM users WHERE id=2').fetchone()[0]
        assert encoded!=PAYLOAD['password']
        assert auth.verify(PAYLOAD['password'],encoded)

@pytest.mark.parametrize('role',['staff','viewer'])
def test_non_admin_denied(client,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=?',(role,))
    assert client.get('/api/users').status_code==403
    assert client.post('/api/users',json=PAYLOAD).status_code==403
    assert client.post('/api/users/1',json={'role':'admin','active':True}).status_code==403

def test_anonymous_and_csrf_denied(client):
    assert client.post('/api/users',json=PAYLOAD,headers={'X-CSRF-Token':''}).status_code==403
    assert client.post('/api/users/1',json={'role':'admin','active':True},headers={'X-CSRF-Token':'wrong'}).status_code==403
    client.cookies.clear()
    assert client.get('/api/users').status_code==401
    assert client.post('/api/users',json=PAYLOAD).status_code==401
    assert client.post('/api/users/1',json={'role':'admin','active':True}).status_code==401

@pytest.mark.parametrize('change',[{'username':' '},{'password':'short'},{'role':'owner'}])
def test_invalid_create(client,change):
    assert client.post('/api/users',json={**PAYLOAD,**change}).status_code==422

def test_last_admin_and_self_protection(client):
    assert client.post('/api/users/1',json={'role':'viewer','active':True}).status_code==409
    assert client.post('/api/users/1',json={'role':'admin','active':False}).status_code==409
    create_user('second-admin','Synthetic-only-password-42','admin')
    result=client.post('/api/users/1',json={'role':'viewer','active':True})
    assert result.status_code==409
    assert 'Kendi hesabınızın' in result.json()['detail']
    assert client.post('/api/users/2',json={'role':'staff','active':True}).status_code==200
    assert client.get('/api/auth/me').status_code==200

def test_update_revokes_sessions_and_deactivation_blocks_login(client):
    created=client.post('/api/users',json=PAYLOAD).json()
    user_id=created['id']
    token='synthetic-session-token'
    with main.database() as db:
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(auth.token_hash(token),user_id,'csrf',9999999999))
    response=client.post(f'/api/users/{user_id}',json={'role':'viewer','active':False})
    assert response.status_code==200
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(user_id,)).fetchone()[0]==0
    client.cookies.clear()
    assert client.post('/api/auth/login',json={'username':'demo-personel','password':PAYLOAD['password']},headers={'X-Requested-With':'doga'}).status_code==401
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==4

def test_missing_user_and_invalid_update(client):
    assert client.post('/api/users/999',json={'role':'viewer','active':True}).status_code==404
    assert client.post('/api/users/1',json={'role':'owner','active':True}).status_code==422
    assert client.post('/api/users/1',json={'role':'admin','active':'false'}).status_code==422

def test_role_change_revokes_even_active_session_and_reactivation(client):
    created=client.post('/api/users',json=PAYLOAD).json()
    user_id=created['id']
    with main.database() as db:
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('synthetic-hash',user_id,'csrf',9999999999))
    assert client.post(f'/api/users/{user_id}',json={'role':'viewer','active':True}).status_code==200
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM sessions WHERE user_id=?',(user_id,)).fetchone()
    assert client.post(f'/api/users/{user_id}',json={'role':'viewer','active':False}).status_code==200
    assert client.post(f'/api/users/{user_id}',json={'role':'viewer','active':True}).status_code==200
    client.cookies.clear()
    response=client.post('/api/auth/login',json={'username':'demo-personel','password':PAYLOAD['password']},headers={'X-Requested-With':'doga'})
    assert response.status_code==200
    assert response.json()['role']=='viewer'
