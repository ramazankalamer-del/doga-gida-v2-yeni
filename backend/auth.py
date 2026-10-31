"""Database-backed sessions; no default accounts or signing secrets."""
import hashlib
import hmac
import secrets
import time
import os
from fastapi import HTTPException, Request

COOKIE = 'doga_session'
TTL = 8 * 60 * 60

def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64*1024*1024)
    return salt.hex() + ':' + digest.hex()

def verify(password, encoded):
    salt, expected = encoded.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64*1024*1024)
    return hmac.compare_digest(actual.hex(), expected)

DUMMY = password_hash(secrets.token_urlsafe(32))

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff','viewer')),
      active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
      csrf TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts(bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, until INTEGER NOT NULL);
    ''')

def current_user(request: Request):
    from main import database
    with database() as db:
        user = db.execute('''SELECT u.id,u.username,u.role,s.csrf FROM sessions s
          JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1''',
          (token_hash(request.cookies.get(COOKIE, '')), int(time.time()))).fetchone()
    if not user:
        raise HTTPException(401, 'Lütfen giriş yapın. Oturumunuz sona ermiş olabilir.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf']):
            raise HTTPException(403, 'İstek doğrulanamadı. Sayfayı yenileyin.')
    return dict(user)

def writer(request: Request):
    user = current_user(request)
    if user['role'] not in ('admin', 'staff'):
        raise HTTPException(403, 'Bu işlem için yetkiniz yok.')
    return user

def administrator(request: Request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Bu işlem yalnızca yöneticilere açıktır.')
    return user

def secure_cookie():
    return os.getenv('COOKIE_SECURE', '1') != '0'
