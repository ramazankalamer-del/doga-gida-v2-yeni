from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import sqlite3
from decimal import Decimal

from fastapi import FastAPI, HTTPException
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
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def initialize():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT NOT NULL, phone TEXT NOT NULL, district TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL UNIQUE, category TEXT NOT NULL, price_cents INTEGER NOT NULL, stock INTEGER NOT NULL, min_stock INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id), amount_cents INTEGER NOT NULL, status TEXT NOT NULL, date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS collections(id INTEGER PRIMARY KEY, amount_cents INTEGER NOT NULL, date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seed_version(version INTEGER PRIMARY KEY);
        ''')
        if not db.execute('SELECT 1 FROM seed_version WHERE version=1').fetchone():
            db.executemany('INSERT INTO customers(name,contact,phone,district) VALUES(?,?,?,?)', [
                ('Örnek Bahar Market','Demo Yetkili 1','','Kadıköy'),('Örnek Deniz Gıda','Demo Yetkili 2','','Üsküdar'),('Örnek Yeşil Bakkal','Demo Yetkili 3','','Ataşehir'),('Örnek Gün Market','Demo Yetkili 4','','Maltepe')])
            db.executemany('INSERT INTO products(name,sku,category,price_cents,stock,min_stock) VALUES(?,?,?,?,?,?)',[
                ('Ayçiçek Yağı 5 L','DG-001','Temel gıda',32500,84,20),('Baldo Pirinç 1 kg','DG-002','Bakliyat',8500,156,30),('Toz Şeker 1 kg','DG-003','Temel gıda',4200,18,25),('Çay 1 kg','DG-004','İçecek',21000,64,15),('Sıvı Sabun 750 ml','DG-005','Temizlik',6500,12,20)])
            db.executemany('INSERT INTO orders(customer_id,amount_cents,status,date) VALUES(?,?,?,?)',[(1,1280000,'Hazırlanıyor',today()),(2,845000,'Dağıtımda',today()),(3,362500,'Teslim edildi',today()),(4,620000,'Bekliyor',today())])
            db.execute('INSERT INTO collections(amount_cents,date) VALUES(?,?)',(1850000,today()))
            db.execute('INSERT INTO seed_version VALUES(1)')

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app = FastAPI(title='Doğa Gıda V2 API', lifespan=lifespan)

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
def customers():
    with database() as db:
        return [dict(row) for row in db.execute('SELECT * FROM customers ORDER BY id DESC')]

@app.post('/api/customers', status_code=201)
def add_customer(item: CustomerInput):
    with database() as db:
        cursor = db.execute('INSERT INTO customers(name,contact,phone,district) VALUES(?,?,?,?)', (item.name,item.contact,item.phone,item.district))
        return {'id':cursor.lastrowid, **item.model_dump()}

def product_dict(row):
    result = dict(row)
    result['price'] = result.pop('price_cents') / 100
    return result

@app.get('/api/products')
def products():
    with database() as db:
        return [product_dict(row) for row in db.execute('SELECT * FROM products ORDER BY id DESC')]

@app.post('/api/products', status_code=201)
def add_product(item: ProductInput):
    try:
        with database() as db:
            cursor = db.execute('INSERT INTO products(name,sku,category,price_cents,stock,min_stock) VALUES(?,?,?,?,?,?)',(item.name,item.sku.upper(),item.category,int(item.price*100),item.stock,item.min_stock))
            return product_dict(db.execute('SELECT * FROM products WHERE id=?',(cursor.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Bu ürün kodu zaten kullanılıyor.')

@app.get('/api/dashboard')
def dashboard():
    with database() as db:
        sales = db.execute('SELECT COALESCE(SUM(amount_cents),0),COUNT(*) FROM orders WHERE date=?',(today(),)).fetchone()
        collected = db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM collections WHERE date=?',(today(),)).fetchone()[0]
        return {'date':today(),'sales':sales[0]/100,'orders':sales[1],'collections':collected/100,'customers':db.execute('SELECT COUNT(*) FROM customers').fetchone()[0], 'stock':db.execute('SELECT COALESCE(SUM(stock),0) FROM products').fetchone()[0], 'low_stock':[product_dict(row) for row in db.execute('SELECT * FROM products WHERE stock<=min_stock')], 'recent_orders':[dict(row) for row in db.execute('SELECT o.id,c.name customer,o.amount_cents/100.0 amount,o.status,o.date FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC LIMIT 5')]}

DIST = Path(__file__).parent.parent / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
