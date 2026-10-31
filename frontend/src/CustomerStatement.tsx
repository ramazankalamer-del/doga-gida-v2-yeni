import {useEffect,useRef,useState,type FormEvent} from 'react';
import {useCustomerDialog} from './useCustomerDialog';

type Customer={id:number;name:string};
type Movement={date:string;kind:'order'|'collection'|'order_cancel'|'collection_cancel';reference:string;record_id:number;note:string;status:string;debit_cents:number;credit_cents:number;balance_cents:number};
type Statement={customer:Customer;start_date:string|null;end_date:string|null;opening_balance_cents:number;debit_cents:number;credit_cents:number;closing_balance_cents:number;current_balance_cents:number;movements:Movement[]};
type Request=<T>(path:string,data?:object)=>Promise<T>;
const money=(cents:number)=>new Intl.NumberFormat('tr-TR',{style:'currency',currency:'TRY'}).format(cents/100);
const day=(value:string)=>new Date(value+'T12:00:00').toLocaleDateString('tr-TR');
const kinds={order:'Sipariş',collection:'Tahsilat',order_cancel:'Sipariş iptali',collection_cancel:'Tahsilat iptali'};
const balanceLabel=(value:number)=>value>0?'Müşterinin borcu':value<0?'Müşterinin alacağı':'Hesap kapalı';

export default function CustomerStatement({customer,request,onClose}:{customer:Customer;request:Request;onClose:()=>void}){
 const [data,setData]=useState<Statement|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const filters=useRef<HTMLFormElement>(null);
 const sequence=useRef(0),dialog=useCustomerDialog(onClose);
 async function load(start:string,end:string){
  if(start&&end&&start>end){setError('Başlangıç tarihi bitiş tarihinden sonra olamaz.');return;}
  const current=++sequence.current;setLoading(true);setError('');
  const query=new URLSearchParams();if(start)query.set('start_date',start);if(end)query.set('end_date',end);
  try{const result=await request<Statement>(`customers/${customer.id}/statement?${query}`);if(current===sequence.current)setData(result);}
  catch(e){if(current===sequence.current)setError((e as Error).message);}
  finally{if(current===sequence.current)setLoading(false);}
 }
 useEffect(()=>{void load('','');return()=>{sequence.current++;};},[customer.id]);
 function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const values=new FormData(e.currentTarget);void load(String(values.get('start_date')??''),String(values.get('end_date')??''));}
 return <div className="modal-backdrop customer-dialog-backdrop"><section ref={dialog} className="modal customer-statement-modal" role="dialog" aria-modal="true" aria-labelledby="statement-title">
  <div className="panel-head"><div><span className="eyebrow">MÜŞTERİ HESABI</span><h2 id="statement-title">Hesap ekstresi</h2><p>{customer.name}</p></div><button type="button" className="secondary" onClick={onClose}>Ekstreyi kapat</button></div>
  <div className="statement-content"><form ref={filters} className="statement-filter" onSubmit={submit}><label>Başlangıç tarihi<input name="start_date" type="date"/></label><label>Bitiş tarihi<input name="end_date" type="date"/></label><button className="primary" disabled={loading}>Göster</button><button type="button" className="secondary" disabled={loading} onClick={()=>{filters.current?.reset();void load('','');}}>Tüm hareketler</button></form>
   {error&&<div className="error" role="alert">{error}</div>}
   {loading?<p role="status" className="loading">Hesap ekstresi yükleniyor…</p>:data&&<>
    <p className="statement-period">Gösterilen dönem: {data.start_date?day(data.start_date):'İlk kayıttan'} — {data.end_date?day(data.end_date):'Son kayda kadar'}</p>
    <div className="statement-summary">{[{label:'Devir bakiyesi',value:data.opening_balance_cents},{label:'Dönem borç',value:data.debit_cents},{label:'Dönem alacak',value:data.credit_cents},{label:'Dönem sonu bakiye',value:data.closing_balance_cents}].map(item=><div key={item.label}><span>{item.label}</span><strong>{money(item.value)}</strong></div>)}</div>
    <p className="statement-current">Güncel hesap bakiyesi: <strong>{money(data.current_balance_cents)}</strong> · {balanceLabel(data.current_balance_cents)}</p>
    <p className="order-help">Borç müşterinin bize borcunu artırır; alacak azaltır. Eksi bakiye müşterinin alacağıdır. İptaller ayrı ters hareket olarak gösterilir.</p>
    <div className="table-wrap"><table><thead><tr><th>TARİH / KAYIT</th><th>İŞLEM / AÇIKLAMA</th><th>BORÇ</th><th>ALACAK</th><th>BAKİYE</th></tr></thead><tbody>{data.movements.map(row=><tr key={`${row.kind}-${row.record_id}`}><td>{day(row.date)}<small>{row.reference}</small></td><td><strong>{kinds[row.kind]}</strong><small>{row.note}</small></td><td className="amount">{row.debit_cents?money(row.debit_cents):'—'}</td><td className="amount">{row.credit_cents?money(row.credit_cents):'—'}</td><td className="amount">{money(row.balance_cents)}<small>{balanceLabel(row.balance_cents)}</small></td></tr>)}</tbody></table>{!data.movements.length&&<p className="empty">Bu dönemde hesap hareketi yok.</p>}</div>
    <p className="order-help">Aynı gün hareketleri sipariş, tahsilat ve iptal sırasıyla; kendi içinde kayıt numarasına göre gösterilir. Müşteriye bağlı olmayan eski tahsilatlar ekstreye dahil değildir.</p>
   </>}
  </div>
 </section></div>;
}
