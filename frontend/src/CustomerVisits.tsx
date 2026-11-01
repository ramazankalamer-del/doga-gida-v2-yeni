import {useEffect,useRef,useState} from 'react';
export type Visit={customer_id:number;visit_date:string;visited:number;version:number;updated_username:string;updated_at:string;note:string;reason:string};
export type VisitRequest=<T>(path:string,data?:object)=>Promise<T>;
export function useCustomerVisits(date:string,enabled:boolean,request:VisitRequest){
 const [visits,setVisits]=useState<Visit[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const generation=useRef(0);
 useEffect(()=>{const id=++generation.current;setVisits([]);setError('');setBusy(false);if(!enabled){setLoading(false);return;}setLoading(true);
 request<Visit[]>(`customer-visits?visit_date=${date}`).then(rows=>{if(id===generation.current)setVisits(rows);}).catch(e=>{if(id===generation.current)setError((e as Error).message);}).finally(()=>{if(id===generation.current)setLoading(false);});
 return()=>{generation.current++;};},[date,enabled,request,revision]);
 async function save(customerId:number,visited:boolean,note:string,reason:string){const id=generation.current;setBusy(true);setError('');try{
 const row=await request<Visit>(`customers/${customerId}/visit`,{visit_date:date,visited,note,reason,expected_version:visits.find(v=>v.customer_id===customerId)?.version??0});
 if(id===generation.current)setVisits(old=>[...old.filter(v=>v.customer_id!==customerId),row]);return true;
 }catch(e){if(id===generation.current)setError((e as Error).message);return false;}finally{if(id===generation.current)setBusy(false);}}
 return {visits,loading,error,busy,save,reload:()=>setRevision(v=>v+1)};
}
export function VisitControls({visit,disabled,onSave}:{visit?:Visit;disabled:boolean;onSave:(visited:boolean,note:string,reason:string)=>Promise<boolean>}){
 const [visited,setVisited]=useState(!!visit?.visited);
 return <form className="visit-controls" onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);await onSave(visited,String(data.get('note')??''),visited?'':String(data.get('reason')??''));}}>
 <strong>Kayıtlı durum: {visit?.visited?'Ziyaret edildi':'Ziyaret edilmedi'}</strong>{visit&&<small>Son kayıt: {visit.updated_username} · {new Date(visit.updated_at).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'})}</small>}
 <fieldset disabled={disabled}><legend>Ziyaret bilgileri</legend><label>Müşteri ziyaret durumu<select value={visited?'visited':'pending'} onChange={e=>{setVisited(e.target.value==='visited');}}><option value="visited">Ziyaret edildi</option><option value="pending">Ziyaret edilmedi</option></select></label>
 <label>Ziyaret notu (isteğe bağlı)<textarea name="note" maxLength={1000} rows={3} defaultValue={visit?.note??''} placeholder="Görüşme veya sonraki ziyaret için not…"/></label>
 {!visited&&<label>Ziyaret edilememe nedeni (isteğe bağlı)<textarea name="reason" maxLength={300} rows={2} defaultValue={visit?.reason??''} placeholder="Örn. müşteri kapalıydı, yetkili yerinde değildi…"/></label>}
 <p className="order-help">Durum ve açıklamalar birlikte kaydedilir. Ziyaret edildi seçilirse edilememe nedeni kaldırılır.</p><button className="secondary" type="submit">Ziyaret kaydını kaydet</button></fieldset>
 </form>;
}
