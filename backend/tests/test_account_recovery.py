import pytest
import main
import account_settings
from test_api import client
from manage_user import create_user


@pytest.fixture(autouse=True)
def loopback(client,monkeypatch):
    monkeypatch.setattr(client._transport,'client',('127.0.0.1',50000))


def recovery(client,token,**changes):
    return client.post('/api/auth/recover',json={'token':token,'username':'recovered-admin',
        'new_password':'Recovery-test-only-password-2026',**changes},headers={'X-Requested-With':'doga'})


def test_recovery_is_opt_in_expires_and_token_is_single_use(client,monkeypatch):
    monkeypatch.setattr(account_settings,'_recovery',None)
    assert recovery(client,'x'*43).status_code==403
    token=account_settings.enable_recovery(main,1)
    assert recovery(client,'y'*43).status_code==403
    user=client.get('/api/auth/me').json()
    client.cookies.clear()
    result=recovery(client,token)
    assert result.status_code==200 and result.json()=={'status':'ok'}
    assert token not in result.text and 'Recovery-test-only-password-2026' not in result.text
    assert recovery(client,token).status_code==403
    with main.database() as db:
        row=db.execute('SELECT * FROM users WHERE id=1').fetchone()
        assert row['username']=='recovered-admin' and row['role']=='admin'
        assert db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=1').fetchone()[0]==0
        assert main.auth.verify('Recovery-test-only-password-2026',row['password_hash'])
    token=account_settings.enable_recovery(main,1)
    account_settings._recovery['expires']=0
    assert recovery(client,token).status_code==403


def test_recovery_duplicate_validation_and_other_accounts_preserved(client,monkeypatch):
    monkeypatch.setattr(account_settings,'_recovery',None)
    create_user('taken-user','Other-test-only-password-2026','admin')
    token=account_settings.enable_recovery(main,1)
    assert recovery(client,token,username='TAKEN-user').status_code==409
    assert recovery(client,token,new_password='short').status_code==422
    assert recovery(client,token,new_password=' '*12).status_code==422
    assert recovery(client,token,username=' ').status_code==422
    assert recovery(client,token).status_code==200
    with main.database() as db:
        other=db.execute("SELECT * FROM users WHERE username='taken-user'").fetchone()
        assert other['role']=='admin' and main.auth.verify('Other-test-only-password-2026',other['password_hash'])
        assert db.execute('SELECT COUNT(*) FROM customers').fetchone()[0]==4


@pytest.mark.parametrize('change',["UPDATE users SET active=0 WHERE id=1","UPDATE users SET role='staff' WHERE id=1","UPDATE users SET password_hash='changed' WHERE id=1"])
def test_recovery_rechecks_target_changes(client,monkeypatch,change):
    monkeypatch.setattr(account_settings,'_recovery',None)
    token=account_settings.enable_recovery(main,1)
    with main.database() as db: db.execute(change)
    assert recovery(client,token).status_code==403
    with main.database() as db: assert db.execute('SELECT username FROM users WHERE id=1').fetchone()[0]=='tester'


def test_recovery_launcher_only_targets_active_admin_and_requires_custom_header(client,monkeypatch):
    monkeypatch.setattr(account_settings,'_recovery',None)
    with pytest.raises(ValueError): account_settings.enable_recovery(main,9999)
    token=account_settings.enable_recovery(main,1)
    response=client.post('/api/auth/recover',json={'token':token,'username':'changed','new_password':'Only-test-password-2026'})
    assert response.status_code==403
    monkeypatch.setattr(client._transport,'client',('192.0.2.1',50000))
    assert recovery(client,token).status_code==403
