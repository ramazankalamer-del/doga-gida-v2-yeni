"""Read-only trade reports and sale-time estimates, stored in integer kuruş."""
from datetime import date, timedelta
from typing import Literal
from fastapi import Depends, HTTPException, Query
from customer_statement import local_day


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS sale_cost_snapshots(
        order_item_id INTEGER PRIMARY KEY REFERENCES order_items(id),
        unit_cost_cents INTEGER, purchase_id INTEGER REFERENCES purchases(id))''')


def snapshot_cost(db, item_id, product_id, sale_date):
    # Only purchases already recorded at sale creation can supply an estimate.
    row=db.execute('''SELECT p.id,i.unit_cost_cents FROM purchase_items i
        JOIN purchases p ON p.id=i.purchase_id WHERE i.product_id=? AND p.date<=?
        AND NOT EXISTS(SELECT 1 FROM purchase_cancellations c WHERE c.purchase_id=p.id)
        ORDER BY p.date DESC,p.id DESC LIMIT 1''',(product_id,sale_date)).fetchone()
    db.execute('INSERT INTO sale_cost_snapshots VALUES(?,?,?)',
               (item_id,row['unit_cost_cents'] if row else None,row['id'] if row else None))


def date_range(start,end):
    if start and end and start>end:
        raise HTTPException(422,'Başlangıç tarihi bitişten sonra olamaz.')
    return start.isoformat() if start else None,end.isoformat() if end else None


def supplier_row(db,sid):
    row=db.execute('SELECT id,name,contact,phone FROM suppliers WHERE id=?',(sid,)).fetchone()
    if not row: raise HTTPException(404,'Tedarikçi bulunamadı.')
    return dict(row)


def statement(db,sid,start,end,offset):
    supplier=supplier_row(db,sid);events=[]
    def add(day,kind,rid,debit,credit,note):
        events.append(dict(date=day,kind=kind,reference=f'{"AL" if kind.startswith("purchase") else "ÖD"}-{rid}',
                           debit_cents=debit,credit_cents=credit,note=note))
    for p in db.execute('''SELECT p.*,c.reason,c.cancelled_at FROM purchases p
            LEFT JOIN purchase_cancellations c ON c.purchase_id=p.id WHERE supplier_id=?''',(sid,)):
        add(p['date'],'purchase',p['id'],p['amount_cents'],0,p['note'])
        if p['cancelled_at']:
            add(local_day(p['cancelled_at']),'purchase_cancel',p['id'],0,p['amount_cents'],p['reason'])
    for p in db.execute('''SELECT p.*,c.reason,c.cancelled_at,a.name account FROM supplier_payments p
            JOIN finance_entries e ON e.id=p.finance_entry_id JOIN finance_accounts a ON a.id=e.account_id
            LEFT JOIN finance_cancellations c ON c.entry_id=e.id WHERE p.supplier_id=?''',(sid,)):
        add(p['date'],'payment',p['id'],0,p['amount_cents'],p['account']+' · '+p['note'])
        if p['cancelled_at']:
            add(local_day(p['cancelled_at']),'payment_cancel',p['id'],p['amount_cents'],0,p['reason'])
    rank={'purchase':0,'payment':1,'purchase_cancel':2,'payment_cancel':3}
    events.sort(key=lambda e:(e['date'],rank[e['kind']],int(e['reference'].split('-')[1])))
    opening=sum(e['debit_cents']-e['credit_cents'] for e in events if start and e['date']<start)
    rows=[e for e in events if (not start or e['date']>=start) and (not end or e['date']<=end)]
    running=opening
    for e in rows:
        running+=e['debit_cents']-e['credit_cents'];e['balance_cents']=running
    return dict(supplier=supplier,start_date=start,end_date=end,opening_cents=opening,
                debit_cents=sum(e['debit_cents'] for e in rows),credit_cents=sum(e['credit_cents'] for e in rows),
                closing_cents=running,current_cents=sum(e['debit_cents']-e['credit_cents'] for e in events),
                total=len(rows),offset=offset,rows=rows[offset:offset+50])


def payables(db,reference,status,supplier_id,offset):
    if supplier_id is not None: supplier_row(db,supplier_id)
    credits={r['supplier_id']:r['amount'] for r in db.execute('''SELECT p.supplier_id,SUM(p.amount_cents) amount
        FROM supplier_payments p WHERE p.date<=? AND NOT EXISTS(SELECT 1 FROM finance_cancellations c
        WHERE c.entry_id=p.finance_entry_id) GROUP BY p.supplier_id''',(reference,))}
    rows=[]
    for p in db.execute('''SELECT p.id,p.supplier_id,p.date,p.due_date,p.amount_cents,s.name supplier,s.phone
            FROM purchases p JOIN suppliers s ON s.id=p.supplier_id WHERE p.date<=?
            AND NOT EXISTS(SELECT 1 FROM purchase_cancellations c WHERE c.purchase_id=p.id)
            ORDER BY p.date,p.id''',(reference,)):
        used=min(credits.get(p['supplier_id'],0),p['amount_cents'])
        credits[p['supplier_id']]=credits.get(p['supplier_id'],0)-used
        remaining=p['amount_cents']-used
        if not remaining: continue
        due=p['due_date'];state='undated' if not due else 'overdue' if due<reference else 'today' if due==reference else 'upcoming'
        include=status=='all' or status==state
        if status in ('week','month'):
            limit=(date.fromisoformat(reference)+timedelta(days=7 if status=='week' else 30)).isoformat()
            include=bool(due and reference<=due<=limit)
        if include and (supplier_id is None or supplier_id==p['supplier_id']):
            rows.append({**dict(p),'remaining_cents':remaining,'allocated_cents':used,'state':state,
                         'overdue_days':max(0,(date.fromisoformat(reference)-date.fromisoformat(due)).days) if due else 0})
    rows.sort(key=lambda r:(r['due_date'] is None,r['due_date'] or '',r['id']))
    # Credit belongs to the supplier; never apply one supplier's advance to another.
    advance=sum(v for sid,v in credits.items() if supplier_id is None or sid==supplier_id)
    return dict(reference_date=reference,total=len(rows),remaining_cents=sum(r['remaining_cents'] for r in rows),
                advance_cents=advance,offset=offset,rows=rows[offset:offset+50])


def profit_report(db,start,end,product_id,offset,reference):
    if product_id is not None and not db.execute('SELECT 1 FROM products WHERE id=?',(product_id,)).fetchone():
        raise HTTPException(404,'Ürün bulunamadı.')
    last_day=min(end or reference,reference)
    def inside(day): return (not start or day>=start) and day<=last_day
    products={r['id']:dict(r, sold_quantity=0,sales_cents=0,known_sales_cents=0,estimated_cost_cents=0,
                            unknown_quantity=0,purchased_quantity=0,purchased_cents=0,last_cost_cents=None)
              for r in db.execute('SELECT id,name,sku FROM products') if product_id is None or r['id']==product_id}
    for p in db.execute('''SELECT p.date,p.id purchase_id,i.* FROM purchases p JOIN purchase_items i ON i.purchase_id=p.id
            WHERE NOT EXISTS(SELECT 1 FROM purchase_cancellations c WHERE c.purchase_id=p.id) ORDER BY p.date,p.id'''):
        if p['product_id'] not in products or p['date']>last_day: continue
        row=products[p['product_id']];row['last_cost_cents']=p['unit_cost_cents']
        if inside(p['date']):
            row['purchased_quantity']+=p['quantity'];row['purchased_cents']+=p['quantity']*p['unit_cost_cents']
    total_sales=unitemized=0
    for o in db.execute("SELECT * FROM orders o WHERE o.status!='İptal edildi' AND NOT EXISTS(SELECT 1 FROM order_cancellations c WHERE c.order_id=o.id)"):
        if not inside(o['date']): continue
        lines=list(db.execute('''SELECT i.*,s.unit_cost_cents FROM order_items i
            LEFT JOIN sale_cost_snapshots s ON s.order_item_id=i.id WHERE i.order_id=?''',(o['id'],)))
        if product_id is None:
            total_sales+=o['amount_cents'];unitemized+=o['amount_cents']-sum(l['quantity']*l['price_cents'] for l in lines)
        for line in lines:
            if line['product_id'] not in products: continue
            row=products[line['product_id']];revenue=line['quantity']*line['price_cents']
            if product_id is not None: total_sales+=revenue
            row['sold_quantity']+=line['quantity'];row['sales_cents']+=revenue
            if line['unit_cost_cents'] is None: row['unknown_quantity']+=line['quantity']
            else:
                row['known_sales_cents']+=revenue;row['estimated_cost_cents']+=line['quantity']*line['unit_cost_cents']
    rows=[]
    for row in products.values():
        if not (row['sold_quantity'] or row['purchased_quantity'] or row['last_cost_cents'] is not None): continue
        row['profit_cents']=row['known_sales_cents']-row['estimated_cost_cents']
        row['unknown_sales_cents']=row['sales_cents']-row['known_sales_cents']
        rows.append(row)
    rows.sort(key=lambda r:r['id'])
    known=sum(r['known_sales_cents'] for r in rows);cost=sum(r['estimated_cost_cents'] for r in rows)
    return dict(start_date=start,end_date=end,reference_date=reference,total=len(rows),offset=offset,
                sales_cents=total_sales,known_sales_cents=known,unknown_sales_cents=total_sales-known,
                unitemized_sales_cents=unitemized,estimated_cost_cents=cost,profit_cents=known-cost,
                rows=rows[offset:offset+50])


def register(app,env):
    @app.get('/api/suppliers/{supplier_id}/statement')
    def supplier_statement(supplier_id:int,start_date:date|None=None,end_date:date|None=None,
                           offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        start,end=date_range(start_date,end_date)
        with env.database() as db:
            db.execute('BEGIN');return statement(db,supplier_id,start,end,offset)

    @app.get('/api/payables')
    def list_payables(status:Literal['all','overdue','today','upcoming','undated','week','month']='all',
                      supplier_id:int|None=None,offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        with env.database() as db:
            db.execute('BEGIN');return payables(db,env.today(),status,supplier_id,offset)

    @app.get('/api/profit-report')
    def profit(start_date:date|None=None,end_date:date|None=None,product_id:int|None=None,
               offset:int=Query(default=0,ge=0),user=Depends(env.auth.current_user)):
        start,end=date_range(start_date,end_date)
        with env.database() as db:
            db.execute('BEGIN');return profit_report(db,start,end,product_id,offset,env.today())
