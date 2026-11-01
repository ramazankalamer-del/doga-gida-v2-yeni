from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import sqlite3
from decimal import Decimal
from typing import Literal, Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Request, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
import auth
import secrets
import time
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from customer_statement import build_statement

DB_PATH = os.getenv('DATABASE_PATH', str(Path(__file__).with_name('data') / 'doga.db'))

def today():
    return datetime.now(ZoneInfo('Europe/Istanbul')).date().isoformat()

@contextmanager
def database():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def backup_before_feature_migration():
    path = Path(DB_PATH).resolve()
    if not path.is_file():
        return
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
        columns = {row[1] for row in source.execute('PRAGMA table_info(products)')}
        customer_columns = {row[1] for row in source.execute('PRAGMA table_info(customers)')}
        has_routes=source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='customer_route_days'").fetchone()
        if not columns or ('return_stock' in columns and {'latitude','longitude'} <= customer_columns and has_routes and all(source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() for table in ('finance_accounts','finance_entries','finance_cancellations')) and source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='route_order_versions'").fetchone() and source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='route_order_positions'").fetchone() and all({'note','reason'} <= {row[1] for row in source.execute(f'PRAGMA table_info({table})')} for table in ('customer_visits','customer_visit_events'))):
            return
        folder = path.parent / 'backups'
        folder.mkdir(exist_ok=True)
        target = folder / f'before-update-{time.time_ns()}.db'
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Şema güncellemesi öncesi veritabanı yedeği doğrulanamadı.')

def initialize():
    backup_before_feature_migration()
    with database() as db:
        auth.initialize(db)
        db.executescript('''
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT NOT NULL, phone TEXT NOT NULL, district TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL UNIQUE, category TEXT NOT NULL, price_cents INTEGER NOT NULL, stock INTEGER NOT NULL, min_stock INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id), amount_cents INTEGER NOT NULL, status TEXT NOT NULL, date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS collections(id INTEGER PRIMARY KEY, amount_cents INTEGER NOT NULL, date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seed_version(version INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL, price_cents INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS order_cancellations(order_id INTEGER PRIMARY KEY REFERENCES orders(id), user_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, cancelled_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS collection_cancellations(collection_id INTEGER PRIMARY KEY REFERENCES collections(id), user_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, cancelled_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_status_events(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), user_id INTEGER NOT NULL REFERENCES users(id), request_id TEXT NOT NULL UNIQUE, from_status TEXT NOT NULL, to_status TEXT NOT NULL, changed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stock_tracking(product_id INTEGER PRIMARY KEY REFERENCES products(id), opening_stock INTEGER NOT NULL, tracked_since TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, sku TEXT NOT NULL, kind TEXT NOT NULL, quantity INTEGER NOT NULL, before_stock INTEGER NOT NULL, after_stock INTEGER NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id), order_id INTEGER REFERENCES orders(id), request_id TEXT UNIQUE, note TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(orders)')}
        if 'request_id' not in columns:
            db.execute('ALTER TABLE orders ADD COLUMN request_id TEXT')
        if 'created_by' not in columns:
            db.execute('ALTER TABLE orders ADD COLUMN created_by INTEGER')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS orders_request_id ON orders(request_id)')
        collection_columns = {row['name'] for row in db.execute('PRAGMA table_info(collections)')}
        for name, definition in [('customer_id','INTEGER REFERENCES customers(id)'), ('request_id','TEXT'), ('created_by','INTEGER REFERENCES users(id)'), ('method','TEXT'), ('note',"TEXT NOT NULL DEFAULT ''"), ('created_at','TEXT')]:
            if name not in collection_columns:
                db.execute(f'ALTER TABLE collections ADD COLUMN {name} {definition}')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS collections_request_id ON collections(request_id)')
        for table in ('customers','products'):
            if 'version' not in {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}:
                db.execute(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 0')
        customer_columns = {row['name'] for row in db.execute('PRAGMA table_info(customers)')}
        db.execute('''CREATE TABLE IF NOT EXISTS customer_route_days(
            customer_id INTEGER NOT NULL REFERENCES customers(id),weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
            PRIMARY KEY(customer_id,weekday))''')
        db.executescript('''CREATE TABLE IF NOT EXISTS customer_visits(
            customer_id INTEGER NOT NULL REFERENCES customers(id), visit_date TEXT NOT NULL,
            visited INTEGER NOT NULL CHECK(visited IN (0,1)), version INTEGER NOT NULL,
            updated_by INTEGER NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL,
            PRIMARY KEY(customer_id,visit_date));
        CREATE TABLE IF NOT EXISTS customer_visit_events(
            id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id), visit_date TEXT NOT NULL,
            visited INTEGER NOT NULL CHECK(visited IN (0,1)), version INTEGER NOT NULL,
            updated_by INTEGER NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL,
            UNIQUE(customer_id,visit_date,version));''')
        db.executescript('''CREATE TABLE IF NOT EXISTS route_order_versions(
            scope_id INTEGER PRIMARY KEY CHECK(scope_id BETWEEN 0 AND 7),version INTEGER NOT NULL,
            updated_by INTEGER NOT NULL REFERENCES users(id),updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS route_order_positions(
            scope_id INTEGER NOT NULL REFERENCES route_order_versions(scope_id),customer_id INTEGER NOT NULL REFERENCES customers(id),
            position INTEGER NOT NULL CHECK(position>=0),PRIMARY KEY(scope_id,customer_id),UNIQUE(scope_id,position));''')
        db.executescript('''CREATE TABLE IF NOT EXISTS finance_accounts(
            id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE COLLATE NOCASE,kind TEXT NOT NULL CHECK(kind IN ('cash','bank')),
            opening_cents INTEGER NOT NULL,request_id TEXT NOT NULL UNIQUE,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS finance_entries(
            id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL REFERENCES finance_accounts(id),kind TEXT NOT NULL CHECK(kind IN ('income','withdrawal','expense')),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),date TEXT NOT NULL,category TEXT NOT NULL,note TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS finance_cancellations(
            entry_id INTEGER PRIMARY KEY REFERENCES finance_entries(id),reason TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),cancelled_at TEXT NOT NULL);''')
        for table in ('customer_visits','customer_visit_events'):
            visit_columns={row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
            for column in ('note','reason'):
                if column not in visit_columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        for column in ('latitude', 'longitude'):
            if column not in customer_columns:
                db.execute(f'ALTER TABLE customers ADD COLUMN {column} REAL')
        # Existing stock and history remain the sellable MERKEZ balance.
        if 'return_stock' not in {row['name'] for row in db.execute('PRAGMA table_info(products)')}:
            db.execute('ALTER TABLE products ADD COLUMN return_stock INTEGER NOT NULL DEFAULT 0 CHECK(return_stock BETWEEN 0 AND 10000000)')
        db.execute('''CREATE TABLE IF NOT EXISTS warehouse_actions(
            request_id TEXT PRIMARY KEY, kind TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
            quantity INTEGER NOT NULL, source TEXT, target TEXT NOT NULL, note TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL)''')
        movement_columns = {row['name'] for row in db.execute('PRAGMA table_info(stock_movements)')}
        if 'warehouse' not in movement_columns:
            db.execute("ALTER TABLE stock_movements ADD COLUMN warehouse TEXT NOT NULL DEFAULT 'MERKEZ'")
        if 'action_id' not in movement_columns:
            db.execute('ALTER TABLE stock_movements ADD COLUMN action_id TEXT REFERENCES warehouse_actions(request_id)')
        if not db.execute('SELECT 1 FROM seed_version WHERE version=1').fetchone():
            db.executemany('INSERT INTO customers(name,contact,phone,district) VALUES(?,?,?,?)', [
                ('Örnek Bahar Market','Demo Yetkili 1','','Kadıköy'),('Örnek Deniz Gıda','Demo Yetkili 2','','Üsküdar'),('Örnek Yeşil Bakkal','Demo Yetkili 3','','Ataşehir'),('Örnek Gün Market','Demo Yetkili 4','','Maltepe')])
            db.executemany('INSERT INTO products(name,sku,category,price_cents,stock,min_stock) VALUES(?,?,?,?,?,?)',[
                ('Ayçiçek Yağı 5 L','DG-001','Temel gıda',32500,84,20),('Baldo Pirinç 1 kg','DG-002','Bakliyat',8500,156,30),('Toz Şeker 1 kg','DG-003','Temel gıda',4200,18,25),('Çay 1 kg','DG-004','İçecek',21000,64,15),('Sıvı Sabun 750 ml','DG-005','Temizlik',6500,12,20)])
            db.executemany('INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,?,?,?)',[(1,1280000,'Hazırlanıyor',today()),(2,845000,'Dağıtımda',today()),(3,362500,'Teslim edildi',today()),(4,620000,'Bekliyor',today())])
            db.execute('INSERT INTO collections(amount_cents,date) VALUES(?,?)',(1850000,today()))
            db.execute('INSERT INTO seed_version VALUES(1)')
        db.execute('INSERT OR IGNORE INTO stock_tracking SELECT id,stock,? FROM products',(datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),))

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='Doğa Gıda V2 API', lifespan=lifespan)

@app.exception_handler(RequestValidationError)
def validation_error(request: Request, error: RequestValidationError):
    # Validation responses must never echo password fields or submitted data.
    return JSONResponse(status_code=422, content={'detail':'Bilgileri kontrol edin. Alanlar geçersiz.'})

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)

@app.post('/api/auth/login')
def login(item: LoginInput, request: Request, response: Response):
    # Custom header + JSON prevents cross-origin form login; no CORS enabled.
    if request.headers.get('x-requested-with') != 'doga':
        raise HTTPException(403, 'İstek doğrulanamadı.')
    now = int(time.time())
    buckets = ['user:' + item.username.strip().lower(), 'ip:' + (request.client.host if request.client else 'unknown')]
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE until<=?', (now,))
        for bucket in buckets:
            attempt = db.execute('SELECT failures FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()
            if attempt and attempt['failures'] >= 5:
                raise HTTPException(429, 'Çok fazla deneme. 15 dakika sonra tekrar deneyin.')
        user = db.execute('SELECT * FROM users WHERE username=?', (item.username.strip().lower(),)).fetchone()
        valid = auth.verify(item.password, user['password_hash'] if user else auth.DUMMY)
        if not valid or not user or not user['active']:
            for bucket in buckets:
                db.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET failures=failures+1', (bucket, now+900))
        else:
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires<=? OR token_hash=?', (now, auth.token_hash(request.cookies.get(auth.COOKIE, ''))))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (auth.token_hash(token), user['id'], csrf, now+auth.TTL))
            db.execute('DELETE FROM login_attempts WHERE bucket=?', (buckets[0],))
            response.set_cookie(auth.COOKIE, token, max_age=auth.TTL, httponly=True, secure=auth.secure_cookie(), samesite='strict', path='/api')
            return {'id':user['id'], 'username':user['username'], 'role':user['role'], 'csrf':csrf}
    raise HTTPException(401, 'Kullanıcı adı veya parola hatalı.')

@app.get('/api/auth/me')
def me(user=Depends(auth.current_user)):
    return user

@app.post('/api/auth/logout')
def logout(request: Request, response: Response, user=Depends(auth.current_user)):
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (auth.token_hash(request.cookies.get(auth.COOKIE, '')),))
    response.delete_cookie(auth.COOKIE, path='/api', secure=auth.secure_cookie(), httponly=True, samesite='strict')
    return {'status':'ok'}

class UserInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: Literal['admin', 'staff', 'viewer']

    @field_validator('username', mode='before')
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

class UserUpdate(BaseModel):
    role: Literal['admin', 'staff', 'viewer']
    active: bool = Field(strict=True)

def require_active_admin(db, user_id):
    # Recheck after acquiring the write lock: a concurrent admin may revoke access.
    actor = db.execute('SELECT role,active FROM users WHERE id=?', (user_id,)).fetchone()
    if not actor or not actor['active'] or actor['role'] != 'admin':
        raise HTTPException(403, 'Bu işlem yalnızca yöneticilere açıktır.')

@app.get('/api/users')
def list_users(user=Depends(auth.administrator)):
    with database() as db:
        return [dict(row) for row in db.execute('SELECT id,username,role,active FROM users ORDER BY id')]

@app.post('/api/users', status_code=201)
def add_user(item: UserInput, user=Depends(auth.administrator)):
    encoded = auth.password_hash(item.password)
    try:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            require_active_admin(db, user['id'])
            cursor = db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)', (item.username,encoded,item.role))
            return {'id':cursor.lastrowid, 'username':item.username, 'role':item.role, 'active':1}
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Bu kullanıcı adı zaten kullanılıyor.')

@app.post('/api/users/{user_id}')
def update_user(user_id: int, item: UserUpdate, user=Depends(auth.administrator)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_admin(db, user['id'])
        target = db.execute('SELECT id,username,role,active FROM users WHERE id=?', (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, 'Kullanıcı bulunamadı.')
        if target['role']=='admin' and target['active'] and (item.role!='admin' or not item.active):
            if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0] <= 1:
                raise HTTPException(409, 'Son aktif yönetici pasife alınamaz veya rolü değiştirilemez.')
        if user_id==user['id'] and (item.role!='admin' or not item.active):
            raise HTTPException(409, 'Kendi hesabınızın rolünü veya aktifliğini değiştiremezsiniz.')
        changed = target['role'] != item.role or bool(target['active']) != item.active
        db.execute('UPDATE users SET role=?,active=? WHERE id=?', (item.role,int(item.active),user_id))
        if changed:
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
        return {'id':target['id'], 'username':target['username'], 'role':item.role, 'active':int(item.active)}

class RouteDaysInput(BaseModel):
    route_days: list[Annotated[int, Field(ge=1,le=7,strict=True)]] = Field(default_factory=list,max_length=7)

    @field_validator('route_days')
    @classmethod
    def unique_days(cls,days):
        if len(days)!=len(set(days)):
            raise ValueError('Rota günleri tekrarlanamaz.')
        return sorted(days)

class CustomerInput(RouteDaysInput):
    name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=2, max_length=100)
    phone: str = Field(default='', max_length=25)
    district: str = Field(min_length=2, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False, strict=True)

    @model_validator(mode='after')
    def coordinate_pair(self):
        if ('latitude' in self.model_fields_set) != ('longitude' in self.model_fields_set):
            raise ValueError('Enlem ve boylam birlikte gönderilmeli.')
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Enlem ve boylam birlikte doldurulmalı veya temizlenmeli.')
        return self

    @field_validator('*', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class ProductInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    sku: str = Field(min_length=2, max_length=40)
    category: str = Field(min_length=2, max_length=60)
    price: Decimal = Field(gt=0, le=10000000, decimal_places=2)
    stock: int = Field(ge=0, le=10000000)
    min_stock: int = Field(default=20, ge=0, le=10000000)

    @field_validator('name', 'sku', 'category', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

@app.get('/api/health')
def health():
    with database() as db:
        db.execute('SELECT 1').fetchone()
    return {'status':'ok'}

@app.get('/api/customers')
def customers(user=Depends(auth.current_user)):
    with database() as db:
        return [customer_dict(db,row) for row in db.execute('SELECT * FROM customers ORDER BY id DESC')]

def customer_dict(db,row):
    return {**dict(row),'route_days':[day['weekday'] for day in db.execute('SELECT weekday FROM customer_route_days WHERE customer_id=? ORDER BY weekday',(row['id'],))]}

def save_route_days(db,customer_id,days):
    db.execute('DELETE FROM customer_route_days WHERE customer_id=?',(customer_id,))
    db.executemany('INSERT INTO customer_route_days VALUES(?,?)',[(customer_id,day) for day in days])

@app.post('/api/customers', status_code=201)
def add_customer(item: CustomerInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        cursor = db.execute('INSERT INTO customers(name,contact,phone,district,latitude,longitude) VALUES(?,?,?,?,?,?)', (item.name,item.contact,item.phone,item.district,item.latitude,item.longitude))
        save_route_days(db,cursor.lastrowid,item.route_days)
        return {'id':cursor.lastrowid, 'version':0, **item.model_dump()}

class CustomerUpdate(CustomerInput):
    expected_version: int = Field(ge=0, strict=True)

def require_active_writer(db, user_id):
    actor = db.execute('SELECT role,active FROM users WHERE id=?',(user_id,)).fetchone()
    if not actor or not actor['active'] or actor['role'] not in ('admin','staff'):
        raise HTTPException(403, 'Bu işlem için yetkiniz yok.')

@app.post('/api/customers/{customer_id}')
def update_customer(customer_id: int, item: CustomerUpdate, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        row = db.execute('SELECT * FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Müşteri bulunamadı.')
        if row['version']!=item.expected_version:
            raise HTTPException(409, 'Kayıt başka bir işlemde değişti. Güncel listeyi yükleyip yeniden deneyin.')
        latitude = item.latitude if 'latitude' in item.model_fields_set else row['latitude']
        longitude = item.longitude if 'longitude' in item.model_fields_set else row['longitude']
        db.execute('UPDATE customers SET name=?,contact=?,phone=?,district=?,latitude=?,longitude=?,version=version+1 WHERE id=?',(item.name,item.contact,item.phone,item.district,latitude,longitude,customer_id))
        if 'route_days' in item.model_fields_set:
            save_route_days(db,customer_id,item.route_days)
        return customer_dict(db,db.execute('SELECT * FROM customers WHERE id=?',(customer_id,)).fetchone())

class RouteDaysUpdate(RouteDaysInput):
    route_days: list[Annotated[int, Field(ge=1,le=7,strict=True)]] = Field(max_length=7)
    expected_version: int = Field(ge=0,strict=True)

@app.post('/api/customers/{customer_id}/route-days')
def update_route_days(customer_id:int,item:RouteDaysUpdate,user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        row=db.execute('SELECT * FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Müşteri bulunamadı.')
        if row['version']!=item.expected_version:
            raise HTTPException(409,'Müşteri kartı değişti. Güncel kartı yükleyip yeniden deneyin.')
        save_route_days(db,customer_id,item.route_days)
        db.execute('UPDATE customers SET version=version+1 WHERE id=?',(customer_id,))
        return customer_dict(db,db.execute('SELECT * FROM customers WHERE id=?',(customer_id,)).fetchone())

class VisitInput(BaseModel):
    note: str = Field(default='',max_length=1000,strict=True)
    reason: str = Field(default='',max_length=300,strict=True)

    @field_validator('note','reason')
    @classmethod
    def trim_visit_text(cls,value):
        return value.strip()

    @model_validator(mode='after')
    def validate_visit_reason(self):
        if self.visited and self.reason:
            raise ValueError('Ziyaret edilen müşteri için ziyaret edilememe nedeni girilemez.')
        return self

    visit_date: date
    visited: bool = Field(strict=True)
    expected_version: int = Field(ge=0,strict=True)

@app.get('/api/customer-visits')
def customer_visits(visit_date:date,user=Depends(auth.current_user)):
    with database() as db:
        return [dict(row) for row in db.execute('SELECT v.*,u.username AS updated_username FROM customer_visits v JOIN users u ON u.id=v.updated_by WHERE visit_date=?',(visit_date.isoformat(),))]

def route_order_members(db,scope_id):
    if scope_id<0 or scope_id>7:
        raise HTTPException(422,'Rota günü geçersiz.')
    if scope_id==0:
        return [row['id'] for row in db.execute('SELECT c.id FROM customers c WHERE NOT EXISTS(SELECT 1 FROM customer_route_days d WHERE d.customer_id=c.id) ORDER BY c.id')]
    return [row['customer_id'] for row in db.execute('SELECT customer_id FROM customer_route_days WHERE weekday=? ORDER BY customer_id',(scope_id,))]

def route_order_data(db,scope_id):
    members=route_order_members(db,scope_id)
    member_set=set(members)
    stored=[row['customer_id'] for row in db.execute('SELECT customer_id FROM route_order_positions WHERE scope_id=? ORDER BY position',(scope_id,)) if row['customer_id'] in member_set]
    stored_set=set(stored)
    version=db.execute('SELECT version FROM route_order_versions WHERE scope_id=?',(scope_id,)).fetchone()
    return {'scope_id':scope_id,'version':version['version'] if version else 0,'customer_ids':stored+[customer for customer in members if customer not in stored_set]}

class RouteOrderInput(BaseModel):
    customer_ids:list[Annotated[int,Field(strict=True,ge=1)]]=Field(max_length=10000)
    expected_version:int=Field(strict=True,ge=0)

    @field_validator('customer_ids')
    @classmethod
    def unique_route_customers(cls,values):
        if len(set(values))!=len(values):
            raise ValueError('Müşteri sıralamasında tekrar olamaz.')
        return values

@app.get('/api/route-order/{scope_id}')
def get_route_order(scope_id:int,user=Depends(auth.current_user)):
    with database() as db:
        db.execute('BEGIN')
        return route_order_data(db,scope_id)

@app.post('/api/route-order/{scope_id}')
def save_route_order(scope_id:int,item:RouteOrderInput,user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        old=route_order_data(db,scope_id)
        if old['version']!=item.expected_version or set(old['customer_ids'])!=set(item.customer_ids):
            raise HTTPException(409,'Rota veya müşteri sırası değişti. Güncel sıralamayı yükleyip yeniden deneyin.')
        db.execute('INSERT INTO route_order_versions VALUES(?,?,?,?) ON CONFLICT(scope_id) DO UPDATE SET version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(scope_id,item.expected_version+1,user['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        db.execute('DELETE FROM route_order_positions WHERE scope_id=?',(scope_id,))
        db.executemany('INSERT INTO route_order_positions VALUES(?,?,?)',[(scope_id,customer,index) for index,customer in enumerate(item.customer_ids)])
        return route_order_data(db,scope_id)

@app.get('/api/daily-route-summary')
def daily_route_summary(visit_date:date,unassigned:bool=False,user=Depends(auth.current_user)):
    day=visit_date.isoformat()
    with database() as db:
        db.execute('BEGIN')
        if unassigned:
            scope='SELECT c.id FROM customers c WHERE NOT EXISTS(SELECT 1 FROM customer_route_days d WHERE d.customer_id=c.id)'
            params=[]
        else:
            scope='SELECT c.id FROM customers c WHERE EXISTS(SELECT 1 FROM customer_route_days d WHERE d.customer_id=c.id AND d.weekday=?)'
            params=[visit_date.isoweekday()]
        customers=db.execute(f'SELECT COUNT(*) FROM ({scope})',params).fetchone()[0]
        visited=db.execute(f'SELECT COUNT(*) FROM customer_visits WHERE customer_id IN ({scope}) AND visit_date=? AND visited=1',[*params,day]).fetchone()[0]
        orders=db.execute(f"SELECT COUNT(*) count,COALESCE(SUM(amount_cents),0) amount FROM orders WHERE customer_id IN ({scope}) AND date=? AND status!='İptal edildi' AND NOT EXISTS(SELECT 1 FROM order_cancellations x WHERE x.order_id=orders.id)",[*params,day]).fetchone()
        collected=db.execute(f'SELECT COUNT(*) count,COALESCE(SUM(amount_cents),0) amount FROM collections WHERE customer_id IN ({scope}) AND date=? AND NOT EXISTS(SELECT 1 FROM collection_cancellations x WHERE x.collection_id=collections.id)',[*params,day]).fetchone()
        return {'date':day,'unassigned':unassigned,'customers':customers,'visited':visited,'remaining':customers-visited,'order_count':orders['count'],'sales_cents':orders['amount'],'collection_count':collected['count'],'collections_cents':collected['amount']}

@app.get('/api/customers/{customer_id}/visits')
def customer_visit_history(customer_id:int,start_date:date|None=None,end_date:date|None=None,offset:int=Query(default=0,ge=0),limit:int=Query(default=50,ge=1,le=100),user=Depends(auth.current_user)):
    if start_date and end_date and start_date>end_date:
        raise HTTPException(422,'Başlangıç tarihi bitiş tarihinden sonra olamaz.')
    with database() as db:
        db.execute('BEGIN')
        customer=db.execute('SELECT id,name FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not customer:
            raise HTTPException(404,'Müşteri bulunamadı.')
        clauses=['v.customer_id=?'];params=[customer_id]
        if start_date:
            clauses.append('v.visit_date>=?');params.append(start_date.isoformat())
        if end_date:
            clauses.append('v.visit_date<=?');params.append(end_date.isoformat())
        where=' AND '.join(clauses)
        totals=db.execute(f'SELECT COUNT(*) total,COALESCE(SUM(visited),0) visited FROM customer_visits v WHERE {where}',params).fetchone()
        rows=db.execute(f'SELECT v.*,u.username AS updated_username FROM customer_visits v JOIN users u ON u.id=v.updated_by WHERE {where} ORDER BY v.visit_date DESC LIMIT ? OFFSET ?',[*params,limit,offset]).fetchall()
        return {'customer':dict(customer),'total':totals['total'],'visited':totals['visited'],'not_visited':totals['total']-totals['visited'],'offset':offset,'limit':limit,'visits':[dict(row) for row in rows]}

@app.post('/api/customers/{customer_id}/visit')
def save_customer_visit(customer_id:int,item:VisitInput,user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        if item.visit_date.isoformat()>today():
            raise HTTPException(422,'Gelecek tarih için ziyaret kaydedilemez.')
        if not db.execute('SELECT 1 FROM customers WHERE id=?',(customer_id,)).fetchone():
            raise HTTPException(404,'Müşteri bulunamadı.')
        day=item.visit_date.isoformat()
        old=db.execute('SELECT * FROM customer_visits WHERE customer_id=? AND visit_date=?',(customer_id,day)).fetchone()
        if (old['version'] if old else 0)!=item.expected_version:
            raise HTTPException(409,'Ziyaret durumu değişti. Ziyaretleri yenileyip yeniden deneyin.')
        version=item.expected_version+1
        stamp=datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()
        note=item.note if 'note' in item.model_fields_set else (old['note'] if old else '')
        reason='' if item.visited else (item.reason if 'reason' in item.model_fields_set else (old['reason'] if old else ''))
        values=(customer_id,day,int(item.visited),version,user['id'],stamp,note,reason)
        db.execute('INSERT INTO customer_visits(customer_id,visit_date,visited,version,updated_by,updated_at,note,reason) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(customer_id,visit_date) DO UPDATE SET visited=excluded.visited,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at,note=excluded.note,reason=excluded.reason',values)
        db.execute('INSERT INTO customer_visit_events(customer_id,visit_date,visited,version,updated_by,updated_at,note,reason) VALUES(?,?,?,?,?,?,?,?)',values)
        return dict(db.execute('SELECT v.*,u.username AS updated_username FROM customer_visits v JOIN users u ON u.id=v.updated_by WHERE customer_id=? AND visit_date=?',(customer_id,day)).fetchone())

class FinanceAccountInput(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    kind:Literal['cash','bank']
    opening:Decimal=Field(default=Decimal('0'),ge=-10000000,le=10000000,decimal_places=2)
    request_id:UUID

    @field_validator('name')
    @classmethod
    def account_name(cls,value):
        value=value.strip()
        if len(value)<2: raise ValueError('Hesap adı en az iki karakter olmalıdır.')
        return value

    @model_validator(mode='after')
    def cash_opening(self):
        if self.kind=='cash' and self.opening<0: raise ValueError('Kasa açılışı negatif olamaz.')
        return self

class FinanceEntryInput(BaseModel):
    account_id:int=Field(strict=True,ge=1)
    kind:Literal['income','withdrawal','expense']
    amount:Decimal=Field(gt=0,le=10000000,decimal_places=2)
    date:date
    category:str=Field(default='',max_length=80)
    note:str=Field(min_length=3,max_length=300)
    request_id:UUID

    @field_validator('category','note')
    @classmethod
    def finance_text(cls,value): return value.strip()

    @model_validator(mode='after')
    def finance_description(self):
        if len(self.note)<3: raise ValueError('Açıklama en az üç karakter olmalıdır.')
        if self.kind=='expense' and len(self.category)<2: raise ValueError('Gider kategorisi girilmelidir.')
        if self.kind!='expense' and self.category: raise ValueError('Kategori yalnızca gider için kullanılabilir.')
        return self

def finance_balance(db,account):
    net=db.execute("SELECT COALESCE(SUM(CASE WHEN e.kind='income' THEN e.amount_cents ELSE -e.amount_cents END),0) FROM finance_entries e WHERE e.account_id=? AND NOT EXISTS(SELECT 1 FROM finance_cancellations x WHERE x.entry_id=e.id)",(account['id'],)).fetchone()[0]
    return account['opening_cents']+net

def finance_entry_dict(db,entry_id):
    row=dict(db.execute('SELECT e.*,a.name account_name,u.username FROM finance_entries e JOIN finance_accounts a ON a.id=e.account_id JOIN users u ON u.id=e.created_by WHERE e.id=?',(entry_id,)).fetchone())
    cancel=db.execute('SELECT x.reason,x.cancelled_at,u.username FROM finance_cancellations x JOIN users u ON u.id=x.user_id WHERE entry_id=?',(entry_id,)).fetchone()
    row['cancellation']=dict(cancel) if cancel else None
    return row

@app.get('/api/finance')
def list_finance(account_id:int|None=None,start_date:date|None=None,end_date:date|None=None,offset:int=Query(default=0,ge=0),user=Depends(auth.current_user)):
    if start_date and end_date and start_date>end_date: raise HTTPException(422,'Tarih aralığı geçersiz.')
    with database() as db:
        db.execute('BEGIN')
        accounts=[{**dict(a),'balance_cents':finance_balance(db,a)} for a in db.execute('SELECT id,name,kind,opening_cents FROM finance_accounts ORDER BY id')]
        if account_id is not None and not any(a['id']==account_id for a in accounts): raise HTTPException(404,'Hesap bulunamadı.')
        clauses=['1=1'];params=[]
        if account_id is not None: clauses.append('e.account_id=?');params.append(account_id)
        if start_date: clauses.append('e.date>=?');params.append(start_date.isoformat())
        if end_date: clauses.append('e.date<=?');params.append(end_date.isoformat())
        where=' AND '.join(clauses)
        total=db.execute(f'SELECT COUNT(*) FROM finance_entries e WHERE {where}',params).fetchone()[0]
        sums={row['kind']:row['amount'] for row in db.execute(f'SELECT e.kind,SUM(e.amount_cents) amount FROM finance_entries e WHERE {where} AND NOT EXISTS(SELECT 1 FROM finance_cancellations x WHERE x.entry_id=e.id) GROUP BY e.kind',params)}
        entries=[finance_entry_dict(db,row['id']) for row in db.execute(f'SELECT e.id FROM finance_entries e WHERE {where} ORDER BY e.date DESC,e.id DESC LIMIT 50 OFFSET ?',[*params,offset])]
        return {'accounts':accounts,'entries':entries,'total':total,'offset':offset,'income_cents':sums.get('income',0),'expense_cents':sums.get('expense',0),'withdrawal_cents':sums.get('withdrawal',0)}

@app.post('/api/finance/accounts')
def create_finance_account(item:FinanceAccountInput,user=Depends(auth.administrator)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE');require_active_admin(db,user['id'])
        previous=db.execute('SELECT * FROM finance_accounts WHERE request_id=?',(str(item.request_id),)).fetchone()
        opening=int(item.opening*100)
        if previous:
            if (previous['name'],previous['kind'],previous['opening_cents'],previous['created_by'])!=(item.name,item.kind,opening,user['id']): raise HTTPException(409,'İstek kimliği farklı hesap için kullanılmış.')
            return {'id':previous['id']}
        if db.execute('SELECT 1 FROM finance_accounts WHERE name=? COLLATE NOCASE',(item.name,)).fetchone(): raise HTTPException(409,'Bu hesap adı zaten kullanılıyor.')
        result=db.execute('INSERT INTO finance_accounts(name,kind,opening_cents,request_id,created_by,created_at) VALUES(?,?,?,?,?,?)',(item.name,item.kind,opening,str(item.request_id),user['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return {'id':result.lastrowid}

@app.post('/api/finance/entries')
def create_finance_entry(item:FinanceEntryInput,user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE');require_active_writer(db,user['id'])
        amount=int(item.amount*100);day=item.date.isoformat()
        previous=db.execute('SELECT * FROM finance_entries WHERE request_id=?',(str(item.request_id),)).fetchone()
        if previous:
            if tuple(previous[k] for k in ('account_id','kind','amount_cents','date','category','note','created_by'))!=(item.account_id,item.kind,amount,day,item.category,item.note,user['id']): raise HTTPException(409,'İstek kimliği farklı işlem için kullanılmış.')
            return finance_entry_dict(db,previous['id'])
        if day>today(): raise HTTPException(422,'Gelecek tarihli hareket kaydedilemez.')
        account=db.execute('SELECT * FROM finance_accounts WHERE id=?',(item.account_id,)).fetchone()
        if not account: raise HTTPException(404,'Hesap bulunamadı.')
        if account['kind']=='cash' and item.kind!='income' and finance_balance(db,account)<amount: raise HTTPException(409,'Kasa bakiyesi bu çıkış için yetersiz.')
        result=db.execute('INSERT INTO finance_entries(account_id,kind,amount_cents,date,category,note,request_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(item.account_id,item.kind,amount,day,item.category,item.note,str(item.request_id),user['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return finance_entry_dict(db,result.lastrowid)

class FinanceCancellationInput(BaseModel):
    reason:str=Field(min_length=3,max_length=300)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('İptal nedeni en az üç karakter olmalıdır.')
        return value

@app.post('/api/finance/entries/{entry_id}/cancel')
def cancel_finance_entry(entry_id:int,item:FinanceCancellationInput,user=Depends(auth.administrator)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE');require_active_admin(db,user['id'])
        row=db.execute('SELECT * FROM finance_entries WHERE id=?',(entry_id,)).fetchone()
        if not row: raise HTTPException(404,'Hareket bulunamadı.')
        if db.execute('SELECT 1 FROM finance_cancellations WHERE entry_id=?',(entry_id,)).fetchone(): return finance_entry_dict(db,entry_id)
        account=db.execute('SELECT * FROM finance_accounts WHERE id=?',(row['account_id'],)).fetchone()
        if account['kind']=='cash' and row['kind']=='income' and finance_balance(db,account)<row['amount_cents']: raise HTTPException(409,'İptal kasa bakiyesini negatife düşürüyor. Önce ilgili çıkışları kontrol edin.')
        db.execute('INSERT INTO finance_cancellations VALUES(?,?,?,?)',(entry_id,item.reason,user['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return finance_entry_dict(db,entry_id)

@app.get('/api/customers/{customer_id}/summary')
def customer_card_summary(customer_id:int,user=Depends(auth.current_user)):
    with database() as db:
        db.execute('BEGIN')
        customer=db.execute('SELECT id,name FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not customer:
            raise HTTPException(404,'Müşteri bulunamadı.')
        balance=build_statement(db,customer)['current_balance_cents']
        latest=db.execute('SELECT v.*,u.username AS updated_username FROM customer_visits v JOIN users u ON u.id=v.updated_by WHERE v.customer_id=? AND v.visit_date<=? ORDER BY v.visit_date DESC LIMIT 1',(customer_id,today())).fetchone()
        successful=db.execute('SELECT MAX(visit_date) FROM customer_visits WHERE customer_id=? AND visited=1 AND visit_date<=?',(customer_id,today())).fetchone()[0]
        return {'customer':dict(customer),'balance_cents':balance,'last_visit_record':dict(latest) if latest else None,'last_successful_visit_date':successful}

@app.get('/api/customers/{customer_id}/statement')
def customer_statement(customer_id:int,start_date:date|None=None,end_date:date|None=None,user=Depends(auth.current_user)):
    if start_date and end_date and start_date>end_date:
        raise HTTPException(422,'Başlangıç tarihi bitiş tarihinden sonra olamaz.')
    with database() as db:
        db.execute('BEGIN')
        customer=db.execute('SELECT id,name,contact,phone,district FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not customer:
            raise HTTPException(404,'Müşteri bulunamadı.')
        return build_statement(db,customer,start_date,end_date)

def product_dict(row):
    result = dict(row)
    result['price'] = result.pop('price_cents') / 100
    return result

def record_stock_movement(db, product, before, after, kind, user_id, order_id=None, request_id=None, note='', warehouse='MERKEZ', action_id=None):
    if before==after:
        return None
    return db.execute('INSERT INTO stock_movements(product_id,name,sku,kind,quantity,before_stock,after_stock,user_id,order_id,request_id,note,created_at,warehouse,action_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(product['id'],product['name'],product['sku'],kind,after-before,before,after,user_id,order_id,request_id,note,datetime.now(ZoneInfo('Europe/Istanbul')).isoformat(),warehouse,action_id)).lastrowid

def movement_dict(db, movement_id):
    return dict(db.execute('SELECT m.id,m.product_id,m.name,m.sku,m.kind,m.quantity,m.before_stock,m.after_stock,m.order_id,m.note,m.created_at,m.warehouse,m.action_id,u.username FROM stock_movements m JOIN users u ON u.id=m.user_id WHERE m.id=?',(movement_id,)).fetchone())

@app.get('/api/products')
def products(user=Depends(auth.current_user)):
    with database() as db:
        return [product_dict(row) for row in db.execute('SELECT * FROM products ORDER BY id DESC')]

@app.post('/api/products', status_code=201)
def add_product(item: ProductInput, user=Depends(auth.writer)):
    try:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            require_active_writer(db,user['id'])
            cursor = db.execute('INSERT INTO products(name,sku,category,price_cents,stock,min_stock) VALUES(?,?,?,?,?,?)',(item.name,item.sku.upper(),item.category,int(item.price*100),item.stock,item.min_stock))
            product = db.execute('SELECT * FROM products WHERE id=?',(cursor.lastrowid,)).fetchone()
            db.execute('INSERT INTO stock_tracking VALUES(?,0,?)',(product['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
            record_stock_movement(db,product,0,item.stock,'opening',user['id'],note='Yeni ürün açılışı')
            return product_dict(product)
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Bu ürün kodu zaten kullanılıyor.')

class ProductUpdate(ProductInput):
    expected_version: int = Field(ge=0, strict=True)

@app.post('/api/products/{product_id}')
def update_product(product_id: int, item: ProductUpdate, user=Depends(auth.writer)):
    try:
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            require_active_writer(db,user['id'])
            row = db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Ürün bulunamadı.')
            if row['version']!=item.expected_version:
                raise HTTPException(409, 'Kayıt başka bir işlemde değişti. Güncel listeyi yükleyip yeniden deneyin.')
            db.execute('UPDATE products SET name=?,sku=?,category=?,price_cents=?,stock=?,min_stock=?,version=version+1 WHERE id=?',(item.name,item.sku.upper(),item.category,int(item.price*100),item.stock,item.min_stock,product_id))
            product = db.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
            record_stock_movement(db,product,row['stock'],item.stock,'correction',user['id'],note='Ürün düzenleme ekranından stok düzeltmesi')
            return product_dict(product)
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Bu ürün kodu zaten kullanılıyor.')

class StockReceiptInput(BaseModel):
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, le=10000000, strict=True)
    note: str = Field(min_length=3, max_length=300)
    request_id: UUID

    @field_validator('note', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

@app.get('/api/stock-ledger')
def stock_ledger(user=Depends(auth.current_user)):
    with database() as db:
        db.execute('BEGIN')
        products = [dict(row) for row in db.execute('''SELECT p.id,p.name,p.sku,p.stock,t.opening_stock,t.tracked_since,COALESCE(m.delta,0) net_change
          FROM products p JOIN stock_tracking t ON t.product_id=p.id
          LEFT JOIN (SELECT product_id,SUM(quantity) delta FROM stock_movements WHERE warehouse='MERKEZ' GROUP BY product_id) m ON m.product_id=p.id ORDER BY p.id DESC''')]
        movements = [movement_dict(db,row['id']) for row in db.execute('SELECT id FROM stock_movements ORDER BY id DESC')]
        return {'products':products,'movements':movements}

@app.post('/api/stock-receipts', status_code=201)
def add_stock_receipt(item: StockReceiptInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        previous = db.execute('SELECT * FROM stock_movements WHERE request_id=?',(str(item.request_id),)).fetchone()
        if previous:
            if previous['kind']!='receipt' or previous['product_id']!=item.product_id or previous['quantity']!=item.quantity or previous['note']!=item.note or previous['user_id']!=user['id']:
                raise HTTPException(409, 'Bu stok giriş isteği daha önce farklı bilgilerle kullanılmış.')
            return movement_dict(db,previous['id'])
        product = db.execute('SELECT * FROM products WHERE id=?',(item.product_id,)).fetchone()
        if not product:
            raise HTTPException(404, 'Ürün bulunamadı.')
        if product['stock']+item.quantity>10000000:
            raise HTTPException(409, 'Stok üst sınırı aşılıyor. En fazla 10.000.000 adet olabilir.')
        db.execute('UPDATE products SET stock=stock+?,version=version+1 WHERE id=?',(item.quantity,item.product_id))
        movement_id = record_stock_movement(db,product,product['stock'],product['stock']+item.quantity,'receipt',user['id'],request_id=str(item.request_id),note=item.note)
        return movement_dict(db,movement_id)

WAREHOUSES = {'MERKEZ': 'Merkez Depo', 'IADE': 'İade Deposu'}
WAREHOUSE_COLUMNS = {'MERKEZ': 'stock', 'IADE': 'return_stock'}

@app.get('/api/warehouses')
def warehouses(user=Depends(auth.current_user)):
    with database() as db:
        db.execute('BEGIN')
        rows = [dict(row) for row in db.execute('SELECT id,name,sku,stock,return_stock FROM products ORDER BY id DESC')]
        return {'warehouses': [{'code': code, 'name': name, 'sellable': code == 'MERKEZ',
                               'stock': sum(row[WAREHOUSE_COLUMNS[code]] for row in rows)}
                              for code, name in WAREHOUSES.items()], 'products': rows}

class TransferInput(StockReceiptInput):
    source: Literal['MERKEZ', 'IADE']
    target: Literal['MERKEZ', 'IADE']
    inspection_confirmed: bool = Field(default=False, strict=True)

def warehouse_action_dict(db, request_id):
    result = dict(db.execute('SELECT * FROM warehouse_actions WHERE request_id=?', (request_id,)).fetchone())
    result['movements'] = [movement_dict(db, row['id']) for row in db.execute(
        'SELECT id FROM stock_movements WHERE action_id=? ORDER BY id', (request_id,))]
    return result

def apply_warehouse_action(item, user, kind, source, target):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db, user['id'])
        request_id = str(item.request_id)
        previous = db.execute('SELECT * FROM warehouse_actions WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if (previous['kind'], previous['product_id'], previous['quantity'], previous['source'], previous['target'], previous['note'], previous['user_id']) != (kind, item.product_id, item.quantity, source, target, item.note, user['id']):
                raise HTTPException(409, 'Bu depo işlem isteği daha önce farklı bilgilerle kullanılmış.')
            return warehouse_action_dict(db, request_id)
        if source == target:
            raise HTTPException(422, 'Kaynak ve hedef depolar farklı olmalı.')
        product = db.execute('SELECT * FROM products WHERE id=?', (item.product_id,)).fetchone()
        if not product:
            raise HTTPException(404, 'Ürün bulunamadı.')
        source_column = WAREHOUSE_COLUMNS[source] if source else None
        target_column = WAREHOUSE_COLUMNS[target]
        if source and product[source_column] < item.quantity:
            raise HTTPException(409, f'{WAREHOUSES[source]} stoğu yetersiz.')
        if product[target_column] + item.quantity > 10000000:
            raise HTTPException(409, 'Hedef depoda stok üst sınırı aşılıyor.')
        db.execute('INSERT INTO warehouse_actions VALUES(?,?,?,?,?,?,?,?,?)',
                   (request_id, kind, item.product_id, item.quantity, source, target, item.note, user['id'], datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        if source:
            db.execute(f'UPDATE products SET {source_column}={source_column}-? WHERE id=?', (item.quantity, item.product_id))
            record_stock_movement(db, product, product[source_column], product[source_column]-item.quantity,
                                  'transfer_out', user['id'], note=item.note, warehouse=source, action_id=request_id)
        db.execute(f'UPDATE products SET {target_column}={target_column}+?,version=version+1 WHERE id=?', (item.quantity, item.product_id))
        record_stock_movement(db, product, product[target_column], product[target_column]+item.quantity,
                              'return_accept' if kind == 'return' else 'transfer_in', user['id'],
                              note=item.note, warehouse=target, action_id=request_id)
        return warehouse_action_dict(db, request_id)

@app.post('/api/warehouse-returns', status_code=201)
def accept_return(item: StockReceiptInput, user=Depends(auth.writer)):
    # Physical return receipt only; it does not change orders or customer balances.
    return apply_warehouse_action(item, user, 'return', None, 'IADE')

@app.post('/api/warehouse-transfers', status_code=201)
def transfer_stock(item: TransferInput, user=Depends(auth.writer)):
    if item.source == 'IADE' and item.target == 'MERKEZ' and not item.inspection_confirmed:
        raise HTTPException(422, 'Merkez Depo’ya aktarım için ürün kontrolünü onaylayın.')
    return apply_warehouse_action(item, user, 'transfer', item.source, item.target)

class OrderLine(BaseModel):
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, le=10000000, strict=True)

class OrderInput(BaseModel):
    customer_id: int = Field(gt=0, strict=True)
    request_id: UUID
    items: list[OrderLine] = Field(min_length=1, max_length=50)

    @field_validator('items')
    @classmethod
    def unique_products(cls, items):
        if len({line.product_id for line in items}) != len(items):
            raise ValueError('Aynı ürün birden fazla satırda olamaz.')
        return items

ORDER_NEXT_STATUS = {'Bekliyor':'Hazırlanıyor','Hazırlanıyor':'Dağıtımda','Dağıtımda':'Teslim edildi'}

def order_dict(db, order_id):
    row = db.execute('SELECT o.id,o.customer_id,c.name customer,o.amount_cents,o.status,o.date FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?',(order_id,)).fetchone()
    result = dict(row)
    result['amount'] = result.pop('amount_cents') / 100
    result['items'] = [dict(line) for line in db.execute('SELECT product_id,name,sku,quantity,price_cents FROM order_items WHERE order_id=? ORDER BY product_id',(order_id,))]
    cancellation = db.execute('SELECT reason,cancelled_at FROM order_cancellations WHERE order_id=?',(order_id,)).fetchone()
    result['cancellation'] = dict(cancellation) if cancellation else None
    result['can_cancel'] = result['status']=='Bekliyor' and bool(result['items']) and not cancellation
    result['next_status'] = ORDER_NEXT_STATUS.get(result['status']) if not cancellation else None
    result['status_history'] = [dict(row) for row in db.execute('SELECT e.from_status,e.to_status,e.changed_at,u.username FROM order_status_events e JOIN users u ON u.id=e.user_id WHERE e.order_id=? ORDER BY e.id',(order_id,))]
    return result

@app.get('/api/orders')
def list_orders(user=Depends(auth.current_user)):
    with database() as db:
        return [order_dict(db,row['id']) for row in db.execute('SELECT id FROM orders ORDER BY id DESC')]

@app.post('/api/orders', status_code=201)
def add_order(item: OrderInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        actor = db.execute('SELECT role,active FROM users WHERE id=?',(user['id'],)).fetchone()
        if not actor or not actor['active'] or actor['role'] not in ('admin','staff'):
            raise HTTPException(403, 'Bu işlem için yetkiniz yok.')
        previous = db.execute('SELECT id,customer_id,created_by FROM orders WHERE request_id=?',(str(item.request_id),)).fetchone()
        if previous:
            lines = [(row['product_id'],row['quantity']) for row in db.execute('SELECT product_id,quantity FROM order_items WHERE order_id=? ORDER BY product_id',(previous['id'],))]
            if previous['created_by']!=user['id'] or previous['customer_id']!=item.customer_id or lines!=sorted((line.product_id,line.quantity) for line in item.items):
                raise HTTPException(409, 'Bu sipariş isteği daha önce farklı bilgilerle kullanılmış.')
            return order_dict(db,previous['id'])
        if not db.execute('SELECT 1 FROM customers WHERE id=?',(item.customer_id,)).fetchone():
            raise HTTPException(404, 'Müşteri bulunamadı.')
        products = []
        for line in item.items:
            product = db.execute('SELECT * FROM products WHERE id=?',(line.product_id,)).fetchone()
            if not product:
                raise HTTPException(404, 'Ürün bulunamadı.')
            if product['stock'] < line.quantity:
                raise HTTPException(409, f"{product['name']} için stok yetersiz. Mevcut: {product['stock']} adet.")
            products.append((line,product))
        total = sum(line.quantity*product['price_cents'] for line,product in products)
        cursor = db.execute('INSERT INTO orders(customer_id,amount_cents,status,date,request_id,created_by) VALUES(?,?,?,?,?,?)',(item.customer_id,total,'Bekliyor',today(),str(item.request_id),user['id']))
        for line,product in products:
            db.execute('UPDATE products SET stock=stock-?,version=version+1 WHERE id=?',(line.quantity,line.product_id))
            record_stock_movement(db,product,product['stock'],product['stock']-line.quantity,'order',user['id'],order_id=cursor.lastrowid,note='Sipariş oluşturma')
            db.execute('INSERT INTO order_items(order_id,product_id,name,sku,quantity,price_cents) VALUES(?,?,?,?,?,?)',(cursor.lastrowid,line.product_id,product['name'],product['sku'],line.quantity,product['price_cents']))
        return order_dict(db,cursor.lastrowid)

class CancellationInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class OrderStatusInput(BaseModel):
    expected_status: Literal['Bekliyor','Hazırlanıyor','Dağıtımda','Teslim edildi']
    status: Literal['Hazırlanıyor','Dağıtımda','Teslim edildi']
    request_id: UUID

@app.post('/api/orders/{order_id}/status')
def update_order_status(order_id: int, item: OrderStatusInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_writer(db,user['id'])
        previous = db.execute('SELECT * FROM order_status_events WHERE request_id=?',(str(item.request_id),)).fetchone()
        if previous:
            if previous['order_id']!=order_id or previous['user_id']!=user['id'] or previous['from_status']!=item.expected_status or previous['to_status']!=item.status:
                raise HTTPException(409, 'Bu aşama isteği daha önce farklı bilgilerle kullanılmış.')
            return order_dict(db,order_id)
        row = db.execute('SELECT status FROM orders WHERE id=?',(order_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Sipariş bulunamadı.')
        if row['status']!=item.expected_status:
            raise HTTPException(409, 'Sipariş durumu değişti. Güncel listeyi yükleyip yeniden deneyin.')
        if ORDER_NEXT_STATUS.get(row['status'])!=item.status:
            raise HTTPException(409, 'Sipariş yalnızca sıradaki aşamaya ilerletilebilir.')
        db.execute('UPDATE orders SET status=? WHERE id=?',(item.status,order_id))
        db.execute('INSERT INTO order_status_events(order_id,user_id,request_id,from_status,to_status,changed_at) VALUES(?,?,?,?,?,?)',(order_id,user['id'],str(item.request_id),row['status'],item.status,datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return order_dict(db,order_id)

@app.post('/api/orders/{order_id}/cancel')
def cancel_order(order_id: int, item: CancellationInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        actor = db.execute('SELECT role,active FROM users WHERE id=?',(user['id'],)).fetchone()
        if not actor or not actor['active'] or actor['role'] not in ('admin','staff'):
            raise HTTPException(403, 'Bu işlem için yetkiniz yok.')
        order = db.execute('SELECT status FROM orders WHERE id=?',(order_id,)).fetchone()
        if not order:
            raise HTTPException(404, 'Sipariş bulunamadı.')
        previous = db.execute('SELECT 1 FROM order_cancellations WHERE order_id=?',(order_id,)).fetchone()
        if previous and order['status']=='İptal edildi':
            return order_dict(db,order_id)
        if order['status']!='Bekliyor' or previous:
            raise HTTPException(409, 'Yalnızca bekleyen siparişler iptal edilebilir.')
        lines = db.execute('SELECT product_id,quantity FROM order_items WHERE order_id=?',(order_id,)).fetchall()
        if not lines:
            raise HTTPException(409, 'Ürün detayı olmayan eski örnek siparişler iptal edilemez.')
        restored_products = {}
        for line in lines:
            product = db.execute('SELECT * FROM products WHERE id=?',(line['product_id'],)).fetchone()
            if not product or product['stock']+line['quantity']>10000000:
                raise HTTPException(409, 'Stok iadesi yapılamadı. Ürün kayıtlarını kontrol edin.')
            restored_products[line['product_id']] = product
        for line in lines:
            db.execute('UPDATE products SET stock=stock+?,version=version+1 WHERE id=?',(line['quantity'],line['product_id']))
            product = restored_products[line['product_id']]
            record_stock_movement(db,product,product['stock'],product['stock']+line['quantity'],'cancellation',user['id'],order_id=order_id,note=item.reason)
        db.execute("UPDATE orders SET status='İptal edildi' WHERE id=?",(order_id,))
        db.execute('INSERT INTO order_cancellations VALUES(?,?,?,?)',(order_id,user['id'],item.reason,datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return order_dict(db,order_id)

class CollectionInput(BaseModel):
    customer_id: int = Field(gt=0, strict=True)
    amount: Decimal = Field(gt=0, le=10000000, decimal_places=2)
    method: Literal['cash','transfer','card']
    note: str = Field(default='', max_length=300)
    request_id: UUID

    @field_validator('note', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

def collection_dict(db, collection_id):
    result = dict(db.execute('SELECT t.id,t.customer_id,c.name customer,t.amount_cents,t.date,t.method,t.note FROM collections t LEFT JOIN customers c ON c.id=t.customer_id WHERE t.id=?',(collection_id,)).fetchone())
    cancellation = db.execute('SELECT reason,cancelled_at FROM collection_cancellations WHERE collection_id=?',(collection_id,)).fetchone()
    original = db.execute('SELECT request_id FROM collections WHERE id=?',(collection_id,)).fetchone()
    result['cancellation'] = dict(cancellation) if cancellation else None
    result['can_cancel'] = result['customer_id'] is not None and original['request_id'] is not None and not cancellation
    return result

@app.get('/api/collections')
def list_collections(user=Depends(auth.current_user)):
    with database() as db:
        return [collection_dict(db,row['id']) for row in db.execute('SELECT id FROM collections ORDER BY id DESC')]

@app.get('/api/customer-balances')
def customer_balances(user=Depends(auth.current_user)):
    with database() as db:
        return [dict(row) for row in db.execute('''
          SELECT c.id,c.name,COALESCE(o.total,0) sales_cents,COALESCE(t.total,0) collected_cents,
                 COALESCE(o.total,0)-COALESCE(t.total,0) balance_cents
          FROM customers c
          LEFT JOIN (SELECT customer_id,SUM(amount_cents) total FROM orders WHERE status!='İptal edildi' GROUP BY customer_id) o ON o.customer_id=c.id
          LEFT JOIN (SELECT customer_id,SUM(amount_cents) total FROM collections p WHERE customer_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM collection_cancellations x WHERE x.collection_id=p.id) GROUP BY customer_id) t ON t.customer_id=c.id
          ORDER BY c.id DESC''')]

@app.post('/api/collections', status_code=201)
def add_collection(item: CollectionInput, user=Depends(auth.writer)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        actor = db.execute('SELECT role,active FROM users WHERE id=?',(user['id'],)).fetchone()
        if not actor or not actor['active'] or actor['role'] not in ('admin','staff'):
            raise HTTPException(403, 'Bu işlem için yetkiniz yok.')
        amount_cents = int(item.amount*100)
        previous = db.execute('SELECT * FROM collections WHERE request_id=?',(str(item.request_id),)).fetchone()
        if previous:
            if previous['created_by']!=user['id'] or previous['customer_id']!=item.customer_id or previous['amount_cents']!=amount_cents or previous['method']!=item.method or previous['note']!=item.note:
                raise HTTPException(409, 'Bu tahsilat isteği daha önce farklı bilgilerle kullanılmış.')
            return collection_dict(db,previous['id'])
        if not db.execute('SELECT 1 FROM customers WHERE id=?',(item.customer_id,)).fetchone():
            raise HTTPException(404, 'Müşteri bulunamadı.')
        cursor = db.execute('INSERT INTO collections(customer_id,amount_cents,date,method,note,request_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(item.customer_id,amount_cents,today(),item.method,item.note,str(item.request_id),user['id'],datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return collection_dict(db,cursor.lastrowid)

@app.post('/api/collections/{collection_id}/cancel')
def cancel_collection(collection_id: int, item: CancellationInput, user=Depends(auth.administrator)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_active_admin(db,user['id'])
        collection = db.execute('SELECT customer_id,request_id FROM collections WHERE id=?',(collection_id,)).fetchone()
        if not collection:
            raise HTTPException(404, 'Tahsilat bulunamadı.')
        if db.execute('SELECT 1 FROM collection_cancellations WHERE collection_id=?',(collection_id,)).fetchone():
            return collection_dict(db,collection_id)
        if collection['customer_id'] is None or collection['request_id'] is None:
            raise HTTPException(409, 'Müşteri veya kayıt detayı eksik eski tahsilatlar iptal edilemez.')
        db.execute('INSERT INTO collection_cancellations VALUES(?,?,?,?)',(collection_id,user['id'],item.reason,datetime.now(ZoneInfo('Europe/Istanbul')).isoformat()))
        return collection_dict(db,collection_id)

@app.get('/api/dashboard')
def dashboard(user=Depends(auth.current_user)):
    with database() as db:
        sales = db.execute("SELECT COALESCE(SUM(amount_cents),0),COUNT(*) FROM orders WHERE date=? AND status!='İptal edildi'",(today(),)).fetchone()
        collected = db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM collections p WHERE date=? AND NOT EXISTS(SELECT 1 FROM collection_cancellations x WHERE x.collection_id=p.id)',(today(),)).fetchone()[0]
        return {'date':today(),'sales':sales[0]/100,'orders':sales[1],'collections':collected/100,'customers':db.execute('SELECT COUNT(*) FROM customers').fetchone()[0], 'stock':db.execute('SELECT COALESCE(SUM(stock),0) FROM products').fetchone()[0], 'low_stock':[product_dict(row) for row in db.execute('SELECT * FROM products WHERE stock<=min_stock')], 'recent_orders':[dict(row) for row in db.execute('SELECT o.id,c.name customer,o.amount_cents/100.0 amount,o.status,o.date FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC LIMIT 5')]}

DIST = Path(__file__).parent.parent / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
else:
    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def frontend_missing():
        return HTMLResponse('''<!doctype html><html lang="tr"><meta charset="utf-8">
        <title>Doğa Gıda — kurulum gerekli</title>
        <h1>Arayüz henüz hazırlanmadı</h1>
        <p>Sunucu çalışıyor. Programı kapatıp proje klasöründeki
        <strong>BASLAT.bat</strong> dosyasını açın; arayüz hazırlanacaktır.</p>
        <p>Elle kurulum: frontend klasöründe <code>npm ci</code>, ardından
        <code>npm run build</code> çalıştırıp sunucuyu yeniden başlatın.</p>
        <p><a href="/docs">API dokümantasyonu</a></p></html>''', status_code=503)

