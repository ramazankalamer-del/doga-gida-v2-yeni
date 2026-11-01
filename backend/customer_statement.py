import commercial_returns
"""Read-only customer ledger derived from recorded orders and collections."""
from datetime import datetime
from zoneinfo import ZoneInfo


def local_day(timestamp):
    value=datetime.fromisoformat(timestamp)
    if value.tzinfo is None:
        value=value.replace(tzinfo=ZoneInfo('Europe/Istanbul'))
    return value.astimezone(ZoneInfo('Europe/Istanbul')).date().isoformat()


def build_statement(db,customer,start_date=None,end_date=None):
    events=[]
    def add(day,kind,record_id,debit,credit,note,status=''):
        prefix='DG' if kind.startswith('order') else 'TH'
        events.append(dict(date=day,kind=kind,record_id=record_id,reference=f'{prefix}-{record_id:04d}',debit_cents=debit,credit_cents=credit,note=note,status=status))
    for row in db.execute('''SELECT o.*,x.reason,x.cancelled_at FROM orders o LEFT JOIN order_cancellations x ON x.order_id=o.id WHERE o.customer_id=?''',(customer['id'],)):
        unknown_cancel=row['status']=='İptal edildi' and not row['cancelled_at']
        add(row['date'],'order',row['id'],0 if unknown_cancel else row['amount_cents'],0,
            'İptal tarihi olmayan eski kayıt; bakiyeye etkisi yok.' if unknown_cancel else 'Sipariş kaydı',row['status'])
        if row['cancelled_at']:
            add(local_day(row['cancelled_at']),'order_cancel',row['id'],0,row['amount_cents'],row['reason'],'İptal edildi')
    for row in db.execute('''SELECT p.*,x.reason,x.cancelled_at FROM collections p LEFT JOIN collection_cancellations x ON x.collection_id=p.id WHERE p.customer_id=?''',(customer['id'],)):
        method={'cash':'Nakit','transfer':'Havale / EFT','card':'Kart'}.get(row['method'],'Yöntem belirtilmemiş')
        add(row['date'],'collection',row['id'],0,row['amount_cents'],method+(' · '+row['note'] if row['note'] else ''),'İptal edildi' if row['cancelled_at'] else 'Geçerli')
        if row['cancelled_at']:
            add(local_day(row['cancelled_at']),'collection_cancel',row['id'],row['amount_cents'],0,row['reason'],'İptal edildi')
    events.extend(commercial_returns.ledger_events(db,'sale',customer['id']))
    rank={'order':0,'collection':1,'sales_return':2,'sales_return_cancel':3,'order_cancel':4,'collection_cancel':5}
    events.sort(key=lambda row:(row['date'],rank[row['kind']],row['record_id']))
    start=start_date.isoformat() if start_date else None
    end=end_date.isoformat() if end_date else None
    opening=sum(row['debit_cents']-row['credit_cents'] for row in events if start and row['date']<start)
    visible=[row for row in events if (not start or row['date']>=start) and (not end or row['date']<=end)]
    running=opening
    for row in visible:
        running+=row['debit_cents']-row['credit_cents']
        row['balance_cents']=running
    return dict(customer=dict(customer),start_date=start,end_date=end,opening_balance_cents=opening,
                debit_cents=sum(row['debit_cents'] for row in visible),credit_cents=sum(row['credit_cents'] for row in visible),
                closing_balance_cents=running,current_balance_cents=sum(row['debit_cents']-row['credit_cents'] for row in events),movements=visible)
