import time
import pytest
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException
import main
import account_settings
from test_api import client
from manage_user import create_user

OLD='Test-only-password-42'
NEW='New-test-only-password-2026'


def change(client,**overrides):
    return client.post('/api/auth/credentials',json={
        'username':'new-admin','current_password':OLD,'new_password':NEW,**overrides})


def login(client,username,password):
    return client.post('/api/auth/login',json={'username':username,'password':password},headers={'X-Requested-With':'doga'})


def test_credentials_atomic_identity_preserved_all_sessions_revoked(client):
    before=client.get('/api/auth/me').json();cookie=client.cookies.get(main.auth.COOKIE)
    with main.database() as db:
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(main.auth.token_hash('other-session'),before['id'],'other-csrf',int(time.time())+3600))
    result=change(client,username='  New-Admin  ',role='viewer',user_id=999)
    assert result.status_code==200 and result.json()=={'status':'ok'}
    assert 'doga_session=' in result.headers['set-cookie'] and 'Max-Age=0' in result.headers['set-cookie']
    assert client.get('/api/auth/me').status_code==401
    with main.database() as db:
        user=db.execute('SELECT * FROM users WHERE id=?',(before['id'],)).fetchone()
        assert user['username']=='new-admin' and user['role']=='admin' and user['active']==1
        assert user['password_hash']!=NEW and main.auth.verify(NEW,user['password_hash'])
        assert db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(before['id'],)).fetchone()[0]==0
    client.cookies.set(main.auth.COOKIE,cookie)
    assert client.get('/api/auth/me').status_code==401
    client.cookies.clear()
    assert login(client,'tester',OLD).status_code==401
    assert login(client,'new-admin',OLD).status_code==401
    assert login(client,'new-admin',NEW).json()['id']==before['id']


def test_wrong_password_duplicate_name_and_weak_input_leave_account_unchanged(client):
    create_user('taken',NEW,'viewer')
    assert change(client,current_password='wrong').status_code==403
    assert change(client,username='TAKEN').status_code==409
    for payload in [{'username':'  '},{'new_password':'short'},{'new_password':' '*12},{'new_password':'x'*129}]:
        result=change(client,**payload)
        assert result.status_code==422
        assert OLD not in result.text and NEW not in result.text
    assert client.get('/api/auth/me').json()['username']=='tester'
    with main.database() as db:
        user=db.execute("SELECT * FROM users WHERE username='tester'").fetchone()
        assert main.auth.verify(OLD,user['password_hash'])
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==1


def test_current_password_attempts_are_limited_and_expire(client):
    for _ in range(5): assert change(client,current_password='wrong').status_code==403
    assert change(client).status_code==429
    with main.database() as db:
        assert db.execute("SELECT failures FROM login_attempts WHERE bucket='credentials:user:1'").fetchone()[0]==5
        db.execute("UPDATE login_attempts SET until=0 WHERE bucket='credentials:user:1'")
    assert change(client).status_code==200


@pytest.mark.parametrize('role',['admin','staff','viewer'])
def test_self_credentials_for_each_role_no_privilege_change(client,role):
    with main.database() as db: db.execute('UPDATE users SET role=?',(role,))
    assert change(client).status_code==200
    assert login(client,'new-admin',NEW).json()['role']==role


def test_credentials_require_session_and_csrf(client):
    response=client.post('/api/auth/credentials',json={'username':'changed','current_password':OLD,'new_password':NEW},headers={'X-CSRF-Token':'wrong'})
    assert response.status_code==403
    assert client.get('/api/auth/me').json()['username']=='tester'
    client.cookies.clear();assert change(client).status_code==401


def test_waiting_request_rechecks_revoked_session_inside_lock(client):
    user=client.get('/api/auth/me').json();cookie=client.cookies.get(main.auth.COOKIE)
    with main.database() as db: db.execute('DELETE FROM sessions')
    route=next(r for r in main.app.routes if getattr(r,'path',None)=='/api/auth/credentials')
    request=Request({'type':'http','method':'POST','path':'/api/auth/credentials',
                     'headers':[(b'cookie',f'{main.auth.COOKIE}={cookie}'.encode())]})
    with pytest.raises(HTTPException) as error:
        route.endpoint(account_settings.CredentialsInput(username='changed',current_password=OLD,new_password=NEW),request,Response(),user)
    assert error.value.status_code==401
    with main.database() as db: assert db.execute('SELECT username FROM users WHERE id=?',(user['id'],)).fetchone()[0]=='tester'
