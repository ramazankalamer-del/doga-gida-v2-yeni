import {useState,type FormEvent} from 'react';
import {routeDayNames} from './CustomerActions';
import {useCustomerDialog} from './useCustomerDialog';
import type {MapCustomer as Customer} from './customerMapData';

type Request=<T>(path:string,data?:object)=>Promise<T>;
export default function CustomerRouteDays({customer,request,onClose,onSaved}:{customer:Customer;request:Request;onClose:()=>void;onSaved:(updated:Customer)=>Promise<void>}){
 const [days,setDays]=useState(customer.route_days??[]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const dialog=useCustomerDialog(onClose,busy);
 async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{const updated=await request<Customer>(`customers/${customer.id}/route-days`,{route_days:days,expected_version:customer.version});await onSaved(updated);onClose();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="modal-backdrop customer-dialog-backdrop"><section ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="route-title"><div className="panel-head"><div><h2 id="route-title">Rota günleri</h2><p>{customer.name}</p></div><button type="button" className="secondary" disabled={busy} onClick={onClose}>Kapat</button></div><form onSubmit={submit}><p className="order-help">Haftalık ziyaret için birden fazla gün seçebilirsiniz. Günleri kaldırmak müşteriyi veya siparişlerini silmez.</p><fieldset className="route-day-options" disabled={busy}><legend>Haftalık ziyaret günleri</legend>{routeDayNames.map((label,index)=><label key={label}><input type="checkbox" checked={days.includes(index+1)} onChange={e=>setDays(old=>e.target.checked?[...old,index+1]:old.filter(day=>day!==index+1))}/>{label}</label>)}</fieldset><button type="button" className="secondary" disabled={busy} onClick={()=>setDays([])}>Günleri temizle</button>{error&&<div className="error" role="alert">{error}</div>}<div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={onClose}>Vazgeç</button><button className="primary" disabled={busy}>{busy?'Kaydediliyor…':'Rota günlerini kaydet'}</button></div></form></section></div>;
}
