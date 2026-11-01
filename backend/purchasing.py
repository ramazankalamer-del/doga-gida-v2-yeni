from datetime import date
from decimal import Decimal
import json
from uuid import UUID
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,Field,field_validator,model_validator

TABLES=('suppliers','purchases','purchase_items','purchase_cancellations','supplier_payments')
def initialize(db):
    db.executescript("""CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,contact TEXT NOT NULL,phone TEXT NOT NULL,note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,request_id TEXT NOT NULL UNIQUE,updated_by INTEGER NOT NULL REFERENCES users(id),updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY,supplier_id INTEGER NOT NULL REFERENCES suppliers(id),date TEXT NOT NULL,due_date TEXT,amount_cents INTEGER NOT NULL,note TEXT NOT NULL,request_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS purchase_items(purchase_id INTEGER NOT NULL REFERENCES purchases(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,sku TEXT NOT NULL,quantity INTEGER NOT NULL,unit_cost_cents INTEGER NOT NULL,PRIMARY KEY(purchase_id,product_id));
    CREATE TABLE IF NOT EXISTS purchase_cancellations(purchase_id INTEGER PRIMARY KEY REFERENCES purchases(id),reason TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),cancelled_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS supplier_payments(id INTEGER PRIMARY KEY,supplier_id INTEGER NOT NULL REFERENCES suppliers(id),date TEXT NOT NULL,amount_cents INTEGER NOT NULL,note TEXT NOT NULL,request_id TEXT NOT NULL UNIQUE,created_by INTEGER NOT NULL REFERENCES users(id),finance_entry_id INTEGER NOT NULL UNIQUE REFERENCES finance_entries(id));""")

class SupplierFields(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    contact:str=Field(default='',max_length=100)
    phone:str=Field(default='',max_length=25)
    note:str=Field(default='',max_length=300)
    @field_validator('name','contact','phone','note')
    @classmethod
    def trim(cls,value): return value.strip()
    @model_validator(mode='after')
    def name_valid(self):
        if len(self.name)<2: raise ValueError('Tedarikçi adı girilmelidir.')
        return self
class SupplierCreate(SupplierFields):
    request_id:UUID
class SupplierUpdate(SupplierFields):
    expected_version:int=Field(ge=0,strict=True)
class PurchaseLine(BaseModel):
    product_id:int=Field(ge=1,strict=True)
    quantity:int=Field(ge=1,le=10000000,strict=True)
    unit_cost:Decimal=Field(gt=0,le=10000000,decimal_places=2)
class PurchaseInput(BaseModel):
    supplier_id:int=Field(ge=1,strict=True)
    date:date
    due_date:date|None=None
    note:str=Field(default='',max_length=300)
    request_id:UUID
    items:list[PurchaseLine]=Field(min_length=1,max_length=50)
    @field_validator('note')
    @classmethod
    def trim(cls,value): return value.strip()
    @model_validator(mode='after')
    def valid(self):
        if len({x.product_id for x in self.items})!=len(self.items): raise ValueError('Aynı ürün tekrar edemez.')
        if self.due_date and self.due_date<self.date: raise ValueError('Vade alış tarihinden önce olamaz.')
        return self
class PaymentInput(BaseModel):
    supplier_id:int=Field(ge=1,strict=True)
    account_id:int=Field(ge=1,strict=True)
    amount:Decimal=Field(gt=0,le=10000000,decimal_places=2)
    date:date
    note:str=Field(min_length=3,max_length=300)
    request_id:UUID
    @field_validator('note')
    @classmethod
    def trim(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('Ödeme açıklaması girilmelidir.')
        return value
class CancelInput(BaseModel):
    reason:str=Field(min_length=3,max_length=300)
    @field_validator('reason')
    @classmethod
    def trim(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('İptal nedeni girilmelidir.')
        return value

def register(app,env):
    def supplier(db,sid):
        row=db.execute('SELECT * FROM suppliers WHERE id=?',(sid,)).fetchone()
        if not row: raise HTTPException(404,'Tedarikçi bulunamadı.')
        return row
    def purchase_dict(db,pid):
        row=dict(db.execute('SELECT p.*,s.name supplier FROM purchases p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?',(pid,)).fetchone())
        row.pop('payload');row['items']=[dict(x) for x in db.execute('SELECT * FROM purchase_items WHERE purchase_id=? ORDER BY product_id',(pid,))]
        cancel=db.execute('SELECT reason,cancelled_at FROM purchase_cancellations WHERE purchase_id=?',(pid,)).fetchone();row['cancellation']=dict(cancel) if cancel else None
        return row
    def payment_dict(db,pid):
        row=dict(db.execute('SELECT p.*,s.name supplier FROM supplier_payments p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?',(pid,)).fetchone());row['finance']=env.finance_entry_dict(db,row['finance_entry_id']);return row
    @app.get('/api/suppliers')
    def suppliers(user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN');rows=[]
            for row in db.execute('SELECT * FROM suppliers ORDER BY id DESC'):
                total=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM purchases p WHERE supplier_id=? AND NOT EXISTS(SELECT 1 FROM purchase_cancellations c WHERE c.purchase_id=p.id)',(row['id'],)).fetchone()[0]
                paid=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM supplier_payments p WHERE supplier_id=? AND NOT EXISTS(SELECT 1 FROM finance_cancellations c WHERE c.entry_id=p.finance_entry_id)',(row['id'],)).fetchone()[0]
                rows.append({**dict(row),'purchases_cents':total,'paid_cents':paid,'balance_cents':total-paid})
            return rows
    @app.post('/api/suppliers')
    def create_supplier(item:SupplierCreate,user=Depends(env.auth.writer)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id'])
            old=db.execute('SELECT * FROM suppliers WHERE request_id=?',(str(item.request_id),)).fetchone()
            if old:
                if tuple(old[k] for k in ('name','contact','phone','note','updated_by'))!=(item.name,item.contact,item.phone,item.note,user['id']): raise HTTPException(409,'İstek kimliği farklı tedarikçi için kullanıldı.')
                return dict(old)
            result=db.execute('INSERT INTO suppliers(name,contact,phone,note,request_id,updated_by,updated_at) VALUES(?,?,?,?,?,?,?)',(item.name,item.contact,item.phone,item.note,str(item.request_id),user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()))
            return dict(supplier(db,result.lastrowid))
    @app.post('/api/suppliers/{supplier_id}')
    def edit_supplier(supplier_id:int,item:SupplierUpdate,user=Depends(env.auth.writer)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id']);old=supplier(db,supplier_id)
            if old['version']!=item.expected_version: raise HTTPException(409,'Tedarikçi değişti. Listeyi yenileyin.')
            db.execute('UPDATE suppliers SET name=?,contact=?,phone=?,note=?,version=version+1,updated_by=?,updated_at=? WHERE id=?',(item.name,item.contact,item.phone,item.note,user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat(),supplier_id));return dict(supplier(db,supplier_id))
    @app.get('/api/purchases')
    def list_purchases(supplier_id:int|None=None,offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN');where='supplier_id=?' if supplier_id else '1=1';params=[supplier_id] if supplier_id else []
            if supplier_id: supplier(db,supplier_id)
            return {'total':db.execute(f'SELECT COUNT(*) FROM purchases WHERE {where}',params).fetchone()[0],'offset':offset,'rows':[purchase_dict(db,x['id']) for x in db.execute(f'SELECT id FROM purchases WHERE {where} ORDER BY date DESC,id DESC LIMIT 50 OFFSET ?',[*params,offset])]}
    @app.post('/api/purchases')
    def create_purchase(item:PurchaseInput,user=Depends(env.auth.writer)):
        fingerprint=json.dumps(item.model_dump(mode='json',exclude={'request_id'}),sort_keys=True)
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id'])
            old=db.execute('SELECT * FROM purchases WHERE request_id=?',(str(item.request_id),)).fetchone()
            if old:
                if old['payload']!=fingerprint or old['created_by']!=user['id']: raise HTTPException(409,'İstek kimliği farklı alış için kullanıldı.')
                return purchase_dict(db,old['id'])
            supplier(db,item.supplier_id)
            if item.date.isoformat()>env.today(): raise HTTPException(422,'Gelecek tarihli alış kaydedilemez.')
            products=[];total=0
            for line in item.items:
                product=db.execute('SELECT * FROM products WHERE id=?',(line.product_id,)).fetchone()
                if not product: raise HTTPException(404,'Ürün bulunamadı.')
                if product['stock']+line.quantity>10000000: raise HTTPException(409,'Merkez stok üst sınırı aşılıyor.')
                total+=line.quantity*int(line.unit_cost*100);products.append((line,product))
            if total>1000000000: raise HTTPException(422,'Alış toplamı 10.000.000 TL sınırını aşıyor.')
            stamp=env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()
            pid=db.execute('INSERT INTO purchases(supplier_id,date,due_date,amount_cents,note,request_id,payload,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(item.supplier_id,item.date.isoformat(),item.due_date.isoformat() if item.due_date else None,total,item.note,str(item.request_id),fingerprint,user['id'],stamp)).lastrowid
            for line,product in products:
                db.execute('INSERT INTO purchase_items VALUES(?,?,?,?,?,?)',(pid,product['id'],product['name'],product['sku'],line.quantity,int(line.unit_cost*100)))
                db.execute('UPDATE products SET stock=stock+?,version=version+1 WHERE id=?',(line.quantity,product['id']))
                env.record_stock_movement(db,product,product['stock'],product['stock']+line.quantity,'purchase_in',user['id'],request_id=f'purchase:{pid}:{product["id"]}',note=f'Alış AL-{pid} · '+item.note)
            return purchase_dict(db,pid)
    @app.post('/api/purchases/{purchase_id}/cancel')
    def cancel_purchase(purchase_id:int,item:CancelInput,user=Depends(env.auth.administrator)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_admin(db,user['id'])
            if not db.execute('SELECT 1 FROM purchases WHERE id=?',(purchase_id,)).fetchone(): raise HTTPException(404,'Alış bulunamadı.')
            if db.execute('SELECT 1 FROM purchase_cancellations WHERE purchase_id=?',(purchase_id,)).fetchone(): return purchase_dict(db,purchase_id)
            lines=list(db.execute('SELECT * FROM purchase_items WHERE purchase_id=?',(purchase_id,)))
            for line in lines:
                product=db.execute('SELECT * FROM products WHERE id=?',(line['product_id'],)).fetchone()
                if product['stock']<line['quantity']: raise HTTPException(409,'Alışı iptal etmek için Merkez stok yetersiz.')
                db.execute('UPDATE products SET stock=stock-?,version=version+1 WHERE id=?',(line['quantity'],product['id']))
                env.record_stock_movement(db,product,product['stock'],product['stock']-line['quantity'],'purchase_cancel_out',user['id'],request_id=f'purchase-cancel:{purchase_id}:{product["id"]}',note=item.reason)
            db.execute('INSERT INTO purchase_cancellations VALUES(?,?,?,?)',(purchase_id,item.reason,user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()));return purchase_dict(db,purchase_id)
    @app.get('/api/supplier-payments')
    def list_payments(supplier_id:int|None=None,offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN');where='supplier_id=?' if supplier_id else '1=1';params=[supplier_id] if supplier_id else []
            if supplier_id: supplier(db,supplier_id)
            return {'total':db.execute(f'SELECT COUNT(*) FROM supplier_payments WHERE {where}',params).fetchone()[0],'offset':offset,'rows':[payment_dict(db,x['id']) for x in db.execute(f'SELECT id FROM supplier_payments WHERE {where} ORDER BY date DESC,id DESC LIMIT 50 OFFSET ?',[*params,offset])]}
    @app.post('/api/supplier-payments')
    def pay_supplier(item:PaymentInput,user=Depends(env.auth.writer)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id']);amount=int(item.amount*100)
            old=db.execute('SELECT * FROM supplier_payments WHERE request_id=?',(str(item.request_id),)).fetchone()
            if old:
                movement=env.finance_entry_dict(db,old['finance_entry_id'])
                if tuple(old[k] for k in ('supplier_id','date','amount_cents','note','created_by'))!=(item.supplier_id,item.date.isoformat(),amount,item.note,user['id']) or movement['account_id']!=item.account_id: raise HTTPException(409,'İstek kimliği farklı ödeme için kullanıldı.')
                return payment_dict(db,old['id'])
            supplier(db,item.supplier_id);account=db.execute('SELECT * FROM finance_accounts WHERE id=?',(item.account_id,)).fetchone()
            if not account: raise HTTPException(404,'Ödeme hesabı bulunamadı.')
            if item.date.isoformat()>env.today(): raise HTTPException(422,'Gelecek tarihli ödeme kaydedilemez.')
            if account['kind']=='cash' and env.finance_balance(db,account)<amount: raise HTTPException(409,'Kasa bakiyesi yetersiz.')
            stamp=env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()
            eid=db.execute('INSERT INTO finance_entries(account_id,kind,amount_cents,date,category,note,request_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(account['id'],'withdrawal',amount,item.date.isoformat(),'',item.note,'supplier-payment:'+str(item.request_id),user['id'],stamp)).lastrowid
            pid=db.execute('INSERT INTO supplier_payments(supplier_id,date,amount_cents,note,request_id,created_by,finance_entry_id) VALUES(?,?,?,?,?,?,?)',(item.supplier_id,item.date.isoformat(),amount,item.note,str(item.request_id),user['id'],eid)).lastrowid
            return payment_dict(db,pid)
    @app.post('/api/supplier-payments/{payment_id}/cancel')
    def cancel_payment(payment_id:int,item:CancelInput,user=Depends(env.auth.administrator)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_admin(db,user['id']);row=db.execute('SELECT * FROM supplier_payments WHERE id=?',(payment_id,)).fetchone()
            if not row: raise HTTPException(404,'Ödeme bulunamadı.')
            env.cancel_finance_row(db,row['finance_entry_id'],item.reason,user['id']);return payment_dict(db,payment_id)
