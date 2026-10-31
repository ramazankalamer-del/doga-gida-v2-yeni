"""Business-rule unit tests, independent of an HTTP server/event loop."""
import time
import pytest
from fastapi import HTTPException
from starlette.requests import Request
import auth
import main
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError
from manage_user import create_user

@pytest.fixture
def operator(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',str(tmp_path/'rules.db'))
    create_user('operator','Synthetic-password-42','admin')
    return {'id':1,'username':'operator','role':'admin'}

def new_user(role='staff'):
    return main.UserInput(username='  Synthetic-user ',password='Synthetic-password-42',role=role)

def rejects(status,call):
    with pytest.raises(HTTPException) as error:
        call()
    assert error.value.status_code==status

def test_creation_normalization_secret_exclusion_and_duplicate(operator):
    result=main.add_user(new_user(),operator)
    assert result=={'id':2,'username':'synthetic-user','role':'staff','active':1}
    assert len(main.list_users(operator))==2
    assert all(set(row)=={'id','username','role','active'} for row in main.list_users(operator))
    rejects(409,lambda:main.add_user(new_user(),operator))
    with main.database() as db:
        assert auth.verify('Synthetic-password-42',db.execute('SELECT password_hash FROM users WHERE id=2').fetchone()[0])

@pytest.mark.parametrize('role',['staff','viewer'])
def test_changed_operator_cannot_mutate(operator,role):
    with main.database() as db:
        db.execute('UPDATE users SET role=? WHERE id=1',(role,))
    rejects(403,lambda:main.add_user(new_user(),operator))
    rejects(403,lambda:main.update_user(1,main.UserUpdate(role='admin',active=True),operator))

@pytest.mark.parametrize('change',[{'role':'viewer','active':True},{'role':'admin','active':False}])
def test_last_administrator_protected(operator,change):
    rejects(409,lambda:main.update_user(1,main.UserUpdate(**change),operator))
    assert main.list_users(operator)[0]['role']=='admin'
    assert main.list_users(operator)[0]['active']==1

def test_self_protection_with_another_admin(operator):
    main.add_user(new_user('admin'),operator)
    rejects(409,lambda:main.update_user(1,main.UserUpdate(role='staff',active=True),operator))
    assert main.update_user(2,main.UserUpdate(role='viewer',active=True),operator)['role']=='viewer'

def test_role_status_revoke_sessions_and_preserve_business_data(operator):
    account=main.add_user(new_user(),operator)
    with main.database() as db:
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('synthetic',account['id'],'csrf',int(time.time())+600))
    main.update_user(account['id'],main.UserUpdate(role='viewer',active=True),operator)
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM sessions WHERE user_id=?',(account['id'],)).fetchone()
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('synthetic2',account['id'],'csrf',int(time.time())+600))
    assert main.update_user(account['id'],main.UserUpdate(role='viewer',active=False),operator)['active']==0
    with main.database() as db:
        assert not db.execute('SELECT 1 FROM sessions WHERE user_id=?',(account['id'],)).fetchone()
        assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==4
        assert db.execute('SELECT COUNT(*) FROM products').fetchone()[0]==5
    assert main.update_user(account['id'],main.UserUpdate(role='viewer',active=True),operator)['active']==1

def test_missing_user(operator):
    rejects(404,lambda:main.update_user(999,main.UserUpdate(role='viewer',active=True),operator))

@pytest.mark.parametrize('role',['admin','staff','viewer'])
def test_admin_dependency_and_csrf(operator,role):
    token='Synthetic-token'
    with main.database() as db:
        db.execute('UPDATE users SET role=? WHERE id=1',(role,))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(auth.token_hash(token),1,'synthetic-csrf',int(time.time())+600))
    request=Request({'type':'http','method':'POST','headers':[(b'cookie',f'{auth.COOKIE}={token}'.encode()),(b'x-csrf-token',b'synthetic-csrf')]})
    if role=='admin':
        assert auth.administrator(request)['id']==1
    else:
        rejects(403,lambda:auth.administrator(request))
    invalid=Request({'type':'http','method':'POST','headers':[(b'cookie',f'{auth.COOKIE}={token}'.encode())]})
    rejects(403,lambda:auth.administrator(invalid))

@pytest.mark.parametrize('change',[{'username':' '},{'password':'short'},{'role':'owner'}])
def test_invalid_user_fields(change):
    with pytest.raises(ValidationError):
        main.UserInput(**{'username':'synthetic','password':'Synthetic-password-42','role':'staff',**change})

def test_active_flag_requires_boolean():
    with pytest.raises(ValidationError):
        main.UserUpdate(role='viewer',active='false')

def test_validation_response_does_not_echo_password():
    response=main.validation_error(None,RequestValidationError([{'input':'Synthetic-secret-password','loc':['body','password'],'type':'too_short'}]))
    assert response.status_code==422
    assert b'Synthetic-secret-password' not in response.body
    assert b'password' not in response.body
