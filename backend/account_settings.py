"""Self-service credential changes; no passwords or recovery secrets are returned."""
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator


class NewCredentialsInput(BaseModel):
    username: str = Field(min_length=1,max_length=100)
    new_password: str = Field(min_length=12,max_length=128)

    @field_validator('username',mode='before')
    @classmethod
    def normalize(cls,value):
        return value.strip().lower() if isinstance(value,str) else value

    @field_validator('new_password')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Parola boş olamaz.')
        return value


class CredentialsInput(NewCredentialsInput):
    current_password: str = Field(min_length=1,max_length=128)


class RecoveryInput(NewCredentialsInput):
    token: str = Field(min_length=32,max_length=128)


_recovery=None


def enable_recovery(env,user_id):
    """Called only by the explicit local recovery launcher, never by HTTP."""
    global _recovery
    with env.database() as db:
        row=db.execute("SELECT * FROM users WHERE id=? AND active=1 AND role='admin'",(user_id,)).fetchone()
        if not row: raise ValueError('Aktif yönetici hesabı bulunamadı.')
    token=env.secrets.token_urlsafe(32)
    _recovery={'user_id':user_id,'hash':env.auth.token_hash(token),'original_hash':row['password_hash'],
               'expires':int(env.time.time())+900}
    return token


def register(app,env):
    @app.post('/api/auth/recover')
    def recover(item:RecoveryInput,request:Request,response:Response):
        global _recovery
        now=int(env.time.time())
        if request.client is None or request.client.host not in ('127.0.0.1','::1') or request.headers.get('x-requested-with')!='doga':
            raise HTTPException(403,'Kurtarma isteği doğrulanamadı.')
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE')
            now=int(env.time.time())
            state=_recovery
            if not state or now>=state['expires'] or not env.secrets.compare_digest(env.auth.token_hash(item.token),state['hash']):
                raise HTTPException(403,'Kurtarma bağlantısı geçersiz, kullanılmış veya süresi dolmuş.')
            actor=db.execute("SELECT * FROM users WHERE id=? AND active=1 AND role='admin'",(state['user_id'],)).fetchone()
            if not actor or not env.secrets.compare_digest(actor['password_hash'],state['original_hash']):
                raise HTTPException(403,'Hesap değişti. Yeni bir yerel kurtarma bağlantısı gerekli.')
            if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?',(item.username,actor['id'])).fetchone():
                raise HTTPException(409,'Bu kullanıcı adı zaten kullanılıyor.')
            db.execute('UPDATE users SET username=?,password_hash=? WHERE id=?',
                       (item.username,env.auth.password_hash(item.new_password),actor['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(actor['id'],))
            for bucket in ('user:'+actor['username'],'user:'+item.username,f'credentials:user:{actor["id"]}',
                           'ip:'+request.client.host):
                db.execute('DELETE FROM login_attempts WHERE bucket=?',(bucket,))
        # Retained state is harmless: the saved password hash has changed, so the
        # same token cannot be replayed even if a response is lost after commit.
        response.delete_cookie(env.auth.COOKIE,path='/api',secure=env.auth.secure_cookie(),httponly=True,samesite='strict')
        return {'status':'ok'}

    @app.post('/api/auth/credentials')
    def change_credentials(item:CredentialsInput,request:Request,response:Response,
                           user=Depends(env.auth.current_user)):
        now=int(env.time.time());bucket=f'credentials:user:{user["id"]}'
        invalid=False
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE')
            now=int(env.time.time())
            # Revalidate the exact session after the lock. Concurrent password
            # changes or account revocation must invalidate a waiting request.
            actor=db.execute('''SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                WHERE u.id=? AND u.active=1 AND s.token_hash=? AND s.expires>? AND s.csrf=?''',
                (user['id'],env.auth.token_hash(request.cookies.get(env.auth.COOKIE,'')),now,user['csrf'])).fetchone()
            if not actor: raise HTTPException(401,'Oturumunuz sona erdi. Yeniden giriş yapın.')
            db.execute('DELETE FROM login_attempts WHERE until<=?',(now,))
            attempt=db.execute('SELECT failures FROM login_attempts WHERE bucket=?',(bucket,)).fetchone()
            if attempt and attempt['failures']>=5:
                raise HTTPException(429,'Çok fazla deneme. 15 dakika sonra tekrar deneyin.')
            if not env.auth.verify(item.current_password,actor['password_hash']):
                db.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET failures=failures+1',(bucket,now+900))
                invalid=True
            else:
                if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?',(item.username,user['id'])).fetchone():
                    raise HTTPException(409,'Bu kullanıcı adı zaten kullanılıyor.')
                encoded=env.auth.password_hash(item.new_password)
                db.execute('UPDATE users SET username=?,password_hash=? WHERE id=?',(item.username,encoded,user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                db.execute('DELETE FROM login_attempts WHERE bucket=?',(bucket,))
        if invalid: raise HTTPException(403,'Mevcut parola hatalı. Bilgiler değiştirilmedi.')
        response.delete_cookie(env.auth.COOKIE,path='/api',secure=env.auth.secure_cookie(),httponly=True,samesite='strict')
        return {'status':'ok'}
