import commercial_returns
from datetime import date
from typing import Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

class DueInput(BaseModel):
    due_date: date | None
    expected_version: int = Field(ge=0, strict=True)

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS order_due_events(order_id INTEGER NOT NULL REFERENCES orders(id),version INTEGER NOT NULL,previous_date TEXT,new_date TEXT,user_id INTEGER NOT NULL REFERENCES users(id),changed_at TEXT NOT NULL,PRIMARY KEY(order_id,version))')

def register(app, env):
    @app.get('/api/receivables')
    def list_receivables(status: Literal['all','overdue','today','upcoming','undated']='all', customer_id: int|None=None, offset:int=Query(default=0,ge=0), user=Depends(env.auth.current_user)):
        reference=env.today()
        with env.database() as db:
            db.execute('BEGIN')
            if customer_id is not None and not db.execute('SELECT 1 FROM customers WHERE id=?',(customer_id,)).fetchone():
                raise HTTPException(404,'Müşteri bulunamadı.')
            credits={r['customer_id']:r['amount'] for r in db.execute('SELECT p.customer_id,SUM(p.amount_cents) amount FROM collections p WHERE p.customer_id IS NOT NULL AND p.date<=? AND NOT EXISTS(SELECT 1 FROM collection_cancellations x WHERE x.collection_id=p.id) GROUP BY p.customer_id',(reference,))}
            rows=[]
            for order in db.execute("SELECT o.id,o.customer_id,o.date,o.due_date,o.due_version,o.amount_cents,c.name customer,c.phone FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.date<=? AND o.status!='İptal edildi' AND NOT EXISTS(SELECT 1 FROM order_cancellations x WHERE x.order_id=o.id) ORDER BY o.date,o.id",(reference,)):
                credit=credits.get(order['customer_id'],0)
                net=order['amount_cents']-commercial_returns.returned_amount(db,'sale',order['id'],reference)
                used=min(credit,net)
                credits[order['customer_id']]=credit-used
                remaining=net-used
                if not remaining: continue
                due=order['due_date']
                state='undated' if not due else 'overdue' if due<reference else 'today' if due==reference else 'upcoming'
                if (customer_id is None or order['customer_id']==customer_id) and (status=='all' or status==state):
                    rows.append({**dict(order),'remaining_cents':remaining,'allocated_cents':used,'state':state,'overdue_days':max(0,(date.fromisoformat(reference)-date.fromisoformat(due)).days) if due else 0})
            rows.sort(key=lambda row:(row['due_date'] is None,row['due_date'] or '9999-12-31',row['id']))
            return {'reference_date':reference,'total':len(rows),'remaining_cents':sum(r['remaining_cents'] for r in rows),'rows':rows[offset:offset+50],'offset':offset}

    @app.post('/api/orders/{order_id}/due-date')
    def set_due_date(order_id:int,item:DueInput,user=Depends(env.auth.writer)):
        with env.database() as db:
            db.execute('BEGIN IMMEDIATE');env.require_active_writer(db,user['id'])
            order=db.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
            if not order: raise HTTPException(404,'Sipariş bulunamadı.')
            if order['status']=='İptal edildi': raise HTTPException(409,'İptal edilmiş siparişin vadesi değiştirilemez.')
            if order['due_version']!=item.expected_version: raise HTTPException(409,'Vade değişti. Güncel listeyi yükleyin.')
            due=item.due_date.isoformat() if item.due_date else None
            if due and due<order['date']: raise HTTPException(422,'Vade sipariş tarihinden önce olamaz.')
            db.execute('INSERT INTO order_due_events VALUES(?,?,?,?,?,?)',(order_id,order['due_version']+1,order['due_date'],due,user['id'],env.datetime.now(env.ZoneInfo('Europe/Istanbul')).isoformat()))
            db.execute('UPDATE orders SET due_date=?,due_version=due_version+1 WHERE id=?',(due,order_id))
            return env.order_dict(db,order_id)
