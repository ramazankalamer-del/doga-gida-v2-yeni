from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import sqlite3
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
import auth
import secrets
import time
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

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

def initialize():
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

class CustomerInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=2, max_length=100)
    phone: str = Field(default='', max_length=25)
    district: str = Field(min_length=2, max_length=80)

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
        return [dict(row) for row in db.execute('SELECT * FROM customers ORDER BY id DESC')]

@app.post('/api/customers', status_code=201)
def add_customer(item: CustomerInput, user=Depends(auth.writer)):
    with database() as db:
        cursor = db.execute('INSERT INTO customers(name,contact,phone,district) VALUES(?,?,?,?)', (item.name,item.contact,item.phone,item.district))
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
        row = db.execute('SELECT version FROM customers WHERE id=?',(customer_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Müşteri bulunamadı.')
        if row['version']!=item.expected_version:
            raise HTTPException(409, 'Kayıt başka bir işlemde değişti. Güncel listeyi yükleyip yeniden deneyin.')
        db.execute('UPDATE customers SET name=?,contact=?,phone=?,district=?,version=version+1 WHERE id=?',(item.name,item.contact,item.phone,item.district,customer_id))
        return dict(db.execute('SELECT * FROM customers WHERE id=?',(customer_id,)).fetchone())

def product_dict(row):
    result = dict(row)
    result['price'] = result.pop('price_cents') / 100
    return result

def record_stock_movement(db, product, before, after, kind, user_id, order_id=None, request_id=None, note=''):
    if before==after:
        return None
    return db.execute('INSERT INTO stock_movements(product_id,name,sku,kind,quantity,before_stock,after_stock,user_id,order_id,request_id,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(product['id'],product['name'],product['sku'],kind,after-before,before,after,user_id,order_id,request_id,note,datetime.now(ZoneInfo('Europe/Istanbul')).isoformat())).lastrowid

def movement_dict(db, movement_id):
    return dict(db.execute('SELECT m.id,m.product_id,m.name,m.sku,m.kind,m.quantity,m.before_stock,m.after_stock,m.order_id,m.note,m.created_at,u.username FROM stock_movements m JOIN users u ON u.id=m.user_id WHERE m.id=?',(movement_id,)).fetchone())

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
          LEFT JOIN (SELECT product_id,SUM(quantity) delta FROM stock_movements GROUP BY product_id) m ON m.product_id=p.id ORDER BY p.id DESC''')]
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

