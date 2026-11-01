from typing import Literal
from uuid import UUID
import json
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,Field,field_validator,model_validator

TABLES=('commercial_returns','commercial_return_items','commercial_return_cancellations')


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS commercial_returns(
        id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('sale','purchase')),
        order_id INTEGER REFERENCES orders(id),purchase_id INTEGER REFERENCES purchases(id),
        warehouse TEXT NOT NULL CHECK(warehouse IN ('MERKEZ','IADE')),date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL CHECK(amount_cents>0),note TEXT NOT NULL,
        request_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
        CHECK((kind='sale' AND order_id IS NOT NULL AND purchase_id IS NULL AND warehouse='IADE') OR
              (kind='purchase' AND purchase_id IS NOT NULL AND order_id IS NULL)));
        CREATE TABLE IF NOT EXISTS commercial_return_items(
        return_id INTEGER NOT NULL REFERENCES commercial_returns(id),product_id INTEGER NOT NULL REFERENCES products(id),
        name TEXT NOT NULL,sku TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),price_cents INTEGER NOT NULL,
        cost_cents INTEGER,PRIMARY KEY(return_id,product_id));
        CREATE TABLE IF NOT EXISTS commercial_return_cancellations(
        return_id INTEGER PRIMARY KEY REFERENCES commercial_returns(id),reason TEXT NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id),cancelled_at TEXT NOT NULL);''')


def active_clause(alias='r'):
    return f'NOT EXISTS(SELECT 1 FROM commercial_return_cancellations rc WHERE rc.return_id={alias}.id)'


def returned_amount(db,kind,source_id,reference=None):
    column='order_id' if kind=='sale' else 'purchase_id'
    return db.execute(f'SELECT COALESCE(SUM(r.amount_cents),0) FROM commercial_returns r WHERE {column}=? AND {active_clause()}'+(' AND r.date<=?' if reference else ''),
                      [source_id,*([reference] if reference else [])]).fetchone()[0]


def returned_quantity(db,kind,source_id,product_id,reference=None):
    column='order_id' if kind=='sale' else 'purchase_id'
    return db.execute(f'''SELECT COALESCE(SUM(i.quantity),0) FROM commercial_return_items i JOIN commercial_returns r
        ON r.id=i.return_id WHERE r.{column}=? AND i.product_id=? AND {active_clause()}'''+(' AND r.date<=?' if reference else ''),
        [source_id,product_id,*([reference] if reference else [])]).fetchone()[0]


def has_returns(db,kind,source_id):
    column='order_id' if kind=='sale' else 'purchase_id'
    return bool(db.execute(f'SELECT 1 FROM commercial_returns r WHERE {column}=? AND {active_clause()}',(source_id,)).fetchone())


def ledger_events(db,kind,party_id):
    table='orders' if kind=='sale' else 'purchases';source_col='order_id' if kind=='sale' else 'purchase_id'
    party_col='customer_id' if kind=='sale' else 'supplier_id';prefix='sales_return' if kind=='sale' else 'purchase_return'
    from customer_statement import local_day
    events=[]
    for r in db.execute(f'''SELECT r.*,c.reason,c.cancelled_at FROM commercial_returns r JOIN {table} o ON o.id=r.{source_col}
            LEFT JOIN commercial_return_cancellations c ON c.return_id=r.id WHERE o.{party_col}=?''',(party_id,)):
        base={'record_id':r['id'],'reference':f'İD-{r["id"]}','status':'İptal edildi' if r['cancelled_at'] else 'Geçerli'}
        events.append({**base,'date':r['date'],'kind':prefix,'debit_cents':0,'credit_cents':r['amount_cents'],'note':r['note']})
        if r['cancelled_at']:
            events.append({**base,'date':local_day(r['cancelled_at']),'kind':prefix+'_cancel','debit_cents':r['amount_cents'],'credit_cents':0,'note':r['reason']})
    return events


def source(db,kind,source_id):
    if kind=='sale':
        row=db.execute('''SELECT o.id,o.date,o.amount_cents,o.customer_id party_id,c.name party,o.status
            FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?''',(source_id,)).fetchone()
        if not row: raise HTTPException(404,'Satış bulunamadı.')
        if row['status']=='İptal edildi' or db.execute('SELECT 1 FROM order_cancellations WHERE order_id=?',(source_id,)).fetchone():
            raise HTTPException(409,'İptal edilen satış için iade alınamaz.')
        lines=db.execute('''SELECT i.product_id,i.name,i.sku,i.quantity,i.price_cents,s.unit_cost_cents cost_cents
            FROM order_items i LEFT JOIN sale_cost_snapshots s ON s.order_item_id=i.id WHERE i.order_id=? ORDER BY i.product_id''',(source_id,))
    else:
        row=db.execute('''SELECT p.id,p.date,p.amount_cents,p.supplier_id party_id,s.name party FROM purchases p
            JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?''',(source_id,)).fetchone()
        if not row: raise HTTPException(404,'Alış bulunamadı.')
        if db.execute('SELECT 1 FROM purchase_cancellations WHERE purchase_id=?',(source_id,)).fetchone():
            raise HTTPException(409,'İptal edilen alış için iade yapılamaz.')
        lines=db.execute('''SELECT product_id,name,sku,quantity,unit_cost_cents price_cents,NULL cost_cents
            FROM purchase_items WHERE purchase_id=? ORDER BY product_id''',(source_id,))
    result=dict(row);result['items']=[]
    for line in lines:
        used=returned_quantity(db,kind,source_id,line['product_id'])
        result['items'].append({**dict(line),'returned_quantity':used,'remaining_quantity':line['quantity']-used})
    return result


def return_dict(db,rid):
    row=dict(db.execute('''SELECT r.*,u.username,COALESCE(c.name,s.name) party FROM commercial_returns r
        JOIN users u ON u.id=r.created_by LEFT JOIN orders o ON o.id=r.order_id LEFT JOIN customers c ON c.id=o.customer_id
        LEFT JOIN purchases p ON p.id=r.purchase_id LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE r.id=?''',(rid,)).fetchone())
    row.pop('payload');row.pop('request_id');row['source_id']=row['order_id'] or row['purchase_id']
    row['items']=[dict(i) for i in db.execute('SELECT product_id,name,sku,quantity,price_cents FROM commercial_return_items WHERE return_id=? ORDER BY product_id',(rid,))]
    cancel=db.execute('SELECT reason,cancelled_at FROM commercial_return_cancellations WHERE return_id=?',(rid,)).fetchone()
    row['cancellation']=dict(cancel) if cancel else None
    return row


class ReturnLine(BaseModel):
    product_id:int=Field(ge=1,strict=True)
    quantity:int=Field(ge=1,le=10000000,strict=True)


class ReturnInput(BaseModel):
    kind:Literal['sale','purchase']
    source_id:int=Field(ge=1,strict=True)
    warehouse:Literal['MERKEZ','IADE']='IADE'
    note:str=Field(min_length=3,max_length=300)
    request_id:UUID
    items:list[ReturnLine]=Field(min_length=1,max_length=50)

    @field_validator('note')
    @classmethod
    def clean(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('İade açıklaması girin.')
        return value

    @model_validator(mode='after')
    def valid(self):
        if len({i.product_id for i in self.items})!=len(self.items): raise ValueError('Ürün tekrar edemez.')
        if self.kind=='sale' and self.warehouse!='IADE': raise ValueError('Satış iadesi İade Deposuna alınır.')
        return self


class CancelInput(BaseModel):
    reason:str=Field(min_length=3,max_length=300)
    @field_validator('reason')
    @classmethod
    def clean(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('İptal nedeni girin.')
        return value


def register(app,env):
    @app.get('/api/returns/sources')
    def sources(kind:Literal['sale','purchase'],party_id:int|None=None,offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        table='orders' if kind=='sale' else 'purchases';party_col='customer_id' if kind=='sale' else 'supplier_id'
        with env.database() as db:
            db.execute('BEGIN');rows=[]
            for row in db.execute(f'SELECT id FROM {table}'+(f' WHERE {party_col}=?' if party_id else '')+' ORDER BY date DESC,id DESC',[party_id] if party_id else []):
                try: item=source(db,kind,row['id'])
                except HTTPException as e:
                    if e.status_code==409: continue
                    raise
                if any(i['remaining_quantity']>0 for i in item['items']): rows.append(item)
            return {'total':len(rows),'offset':offset,'rows':rows[offset:offset+50]}

    @app.get('/api/returns')
    def list_returns(kind:Literal['sale','purchase'],party_id:int|None=None,offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN')
            join='JOIN orders o ON o.id=r.order_id' if kind=='sale' else 'JOIN purchases o ON o.id=r.purchase_id'
            col='customer_id' if kind=='sale' else 'supplier_id'
            where='r.kind=?'+(f' AND o.{col}=?' if party_id else '');params=[kind,*([party_id] if party_id else [])]
            query=f'FROM commercial_returns r {join} WHERE {where}'
            return {'total':db.execute('SELECT COUNT(*) '+query,params).fetchone()[0],'offset':offset,
                    'rows':[return_dict(db,r['id']) for r in db.execute('SELECT r.id '+query+' ORDER BY r.id DESC LIMIT 50 OFFSET ?',[*params,offset])]}

    @app.post('/api/returns',status_code=201)
    def create_return(item:ReturnInput,user=Depends(env.auth.writer)):
        payload=item.model_dump(mode='json',exclude={'request_id'});payload['items']=sorted(payload['items'],key=lambda i:i['product_id'])
        fingerprint=json.dumps(payload,sort_keys=True)
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id'])
            old=db.execute('SELECT id,payload,created_by FROM commercial_returns WHERE request_id=?',(str(item.request_id),)).fetchone()
            if old:
                if old['payload']!=fingerprint or old['created_by']!=user['id']: raise HTTPException(409,'İstek kimliği farklı iade için kullanıldı.')
                return return_dict(db,old['id'])
            original=source(db,item.kind,item.source_id);day=env.today()
            if original['date']>day: raise HTTPException(409,'Gelecek tarihli kayda iade yapılamaz.')
            lines={i['product_id']:i for i in original['items']};validated=[];total=0
            column='return_stock' if item.warehouse=='IADE' else 'stock'
            for line in item.items:
                original_line=lines.get(line.product_id)
                if not original_line or line.quantity>original_line['remaining_quantity']:
                    raise HTTPException(409,'İade adedi kalan satış/alış adedini aşıyor. Listeyi yenileyin.')
                product=db.execute('SELECT * FROM products WHERE id=?',(line.product_id,)).fetchone()
                after=product[column]+(line.quantity if item.kind=='sale' else -line.quantity)
                if not 0<=after<=10000000: raise HTTPException(409,'Seçilen depoda stok yetersiz veya üst sınır aşılıyor.')
                total+=line.quantity*original_line['price_cents'];validated.append((line,original_line,product,after))
            rid=db.execute('''INSERT INTO commercial_returns(kind,order_id,purchase_id,warehouse,date,amount_cents,note,request_id,payload,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(item.kind,item.source_id if item.kind=='sale' else None,item.source_id if item.kind=='purchase' else None,
                    item.warehouse,day,total,item.note,str(item.request_id),fingerprint,user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat())).lastrowid
            for line,original_line,product,after in validated:
                db.execute('INSERT INTO commercial_return_items VALUES(?,?,?,?,?,?,?)',(rid,line.product_id,original_line['name'],original_line['sku'],line.quantity,original_line['price_cents'],original_line['cost_cents']))
                db.execute(f'UPDATE products SET {column}=?,version=version+1 WHERE id=?',(after,line.product_id))
                env.record_stock_movement(db,product,product[column],after,'sales_return_in' if item.kind=='sale' else 'purchase_return_out',user['id'],
                    order_id=item.source_id if item.kind=='sale' else None,warehouse=item.warehouse,request_id=f'commercial-return:{rid}:{line.product_id}',note=f'İade İD-{rid} · '+item.note)
            return return_dict(db,rid)

    @app.post('/api/returns/{return_id}/cancel')
    def cancel_return(return_id:int,item:CancelInput,user=Depends(env.auth.administrator)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_admin(db,user['id'])
            row=db.execute('SELECT * FROM commercial_returns WHERE id=?',(return_id,)).fetchone()
            if not row: raise HTTPException(404,'İade bulunamadı.')
            if db.execute('SELECT 1 FROM commercial_return_cancellations WHERE return_id=?',(return_id,)).fetchone(): return return_dict(db,return_id)
            column='return_stock' if row['warehouse']=='IADE' else 'stock';validated=[]
            for line in db.execute('SELECT * FROM commercial_return_items WHERE return_id=?',(return_id,)):
                product=db.execute('SELECT * FROM products WHERE id=?',(line['product_id'],)).fetchone()
                after=product[column]+(-line['quantity'] if row['kind']=='sale' else line['quantity'])
                if not 0<=after<=10000000: raise HTTPException(409,'İptal için depo stoğu yetersiz veya üst sınır aşılıyor.')
                validated.append((line,product,after))
            for line,product,after in validated:
                db.execute(f'UPDATE products SET {column}=?,version=version+1 WHERE id=?',(after,product['id']))
                env.record_stock_movement(db,product,product[column],after,'sales_return_cancel_out' if row['kind']=='sale' else 'purchase_return_cancel_in',user['id'],
                    order_id=row['order_id'],warehouse=row['warehouse'],request_id=f'commercial-return-cancel:{return_id}:{product["id"]}',note=f'İade İD-{return_id} iptali · '+item.reason)
            db.execute('INSERT INTO commercial_return_cancellations VALUES(?,?,?,?)',(return_id,item.reason,user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()))
            return return_dict(db,return_id)

    @app.get('/api/stock-needs')
    def stock_needs(status:Literal['all','low','out']='all',offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN');rows=[]
            for p in db.execute('SELECT id,name,sku,stock,return_stock,min_stock FROM products WHERE stock<=min_stock ORDER BY stock,id'):
                if status=='out' and p['stock']!=0 or status=='low' and p['stock']==0: continue
                target=min(10000000,p['min_stock']+1);quantity=max(0,target-p['stock'])
                last=db.execute(f'''SELECT i.unit_cost_cents,p.id FROM purchase_items i JOIN purchases p ON p.id=i.purchase_id
                    WHERE i.product_id=? AND p.date<=? AND NOT EXISTS(SELECT 1 FROM purchase_cancellations c WHERE c.purchase_id=p.id)
                    AND i.quantity>COALESCE((SELECT SUM(ri.quantity) FROM commercial_return_items ri JOIN commercial_returns r ON r.id=ri.return_id
                        WHERE r.purchase_id=p.id AND ri.product_id=i.product_id AND {active_clause()}),0)
                    ORDER BY p.date DESC,p.id DESC LIMIT 1''',(p['id'],env.today())).fetchone()
                cost=last['unit_cost_cents'] if last else None
                rows.append({**dict(p),'target_stock':target,'needed_quantity':quantity,'unit_cost_cents':cost,
                             'estimated_cents':quantity*cost if cost is not None else None})
            return {'total':len(rows),'offset':offset,'needed_quantity':sum(r['needed_quantity'] for r in rows),
                    'known_estimated_cents':sum(r['estimated_cents'] or 0 for r in rows),
                    'unknown_cost_products':sum(1 for r in rows if r['unit_cost_cents'] is None and r['needed_quantity']>0),'rows':rows[offset:offset+50]}
